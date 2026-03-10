"""Interactive REPL mode — Claude Code-style terminal UX."""

from __future__ import annotations

import asyncio
import os
import sys
from importlib.resources import files
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    CLINotFoundError,
)
from claude_agent_sdk.types import (
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    StreamEvent,
    TaskStartedMessage,
    TaskProgressMessage,
    TaskNotificationMessage,
    SystemMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
    SandboxSettings,
)

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PTStyle

from . import display
from .providers import ProviderRegistry, ProviderStatus
from .setup import run_setup, _show_status

_INTERACTIVE_PROMPT = files("inductiveclaw.prompts").joinpath("interactive.md").read_text()

console = Console()

SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/config": "Re-run provider setup",
    "/status": "Show provider status",
    "/cost": "Show session cost",
    "/clear": "Clear conversation (start new session)",
    "/quit": "Exit iclaw",
}


# --- Sandbox enforcement ---

_FILE_WRITE_TOOLS = {"Write", "Edit"}
_FILE_READ_TOOLS = {"Read"}
_FILE_ALL_TOOLS = _FILE_WRITE_TOOLS | _FILE_READ_TOOLS | {"Glob", "Grep"}


def _make_sandbox_guard(project_dir: str):
    """Create a can_use_tool callback that restricts all file access to project_dir."""
    resolved = Path(project_dir).resolve()
    resolved_str = str(resolved)

    def _path_in_sandbox(p: str) -> bool:
        try:
            target = Path(p).resolve()
            target_str = str(target)
            return target_str == resolved_str or target_str.startswith(resolved_str + os.sep)
        except (ValueError, OSError):
            return False

    async def guard(
        tool_name: str,
        tool_input: dict,
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:

        if tool_name in _FILE_WRITE_TOOLS | _FILE_READ_TOOLS:
            file_path = tool_input.get("file_path", "")
            if file_path and not _path_in_sandbox(file_path):
                return PermissionResultDeny(
                    behavior="deny",
                    message=f"Sandbox: {tool_name} blocked — {file_path} "
                            f"is outside {project_dir}",
                )

        if tool_name in ("Glob", "Grep"):
            search_path = tool_input.get("path", "")
            if search_path and not _path_in_sandbox(search_path):
                return PermissionResultDeny(
                    behavior="deny",
                    message=f"Sandbox: {tool_name} blocked — {search_path} "
                            f"is outside {project_dir}",
                )

        if tool_name == "Bash":
            cmd = tool_input.get("command", "").strip()
            words = cmd.split()
            if not words:
                return PermissionResultAllow(behavior="allow")

            if words[0] == "sudo" or "sudo " in cmd:
                return PermissionResultDeny(
                    behavior="deny",
                    message="Sandbox: sudo is not allowed",
                )

            for word in words[1:]:
                if word.startswith("/") and not _path_in_sandbox(word):
                    return PermissionResultDeny(
                        behavior="deny",
                        message=f"Sandbox: Bash blocked — references path {word} "
                                f"outside {project_dir}",
                    )

        return PermissionResultAllow(behavior="allow")

    return guard


def _clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


# --- Streaming text accumulator ---

class _StreamAccumulator:
    """Accumulates streaming text deltas and renders them live."""

    def __init__(self):
        self._buffer = ""
        self._line_count = 0

    def feed(self, delta: str) -> None:
        self._buffer += delta
        # Print each character as it arrives for live feel
        sys.stdout.write(delta)
        sys.stdout.flush()

    def finish(self) -> str:
        """Finalize streaming output, return full text."""
        if self._buffer:
            sys.stdout.write("\n")
            sys.stdout.flush()
        text = self._buffer
        self._buffer = ""
        return text


# --- Styled output helpers ---

def _show_tool_use(name: str, input_data: dict) -> None:
    summary = _summarize_tool_input(name, input_data)
    if summary:
        console.print(Text(f"  ⏺ {name}({summary})", style="bold blue"))
    else:
        console.print(Text(f"  ⏺ {name}", style="bold blue"))


def _summarize_tool_input(name: str, data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    if name == "Bash":
        return data.get("command", data.get("description", ""))[:80]
    if name in ("Read", "Write", "Edit"):
        return data.get("file_path", "")
    if name == "Glob":
        return data.get("pattern", "")
    if name == "Grep":
        return data.get("pattern", "")[:60]
    for v in data.values():
        if isinstance(v, str) and v.strip():
            return v[:60]
    return ""


def _show_thinking(text: str) -> None:
    lines = text.strip().split("\n")
    preview = lines[0][:120]
    if len(lines) > 1 or len(lines[0]) > 120:
        preview += "..."
    console.print(Text(f"  ✻ {preview}", style="dim italic"))


def _show_tool_result(block: ToolResultBlock) -> None:
    """Show tool result — only errors get detail, success is silent."""
    if not block.is_error:
        return
    content = block.content
    if content is None:
        return
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        text = "\n".join(parts).strip()
    else:
        return
    if not text:
        return
    lines = text.split("\n")
    if len(lines) > 3:
        lines = lines[:3] + [f"  ... ({len(lines) - 3} more lines)"]
    for line in lines:
        console.print(Text(f"  ⎿  {line}", style="red"))


def _show_response(text: str) -> None:
    console.print()
    console.print(Markdown(text))


def _show_separator() -> None:
    width = console.width
    side = (width - 5) // 2
    line = "─" * side + " ▪▪▪ " + "─" * (width - side - 5)
    console.print()
    console.print(Text(line, style="dim"))


def _show_task_started(msg: TaskStartedMessage) -> None:
    desc = msg.description[:80] if msg.description else "sub-agent"
    task_type = f" ({msg.task_type})" if msg.task_type else ""
    console.print(Text(f"  ◉ Task started: {desc}{task_type}", style="bold magenta"))


def _show_task_progress(msg: TaskProgressMessage) -> None:
    desc = msg.description[:60] if msg.description else ""
    tool = f" → {msg.last_tool_name}" if msg.last_tool_name else ""
    tokens = msg.usage.get("total_tokens", 0) if msg.usage else 0
    tools_used = msg.usage.get("tool_uses", 0) if msg.usage else 0
    console.print(Text(
        f"  ◌ {desc}{tool} [{tools_used} tools, {tokens:,} tokens]",
        style="dim magenta",
    ))


def _show_task_notification(msg: TaskNotificationMessage) -> None:
    status_style = {
        "completed": "green",
        "failed": "red",
        "stopped": "yellow",
    }.get(msg.status, "dim")
    icon = {"completed": "✓", "failed": "✗", "stopped": "⏹"}.get(msg.status, "●")
    summary = msg.summary[:100] if msg.summary else msg.status
    console.print(Text(f"  {icon} Task {msg.status}: {summary}", style=status_style))


def _show_assistant_error(error: str) -> None:
    error_messages = {
        "authentication_failed": "Authentication failed — check your API key",
        "billing_error": "Billing error — check your account",
        "rate_limit": "Rate limited — waiting...",
        "invalid_request": "Invalid request",
        "server_error": "Server error — retrying...",
        "unknown": "Unknown error",
    }
    msg = error_messages.get(error, f"Error: {error}")
    console.print(Text(f"  ⚠ {msg}", style="bold red"))


def _show_result_details(msg: ResultMessage) -> None:
    """Show end-of-turn details from ResultMessage."""
    parts = []
    if msg.total_cost_usd:
        parts.append(f"${msg.total_cost_usd:.4f}")
    if msg.num_turns:
        parts.append(f"{msg.num_turns} turns")
    if msg.duration_api_ms:
        secs = msg.duration_api_ms / 1000
        parts.append(f"{secs:.1f}s API")
    if msg.usage:
        input_tokens = msg.usage.get("input_tokens", 0)
        output_tokens = msg.usage.get("output_tokens", 0)
        if input_tokens or output_tokens:
            parts.append(f"{input_tokens + output_tokens:,} tokens")
    if msg.stop_reason and msg.stop_reason != "end_turn":
        parts.append(f"stopped: {msg.stop_reason}")
    if msg.is_error:
        parts.append("⚠ error")
    if parts:
        console.print(Text(f"  [{' · '.join(parts)}]", style="dim"))


def _handle_stream_event(event: StreamEvent, accum: _StreamAccumulator) -> None:
    """Process a raw Anthropic stream event for live output."""
    ev = event.event
    ev_type = ev.get("type", "")

    if ev_type == "content_block_delta":
        delta = ev.get("delta", {})
        delta_type = delta.get("type", "")
        if delta_type == "text_delta":
            accum.feed(delta.get("text", ""))
        elif delta_type == "thinking_delta":
            # Don't stream thinking — we show a preview from the full block
            pass
        elif delta_type == "input_json_delta":
            # Tool input streaming — skip, we show the full tool_use block
            pass


def _print_help() -> None:
    from rich.table import Table
    table = Table(title="Commands", show_header=True, border_style="dim")
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    for cmd, desc in SLASH_COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)


# --- Input with prompt_toolkit ---

def _bottom_toolbar(registry: ProviderRegistry, cost: float, turns: int) -> str:
    provider = registry.active
    name = provider.display_name if provider else "none"
    cost_str = f"${cost:.4f}" if cost > 0 else "$0"
    return f"  ⏵⏵ sandbox on  |  {name}  |  {cost_str} · {turns} turns  |  /help for commands"


_PT_STYLE = PTStyle.from_dict({
    "bottom-toolbar": "noinherit dim",
})


def _build_session(
    registry: ProviderRegistry,
    cost_ref: list[float],
    turns_ref: list[int],
) -> PromptSession:
    completer = WordCompleter(list(SLASH_COMMANDS.keys()), sentence=True)
    return PromptSession(
        history=InMemoryHistory(),
        completer=completer,
        complete_while_typing=False,
        bottom_toolbar=lambda: _bottom_toolbar(registry, cost_ref[0], turns_ref[0]),
        style=_PT_STYLE,
    )


def _build_options(
    registry: ProviderRegistry,
    cwd: str,
) -> ClaudeAgentOptions:
    provider = registry.active
    assert provider is not None

    sandbox: SandboxSettings = {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "allowUnsandboxedCommands": False,
    }

    opts = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        cwd=cwd,
        add_dirs=[cwd],
        system_prompt=_INTERACTIVE_PROMPT,
        env=provider.get_sdk_env(),
        sandbox=sandbox,
        can_use_tool=_make_sandbox_guard(cwd),
        include_partial_messages=True,
    )
    model = provider.get_model()
    if model:
        opts.model = model
    return opts


async def run_interactive(
    registry: ProviderRegistry,
    cwd: str = ".",
    model_override: str | None = None,
) -> None:
    """Main interactive REPL loop with Claude Code-style UX."""
    cwd = str(Path(cwd).resolve())
    # Mutable refs so the toolbar closure can read live values
    cost_ref = [0.0]
    turns_ref = [0]

    options = _build_options(registry, cwd)
    if model_override:
        options.model = model_override

    session = _build_session(registry, cost_ref, turns_ref)

    try:
        _clear_screen()
        console.print(Text("  Starting iclaw...\n", style="dim"))

        async with ClaudeSDKClient(options=options) as client:
            _clear_screen()
            display.show_banner_interactive(registry)

            while True:
                try:
                    user_input = await session.prompt_async(
                        HTML("<b>❯</b> "),
                    )
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    break

                if not user_input.strip():
                    continue

                # Handle slash commands
                cmd = user_input.strip().lower()
                if cmd in ("/quit", "/exit"):
                    break
                if cmd == "/help":
                    _print_help()
                    continue
                if cmd == "/config":
                    run_setup(registry)
                    options = _build_options(registry, cwd)
                    if model_override:
                        options.model = model_override
                    console.print("Provider config updated. Restarting session...\n")
                    break
                if cmd == "/status":
                    _show_status(registry)
                    continue
                if cmd == "/cost":
                    _show_cost(cost_ref[0], turns_ref[0])
                    continue
                if cmd == "/clear":
                    _clear_screen()
                    display.show_banner_interactive(registry)
                    continue

                # Send to agent
                try:
                    await client.query(user_input)
                    shown_thinking = False
                    accum = _StreamAccumulator()
                    streaming_text = False

                    async for message in client.receive_response():
                        # --- Token-by-token streaming ---
                        if isinstance(message, StreamEvent):
                            if not shown_thinking:
                                console.print(Text("  ✻ thinking...", style="dim cyan"))
                                shown_thinking = True
                            if not streaming_text:
                                console.print()
                                sys.stdout.write("  ")
                                streaming_text = True
                            _handle_stream_event(message, accum)
                            continue

                        # If we were streaming text and now got a non-stream message,
                        # finalize the streamed output
                        if streaming_text:
                            accum.finish()
                            streaming_text = False

                        # --- Full message blocks ---
                        if isinstance(message, AssistantMessage):
                            # Check for error state on the message
                            if message.error:
                                _show_assistant_error(message.error)

                            for block in message.content:
                                if isinstance(block, ThinkingBlock) and block.thinking.strip():
                                    _show_thinking(block.thinking)
                                    shown_thinking = True
                                elif isinstance(block, TextBlock) and block.text.strip():
                                    if not shown_thinking:
                                        console.print(Text("  ✻ thinking...", style="dim cyan"))
                                        shown_thinking = True
                                    _show_response(block.text)
                                elif isinstance(block, ToolUseBlock):
                                    if not shown_thinking:
                                        console.print(Text("  ✻ thinking...", style="dim cyan"))
                                        shown_thinking = True
                                    _show_tool_use(
                                        block.name,
                                        block.input if isinstance(block.input, dict) else {},
                                    )
                                elif isinstance(block, ToolResultBlock):
                                    _show_tool_result(block)

                        # --- Task lifecycle (sub-agents) ---
                        elif isinstance(message, TaskStartedMessage):
                            _show_task_started(message)
                        elif isinstance(message, TaskProgressMessage):
                            _show_task_progress(message)
                        elif isinstance(message, TaskNotificationMessage):
                            _show_task_notification(message)
                        elif isinstance(message, SystemMessage):
                            # Generic system message — log if interesting
                            pass

                        # --- Result (end of turn) ---
                        elif isinstance(message, ResultMessage):
                            if message.total_cost_usd:
                                cost_ref[0] += message.total_cost_usd
                            if message.num_turns:
                                turns_ref[0] += message.num_turns
                            _show_result_details(message)

                    # Finalize any remaining streamed text
                    if streaming_text:
                        accum.finish()

                    _show_separator()

                except (KeyboardInterrupt, asyncio.CancelledError):
                    console.print(Text("\n  ⏹ interrupted", style="bold yellow"))
                    _show_separator()
                except CLINotFoundError:
                    console.print(
                        "[bold red]Error:[/] Claude Code CLI not found. "
                        "Install: npm install -g @anthropic-ai/claude-code"
                    )
                    sys.exit(1)
                except Exception as e:
                    err_str = str(e).lower()
                    if "rate" in err_str and "limit" in err_str:
                        new_provider = registry.handle_rate_limit()
                        if new_provider and new_provider.status == ProviderStatus.CONNECTED:
                            console.print(
                                f"\n[yellow]Rate limited. Switching to "
                                f"{new_provider.display_name}...[/]"
                            )
                            options = _build_options(registry, cwd)
                            if model_override:
                                options.model = model_override
                            break
                        else:
                            console.print(
                                "\n[bold red]Rate limited and no available providers. "
                                "Try again later.[/]"
                            )
                            return
                    else:
                        console.print(f"\n[red]Error: {e}[/]\n")

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    display.show_interactive_summary(cost_ref[0], turns_ref[0])


def _show_cost(total_cost: float, total_turns: int) -> None:
    console.print(f"  [dim]Session cost: ${total_cost:.4f} | Turns: {total_turns}[/]")

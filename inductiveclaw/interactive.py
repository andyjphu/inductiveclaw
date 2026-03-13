"""Interactive REPL mode — Claude Code-style terminal UX."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PTStyle

from . import display
from .backends import (
    AgentMessage,
    AgentResult,
    AgentStreamEvent,
    AgentTaskNotification,
    AgentTaskProgress,
    AgentTaskStarted,
    AgentTextBlock,
    AgentThinkingBlock,
    AgentToolResultBlock,
    AgentToolUseBlock,
    BackendNotFoundError,
    BackendProcessError,
    BackendRateLimitError,
    InteractiveBackend,
    create_interactive_backend,
)
from .providers import ProviderRegistry, ProviderStatus
from .sessions import SessionRecord, SessionStore
from .setup import run_setup, _show_status

_INTERACTIVE_PROMPT = files("inductiveclaw.prompts").joinpath("interactive.md").read_text()

console = Console()

SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/config": "Re-run provider setup",
    "/status": "Show provider status",
    "/cost": "Show session cost",
    "/sessions": "List saved sessions",
    "/resume": "Resume a saved session (/resume <id or #>)",
    "/clear": "Clear conversation (start new session)",
    "/quit": "Exit iclaw",
}


def _clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


class _ThinkingSpinner:
    """Animated 'thinking...' indicator that runs as a background task."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _INTERVAL = 0.08

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._visible = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._spin())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        if self._visible:
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
            self._visible = False

    async def _spin(self) -> None:
        try:
            i = 0
            while True:
                frame = self._FRAMES[i % len(self._FRAMES)]
                sys.stdout.write(f"\r  \033[36m\033[2m{frame} thinking...\033[0m")
                sys.stdout.flush()
                self._visible = True
                i += 1
                await asyncio.sleep(self._INTERVAL)
        except asyncio.CancelledError:
            pass


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


def _show_tool_result(block: AgentToolResultBlock) -> None:
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


def _show_task_started(msg: AgentTaskStarted) -> None:
    desc = msg.description[:80] if msg.description else "sub-agent"
    task_type = f" ({msg.task_type})" if msg.task_type else ""
    console.print(Text(f"  ◉ Task started: {desc}{task_type}", style="bold magenta"))


def _show_task_progress(msg: AgentTaskProgress) -> None:
    desc = msg.description[:60] if msg.description else ""
    tool = f" → {msg.last_tool_name}" if msg.last_tool_name else ""
    tokens = msg.usage.get("total_tokens", 0) if msg.usage else 0
    tools_used = msg.usage.get("tool_uses", 0) if msg.usage else 0
    console.print(Text(
        f"  ◌ {desc}{tool} [{tools_used} tools, {tokens:,} tokens]",
        style="dim magenta",
    ))


def _show_task_notification(msg: AgentTaskNotification) -> None:
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


def _show_result_details(msg: AgentResult) -> None:
    """Show end-of-turn details."""
    parts = []
    if msg.cost_usd:
        parts.append(f"${msg.cost_usd:.4f}")
    if msg.num_turns:
        parts.append(f"{msg.num_turns} turns")
    if msg.duration_ms:
        secs = msg.duration_ms / 1000
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


def _print_help() -> None:
    from rich.table import Table
    table = Table(title="Commands", show_header=True, border_style="dim")
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    for cmd, desc in SLASH_COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)


# --- Input with prompt_toolkit ---

def _bottom_toolbar(registry: ProviderRegistry, cost: float, turns: int, sandbox_path: str = "") -> str:
    provider = registry.active
    name = provider.display_name if provider else "none"
    cost_str = f"${cost:.4f}" if cost > 0 else "$0"
    short_path = sandbox_path.replace(str(Path.home()), "~") if sandbox_path else "on"
    return f"  ⏵⏵ sandbox: {short_path}  |  {name}  |  {cost_str} · {turns} turns  |  /help for commands"


_PT_STYLE = PTStyle.from_dict({
    "bottom-toolbar": "noinherit #666666",
})


def _build_session(
    registry: ProviderRegistry,
    cost_ref: list[float],
    turns_ref: list[int],
    sandbox_path: str = "",
) -> PromptSession:
    completer = WordCompleter(list(SLASH_COMMANDS.keys()), sentence=True)
    return PromptSession(
        history=InMemoryHistory(),
        completer=completer,
        complete_while_typing=False,
        bottom_toolbar=lambda: _bottom_toolbar(registry, cost_ref[0], turns_ref[0], sandbox_path),
        style=_PT_STYLE,
    )


# --- Main REPL ---

async def run_interactive(
    registry: ProviderRegistry,
    cwd: str = ".",
    model_override: str | None = None,
    auto_continue: bool = True,
    resume_session_id: str | None = None,
) -> None:
    """Main interactive REPL loop with Claude Code-style UX."""
    cwd = str(Path(cwd).resolve())
    Path(cwd).mkdir(parents=True, exist_ok=True)
    cost_ref = [0.0]
    turns_ref = [0]
    session_id: str | None = None

    store = SessionStore()
    active_record: SessionRecord | None = None
    restore_msgs: list | None = None

    # Resume from a previous session if requested
    if resume_session_id:
        active_record = store.load(resume_session_id)
        if active_record:
            cost_ref[0] = active_record.total_cost_usd
            turns_ref[0] = active_record.total_turns
            if active_record.backend_type == "claude":
                session_id = active_record.session_id
            else:
                restore_msgs = active_record.messages

    # Clean up old sessions on startup
    store.cleanup()

    session = _build_session(registry, cost_ref, turns_ref, cwd)

    _clear_screen()
    console.print(Text("  Starting iclaw...\n", style="dim"))

    try:
        first_connect = True
        while True:
            backend = create_interactive_backend(
                provider=registry.active,
                system_prompt=_INTERACTIVE_PROMPT,
                cwd=cwd,
                model=model_override or registry.active.get_model(),
                resume=session_id,
            )

            try:
                async with backend:
                    if first_connect:
                        _clear_screen()
                        display.show_banner_interactive(registry, cwd)
                        first_connect = False

                    # Restore message history for non-Claude backends
                    if restore_msgs is not None:
                        backend.restore_messages(restore_msgs)
                        if active_record:
                            backend._session_id = active_record.session_id
                        console.print(Text(
                            f"  ↻ Resumed session: {active_record.title if active_record else ''}",
                            style="green",
                        ))
                        restore_msgs = None  # Only restore once

                    while True:
                        try:
                            user_input = await session.prompt_async(
                                HTML("<b>❯</b> "),
                            )
                        except (EOFError, KeyboardInterrupt):
                            console.print()
                            display.show_interactive_summary(cost_ref[0], turns_ref[0])
                            return

                        if not user_input.strip():
                            continue

                        cmd = user_input.strip().lower()
                        if cmd in ("/quit", "/exit"):
                            display.show_interactive_summary(cost_ref[0], turns_ref[0])
                            return
                        if cmd == "/help":
                            _print_help()
                            continue
                        if cmd == "/config":
                            run_setup(registry)
                            if model_override is None:
                                pass  # new backend picks up new provider's model
                            console.print("Provider config updated. Reconnecting...\n")
                            break
                        if cmd == "/status":
                            _show_status(registry)
                            continue
                        if cmd == "/cost":
                            _show_cost(cost_ref[0], turns_ref[0])
                            continue
                        if cmd == "/sessions clean":
                            removed = store.cleanup(retention_days=7)
                            console.print(f"  [dim]Removed {removed} old session(s).[/]")
                            continue
                        if cmd == "/sessions":
                            _show_sessions(store)
                            continue
                        if cmd.startswith("/resume"):
                            parts = cmd.split(maxsplit=1)
                            if len(parts) < 2:
                                console.print("  [dim]Usage: /resume <session_id or #>[/]")
                                continue
                            target = parts[1].strip()
                            record = store.load(target)
                            if not record:
                                sessions = store.list_sessions()
                                try:
                                    idx = int(target) - 1
                                    if 0 <= idx < len(sessions):
                                        record = store.load(sessions[idx]["session_id"])
                                except ValueError:
                                    pass
                            if record:
                                active_record = record
                                cost_ref[0] = record.total_cost_usd
                                turns_ref[0] = record.total_turns
                                if record.backend_type == "claude":
                                    session_id = record.session_id
                                    restore_msgs = None
                                else:
                                    session_id = None
                                    restore_msgs = record.messages
                                console.print(f"  [green]Resuming: {record.title}[/]")
                                break  # break inner loop to reconnect
                            console.print("  [red]Session not found.[/]")
                            continue
                        if cmd == "/clear":
                            session_id = None
                            active_record = None
                            _clear_screen()
                            display.show_banner_interactive(registry, cwd)
                            break

                        # Send to agent and auto-continue until interrupted
                        try:
                            await backend.send_message(user_input)
                            stop = await _run_agent_turn(backend, cost_ref, turns_ref)
                            active_record = _auto_save(
                                store, backend, active_record, registry,
                                model_override, cwd, cost_ref, turns_ref,
                                user_input,
                            )

                            while auto_continue and stop == "end_turn":
                                console.print(Text(
                                    "  ↻ continuing...",
                                    style="dim cyan",
                                ))
                                await backend.send_message(
                                    "Continue building. Do NOT stop. Do NOT re-explore the "
                                    "codebase from scratch — you already know the project "
                                    "structure from previous turns.\n\n"
                                    "BEFORE picking your next feature, do a quick WebSearch: "
                                    "\"top 10 ways to improve a [your project type]\" or "
                                    "\"[your project type] features users love\". Find fresh "
                                    "inspiration from real-world examples. Save findings to "
                                    "docs/research/. Think long-term: what features will make "
                                    "this project amazing 10 iterations from now?\n\n"
                                    "If you've done 3-4 features since last checkpoint, do "
                                    "housekeeping: checkpoint, archive snapshot (appname1.X/ "
                                    "with run.sh), update README, log mistakes, update "
                                    "BACKLOG, save all research to docs/. Then continue.\n\n"
                                    "Remember: use RELATIVE paths only. Stay inside the "
                                    "sandbox. Do NOT use absolute paths or .. traversal."
                                )
                                stop = await _run_agent_turn(backend, cost_ref, turns_ref)
                                active_record = _auto_save(
                                    store, backend, active_record, registry,
                                    model_override, cwd, cost_ref, turns_ref,
                                )

                        except (KeyboardInterrupt, asyncio.CancelledError):
                            # Save on interrupt before breaking
                            if backend.session_id and active_record:
                                active_record.messages = backend.get_messages()
                                store.save(active_record)
                            console.print(Text("\n  ⏹ interrupted", style="bold yellow"))
                            _show_separator()
                            break
                        except BackendNotFoundError:
                            console.print(
                                "[bold red]Error:[/] Claude Code CLI not found. "
                                "Install: npm install -g @anthropic-ai/claude-code"
                            )
                            return
                        except BackendProcessError as e:
                            if hasattr(e, "exit_code") and e.exit_code == -2:
                                console.print(Text("\n  ⏹ interrupted", style="bold yellow"))
                                _show_separator()
                                break
                            console.print(f"\n[red]Error: {e}[/]\n")
                            break
                        except BackendRateLimitError:
                            new_provider = registry.handle_rate_limit()
                            if new_provider and new_provider.status == ProviderStatus.CONNECTED:
                                console.print(
                                    f"\n[yellow]Rate limited. Switching to "
                                    f"{new_provider.display_name}...[/]"
                                )
                                break
                            else:
                                console.print(
                                    "\n[bold red]Rate limited and no available providers. "
                                    "Try again later.[/]"
                                )
                                return
                        except Exception as e:
                            console.print(f"\n[red]Error: {e}[/]\n")

                # Save session_id for potential reconnect
                session_id = backend.session_id

            except BackendNotFoundError:
                console.print(
                    "[bold red]Error:[/] Claude Code CLI not found. "
                    "Install: npm install -g @anthropic-ai/claude-code"
                )
                return
            except (KeyboardInterrupt, asyncio.CancelledError):
                if session_id:
                    continue
                break

    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    display.show_interactive_summary(cost_ref[0], turns_ref[0])


async def _run_agent_turn(
    backend: InteractiveBackend,
    cost_ref: list[float],
    turns_ref: list[int],
) -> str | None:
    """Run a single agent turn with live streaming output.

    Returns the stop_reason (e.g., "end_turn", "max_tokens").
    """
    shown_thinking = False
    streaming_text = False
    streamed_text = False
    in_tool = False
    stop_reason: str | None = None
    spinner = _ThinkingSpinner()
    spinner.start()
    saw_tool_result = False

    async for message in backend.receive():
        # --- Live streaming events ---
        if isinstance(message, AgentStreamEvent):
            event_type = message.event_type

            if event_type == "content_block_start":
                spinner.stop()
                block_type = message.block_type

                if block_type == "tool_use":
                    if streaming_text:
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        streaming_text = False
                    in_tool = True
                elif block_type == "text":
                    if streaming_text:
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                    console.print()
                    sys.stdout.write("  ")
                    streaming_text = True
                    streamed_text = True
                    in_tool = False
                elif block_type == "thinking":
                    if not shown_thinking:
                        spinner.start()

            elif event_type == "content_block_delta":
                delta_type = message.delta_type

                if delta_type == "text_delta" and not in_tool:
                    spinner.stop()
                    text = message.text
                    if text:
                        if not streaming_text:
                            console.print()
                            sys.stdout.write("  ")
                            streaming_text = True
                            streamed_text = True
                        sys.stdout.write(text)
                        sys.stdout.flush()
                elif delta_type == "thinking_delta":
                    if not shown_thinking and not spinner._visible:
                        spinner.start()

            elif event_type == "content_block_stop":
                if streaming_text:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    streaming_text = False
                in_tool = False

            continue

        # Finalize streaming before processing full messages
        if streaming_text:
            sys.stdout.write("\n")
            sys.stdout.flush()
            streaming_text = False

        # --- Full message blocks ---
        if isinstance(message, AgentMessage):
            spinner.stop()
            if message.error:
                _show_assistant_error(message.error)

            saw_tool_result = False
            for block in message.content:
                if isinstance(block, AgentThinkingBlock) and block.thinking.strip():
                    if not shown_thinking:
                        _show_thinking(block.thinking)
                        shown_thinking = True
                elif isinstance(block, AgentTextBlock) and block.text.strip():
                    if streamed_text:
                        continue
                    _show_response(block.text)
                elif isinstance(block, AgentToolUseBlock):
                    _show_tool_use(
                        block.name,
                        block.input if isinstance(block.input, dict) else {},
                    )
                elif isinstance(block, AgentToolResultBlock):
                    _show_tool_result(block)
                    saw_tool_result = True

            if saw_tool_result:
                spinner.start()
                shown_thinking = False

        # --- Task lifecycle (sub-agents, Claude-specific) ---
        elif isinstance(message, AgentTaskStarted):
            spinner.stop()
            _show_task_started(message)
        elif isinstance(message, AgentTaskProgress):
            _show_task_progress(message)
        elif isinstance(message, AgentTaskNotification):
            spinner.stop()
            _show_task_notification(message)

        # --- Result (end of turn) ---
        elif isinstance(message, AgentResult):
            spinner.stop()
            if message.cost_usd:
                cost_ref[0] += message.cost_usd
            if message.num_turns:
                turns_ref[0] += message.num_turns
            stop_reason = message.stop_reason
            _show_result_details(message)

    spinner.stop()
    _show_separator()
    return stop_reason


def _show_cost(total_cost: float, total_turns: int) -> None:
    console.print(f"  [dim]Session cost: ${total_cost:.4f} | Turns: {total_turns}[/]")


def _show_sessions(store: SessionStore) -> None:
    """Display a table of saved sessions."""
    sessions = store.list_sessions()
    if not sessions:
        console.print("  [dim]No saved sessions.[/]")
        return
    from rich.table import Table
    table = Table(show_header=True, border_style="dim")
    table.add_column("#", style="bold")
    table.add_column("Title")
    table.add_column("Provider")
    table.add_column("Cost", justify="right")
    table.add_column("Turns", justify="right")
    table.add_column("Updated")
    for i, s in enumerate(sessions[:20], 1):
        table.add_row(
            str(i),
            s.get("title", "Untitled")[:40],
            s.get("provider_id", "?"),
            f"${s.get('total_cost_usd', 0):.4f}",
            str(s.get("total_turns", 0)),
            s.get("updated_at", "?")[:16],
        )
    console.print(table)
    console.print("  [dim]Use /resume <#> to continue a session.[/]")


def _auto_save(
    store: SessionStore,
    backend: InteractiveBackend,
    active_record: SessionRecord | None,
    registry: ProviderRegistry,
    model_override: str | None,
    cwd: str,
    cost_ref: list[float],
    turns_ref: list[int],
    first_user_input: str | None = None,
) -> SessionRecord:
    """Save session state after each turn. Returns the (possibly new) record."""
    if active_record is None:
        sid = backend.session_id or f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        provider = registry.active
        backend_type = "claude"
        if hasattr(provider, "id"):
            pid = provider.id.value
            if pid == "openai":
                backend_type = "openai"
            elif pid == "gemini":
                backend_type = "gemini"
        active_record = SessionRecord(
            session_id=sid,
            backend_type=backend_type,
            provider_id=getattr(provider.id, "value", "unknown") if hasattr(provider, "id") else "unknown",
            model=model_override or (provider.get_model() if provider else "default"),
            cwd=cwd,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            title=SessionStore.extract_title(first_user_input) if first_user_input else "Untitled",
        )

    active_record.total_cost_usd = cost_ref[0]
    active_record.total_turns = turns_ref[0]
    active_record.messages = backend.get_messages()
    store.save(active_record)
    return active_record

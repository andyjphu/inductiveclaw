"""Interactive REPL mode — Claude Code-style terminal UX."""

from __future__ import annotations

import os
import select
import sys
import termios
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
    ToolUseBlock,
    ToolResultBlock,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
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

# Tools that take a file_path and can write outside the sandbox
_FILE_WRITE_TOOLS = {"Write", "Edit"}
_FILE_READ_TOOLS = {"Read"}
_FILE_ALL_TOOLS = _FILE_WRITE_TOOLS | _FILE_READ_TOOLS | {"Glob", "Grep"}


def _make_sandbox_guard(project_dir: str):
    """Create a can_use_tool callback that restricts all file access to project_dir.

    Every tool call passes through this gate. The CLI sends permission requests
    because we don't set bypassPermissions — our callback auto-allows anything
    inside the sandbox and denies everything outside it.
    """
    resolved = Path(project_dir).resolve()
    resolved_str = str(resolved)

    def _path_in_sandbox(p: str) -> bool:
        """Check if a path is inside the project directory."""
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

        # --- File tools: check file_path ---
        if tool_name in _FILE_WRITE_TOOLS | _FILE_READ_TOOLS:
            file_path = tool_input.get("file_path", "")
            if file_path and not _path_in_sandbox(file_path):
                return PermissionResultDeny(
                    behavior="deny",
                    message=f"Sandbox: {tool_name} blocked — {file_path} "
                            f"is outside {project_dir}",
                )

        # --- Search tools: check path ---
        if tool_name in ("Glob", "Grep"):
            search_path = tool_input.get("path", "")
            if search_path and not _path_in_sandbox(search_path):
                return PermissionResultDeny(
                    behavior="deny",
                    message=f"Sandbox: {tool_name} blocked — {search_path} "
                            f"is outside {project_dir}",
                )

        # --- Bash: block dangerous commands and out-of-sandbox writes ---
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").strip()
            words = cmd.split()
            if not words:
                return PermissionResultAllow(behavior="allow")

            first = words[0]

            # Hard-block dangerous commands
            if first == "sudo" or "sudo " in cmd:
                return PermissionResultDeny(
                    behavior="deny",
                    message="Sandbox: sudo is not allowed",
                )

            # Block commands that explicitly target paths outside sandbox
            # Check for absolute paths in the command that aren't in the sandbox
            for word in words[1:]:
                if word.startswith("/") and not _path_in_sandbox(word):
                    return PermissionResultDeny(
                        behavior="deny",
                        message=f"Sandbox: Bash blocked — references path {word} "
                                f"outside {project_dir}",
                    )

        # Everything else: allow
        return PermissionResultAllow(behavior="allow")

    return guard


# --- Terminal control ---

def _enter_alt_screen() -> None:
    """Switch to alternate screen buffer (clean slate, restored on exit)."""
    sys.stdout.write("\033[?1049h\033[H")
    sys.stdout.flush()


def _exit_alt_screen() -> None:
    """Restore the original terminal content."""
    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()


def _cursor_row() -> int:
    """Query the terminal for the current cursor row (1-based)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        new = termios.tcgetattr(fd)
        new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(fd, termios.TCSANOW, new)
        # DSR — Device Status Report: terminal replies with \033[row;colR
        sys.stdout.write("\033[6n")
        sys.stdout.flush()
        resp = ""
        while True:
            ch = os.read(fd, 1).decode()
            resp += ch
            if ch == "R":
                break
        # Parse \033[row;colR
        row = int(resp.split("[")[1].split(";")[0])
        return row
    except Exception:
        return os.get_terminal_size().lines
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)


def _pad_to_bottom() -> None:
    """Push the cursor near the terminal bottom so the prompt sits above the toolbar."""
    term_height = os.get_terminal_size().lines
    current_row = _cursor_row()
    # We want prompt at (term_height - 2): 1 for toolbar, 1 for prompt itself
    needed = term_height - 2 - current_row
    if needed > 0:
        sys.stdout.write("\n" * needed)
        sys.stdout.flush()


def _drain_stdin() -> None:
    """Discard any pending input (scroll escape sequences, stray keypresses)."""
    fd = sys.stdin.fileno()
    while select.select([fd], [], [], 0.0)[0]:
        os.read(fd, 4096)


def _suppress_stdin() -> list | None:
    """Disable terminal echo and canonical mode during agent work."""
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return None
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
    termios.tcsetattr(fd, termios.TCSANOW, new)
    return old


def _restore_stdin(old: list | None) -> None:
    """Restore terminal settings saved by _suppress_stdin."""
    if old is None:
        return
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSANOW, old)


# --- Styled output helpers ---

def _show_tool_use(name: str, input_data: dict) -> None:
    """Show a tool call in Claude Code style: ⏺ ToolName(summary)"""
    summary = _summarize_tool_input(name, input_data)
    if summary:
        console.print(Text(f"  ⏺ {name}({summary})", style="bold blue"))
    else:
        console.print(Text(f"  ⏺ {name}", style="bold blue"))


def _summarize_tool_input(name: str, data: dict) -> str:
    """Extract the most useful one-liner from tool input."""
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


def _show_tool_result(block: ToolResultBlock) -> None:
    """Show tool result in Claude Code style with ⎿ prefix."""
    content = block.content
    if content is None:
        return
    # content can be a string or list of dicts
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        # Extract text from content blocks
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        text = "\n".join(parts).strip()
    else:
        return
    if not text:
        return
    # Truncate long results, show first few lines
    lines = text.split("\n")
    if len(lines) > 5:
        lines = lines[:5] + [f"  ... ({len(lines) - 5} more lines)"]
    style = "red" if block.is_error else "dim"
    for line in lines:
        console.print(Text(f"  ⎿  {line}", style=style))


def _show_response(text: str) -> None:
    """Render agent text as markdown."""
    console.print()
    console.print(Markdown(text))


def _show_separator() -> None:
    width = console.width
    side = (width - 5) // 2
    line = "─" * side + " ▪▪▪ " + "─" * (width - side - 5)
    console.print()
    console.print(Text(line, style="dim"))


def _print_help() -> None:
    from rich.table import Table
    table = Table(title="Commands", show_header=True, border_style="dim")
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    for cmd, desc in SLASH_COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)


# --- Input with prompt_toolkit ---

def _bottom_toolbar(registry: ProviderRegistry) -> str:
    provider = registry.active
    name = provider.display_name if provider else "none"
    return f"  ⏵⏵ sandbox on  |  {name}  |  /help for commands"


_PT_STYLE = PTStyle.from_dict({
    "bottom-toolbar": "noinherit dim",
})


def _build_session(registry: ProviderRegistry) -> PromptSession:
    completer = WordCompleter(list(SLASH_COMMANDS.keys()), sentence=True)
    return PromptSession(
        history=InMemoryHistory(),
        completer=completer,
        complete_while_typing=False,
        bottom_toolbar=lambda: _bottom_toolbar(registry),
        style=_PT_STYLE,
    )


def _build_options(
    registry: ProviderRegistry,
    cwd: str,
) -> ClaudeAgentOptions:
    provider = registry.active
    assert provider is not None

    opts = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        cwd=cwd,
        add_dirs=[cwd],
        system_prompt=_INTERACTIVE_PROMPT,
        env=provider.get_sdk_env(),
        can_use_tool=_make_sandbox_guard(cwd),
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
    total_cost = 0.0
    total_turns = 0

    options = _build_options(registry, cwd)
    if model_override:
        options.model = model_override

    session = _build_session(registry)

    _enter_alt_screen()
    try:
        console.print(Text("  Starting iclaw...\n", style="dim"))

        async with ClaudeSDKClient(options=options) as client:
            # Clear the "Starting..." text now that we're connected
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            display.show_banner_interactive(registry)
            _pad_to_bottom()

            while True:
                # Get input via prompt_toolkit (it owns stdin here)
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
                    _show_cost(total_cost, total_turns)
                    continue
                if cmd == "/clear":
                    console.print("Starting new session...\n")
                    break

                # Send to agent — suppress stdin to prevent scroll artifacts
                old_term = _suppress_stdin()
                try:
                    await client.query(user_input)
                    console.print(Text("  ✻ thinking...", style="dim cyan"))
                    async for message in client.receive_response():
                        if isinstance(message, AssistantMessage):
                            for block in message.content:
                                if isinstance(block, TextBlock) and block.text.strip():
                                    _show_response(block.text)
                                elif isinstance(block, ToolUseBlock):
                                    _show_tool_use(
                                        block.name,
                                        block.input if isinstance(block.input, dict) else {},
                                    )
                                elif isinstance(block, ToolResultBlock):
                                    _show_tool_result(block)
                        if isinstance(message, ResultMessage):
                            if message.total_cost_usd:
                                total_cost += message.total_cost_usd
                            if message.num_turns:
                                total_turns += message.num_turns

                    _show_separator()

                except KeyboardInterrupt:
                    # Ctrl+C during agent work — stop the current turn
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
                finally:
                    # Restore terminal, drain any queued scroll sequences
                    _restore_stdin(old_term)
                    _drain_stdin()
                    _pad_to_bottom()

    except KeyboardInterrupt:
        pass
    finally:
        _exit_alt_screen()

    display.show_interactive_summary(total_cost, total_turns)


def _show_cost(total_cost: float, total_turns: int) -> None:
    console.print(f"  [dim]Session cost: ${total_cost:.4f} | Turns: {total_turns}[/]")

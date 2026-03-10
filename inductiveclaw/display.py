"""Terminal output formatting and progress display."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ClawConfig, UsageTracker
    from .providers import ProviderRegistry

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    _has_rich = True
except ImportError:
    _has_rich = False

BANNER = r"""
 ██▓ ███▄    █ ▓█████▄  █    ██  ▄████▄  ▄▄▄█████▓ ██▓ ██▒   █▓▓█████  ▄████▄   ██▓    ▄▄▄       █     █░
▓██▒ ██ ▀█   █ ▒██▀ ██▌ ██  ▓██▒▒██▀ ▀█  ▓  ██▒ ▓▒▓██▒▓██░   █▒▓█   ▀ ▒██▀ ▀█  ▓██▒   ▒████▄    ▓█░ █ ░█░
▒██▒▓██  ▀█ ██▒░██   █▌▓██  ▒██░▒▓█    ▄ ▒ ▓██░ ▒░▒██▒ ▓██  █▒░▒███   ▒▓█    ▄ ▒██░   ▒██  ▀█▄  ▒█░ █ ░█
░██░▓██▒  ▐▌██▒░▓█▄   ▌▓▓█  ░██░▒▓▓▄ ▄██▒░ ▓██▓ ░ ░██░  ▒██ █░░▒▓█  ▄ ▒▓▓▄ ▄██▒▒██░   ░██▄▄▄▄██ ░█░ █ ░█
░██░▒██░   ▓██░░▒████▓ ▒▒█████▓ ▒ ▓███▀ ░  ▒██▒ ░ ░██░   ▒▀█░  ░▒████▒▒ ▓███▀ ░░██████▒▓█   ▓██▒░░██▒██▓
░▓  ░ ▒░   ▒ ▒  ▒▒▓  ▒ ░▒▓▒ ▒ ▒ ░ ░▒ ▒  ░  ▒ ░░   ░▓     ░ ▐░  ░░ ▒░ ░░ ░▒ ▒  ░░ ▒░▓  ░▒▒   ▓▒█░░ ▓░▒ ▒
"""


def show_banner(config: ClawConfig, registry: ProviderRegistry) -> None:
    provider = registry.active
    provider_name = provider.display_name if provider else "none"
    auth_line = provider.status_line() if provider else "not configured"

    if _has_rich:
        console.print(Text(BANNER, style="bold cyan"))
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold]Goal[/]", config.goal)
        table.add_row("[bold]Project[/]", config.project_dir)
        table.add_row("[bold]Provider[/]", f"{provider_name} — {auth_line}")
        table.add_row("[bold]Model[/]", config.model or "default")
        table.add_row("[bold]Threshold[/]", f"{config.quality_threshold}/10")
        table.add_row("[bold]Max iterations[/]", str(config.max_iterations))
        if registry.cycle_enabled:
            table.add_row("[bold]Cycling[/]", "enabled")
        console.print(Panel(table, title="[bold]Configuration[/]", border_style="cyan"))
        console.print()
    else:
        print(BANNER)
        print(f"Goal: {config.goal}")
        print(f"Project: {config.project_dir}")
        print(f"Provider: {provider_name} — {auth_line}")
        print(f"Threshold: {config.quality_threshold}/10")
        print()


def show_banner_interactive(registry: ProviderRegistry, sandbox_path: str | None = None) -> None:
    provider = registry.active
    provider_name = provider.display_name if provider else "none"
    auth_line = provider.status_line() if provider else "not configured"

    if _has_rich:
        console.print(Text(BANNER, style="bold cyan"))
        console.print(f"  [bold]Provider:[/] {provider_name} — {auth_line}")
        if sandbox_path:
            console.print(f"  [bold]Sandbox:[/] {sandbox_path}")
        if registry.cycle_enabled:
            console.print(f"  [bold]Cycling:[/] enabled")
        console.print(f"\n  Type [bold cyan]/help[/] for commands, [bold cyan]/quit[/] to exit.\n")
    else:
        print(BANNER)
        print(f"  Provider: {provider_name} — {auth_line}")
        if sandbox_path:
            print(f"  Sandbox: {sandbox_path}")
        print(f"\n  Type /help for commands, /quit to exit.\n")


def show_interactive_response(text: str) -> None:
    if _has_rich:
        console.print(text)
    else:
        print(text)


def show_interactive_summary(total_cost: float, total_turns: int) -> None:
    if _has_rich:
        console.print(f"\n[dim]Session: ${total_cost:.4f} | {total_turns} turns[/]")
    else:
        print(f"\nSession: ${total_cost:.4f} | {total_turns} turns")


def show_iteration_header(n: int, tracker: UsageTracker) -> None:
    features = len(tracker.features_completed)
    score = tracker.last_quality_score
    score_str = f" | Score: {score}/10" if score is not None else ""
    label = f"Iteration {n} | Features: {features}{score_str} | {tracker.duration_display}"

    if _has_rich:
        console.rule(f"[bold yellow]{label}[/]")
    else:
        print(f"\n{'=' * 60}")
        print(f"  {label}")
        print(f"{'=' * 60}")


def show_agent_text(text: str) -> None:
    preview = text[:200] + "..." if len(text) > 200 else text
    if _has_rich:
        console.print(f"[dim]{preview}[/]")
    else:
        print(f"  {preview}")


def show_tool_call(name: str, summary: str) -> None:
    if _has_rich:
        console.print(f"  [bold blue]tool:[/] {name}: {summary[:100]}")
    else:
        print(f"  tool: {name}: {summary[:100]}")


def show_feature_completed(name: str) -> None:
    if _has_rich:
        console.print(f"  [bold green]completed:[/] {name}")
    else:
        print(f"  completed: {name}")


def show_error(iteration: int, error: Exception) -> None:
    if _has_rich:
        console.print(f"  [bold red]error in iteration {iteration}:[/] {error}")
    else:
        print(f"  error in iteration {iteration}: {error}")


def show_quality_reached(tracker: UsageTracker) -> None:
    if _has_rich:
        console.print(
            Panel(
                f"[bold green]Quality threshold reached! Score: {tracker.last_quality_score}/10[/]",
                border_style="green",
            )
        )
    else:
        print(f"\nQuality threshold reached! Score: {tracker.last_quality_score}/10")


def show_interrupted() -> None:
    if _has_rich:
        console.print("\n[bold red]Interrupted by user[/]")
    else:
        print("\nInterrupted by user")


def show_result(text: str) -> None:
    if _has_rich:
        console.print(f"  [dim cyan]{text[:300]}[/]")
    else:
        print(f"  {text[:300]}")


def show_summary(tracker: UsageTracker) -> None:
    if _has_rich:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold]Iterations[/]", str(tracker.iterations_completed))
        table.add_row("[bold]Features[/]", str(len(tracker.features_completed)))
        table.add_row("[bold]Final score[/]", f"{tracker.last_quality_score}/10" if tracker.last_quality_score else "N/A")
        table.add_row("[bold]Duration[/]", tracker.duration_display)
        if tracker.quality_history:
            table.add_row("[bold]Score history[/]", " -> ".join(str(s) for s in tracker.quality_history))
        if tracker.errors:
            table.add_row("[bold]Errors[/]", str(len(tracker.errors)))
        console.print()
        console.print(Panel(table, title="[bold]Summary[/]", border_style="cyan"))
    else:
        print(f"\n--- Summary ---")
        print(f"Iterations: {tracker.iterations_completed}")
        print(f"Features: {len(tracker.features_completed)}")
        print(f"Final score: {tracker.last_quality_score}/10" if tracker.last_quality_score else "Final score: N/A")
        print(f"Duration: {tracker.duration_display}")
        if tracker.quality_history:
            print(f"Score history: {' -> '.join(str(s) for s in tracker.quality_history)}")

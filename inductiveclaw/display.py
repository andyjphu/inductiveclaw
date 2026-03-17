"""Terminal output formatting and progress display."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .budget import BudgetTracker
    from .config import ClawConfig, IdeaRecord, UsageTracker
    from .providers import ProviderRegistry

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
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
        if config.budget_usd is not None:
            table.add_row("[bold]Budget[/]", f"${config.budget_usd:.2f}")
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
    cost_str = f" | Cost: ${tracker.total_cost_usd:.4f}" if tracker.total_cost_usd > 0 else ""
    label = f"Iteration {n} | Features: {features}{score_str}{cost_str} | {tracker.duration_display}"

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


def show_idea_transition(new_idea: IdeaRecord, history: list[IdeaRecord]) -> None:
    prev = history[-1] if history else None
    if _has_rich:
        console.print()
        console.print(Rule(f"[bold magenta]New Idea: {new_idea.title}[/]", style="magenta"))
        if prev:
            console.print(f"  [dim]Previous: {prev.title} — score {prev.final_score}/10, {len(prev.features)} features[/]")
        console.print(f"  [bold]{new_idea.description}[/]")
        console.print(f"  [dim]Relationship: {new_idea.relationship} | Branch: {new_idea.branch}[/]")
        console.print(f"  [dim]Worktree: {new_idea.worktree_path}[/]")
        console.print()
    else:
        print(f"\n{'='*60}")
        print(f"  NEW IDEA: {new_idea.title}")
        if prev:
            print(f"  Previous: {prev.title} — score {prev.final_score}/10")
        print(f"  {new_idea.description}")
        print(f"  Branch: {new_idea.branch}")
        print(f"{'='*60}\n")


def show_summary(tracker: UsageTracker) -> None:
    if _has_rich:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold]Iterations[/]", str(tracker.iterations_completed))
        table.add_row("[bold]Features[/]", str(len(tracker.features_completed)))
        table.add_row("[bold]Final score[/]", f"{tracker.last_quality_score}/10" if tracker.last_quality_score else "N/A")
        table.add_row("[bold]Duration[/]", tracker.duration_display)
        if tracker.total_cost_usd > 0:
            table.add_row("[bold]Total cost[/]", f"${tracker.total_cost_usd:.4f}")
        if tracker.quality_history:
            table.add_row("[bold]Score history[/]", " -> ".join(str(s) for s in tracker.quality_history))
        if tracker.errors:
            table.add_row("[bold]Errors[/]", str(len(tracker.errors)))
        if tracker.idea_history:
            ideas = ", ".join(
                f"{i.title} ({i.final_score}/10)" for i in tracker.idea_history
            )
            table.add_row("[bold]Ideas completed[/]", ideas)
            table.add_row("[bold]Total ideas[/]", str(len(tracker.idea_history) + 1))
        console.print()
        console.print(Panel(table, title="[bold]Summary[/]", border_style="cyan"))
    else:
        print(f"\n--- Summary ---")
        print(f"Iterations: {tracker.iterations_completed}")
        print(f"Features: {len(tracker.features_completed)}")
        print(f"Final score: {tracker.last_quality_score}/10" if tracker.last_quality_score else "Final score: N/A")
        print(f"Duration: {tracker.duration_display}")
        if tracker.total_cost_usd > 0:
            print(f"Total cost: ${tracker.total_cost_usd:.4f}")
        if tracker.quality_history:
            print(f"Score history: {' -> '.join(str(s) for s in tracker.quality_history)}")


# Tournament display lives in display_parallel.py to stay under 300 lines.
# Re-export so `display.*` calls from parallel.py and agent_worker.py work.
from .display_parallel import (  # noqa: F401
    show_branch_event,
    show_parallel_banner,
    show_round_header,
    show_round_results,
    show_tournament_summary,
)


def show_budget_warning(budget: BudgetTracker) -> None:
    """Display a warning when budget reaches 80%."""
    remaining = budget.remaining_usd or 0.0
    if _has_rich:
        console.print(
            f"\n  [bold yellow]Budget warning:[/] "
            f"[yellow]{budget.format_status()} spent "
            f"(${remaining:.4f} remaining)[/]\n"
        )
    else:
        print(f"\n  Budget warning: {budget.format_status()} "
              f"(${remaining:.4f} remaining)\n")


def show_budget_exceeded(budget: BudgetTracker) -> None:
    """Display a message when budget is fully spent."""
    if _has_rich:
        console.print(Panel(
            f"[bold red]Budget exceeded:[/] {budget.format_status()}\n"
            f"Gracefully stopping.",
            border_style="red",
            title="[bold red]Budget Limit Reached[/]",
        ))
    else:
        print(f"\n  BUDGET EXCEEDED: {budget.format_status()}")
        print("  Gracefully stopping.\n")

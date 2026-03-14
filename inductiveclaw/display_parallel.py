"""Tournament / parallel display functions — extracted from display.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ClawConfig
    from .providers import ProviderRegistry

try:
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table

    from .display import console, show_banner
    _has_rich = True
except ImportError:
    _has_rich = False

_BRANCH_COLORS = ["cyan", "magenta", "yellow", "green", "blue", "red"]


def show_parallel_banner(
    config: ClawConfig, registry: ProviderRegistry, num_branches: int,
) -> None:
    """Show banner with tournament configuration."""
    from .display import show_banner
    show_banner(config, registry)
    round_length = config.round_length or config.eval_frequency
    if _has_rich:
        console.print(
            f"  [bold]Tournament:[/] {num_branches} branches/round, "
            f"{round_length} iterations/round\n"
        )
    else:
        print(f"  Tournament: {num_branches} branches/round, {round_length} iterations/round\n")


def show_round_header(round_num: int, num_branches: int, round_length: int) -> None:
    label = f"Round {round_num} | {num_branches} branches | {round_length} iterations each"
    if _has_rich:
        console.print()
        console.rule(f"[bold magenta]{label}[/]", style="magenta")
    else:
        print(f"\n{'#' * 60}")
        print(f"  {label}")
        print(f"{'#' * 60}")


def show_branch_event(
    branch_id: str, event_type: str, data: dict,
) -> None:
    """Show a progress event from a running branch."""
    idx = ord(branch_id) - ord("A") if len(branch_id) == 1 and branch_id.isalpha() else 0
    color = _BRANCH_COLORS[idx % len(_BRANCH_COLORS)]

    if event_type == "iteration_start":
        msg = f"iteration {data.get('iteration', '?')}"
    elif event_type == "tool_call":
        msg = f"tool: {data.get('name', '?')}"
    elif event_type == "feature":
        msg = f"completed: {data.get('name', '?')}"
    elif event_type == "score":
        msg = f"score: {data.get('score', '?')}/10"
    elif event_type == "error":
        msg = f"error: {data.get('message', '?')}"
    elif event_type == "done":
        msg = f"done ({data.get('reason', '?')})"
    else:
        msg = str(data)

    if _has_rich:
        console.print(f"  [{color}][Branch {branch_id}][/{color}] {msg}")
    else:
        print(f"  [Branch {branch_id}] {msg}")


def show_round_results(
    round_num: int,
    results: list,
    winner: object,
) -> None:
    """Show comparison table for a completed round."""
    if _has_rich:
        table = Table(title=f"Round {round_num} Results", border_style="magenta")
        table.add_column("Branch", style="bold")
        table.add_column("Score", justify="center")
        table.add_column("Features", justify="center")
        table.add_column("Iterations", justify="center")
        table.add_column("Cost", justify="right")
        table.add_column("Status")

        for r in sorted(results, key=lambda x: x.final_score or 0, reverse=True):
            is_winner = r.branch_id == winner.branch_id
            score_str = f"{r.final_score}/10" if r.final_score else "N/A"
            prefix = "[bold green]" if is_winner else ""
            suffix = "[/]" if is_winner else ""
            marker = " (winner)" if is_winner else ""
            table.add_row(
                f"{prefix}{r.branch_id}{marker}{suffix}",
                f"{prefix}{score_str}{suffix}",
                f"{prefix}{len(r.features)}{suffix}",
                f"{prefix}{r.iterations_completed}{suffix}",
                f"{prefix}${r.cost_usd:.4f}{suffix}",
                f"{prefix}{r.stop_reason}{suffix}",
            )
        console.print()
        console.print(table)
        console.print()
    else:
        print(f"\n--- Round {round_num} Results ---")
        for r in sorted(results, key=lambda x: x.final_score or 0, reverse=True):
            marker = " (WINNER)" if r.branch_id == winner.branch_id else ""
            score_str = f"{r.final_score}/10" if r.final_score else "N/A"
            print(f"  Branch {r.branch_id}{marker}: score {score_str}, "
                  f"{len(r.features)} features, {r.iterations_completed} iters, "
                  f"${r.cost_usd:.4f}")
        print()


def show_tournament_summary(round_summaries: list, budget: object) -> None:
    """Show the final tournament results."""
    if not round_summaries:
        return

    final_winner = round_summaries[-1].winner
    total_cost = sum(
        r.cost_usd for s in round_summaries for r in s.results
    )
    total_iters = sum(
        r.iterations_completed for s in round_summaries for r in s.results
    )
    total_features = len(final_winner.features)

    if _has_rich:
        console.print()
        console.print(Rule("[bold green]Tournament Complete[/]", style="green"))

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold]Rounds[/]", str(len(round_summaries)))
        table.add_row("[bold]Total iterations[/]", str(total_iters))
        table.add_row("[bold]Total cost[/]", f"${total_cost:.4f}")
        table.add_row("[bold]Winner[/]", f"Branch {final_winner.branch_id}")
        table.add_row(
            "[bold]Final score[/]",
            f"{final_winner.final_score}/10" if final_winner.final_score else "N/A",
        )
        table.add_row("[bold]Features[/]", str(total_features))
        table.add_row("[bold]Output[/]", final_winner.project_dir)

        progression = " -> ".join(
            f"R{s.round_num}: {s.winner.branch_id} ({s.winner.final_score or '?'}/10)"
            for s in round_summaries
        )
        table.add_row("[bold]Progression[/]", progression)

        console.print(Panel(table, title="[bold]Tournament Summary[/]", border_style="green"))
    else:
        print(f"\n=== Tournament Complete ===")
        print(f"Rounds: {len(round_summaries)}")
        print(f"Total iterations: {total_iters}")
        print(f"Total cost: ${total_cost:.4f}")
        print(f"Winner: Branch {final_winner.branch_id}")
        print(f"Final score: {final_winner.final_score}/10" if final_winner.final_score else "Final score: N/A")
        print(f"Features: {total_features}")

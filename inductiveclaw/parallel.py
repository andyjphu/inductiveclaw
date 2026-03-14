"""Tournament-style parallel exploration coordinator.

Runs multiple branches in parallel per round, picks the best scorer,
forks new branches from the winner, and repeats until the quality
threshold is reached or the budget is exhausted.
"""

from __future__ import annotations

import shutil
import signal
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import anyio

from . import display
from .agent_worker import BranchEvent, BranchResult, run_branch
from .budget import BudgetStatus, BudgetTracker
from .config import ClawConfig
from .providers import ProviderRegistry

APPROACH_HINTS = [
    "Focus on minimalism: fewest dependencies, simplest architecture, most readable code.",
    "Focus on robustness: error handling, edge cases, testing, defensive coding from the start.",
    "Focus on user experience: beautiful, responsive, delightful interface before internals.",
    "Focus on performance: speed, efficient data structures, benchmark everything.",
    "Focus on extensibility: plugins, hooks, clean abstractions for easy extension.",
    "Focus on completeness: widest feature set, covering as many use cases as possible.",
]

_BRANCH_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class RoundSummary:
    """Snapshot of one tournament round."""
    round_num: int
    results: list[BranchResult]
    winner: BranchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _select_hints(round_num: int, num_branches: int) -> list[str]:
    """Pick *num_branches* approach hints, rotating through the pool each round."""
    offset = (round_num - 1) * num_branches
    return [APPROACH_HINTS[(offset + i) % len(APPROACH_HINTS)] for i in range(num_branches)]


def _create_branch_dirs(base_dir: str, num_branches: int, round_num: int) -> list[str]:
    """Create *num_branches* isolated copies of *base_dir* as siblings."""
    base = Path(base_dir)
    branch_dirs: list[str] = []
    for i in range(num_branches):
        label = _BRANCH_LABELS[i] if i < len(_BRANCH_LABELS) else str(i)
        name = f"{base.name}-r{round_num}-branch-{label.lower()}"
        dest = base.parent / name
        if dest.exists():
            shutil.rmtree(dest)
        if base.exists() and any(base.iterdir()):
            shutil.copytree(base, dest, dirs_exist_ok=True)
        else:
            dest.mkdir(parents=True, exist_ok=True)
        branch_dirs.append(str(dest))
    return branch_dirs


def _cleanup_dirs(dirs: list[str]) -> None:
    """Remove a list of directories (best-effort)."""
    for d in dirs:
        try:
            shutil.rmtree(d)
        except OSError:
            pass


def _make_branch_config(config: ClawConfig, branch_dir: str) -> ClawConfig:
    """Create a branch-specific copy of the config pointing to *branch_dir*."""
    bc = deepcopy(config)
    bc.project_dir = branch_dir
    return bc


# ---------------------------------------------------------------------------
# Tournament coordinator
# ---------------------------------------------------------------------------

async def run_parallel(config: ClawConfig, registry: ProviderRegistry) -> None:
    """Run a tournament-style parallel exploration loop."""
    num_branches = config.num_branches
    round_length = config.round_length or config.eval_frequency
    budget = BudgetTracker(budget_usd=config.budget_usd)

    display.show_parallel_banner(config, registry, num_branches)
    Path(config.project_dir).mkdir(parents=True, exist_ok=True)

    current_base_dir = config.project_dir
    total_iterations = 0
    round_summaries: list[RoundSummary] = []
    stop_event = anyio.Event()

    # Signal handling at coordinator level
    interrupted = False

    def handle_interrupt(sig, frame):
        nonlocal interrupted
        interrupted = True
        stop_event.set()

    prev_handler = signal.signal(signal.SIGINT, handle_interrupt)
    prev_term = signal.signal(signal.SIGTERM, handle_interrupt)

    try:
        round_num = 0
        while True:
            round_num += 1
            if interrupted:
                break

            remaining_iters = config.max_iterations - total_iterations
            if remaining_iters <= 0:
                break

            effective_round_length = min(round_length, remaining_iters)
            display.show_round_header(round_num, num_branches, effective_round_length)

            # Create isolated branch directories
            branch_dirs = _create_branch_dirs(current_base_dir, num_branches, round_num)
            hints = _select_hints(round_num, num_branches)

            # Run branches in parallel
            results: list[BranchResult] = []

            async def _run_branch_task(
                idx: int, branch_dir: str, hint: str,
            ) -> None:
                label = _BRANCH_LABELS[idx] if idx < len(_BRANCH_LABELS) else str(idx)
                branch_config = _make_branch_config(config, branch_dir)

                def on_event(event: BranchEvent) -> None:
                    display.show_branch_event(event.branch_id, event.event_type, event.data)

                try:
                    result = await run_branch(
                        config=branch_config,
                        registry=registry,
                        budget=budget,
                        branch_id=label,
                        approach_hint=hint,
                        max_iterations=effective_round_length,
                        stop_event=stop_event,
                        on_event=on_event,
                    )
                    results.append(result)
                except Exception as e:
                    # One branch failing shouldn't kill the tournament
                    from .config import UsageTracker
                    results.append(BranchResult(
                        branch_id=label,
                        tracker=UsageTracker(),
                        project_dir=branch_dir,
                        final_score=0,
                        iterations_completed=0,
                        features=[],
                        cost_usd=0.0,
                        stop_reason=f"error: {e}",
                    ))

            async with anyio.create_task_group() as tg:
                for idx, (branch_dir, hint) in enumerate(zip(branch_dirs, hints)):
                    tg.start_soon(_run_branch_task, idx, branch_dir, hint)

            if not results:
                break

            # Pick winner
            winner = max(results, key=lambda r: r.final_score or 0)
            round_summaries.append(RoundSummary(
                round_num=round_num, results=list(results), winner=winner,
            ))
            display.show_round_results(round_num, results, winner)

            # Accumulate total iterations
            for r in results:
                total_iterations += r.iterations_completed

            # Stop conditions
            if winner.final_score and winner.final_score >= config.quality_threshold:
                break
            if budget.check() == BudgetStatus.EXCEEDED:
                break
            if interrupted:
                break

            # Clean up losing branches, keep winner as next base
            losing_dirs = [r.project_dir for r in results if r.branch_id != winner.branch_id]
            _cleanup_dirs(losing_dirs)
            current_base_dir = winner.project_dir

    finally:
        signal.signal(signal.SIGINT, prev_handler)
        signal.signal(signal.SIGTERM, prev_term)

    # Finalize: copy winner to original project dir
    if round_summaries:
        final_winner = round_summaries[-1].winner
        _finalize_winner(final_winner, config.project_dir)
        display.show_tournament_summary(round_summaries, budget)
    else:
        display.show_interrupted()


def _finalize_winner(winner: BranchResult, original_project_dir: str) -> None:
    """Copy the winning branch's project to the original project directory."""
    src = Path(winner.project_dir)
    dst = Path(original_project_dir)

    if src.resolve() == dst.resolve():
        return

    # Clear destination and copy winner
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

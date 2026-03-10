"""Per-iteration prompt builder — templates loaded from .md files."""

from __future__ import annotations

from importlib.resources import files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ClawConfig, UsageTracker

_FIRST = files(__package__).joinpath("iteration_first.md").read_text()
_NEXT = files(__package__).joinpath("iteration_next.md").read_text()
_EVAL = files(__package__).joinpath("eval_trigger.md").read_text().strip()
_SCREENSHOT = files(__package__).joinpath("screenshot_trigger.md").read_text().strip()


def build_iteration_prompt(
    config: ClawConfig, iteration: int, tracker: UsageTracker
) -> str:
    """Build the user-message prompt for a single iteration."""

    if iteration == 1:
        return _FIRST.format(goal=config.goal)

    return _subsequent(config, iteration, tracker)


def _subsequent(
    config: ClawConfig, iteration: int, tracker: UsageTracker
) -> str:
    context_parts: list[str] = []

    if tracker.features_completed:
        recent = tracker.features_completed[-5:]
        context_parts.append(f"Recently completed: {', '.join(recent)}")

    if tracker.last_quality_score is not None:
        context_parts.append(f"Last quality score: {tracker.last_quality_score}/10")
        gap = config.quality_threshold - tracker.last_quality_score
        if gap > 0:
            context_parts.append(f"Need {gap} more points to reach threshold.")

    if tracker.errors:
        recent_errors = tracker.errors[-2:]
        context_parts.append(f"Recent errors to be aware of: {'; '.join(recent_errors)}")

    if iteration % config.eval_frequency == 0:
        context_parts.append(_EVAL)

    if config.auto_screenshot and iteration % config.eval_frequency == 0:
        context_parts.append(_SCREENSHOT)

    return _NEXT.format(
        goal=config.goal,
        iteration=iteration,
        context="\n".join(context_parts),
    )

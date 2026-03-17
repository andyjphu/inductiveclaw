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
_IDEA_PROPOSAL = files(__package__).joinpath("idea_proposal.md").read_text().strip()


_BROWSER_EVAL = files(__package__).joinpath("browser_eval_trigger.md").read_text().strip()
_APPROACH_HINT = files(__package__).joinpath("approach_hint.md").read_text().strip()


def build_iteration_prompt(
    config: ClawConfig,
    iteration: int,
    tracker: UsageTracker,
    approach_hint: str | None = None,
) -> str:
    """Build the user-message prompt for a single iteration."""

    # New idea just started — treat as first iteration
    if iteration == 1 or (
        tracker.current_idea
        and tracker.iterations_completed == 0
        and tracker.idea_number > 1
    ):
        prompt = _build_new_idea_prompt(config, tracker)
    else:
        prompt = _subsequent(config, iteration, tracker)

    if approach_hint:
        prompt = _APPROACH_HINT.format(approach_hint=approach_hint) + "\n\n" + prompt

    return prompt


def _build_new_idea_prompt(config: ClawConfig, tracker: UsageTracker) -> str:
    """Build prompt for the first iteration of an idea (including the very first)."""
    idea = tracker.current_idea
    if idea and tracker.idea_number > 1:
        # Continuing from a previous idea — inject context
        history = _build_idea_history(tracker)
        return (
            f"GOAL: {config.goal}\n\n"
            f"## New Idea: {idea.title}\n\n"
            f"**Description:** {idea.description}\n"
            f"**Relationship to previous work:** {idea.relationship}\n\n"
            f"### Previous Ideas\n{history}\n\n"
            f"You are starting fresh in a new git worktree. The previous idea's "
            f"code is in a sibling directory — you can reference it with Read but "
            f"don't modify it.\n\n"
        ) + _FIRST.format(goal=f"{idea.title}: {idea.description}")

    return _FIRST.format(goal=config.goal)


def _subsequent(
    config: ClawConfig, iteration: int, tracker: UsageTracker
) -> str:
    context_parts: list[str] = []

    # Idea context
    if tracker.current_idea and tracker.idea_number > 1:
        context_parts.append(
            f"Current idea: **{tracker.current_idea.title}** "
            f"(idea #{tracker.idea_number}, {tracker.current_idea.relationship})"
        )

    # Progress summary
    if tracker.features_completed:
        recent = tracker.features_completed[-5:]
        context_parts.append(f"Completed so far: {', '.join(recent)}")

    if tracker.last_quality_score is not None:
        context_parts.append(f"Last quality score: {tracker.last_quality_score}/10")
        gap = config.quality_threshold - tracker.last_quality_score
        if gap > 0:
            context_parts.append(
                f"Need {gap} more points to reach ship threshold "
                f"({config.quality_threshold}/10). Focus on the weakest dimension."
            )
        else:
            context_parts.append(
                "Score meets threshold — focus on completeness and polish."
            )

    # Surface recent errors
    if tracker.errors:
        recent_errors = tracker.errors[-3:]
        context_parts.append(
            "Recent errors (do NOT retry the same approach):\n"
            + "\n".join(f"  - {e}" for e in recent_errors)
        )

    # Eval and screenshot triggers
    if iteration % config.eval_frequency == 0:
        context_parts.append(_EVAL)

    if config.browser_eval and iteration % config.eval_frequency == 0:
        context_parts.append(_BROWSER_EVAL)

    if config.auto_screenshot and iteration % config.eval_frequency == 0:
        context_parts.append(_SCREENSHOT)

    # Dashboard steering hint (injected via --dash UI)
    steering_hint = getattr(config, "_steering_hint", None)
    if steering_hint:
        context_parts.append(
            f"**PRIORITY FROM OPERATOR:** {steering_hint}\n"
            f"Address this directive in the current iteration."
        )
        config._steering_hint = None  # type: ignore[attr-defined]

    # Idea proposal trigger — when quality threshold met
    pending = getattr(tracker, "_pending_idea_prompt", False)
    if pending:
        history = _build_idea_history(tracker)
        context_parts.append(_IDEA_PROPOSAL.format(
            threshold=config.quality_threshold,
            idea_history=history,
        ))
        tracker._pending_idea_prompt = False  # type: ignore[attr-defined]

    return _NEXT.format(
        goal=config.goal,
        iteration=iteration,
        context="\n".join(context_parts),
    )


def _build_idea_history(tracker: UsageTracker) -> str:
    """Format completed ideas for prompt injection."""
    if not tracker.idea_history:
        return "(this is the first idea)"
    lines = []
    for i, idea in enumerate(tracker.idea_history, 1):
        score = f"{idea.final_score}/10" if idea.final_score else "?"
        lines.append(
            f"{i}. **{idea.title}** ({idea.relationship}) — "
            f"score {score}, {len(idea.features)} features, "
            f"{idea.iterations} iterations. Branch: `{idea.branch}`"
        )
    return "\n".join(lines)

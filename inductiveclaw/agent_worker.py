"""Single-branch iteration loop — the core reusable unit.

Extracted from agent.py. Uses git_helpers for worktree/idea management.
"""

from __future__ import annotations

import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import anyio

from . import display
from .budget import BudgetStatus, BudgetTracker
from .backends import (
    AgentMessage,
    AgentResult,
    AgentTextBlock,
    AgentToolUseBlock,
    BackendNotFoundError,
    BackendProcessError,
    BackendRateLimitError,
    create_autonomous_backend,
)
from .config import ClawConfig, IdeaRecord, UsageTracker
from .git_helpers import (
    IterationResult,
    commit_idea,
    extract_iteration_results,
    finalize_idea,
    read_idea_proposal,
    transition_to_idea,
)
from .prompts import SYSTEM_PROMPT, build_iteration_prompt
from .providers import ProviderRegistry, ProviderStatus
from .tools import create_iclaw_tools

MAX_CONSECUTIVE_ERRORS = 3

AUTONOMOUS_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebSearch", "WebFetch",
    "mcp__iclaw-tools__update_backlog",
    "mcp__iclaw-tools__self_evaluate",
    "mcp__iclaw-tools__take_screenshot",
    "mcp__iclaw-tools__write_docs",
    "mcp__iclaw-tools__smoke_test",
    "mcp__iclaw-tools__propose_idea",
]


@dataclass
class BranchEvent:
    """Progress event emitted by a running branch."""
    branch_id: str
    event_type: str  # iteration_start, tool_call, feature, score, error, done
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class BranchResult:
    """Final outcome of a single branch run."""
    branch_id: str
    tracker: UsageTracker
    project_dir: str
    final_score: int | None
    iterations_completed: int
    features: list[str]
    cost_usd: float
    stop_reason: str  # quality_reached, budget, max_iterations, error, interrupted


# ---------------------------------------------------------------------------
# Single iteration
# ---------------------------------------------------------------------------

async def _run_single_iteration(
    prompt: str,
    config: ClawConfig,
    tracker: UsageTracker,
    registry: ProviderRegistry,
    tools_server: object,
    project_dir: str,
    verbose: bool,
    budget: BudgetTracker | None = None,
    branch_id: str | None = None,
    on_event: Callable[[BranchEvent], None] | None = None,
) -> IterationResult:
    """Run one iteration via the provider's backend."""
    backend = create_autonomous_backend(
        provider=registry.active,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=AUTONOMOUS_TOOLS,
        cwd=project_dir,
        model=config.model or registry.active.get_model(),
        max_turns=config.max_turns_per_iteration,
        mcp_servers={"iclaw-tools": tools_server},
    )

    async for message in backend.run_iteration(prompt):
        if isinstance(message, AgentMessage):
            for block in message.content:
                if isinstance(block, AgentTextBlock) and block.text.strip():
                    if verbose:
                        display.show_agent_text(block.text)
                elif isinstance(block, AgentToolUseBlock):
                    if branch_id and on_event:
                        on_event(BranchEvent(branch_id, "tool_call", {"name": block.name}))
                    else:
                        display.show_tool_call(block.name, str(block.input)[:100])

        elif isinstance(message, AgentResult):
            if message.cost_usd:
                tracker.total_cost_usd += message.cost_usd
            if message.num_turns:
                tracker.total_turns += message.num_turns

            if budget is not None:
                status = budget.add_cost(message.cost_usd)
                if status == BudgetStatus.WARNING and not budget.warning_already_shown:
                    budget.mark_warning_shown()
                    display.show_budget_warning(budget)
                elif status == BudgetStatus.EXCEEDED:
                    display.show_budget_exceeded(budget)

            if message.result:
                if not branch_id:
                    display.show_result(message.result)

    return extract_iteration_results(config, tracker, branch_id, on_event)


# ---------------------------------------------------------------------------
# Branch runner
# ---------------------------------------------------------------------------

async def run_branch(
    config: ClawConfig,
    registry: ProviderRegistry,
    budget: BudgetTracker,
    branch_id: str | None = None,
    approach_hint: str | None = None,
    max_iterations: int | None = None,
    stop_event: anyio.abc.Event | None = None,
    on_event: Callable[[BranchEvent], None] | None = None,
) -> BranchResult:
    """Run the full iteration loop for a single branch."""
    tracker = UsageTracker()
    effective_max = max_iterations or config.max_iterations

    tracker.current_idea = IdeaRecord(
        title=config.goal[:40],
        description=config.goal,
        relationship="origin",
        branch="main",
        worktree_path=str(Path(config.project_dir).resolve()),
    )

    current_project_dir = config.project_dir
    tools_server = create_iclaw_tools(config)
    Path(current_project_dir).mkdir(parents=True, exist_ok=True)

    interrupted = False
    consecutive_errors = 0
    stop_reason = "max_iterations"

    def handle_interrupt(sig, frame):
        nonlocal interrupted
        interrupted = True

    prev_handler = prev_term = None
    if branch_id is None:
        prev_handler = signal.signal(signal.SIGINT, handle_interrupt)
        prev_term = signal.signal(signal.SIGTERM, handle_interrupt)

    try:
        for iteration in range(1, effective_max + 1):
            if interrupted:
                stop_reason = "interrupted"
                if not branch_id:
                    display.show_interrupted()
                break
            if stop_event is not None and stop_event.is_set():
                stop_reason = "interrupted"
                break

            tracker.iterations_completed = iteration

            if branch_id and on_event:
                on_event(BranchEvent(branch_id, "iteration_start", {"iteration": iteration}))
            else:
                display.show_iteration_header(iteration, tracker)

            prompt = build_iteration_prompt(
                config, iteration, tracker, approach_hint=approach_hint,
            )

            try:
                result = await _run_single_iteration(
                    prompt, config, tracker, registry, tools_server,
                    current_project_dir, config.verbose, budget,
                    branch_id=branch_id, on_event=on_event,
                )
                consecutive_errors = 0
            except KeyboardInterrupt:
                stop_reason = "interrupted"
                if not branch_id:
                    display.show_interrupted()
                break
            except BackendNotFoundError:
                stop_reason = "error"
                if not branch_id:
                    display.show_error(
                        iteration,
                        Exception("Claude Code CLI not found. Install it: "
                                  "npm install -g @anthropic-ai/claude-code"),
                    )
                break
            except BackendRateLimitError:
                new_provider = registry.handle_rate_limit()
                if new_provider and new_provider.status == ProviderStatus.CONNECTED:
                    if not branch_id:
                        display.show_error(iteration, Exception(
                            f"Rate limited. Cycling to {new_provider.display_name}..."
                        ))
                    continue
                else:
                    stop_reason = "error"
                    if not branch_id:
                        display.show_error(iteration, Exception("All providers exhausted."))
                    break
            except (BackendProcessError, Exception) as e:
                consecutive_errors += 1
                tracker.errors.append(f"Iteration {iteration}: {e}")
                if branch_id and on_event:
                    on_event(BranchEvent(branch_id, "error", {"message": str(e)}))
                else:
                    display.show_error(iteration, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    stop_reason = "error"
                    break
                continue

            if budget.check() == BudgetStatus.EXCEEDED:
                stop_reason = "budget"
                break

            # Idea transition (single-branch mode only)
            if branch_id is None and result.idea_proposed:
                proposal = read_idea_proposal(current_project_dir)
                if proposal:
                    finalize_idea(config, tracker)
                    new_dir = transition_to_idea(config, tracker, proposal)
                    if new_dir:
                        current_project_dir = new_dir
                        config.project_dir = new_dir
                        tools_server = create_iclaw_tools(config)
                        continue

            if result.should_stop and not result.idea_proposed:
                if branch_id is None:
                    result.should_stop = False
                    tracker._pending_idea_prompt = True  # type: ignore[attr-defined]
                else:
                    stop_reason = "quality_reached"
                    break

    finally:
        if prev_handler is not None:
            signal.signal(signal.SIGINT, prev_handler)
        if prev_term is not None:
            signal.signal(signal.SIGTERM, prev_term)

    if branch_id is None and tracker.current_idea:
        commit_idea(
            current_project_dir,
            f"idea/{tracker.current_idea.title}: session end "
            f"(score {tracker.last_quality_score or '?'}/10)",
        )

    if branch_id and on_event:
        on_event(BranchEvent(branch_id, "done", {"reason": stop_reason}))

    return BranchResult(
        branch_id=branch_id or "main",
        tracker=tracker,
        project_dir=current_project_dir,
        final_score=tracker.last_quality_score,
        iterations_completed=tracker.iterations_completed,
        features=list(tracker.features_completed),
        cost_usd=tracker.total_cost_usd,
        stop_reason=stop_reason,
    )

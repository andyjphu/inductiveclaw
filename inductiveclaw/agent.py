"""The outer autonomous loop with idea-phase management via git worktrees."""

from __future__ import annotations

import json
import re
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import display
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
class IterationResult:
    should_stop: bool = False
    features_completed: list[str] = field(default_factory=list)
    quality_score: int | None = None
    idea_proposed: bool = False


# --- Git worktree management ---

def _git(*args: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _ensure_git_repo(project_dir: str) -> bool:
    """Initialize a git repo in project_dir if one doesn't exist. Returns True if ready."""
    p = Path(project_dir)
    if (p / ".git").exists():
        return True
    result = _git("rev-parse", "--git-dir", cwd=project_dir)
    if result.returncode == 0:
        return True
    result = _git("init", cwd=project_dir)
    if result.returncode != 0:
        return False
    _git("add", "-A", cwd=project_dir)
    _git("commit", "-m", "initial (iclaw)", "--allow-empty", cwd=project_dir)
    return True


def _create_worktree(base_dir: str, branch_name: str, worktree_name: str) -> str | None:
    """Create a git worktree as a sibling of base_dir. Returns the worktree path or None."""
    base = Path(base_dir)
    worktree_path = base.parent / worktree_name
    if worktree_path.exists():
        return str(worktree_path)

    result = _git(
        "worktree", "add", str(worktree_path), "-b", branch_name,
        cwd=base_dir,
    )
    if result.returncode != 0:
        display.show_error(0, Exception(f"Failed to create worktree: {result.stderr.strip()}"))
        return None

    return str(worktree_path)


def _commit_idea(project_dir: str, message: str) -> None:
    """Commit current state in the worktree."""
    _git("add", "-A", cwd=project_dir)
    _git("commit", "-m", message, "--allow-empty", cwd=project_dir)


# --- Single iteration ---

async def _run_single_iteration(
    prompt: str,
    config: ClawConfig,
    tracker: UsageTracker,
    registry: ProviderRegistry,
    tools_server: object,
    project_dir: str,
    verbose: bool,
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
                    display.show_tool_call(block.name, str(block.input)[:100])

        elif isinstance(message, AgentResult):
            if message.result:
                display.show_result(message.result)

    return _extract_iteration_results(config, tracker)


def _extract_iteration_results(config: ClawConfig, tracker: UsageTracker) -> IterationResult:
    """Read project files to determine what happened in this iteration."""
    result = IterationResult()
    project = Path(config.project_dir)

    # Parse latest evaluation
    eval_path = project / "EVALUATIONS.md"
    if eval_path.exists():
        content = eval_path.read_text()
        scores = re.findall(r"\*\*Overall\*\*\s*\|\s*\*\*(\d+)/10\*\*", content)
        if scores:
            score = int(scores[-1])
            tracker.last_quality_score = score
            tracker.quality_history.append(score)
            result.quality_score = score
            if score >= config.quality_threshold:
                ship_matches = re.findall(r"\*\*Ready to ship:\*\*\s*(Yes|No)", content)
                if ship_matches and ship_matches[-1] == "Yes":
                    result.should_stop = True

    # Parse completed items from backlog
    backlog_path = project / "BACKLOG.md"
    if backlog_path.exists():
        content = backlog_path.read_text()
        completed = re.findall(r"\*\*Completed:\*\*\s*(.+)", content)
        for item in completed:
            item = item.strip()
            if item and item not in tracker.features_completed:
                tracker.features_completed.append(item)
                display.show_feature_completed(item)

    # Check for idea proposal
    proposal_path = project / ".iclaw" / "idea_proposal.json"
    if proposal_path.exists():
        result.idea_proposed = True

    return result


# --- Idea transition ---

def _read_idea_proposal(project_dir: str) -> dict | None:
    """Read and consume an idea proposal from the project."""
    proposal_path = Path(project_dir) / ".iclaw" / "idea_proposal.json"
    if not proposal_path.exists():
        return None
    try:
        proposal = json.loads(proposal_path.read_text())
        proposal_path.unlink()
        return proposal
    except (json.JSONDecodeError, OSError):
        return None


def _finalize_idea(config: ClawConfig, tracker: UsageTracker) -> None:
    """Commit and record the current idea before transitioning."""
    idea = tracker.current_idea
    if idea is None:
        return

    idea.final_score = tracker.last_quality_score
    idea.features = list(tracker.features_completed)
    idea.iterations = tracker.iterations_completed

    _commit_idea(
        config.project_dir,
        f"idea/{idea.title}: final (score {idea.final_score or '?'}/10, "
        f"{len(idea.features)} features, {idea.iterations} iterations)",
    )

    tracker.idea_history.append(idea)


def _transition_to_idea(
    config: ClawConfig,
    tracker: UsageTracker,
    proposal: dict,
) -> str | None:
    """Create a new worktree for the proposed idea. Returns the new project_dir or None."""
    idea_num = tracker.idea_number + 1
    title = proposal.get("title", f"idea-{idea_num}")
    safe_title = re.sub(r'[^\w\-]', '-', title.lower())
    branch_name = f"idea/{idea_num}-{safe_title}"
    worktree_name = f"{Path(config.project_dir).name}-{safe_title}"

    if not _ensure_git_repo(config.project_dir):
        display.show_error(0, Exception("Cannot create worktree: git init failed"))
        return None

    _commit_idea(config.project_dir, f"pre-transition to {title}")

    new_dir = _create_worktree(config.project_dir, branch_name, worktree_name)
    if new_dir is None:
        return None

    tracker.idea_number = idea_num
    tracker.current_idea = IdeaRecord(
        title=title,
        description=proposal.get("description", ""),
        relationship=proposal.get("relationship", "extension"),
        branch=branch_name,
        worktree_path=new_dir,
    )

    tracker.features_completed = []
    tracker.last_quality_score = None
    tracker.quality_history = []
    tracker.errors = []
    tracker.iterations_completed = 0

    display.show_idea_transition(tracker.current_idea, tracker.idea_history)

    return new_dir


def _build_idea_history_text(tracker: UsageTracker) -> str:
    """Format idea history for prompt injection."""
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


# --- Main loop ---

async def run(config: ClawConfig, registry: ProviderRegistry) -> None:
    """Main autonomous loop with idea-phase transitions."""
    tracker = UsageTracker()

    tracker.current_idea = IdeaRecord(
        title=config.goal[:40],
        description=config.goal,
        relationship="origin",
        branch="main",
        worktree_path=str(Path(config.project_dir).resolve()),
    )

    current_project_dir = config.project_dir
    tools_server = create_iclaw_tools(config)

    display.show_banner(config, registry)
    Path(current_project_dir).mkdir(parents=True, exist_ok=True)

    interrupted = False
    consecutive_errors = 0
    total_iterations = 0

    def handle_interrupt(sig, frame):
        nonlocal interrupted
        interrupted = True

    prev_handler = signal.signal(signal.SIGINT, handle_interrupt)
    prev_term = signal.signal(signal.SIGTERM, handle_interrupt)

    try:
        for iteration in range(1, config.max_iterations + 1):
            if interrupted:
                display.show_interrupted()
                break

            total_iterations += 1
            display.show_iteration_header(iteration, tracker)

            prompt = build_iteration_prompt(config, iteration, tracker)

            try:
                result = await _run_single_iteration(
                    prompt, config, tracker, registry, tools_server,
                    current_project_dir, config.verbose,
                )
                consecutive_errors = 0
            except KeyboardInterrupt:
                display.show_interrupted()
                break
            except BackendNotFoundError:
                display.show_error(
                    iteration,
                    Exception("Claude Code CLI not found. Install it: "
                              "npm install -g @anthropic-ai/claude-code"),
                )
                break
            except BackendRateLimitError:
                new_provider = registry.handle_rate_limit()
                if new_provider and new_provider.status == ProviderStatus.CONNECTED:
                    display.show_error(iteration, Exception(
                        f"Rate limited. Cycling to {new_provider.display_name}..."
                    ))
                    continue
                else:
                    display.show_error(iteration, Exception("All providers exhausted."))
                    break
            except (BackendProcessError, Exception) as e:
                consecutive_errors += 1
                tracker.errors.append(f"Iteration {iteration}: {e}")
                display.show_error(iteration, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    display.show_error(iteration, Exception(
                        f"{MAX_CONSECUTIVE_ERRORS} consecutive errors, stopping."
                    ))
                    break
                continue

            tracker.iterations_completed = iteration

            # --- Idea transition check ---
            if result.idea_proposed:
                proposal = _read_idea_proposal(current_project_dir)
                if proposal:
                    _finalize_idea(config, tracker)
                    new_dir = _transition_to_idea(config, tracker, proposal)
                    if new_dir:
                        current_project_dir = new_dir
                        config.project_dir = new_dir
                        tools_server = create_iclaw_tools(config)
                        continue

            if result.should_stop and not result.idea_proposed:
                result.should_stop = False
                tracker._pending_idea_prompt = True  # type: ignore[attr-defined]

    finally:
        signal.signal(signal.SIGINT, prev_handler)
        signal.signal(signal.SIGTERM, prev_term)

    if tracker.current_idea:
        _commit_idea(
            current_project_dir,
            f"idea/{tracker.current_idea.title}: session end "
            f"(score {tracker.last_quality_score or '?'}/10)",
        )

    display.show_summary(tracker)

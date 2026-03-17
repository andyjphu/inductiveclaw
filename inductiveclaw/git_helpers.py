"""Git worktree management, idea transitions, and project file parsing."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import display
from .config import ClawConfig, IdeaRecord, UsageTracker


# ---------------------------------------------------------------------------
# Low-level git operations
# ---------------------------------------------------------------------------

def git(*args: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


def ensure_git_repo(project_dir: str) -> bool:
    """Initialize a git repo in *project_dir* if one doesn't exist."""
    p = Path(project_dir)
    if (p / ".git").exists():
        return True
    result = git("rev-parse", "--git-dir", cwd=project_dir)
    if result.returncode == 0:
        return True
    result = git("init", cwd=project_dir)
    if result.returncode != 0:
        return False
    git("add", "-A", cwd=project_dir)
    git("commit", "-m", "initial (iclaw)", "--allow-empty", cwd=project_dir)
    return True


def create_worktree(base_dir: str, branch_name: str, worktree_name: str) -> str | None:
    """Create a git worktree as a sibling of *base_dir*."""
    base = Path(base_dir)
    worktree_path = base.parent / worktree_name
    if worktree_path.exists():
        return str(worktree_path)
    result = git(
        "worktree", "add", str(worktree_path), "-b", branch_name,
        cwd=base_dir,
    )
    if result.returncode != 0:
        display.show_error(0, Exception(f"Failed to create worktree: {result.stderr.strip()}"))
        return None
    return str(worktree_path)


def commit_idea(project_dir: str, message: str) -> None:
    """Commit current state in the worktree."""
    git("add", "-A", cwd=project_dir)
    git("commit", "-m", message, "--allow-empty", cwd=project_dir)


# ---------------------------------------------------------------------------
# Idea transition
# ---------------------------------------------------------------------------

def read_idea_proposal(project_dir: str) -> dict | None:
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


def finalize_idea(config: ClawConfig, tracker: UsageTracker) -> None:
    """Commit and record the current idea before transitioning."""
    idea = tracker.current_idea
    if idea is None:
        return
    idea.final_score = tracker.last_quality_score
    idea.features = list(tracker.features_completed)
    idea.iterations = tracker.iterations_completed
    commit_idea(
        config.project_dir,
        f"idea/{idea.title}: final (score {idea.final_score or '?'}/10, "
        f"{len(idea.features)} features, {idea.iterations} iterations)",
    )
    tracker.idea_history.append(idea)


def transition_to_idea(
    config: ClawConfig,
    tracker: UsageTracker,
    proposal: dict,
) -> str | None:
    """Create a new worktree for the proposed idea."""
    idea_num = tracker.idea_number + 1
    title = proposal.get("title", f"idea-{idea_num}")
    safe_title = re.sub(r'[^\w\-]', '-', title.lower())
    branch_name = f"idea/{idea_num}-{safe_title}"
    worktree_name = f"{Path(config.project_dir).name}-{safe_title}"

    if not ensure_git_repo(config.project_dir):
        display.show_error(0, Exception("Cannot create worktree: git init failed"))
        return None

    commit_idea(config.project_dir, f"pre-transition to {title}")

    new_dir = create_worktree(config.project_dir, branch_name, worktree_name)
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


# ---------------------------------------------------------------------------
# Iteration result extraction (reads project files after each iteration)
# ---------------------------------------------------------------------------

@dataclass
class IterationResult:
    should_stop: bool = False
    features_completed: list[str] = field(default_factory=list)
    quality_score: int | None = None
    idea_proposed: bool = False


def extract_iteration_results(
    config: ClawConfig,
    tracker: UsageTracker,
    branch_id: str | None = None,
    on_event: Callable | None = None,
) -> IterationResult:
    """Read project files to determine what happened in this iteration."""
    result = IterationResult()
    project = Path(config.project_dir)

    eval_path = project / "EVALUATIONS.md"
    if eval_path.exists():
        content = eval_path.read_text()
        scores = re.findall(r"\*\*Overall\*\*\s*\|\s*\*\*(\d+)/10\*\*", content)
        if scores:
            score = int(scores[-1])
            tracker.last_quality_score = score
            tracker.quality_history.append(score)
            result.quality_score = score
            if branch_id and on_event:
                from .agent_worker import BranchEvent
                on_event(BranchEvent(branch_id, "score", {"score": score}))
            if score >= config.quality_threshold:
                ship_matches = re.findall(r"\*\*Ready to ship:\*\*\s*(Yes|No)", content)
                if ship_matches and ship_matches[-1] == "Yes":
                    result.should_stop = True

    backlog_path = project / "BACKLOG.md"
    if backlog_path.exists():
        content = backlog_path.read_text()
        completed = re.findall(r"\*\*Completed:\*\*\s*(.+)", content)
        for item in completed:
            item = item.strip()
            if item and item not in tracker.features_completed:
                tracker.features_completed.append(item)
                if branch_id and on_event:
                    from .agent_worker import BranchEvent
                    on_event(BranchEvent(branch_id, "feature", {"name": item}))
                else:
                    display.show_feature_completed(item)

    proposal_path = project / ".iclaw" / "idea_proposal.json"
    if proposal_path.exists():
        result.idea_proposed = True

    return result

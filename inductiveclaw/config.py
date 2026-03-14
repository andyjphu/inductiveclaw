"""Configuration dataclass and usage tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ClawConfig:
    project_dir: str = "./project"
    goal: str = ""
    model: str | None = None
    max_iterations: int = 100
    quality_threshold: int = 8
    max_turns_per_iteration: int = 30
    auto_screenshot: bool = True
    screenshot_port: int = 3000
    dev_server_cmd: str | None = None
    verbose: bool = True
    eval_frequency: int = 3
    budget_usd: float | None = None
    num_branches: int = 1
    round_length: int | None = None  # defaults to eval_frequency at runtime


@dataclass
class IdeaRecord:
    """A completed idea phase."""
    title: str
    description: str
    relationship: str  # "origin", "companion", "rewrite", "extension", etc.
    branch: str
    worktree_path: str
    final_score: int | None = None
    features: list[str] = field(default_factory=list)
    iterations: int = 0


@dataclass
class UsageTracker:
    iterations_completed: int = 0
    features_completed: list[str] = field(default_factory=list)
    last_quality_score: int | None = None
    quality_history: list[int] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    errors: list[str] = field(default_factory=list)

    # Cost tracking
    total_cost_usd: float = 0.0
    total_turns: int = 0

    # Idea phase tracking
    current_idea: IdeaRecord | None = None
    idea_history: list[IdeaRecord] = field(default_factory=list)
    idea_number: int = 1

    @property
    def duration_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def duration_display(self) -> str:
        secs = int(self.duration_seconds)
        if secs < 60:
            return f"{secs}s"
        mins, secs = divmod(secs, 60)
        if mins < 60:
            return f"{mins}m {secs}s"
        hours, mins = divmod(mins, 60)
        return f"{hours}h {mins}m"

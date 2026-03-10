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


@dataclass
class UsageTracker:
    iterations_completed: int = 0
    features_completed: list[str] = field(default_factory=list)
    last_quality_score: int | None = None
    quality_history: list[int] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    errors: list[str] = field(default_factory=list)

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

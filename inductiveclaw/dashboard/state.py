"""Dashboard state — aggregated snapshot for the frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..agent_worker import BranchEvent
    from ..config import ClawConfig


@dataclass
class BranchState:
    """Live state of a single branch."""
    branch_id: str
    iteration: int = 0
    score: int | None = None
    score_history: list[int] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    status: str = "running"  # running, paused, done
    last_tool: str | None = None
    last_text: str | None = None
    errors: list[str] = field(default_factory=list)
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "iteration": self.iteration,
            "score": self.score,
            "score_history": list(self.score_history),
            "features": list(self.features),
            "cost_usd": self.cost_usd,
            "status": self.status,
            "last_tool": self.last_tool,
            "last_text": self.last_text,
            "errors": list(self.errors[-10:]),  # last 10
            "stop_reason": self.stop_reason,
        }


@dataclass
class DashboardState:
    """Full dashboard state — serialized as snapshot for new WS clients."""
    goal: str = ""
    mode: str = "single"  # single, tournament
    threshold: int = 8
    max_iterations: int = 100
    budget_usd: float | None = None
    branches: dict[str, BranchState] = field(default_factory=dict)
    rounds: list[dict[str, Any]] = field(default_factory=list)
    total_cost_usd: float = 0.0
    budget_fraction: float | None = None
    budget_status: str = "ok"  # ok, warning, exceeded
    paused: bool = False
    browser_eval: dict[str, Any] | None = None
    activity_log: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: ClawConfig) -> DashboardState:
        mode = "tournament" if config.num_branches > 1 else "single"
        return cls(
            goal=config.goal,
            mode=mode,
            threshold=config.quality_threshold,
            max_iterations=config.max_iterations,
            budget_usd=config.budget_usd,
        )

    def _ensure_branch(self, branch_id: str) -> BranchState:
        if branch_id not in self.branches:
            self.branches[branch_id] = BranchState(branch_id=branch_id)
        return self.branches[branch_id]

    def update(self, event: BranchEvent) -> None:
        """Mutate state from a BranchEvent."""
        branch = self._ensure_branch(event.branch_id)
        et = event.event_type
        data = event.data

        if et == "iteration_start":
            branch.iteration = data.get("iteration", branch.iteration)
            branch.status = "running"

        elif et == "tool_call":
            branch.last_tool = data.get("name")

        elif et == "text_preview":
            text = data.get("text", "")
            branch.last_text = text[:200] if text else None

        elif et == "feature":
            name = data.get("name", "")
            if name and name not in branch.features:
                branch.features.append(name)

        elif et == "score":
            score = data.get("score")
            if isinstance(score, int):
                branch.score = score
                branch.score_history.append(score)

        elif et == "error":
            msg = data.get("message", "unknown error")
            branch.errors.append(msg[:200])

        elif et == "done":
            branch.status = "done"
            branch.stop_reason = data.get("reason")

        elif et == "budget":
            self.total_cost_usd = data.get("spent", self.total_cost_usd)
            self.budget_fraction = data.get("fraction")
            self.budget_status = data.get("status", "ok")

        elif et == "browser_eval":
            self.browser_eval = data

        # Append to activity log (keep last 200)
        log_entry = {
            "branch_id": event.branch_id,
            "event": et,
            **data,
        }
        self.activity_log.append(log_entry)
        if len(self.activity_log) > 200:
            self.activity_log = self.activity_log[-200:]

        # Recompute total cost
        self.total_cost_usd = sum(b.cost_usd for b in self.branches.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "mode": self.mode,
            "threshold": self.threshold,
            "max_iterations": self.max_iterations,
            "budget_usd": self.budget_usd,
            "branches": {bid: b.to_dict() for bid, b in self.branches.items()},
            "rounds": list(self.rounds),
            "total_cost_usd": self.total_cost_usd,
            "budget_fraction": self.budget_fraction,
            "budget_status": self.budget_status,
            "paused": self.paused,
            "browser_eval": self.browser_eval,
            "activity_log": self.activity_log[-50:],  # last 50 for snapshot
        }

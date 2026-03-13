"""Cost budget tracking and enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class BudgetStatus(Enum):
    """Result of a budget check."""

    OK = auto()
    WARNING = auto()       # >= 80% of budget
    EXCEEDED = auto()      # >= 100% of budget
    NO_BUDGET = auto()     # No budget set


@dataclass
class BudgetTracker:
    """Tracks spending against an optional USD budget.

    Usage:
        budget = BudgetTracker(budget_usd=5.0)
        status = budget.add_cost(0.50)
        if status == BudgetStatus.WARNING:
            ...  # approaching limit
        elif status == BudgetStatus.EXCEEDED:
            ...  # over limit, stop
    """

    budget_usd: float | None = None
    total_spent_usd: float = 0.0
    _warning_shown: bool = False

    WARNING_THRESHOLD: float = 0.80
    STOP_THRESHOLD: float = 1.00

    def add_cost(self, cost: float | None) -> BudgetStatus:
        """Record a cost increment and return the current budget status."""
        if cost is not None and cost > 0:
            self.total_spent_usd += cost
        return self.check()

    def check(self) -> BudgetStatus:
        """Check current spending against the budget."""
        if self.budget_usd is None:
            return BudgetStatus.NO_BUDGET
        if self.total_spent_usd >= self.budget_usd * self.STOP_THRESHOLD:
            return BudgetStatus.EXCEEDED
        if self.total_spent_usd >= self.budget_usd * self.WARNING_THRESHOLD:
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    @property
    def remaining_usd(self) -> float | None:
        """Remaining budget in USD, or None if no budget set."""
        if self.budget_usd is None:
            return None
        return max(0.0, self.budget_usd - self.total_spent_usd)

    @property
    def usage_fraction(self) -> float | None:
        """Fraction of budget used (0.0 to 1.0+), or None if no budget."""
        if self.budget_usd is None or self.budget_usd == 0:
            return None
        return self.total_spent_usd / self.budget_usd

    @property
    def usage_percent(self) -> int | None:
        """Percentage of budget used (0 to 100+), or None if no budget."""
        frac = self.usage_fraction
        if frac is None:
            return None
        return int(frac * 100)

    def format_status(self) -> str:
        """Format a short status string like '$1.23/$5.00 (25%)'."""
        if self.budget_usd is None:
            return f"${self.total_spent_usd:.4f}"
        pct = self.usage_percent or 0
        return f"${self.total_spent_usd:.4f}/${self.budget_usd:.2f} ({pct}%)"

    @property
    def warning_already_shown(self) -> bool:
        return self._warning_shown

    def mark_warning_shown(self) -> None:
        self._warning_shown = True

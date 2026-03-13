"""Tests for cost budgeting — BudgetTracker lifecycle, thresholds, and formatting."""

from __future__ import annotations

import pytest

from inductiveclaw.budget import BudgetStatus, BudgetTracker


# --- No budget set ---


class TestBudgetTrackerNoBudget:
    def test_check_returns_no_budget(self):
        bt = BudgetTracker()
        assert bt.check() == BudgetStatus.NO_BUDGET

    def test_add_cost_returns_no_budget(self):
        bt = BudgetTracker()
        assert bt.add_cost(1.50) == BudgetStatus.NO_BUDGET

    def test_remaining_usd_is_none(self):
        assert BudgetTracker().remaining_usd is None

    def test_usage_fraction_is_none(self):
        assert BudgetTracker().usage_fraction is None

    def test_usage_percent_is_none(self):
        assert BudgetTracker().usage_percent is None

    def test_format_status_shows_spent_only(self):
        bt = BudgetTracker(total_spent_usd=1.2345)
        assert bt.format_status() == "$1.2345"


# --- Under budget (OK) ---


class TestBudgetTrackerOK:
    def test_under_budget_returns_ok(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert bt.add_cost(1.0) == BudgetStatus.OK

    def test_zero_cost_returns_ok(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert bt.add_cost(0.0) == BudgetStatus.OK

    def test_none_cost_returns_ok(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert bt.add_cost(None) == BudgetStatus.OK

    def test_remaining_usd(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=3.0)
        assert bt.remaining_usd == 7.0

    def test_usage_fraction(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=2.5)
        assert bt.usage_fraction == 0.25

    def test_usage_percent(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=2.5)
        assert bt.usage_percent == 25


# --- Warning threshold (80%) ---


class TestBudgetTrackerWarning:
    def test_at_80_percent(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert bt.add_cost(8.0) == BudgetStatus.WARNING

    def test_exactly_80_percent(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=8.0)
        assert bt.check() == BudgetStatus.WARNING

    def test_at_90_percent(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=9.0)
        assert bt.check() == BudgetStatus.WARNING

    def test_just_below_80_percent_is_ok(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=7.99)
        assert bt.check() == BudgetStatus.OK

    def test_warning_shown_tracking(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert not bt.warning_already_shown
        bt.mark_warning_shown()
        assert bt.warning_already_shown


# --- Exceeded threshold (100%) ---


class TestBudgetTrackerExceeded:
    def test_at_100_percent(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert bt.add_cost(10.0) == BudgetStatus.EXCEEDED

    def test_over_100_percent(self):
        bt = BudgetTracker(budget_usd=10.0)
        bt.add_cost(5.0)
        assert bt.add_cost(6.0) == BudgetStatus.EXCEEDED

    def test_remaining_usd_clamps_to_zero(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=12.0)
        assert bt.remaining_usd == 0.0

    def test_usage_percent_over_100(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=15.0)
        assert bt.usage_percent == 150


# --- Accumulation ---


class TestBudgetTrackerAccumulation:
    def test_multiple_add_cost(self):
        bt = BudgetTracker(budget_usd=10.0)
        bt.add_cost(2.0)
        bt.add_cost(3.0)
        bt.add_cost(1.5)
        assert bt.total_spent_usd == 6.5

    def test_negative_cost_ignored(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=5.0)
        bt.add_cost(-1.0)
        assert bt.total_spent_usd == 5.0

    def test_none_cost_no_change(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=5.0)
        bt.add_cost(None)
        assert bt.total_spent_usd == 5.0

    def test_transition_ok_to_warning_to_exceeded(self):
        bt = BudgetTracker(budget_usd=10.0)
        assert bt.add_cost(5.0) == BudgetStatus.OK
        assert bt.add_cost(3.5) == BudgetStatus.WARNING
        assert bt.add_cost(2.0) == BudgetStatus.EXCEEDED


# --- Format ---


class TestBudgetTrackerFormatStatus:
    def test_with_budget(self):
        bt = BudgetTracker(budget_usd=5.0, total_spent_usd=1.2345)
        s = bt.format_status()
        assert "$1.2345/$5.00" in s
        assert "24%" in s

    def test_without_budget(self):
        bt = BudgetTracker(total_spent_usd=1.2345)
        s = bt.format_status()
        assert "$1.2345" in s
        assert "/" not in s

    def test_zero_spent(self):
        bt = BudgetTracker(budget_usd=5.0)
        s = bt.format_status()
        assert "$0.0000/$5.00 (0%)" == s


# --- Session resume ---


class TestBudgetTrackerResume:
    def test_resume_under_budget(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=7.0)
        assert bt.check() == BudgetStatus.OK

    def test_resume_at_warning(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=8.5)
        assert bt.check() == BudgetStatus.WARNING

    def test_resume_already_exceeded(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=11.0)
        assert bt.check() == BudgetStatus.EXCEEDED

    def test_resume_then_add_cost(self):
        bt = BudgetTracker(budget_usd=10.0, total_spent_usd=7.0)
        assert bt.add_cost(0.5) == BudgetStatus.OK
        assert bt.total_spent_usd == 7.5
        assert bt.add_cost(1.0) == BudgetStatus.WARNING
        assert bt.total_spent_usd == 8.5


# --- Edge cases ---


class TestBudgetTrackerEdgeCases:
    def test_zero_budget(self):
        bt = BudgetTracker(budget_usd=0.0)
        assert bt.usage_fraction is None
        # Any spend exceeds a zero budget
        assert bt.add_cost(0.01) == BudgetStatus.EXCEEDED

    def test_very_small_budget(self):
        bt = BudgetTracker(budget_usd=0.001)
        assert bt.add_cost(0.0005) == BudgetStatus.OK
        assert bt.add_cost(0.0004) == BudgetStatus.WARNING

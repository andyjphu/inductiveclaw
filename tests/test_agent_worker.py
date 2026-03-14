"""Tests for agent_worker — extracted iteration logic and run_branch."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from inductiveclaw.agent_worker import (
    AUTONOMOUS_TOOLS,
    BranchEvent,
    BranchResult,
    MAX_CONSECUTIVE_ERRORS,
)
from inductiveclaw.config import ClawConfig, IdeaRecord, UsageTracker
from inductiveclaw.git_helpers import IterationResult, extract_iteration_results as _extract_iteration_results


# --- Constants ---


class TestConstants:
    def test_max_consecutive_errors_is_positive(self):
        assert MAX_CONSECUTIVE_ERRORS > 0

    def test_autonomous_tools_includes_bash(self):
        assert "Bash" in AUTONOMOUS_TOOLS

    def test_autonomous_tools_includes_custom_mcp(self):
        assert any("iclaw-tools" in t for t in AUTONOMOUS_TOOLS)

    def test_autonomous_tools_includes_self_evaluate(self):
        assert "mcp__iclaw-tools__self_evaluate" in AUTONOMOUS_TOOLS


# --- Dataclasses ---


class TestIterationResult:
    def test_defaults(self):
        r = IterationResult()
        assert r.should_stop is False
        assert r.features_completed == []
        assert r.quality_score is None
        assert r.idea_proposed is False

    def test_fields(self):
        r = IterationResult(should_stop=True, quality_score=8, idea_proposed=True)
        assert r.should_stop
        assert r.quality_score == 8
        assert r.idea_proposed


class TestBranchEvent:
    def test_creation(self):
        e = BranchEvent(branch_id="A", event_type="score", data={"score": 7})
        assert e.branch_id == "A"
        assert e.event_type == "score"
        assert e.data["score"] == 7

    def test_default_data(self):
        e = BranchEvent(branch_id="B", event_type="done")
        assert e.data == {}


class TestBranchResult:
    def test_creation(self):
        tracker = UsageTracker()
        r = BranchResult(
            branch_id="A",
            tracker=tracker,
            project_dir="/tmp/test",
            final_score=7,
            iterations_completed=3,
            features=["auth", "db"],
            cost_usd=1.23,
            stop_reason="quality_reached",
        )
        assert r.branch_id == "A"
        assert r.final_score == 7
        assert len(r.features) == 2
        assert r.stop_reason == "quality_reached"


# --- Extract iteration results ---


class TestExtractIterationResults:
    def test_no_project_files(self, tmp_path):
        config = ClawConfig(project_dir=str(tmp_path))
        tracker = UsageTracker()
        result = _extract_iteration_results(config, tracker)
        assert result.quality_score is None
        assert result.should_stop is False
        assert not result.idea_proposed

    def test_parses_evaluation_score(self, tmp_path):
        eval_file = tmp_path / "EVALUATIONS.md"
        eval_file.write_text(textwrap.dedent("""\
            | Dimension | Score |
            |---|---|
            | **Overall** | **7/10** |
        """))
        config = ClawConfig(project_dir=str(tmp_path), quality_threshold=8)
        tracker = UsageTracker()
        result = _extract_iteration_results(config, tracker)
        assert result.quality_score == 7
        assert tracker.last_quality_score == 7
        assert tracker.quality_history == [7]
        assert result.should_stop is False  # 7 < 8

    def test_should_stop_on_threshold(self, tmp_path):
        eval_file = tmp_path / "EVALUATIONS.md"
        eval_file.write_text(textwrap.dedent("""\
            | Dimension | Score |
            |---|---|
            | **Overall** | **9/10** |
            **Ready to ship:** Yes
        """))
        config = ClawConfig(project_dir=str(tmp_path), quality_threshold=8)
        tracker = UsageTracker()
        result = _extract_iteration_results(config, tracker)
        assert result.quality_score == 9
        assert result.should_stop is True

    def test_not_ready_to_ship(self, tmp_path):
        eval_file = tmp_path / "EVALUATIONS.md"
        eval_file.write_text(textwrap.dedent("""\
            | Dimension | Score |
            |---|---|
            | **Overall** | **9/10** |
            **Ready to ship:** No
        """))
        config = ClawConfig(project_dir=str(tmp_path), quality_threshold=8)
        tracker = UsageTracker()
        result = _extract_iteration_results(config, tracker)
        assert result.quality_score == 9
        assert result.should_stop is False

    def test_parses_backlog_features(self, tmp_path):
        backlog_file = tmp_path / "BACKLOG.md"
        backlog_file.write_text(textwrap.dedent("""\
            **Completed:** Auth system
            **Completed:** Database setup
        """))
        config = ClawConfig(project_dir=str(tmp_path))
        tracker = UsageTracker()
        _extract_iteration_results(config, tracker)
        assert "Auth system" in tracker.features_completed
        assert "Database setup" in tracker.features_completed

    def test_no_duplicate_features(self, tmp_path):
        backlog_file = tmp_path / "BACKLOG.md"
        backlog_file.write_text("**Completed:** Auth system\n")
        config = ClawConfig(project_dir=str(tmp_path))
        tracker = UsageTracker()
        tracker.features_completed = ["Auth system"]
        _extract_iteration_results(config, tracker)
        assert tracker.features_completed.count("Auth system") == 1

    def test_detects_idea_proposal(self, tmp_path):
        iclaw_dir = tmp_path / ".iclaw"
        iclaw_dir.mkdir()
        (iclaw_dir / "idea_proposal.json").write_text('{"title":"new"}')
        config = ClawConfig(project_dir=str(tmp_path))
        tracker = UsageTracker()
        result = _extract_iteration_results(config, tracker)
        assert result.idea_proposed is True

    def test_branch_events_emitted(self, tmp_path):
        eval_file = tmp_path / "EVALUATIONS.md"
        eval_file.write_text("| **Overall** | **6/10** |")
        backlog_file = tmp_path / "BACKLOG.md"
        backlog_file.write_text("**Completed:** Feature X\n")

        config = ClawConfig(project_dir=str(tmp_path))
        tracker = UsageTracker()
        events: list[BranchEvent] = []
        _extract_iteration_results(config, tracker, branch_id="A", on_event=events.append)
        types = [e.event_type for e in events]
        assert "score" in types
        assert "feature" in types

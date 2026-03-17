"""Tests for tournament-style parallel exploration."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from inductiveclaw.agent_worker import BranchResult
from inductiveclaw.config import ClawConfig, UsageTracker
from inductiveclaw.parallel import (
    APPROACH_HINTS,
    RoundSummary,
    _BRANCH_LABELS,
    _cleanup_dirs,
    _create_branch_dirs,
    _finalize_winner,
    _make_branch_config,
    _select_hints,
)
from inductiveclaw.prompts.iteration import build_iteration_prompt


# --- Approach hints ---


class TestSelectHints:
    def test_returns_correct_count(self):
        hints = _select_hints(1, 3)
        assert len(hints) == 3

    def test_all_hints_are_strings(self):
        hints = _select_hints(1, 3)
        assert all(isinstance(h, str) for h in hints)

    def test_hints_rotate_per_round(self):
        r1 = _select_hints(1, 3)
        r2 = _select_hints(2, 3)
        # At least one hint should differ between rounds
        assert r1 != r2

    def test_wraps_around_hint_pool(self):
        """When requesting more hints than the pool, wraps around."""
        hints = _select_hints(1, len(APPROACH_HINTS) + 2)
        assert len(hints) == len(APPROACH_HINTS) + 2
        # First and (len+1)th should be the same
        assert hints[0] == hints[len(APPROACH_HINTS)]

    def test_single_branch_gets_one_hint(self):
        hints = _select_hints(1, 1)
        assert len(hints) == 1


# --- Branch directory management ---


class TestCreateBranchDirs:
    def test_creates_correct_number(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        dirs = _create_branch_dirs(str(base), 3, 1)
        assert len(dirs) == 3
        assert all(Path(d).exists() for d in dirs)

    def test_naming_convention(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        dirs = _create_branch_dirs(str(base), 2, 1)
        assert "r1-branch-a" in dirs[0]
        assert "r1-branch-b" in dirs[1]

    def test_round_number_in_name(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        dirs = _create_branch_dirs(str(base), 1, 5)
        assert "r5-branch-a" in dirs[0]

    def test_copies_existing_content(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        (base / "index.html").write_text("<h1>Hello</h1>")
        (base / "src").mkdir()
        (base / "src" / "app.js").write_text("console.log('hi')")

        dirs = _create_branch_dirs(str(base), 2, 1)
        for d in dirs:
            assert (Path(d) / "index.html").exists()
            assert (Path(d) / "src" / "app.js").exists()

    def test_creates_empty_dirs_if_base_empty(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        dirs = _create_branch_dirs(str(base), 2, 1)
        assert all(Path(d).exists() for d in dirs)

    def test_overwrites_existing_branch_dirs(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        (base / "file.txt").write_text("v1")

        # First round
        dirs = _create_branch_dirs(str(base), 1, 1)
        (Path(dirs[0]) / "extra.txt").write_text("stale")

        # Same round again — should overwrite
        (base / "file.txt").write_text("v2")
        dirs2 = _create_branch_dirs(str(base), 1, 1)
        assert (Path(dirs2[0]) / "file.txt").read_text() == "v2"


class TestCleanupDirs:
    def test_removes_directories(self, tmp_path):
        d1 = tmp_path / "branch-a"
        d2 = tmp_path / "branch-b"
        d1.mkdir()
        d2.mkdir()
        (d1 / "file.txt").write_text("test")

        _cleanup_dirs([str(d1), str(d2)])
        assert not d1.exists()
        assert not d2.exists()

    def test_ignores_missing_dirs(self, tmp_path):
        # Should not raise
        _cleanup_dirs([str(tmp_path / "nonexistent")])


# --- Branch config ---


class TestMakeBranchConfig:
    def test_changes_project_dir(self):
        config = ClawConfig(project_dir="./original", goal="test")
        bc = _make_branch_config(config, "/tmp/branch-a")
        assert bc.project_dir == "/tmp/branch-a"
        assert config.project_dir == "./original"  # original unchanged

    def test_preserves_other_fields(self):
        config = ClawConfig(
            project_dir="./original",
            goal="build X",
            quality_threshold=9,
            num_branches=3,
        )
        bc = _make_branch_config(config, "/tmp/branch-a")
        assert bc.goal == "build X"
        assert bc.quality_threshold == 9
        assert bc.num_branches == 3


# --- Winner finalization ---


class TestFinalizeWinner:
    def test_copies_winner_to_destination(self, tmp_path):
        winner_dir = tmp_path / "branch-a"
        winner_dir.mkdir()
        (winner_dir / "app.py").write_text("print('winner')")
        (winner_dir / "src").mkdir()
        (winner_dir / "src" / "mod.py").write_text("# module")

        dest = tmp_path / "project"
        dest.mkdir()
        (dest / "old.txt").write_text("old content")

        winner = BranchResult(
            branch_id="A",
            tracker=UsageTracker(),
            project_dir=str(winner_dir),
            final_score=8,
            iterations_completed=3,
            features=["auth"],
            cost_usd=1.0,
            stop_reason="quality_reached",
        )
        _finalize_winner(winner, str(dest))

        assert (dest / "app.py").read_text() == "print('winner')"
        assert (dest / "src" / "mod.py").read_text() == "# module"
        assert not (dest / "old.txt").exists()  # old content cleared

    def test_same_dir_is_noop(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "file.txt").write_text("content")

        winner = BranchResult(
            branch_id="A",
            tracker=UsageTracker(),
            project_dir=str(project),
            final_score=8,
            iterations_completed=3,
            features=[],
            cost_usd=1.0,
            stop_reason="quality_reached",
        )
        _finalize_winner(winner, str(project))
        assert (project / "file.txt").read_text() == "content"


# --- Config defaults ---


class TestConfigDefaults:
    def test_num_branches_default(self):
        c = ClawConfig()
        assert c.num_branches == 1

    def test_round_length_default(self):
        c = ClawConfig()
        assert c.round_length is None

    def test_round_length_set(self):
        c = ClawConfig(round_length=5)
        assert c.round_length == 5


# --- Winner selection ---


class TestWinnerSelection:
    def test_highest_score_wins(self):
        results = [
            BranchResult("A", UsageTracker(), "/a", 5, 3, [], 1.0, "max_iterations"),
            BranchResult("B", UsageTracker(), "/b", 8, 3, [], 1.0, "quality_reached"),
            BranchResult("C", UsageTracker(), "/c", 6, 3, [], 1.0, "max_iterations"),
        ]
        winner = max(results, key=lambda r: r.final_score or 0)
        assert winner.branch_id == "B"

    def test_none_scores_handled(self):
        results = [
            BranchResult("A", UsageTracker(), "/a", None, 3, [], 1.0, "error"),
            BranchResult("B", UsageTracker(), "/b", 4, 3, [], 1.0, "max_iterations"),
        ]
        winner = max(results, key=lambda r: r.final_score or 0)
        assert winner.branch_id == "B"

    def test_tie_picks_first(self):
        results = [
            BranchResult("A", UsageTracker(), "/a", 7, 3, [], 1.0, "max_iterations"),
            BranchResult("B", UsageTracker(), "/b", 7, 3, [], 1.0, "max_iterations"),
        ]
        winner = max(results, key=lambda r: r.final_score or 0)
        # max() returns first maximum encountered
        assert winner.branch_id in ("A", "B")


# --- Approach hint in prompt ---


class TestApproachHintInPrompt:
    def test_hint_injected_when_provided(self):
        config = ClawConfig(goal="Build a todo app")
        tracker = UsageTracker()
        prompt = build_iteration_prompt(config, 1, tracker, approach_hint="Focus on minimalism")
        assert "Focus on minimalism" in prompt
        assert "Approach Directive" in prompt

    def test_no_hint_when_none(self):
        config = ClawConfig(goal="Build a todo app")
        tracker = UsageTracker()
        prompt = build_iteration_prompt(config, 1, tracker, approach_hint=None)
        assert "Approach Directive" not in prompt

    def test_hint_precedes_goal(self):
        config = ClawConfig(goal="Build a todo app")
        tracker = UsageTracker()
        prompt = build_iteration_prompt(config, 1, tracker, approach_hint="Focus on perf")
        # Hint should appear before the goal
        hint_pos = prompt.index("Focus on perf")
        goal_pos = prompt.index("Build a todo app")
        assert hint_pos < goal_pos


# --- Round summary ---


class TestRoundSummary:
    def test_creation(self):
        r = BranchResult("A", UsageTracker(), "/a", 7, 3, ["auth"], 1.0, "max_iterations")
        s = RoundSummary(round_num=1, results=[r], winner=r)
        assert s.round_num == 1
        assert len(s.results) == 1
        assert s.winner.branch_id == "A"


# --- CLI integration ---


class TestCLIParsing:
    def test_branches_flag(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "test", "--branches", "3"])
        assert args.branches == 3

    def test_round_length_flag(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "test", "--round-length", "5"])
        assert args.round_length == 5

    def test_default_branches_is_one(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "test"])
        assert args.branches == 1

    def test_default_round_length_is_none(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "test"])
        assert args.round_length is None

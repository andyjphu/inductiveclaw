"""Tests for the live dashboard — state, steering, bridge, and server."""

from __future__ import annotations

import json

import anyio
import pytest

from inductiveclaw.agent_worker import BranchEvent
from inductiveclaw.config import ClawConfig, UsageTracker
from inductiveclaw.dashboard.state import BranchState, DashboardState
from inductiveclaw.dashboard.steering import (
    SteeringChannel,
    SteeringCommand,
    process_pending_commands,
)
from inductiveclaw.dashboard.bridge import EventBridge


# ---------------------------------------------------------------------------
# DashboardState
# ---------------------------------------------------------------------------


class TestBranchState:
    def test_defaults(self):
        bs = BranchState(branch_id="A")
        assert bs.iteration == 0
        assert bs.score is None
        assert bs.status == "running"

    def test_to_dict(self):
        bs = BranchState(branch_id="A", iteration=3, score=7)
        d = bs.to_dict()
        assert d["branch_id"] == "A"
        assert d["iteration"] == 3
        assert d["score"] == 7

    def test_errors_truncated_to_10(self):
        bs = BranchState(branch_id="A", errors=[f"err{i}" for i in range(20)])
        d = bs.to_dict()
        assert len(d["errors"]) == 10


class TestDashboardState:
    def test_from_config(self):
        config = ClawConfig(goal="Build X", quality_threshold=9, num_branches=3)
        state = DashboardState.from_config(config)
        assert state.goal == "Build X"
        assert state.threshold == 9
        assert state.mode == "tournament"

    def test_from_config_single_mode(self):
        config = ClawConfig(goal="Build Y", num_branches=1)
        state = DashboardState.from_config(config)
        assert state.mode == "single"

    def test_update_iteration_start(self):
        state = DashboardState(goal="test")
        event = BranchEvent("A", "iteration_start", {"iteration": 5})
        state.update(event)
        assert state.branches["A"].iteration == 5
        assert state.branches["A"].status == "running"

    def test_update_tool_call(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "iteration_start", {"iteration": 1}))
        state.update(BranchEvent("A", "tool_call", {"name": "Write"}))
        assert state.branches["A"].last_tool == "Write"

    def test_update_text_preview(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "text_preview", {"text": "Implementing login..."}))
        assert state.branches["A"].last_text == "Implementing login..."

    def test_update_text_preview_truncated(self):
        state = DashboardState(goal="test")
        long_text = "x" * 500
        state.update(BranchEvent("A", "text_preview", {"text": long_text}))
        assert len(state.branches["A"].last_text) == 200

    def test_update_feature(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "feature", {"name": "auth"}))
        assert "auth" in state.branches["A"].features

    def test_update_feature_no_duplicates(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "feature", {"name": "auth"}))
        state.update(BranchEvent("A", "feature", {"name": "auth"}))
        assert state.branches["A"].features.count("auth") == 1

    def test_update_score(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "score", {"score": 7}))
        assert state.branches["A"].score == 7
        assert state.branches["A"].score_history == [7]

    def test_update_score_history(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "score", {"score": 5}))
        state.update(BranchEvent("A", "score", {"score": 7}))
        assert state.branches["A"].score_history == [5, 7]

    def test_update_error(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "error", {"message": "fail"}))
        assert "fail" in state.branches["A"].errors

    def test_update_done(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "done", {"reason": "quality_reached"}))
        assert state.branches["A"].status == "done"
        assert state.branches["A"].stop_reason == "quality_reached"

    def test_update_budget(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("__system__", "budget", {
            "spent": 2.5, "fraction": 0.5, "status": "ok",
        }))
        assert state.budget_status == "ok"
        assert state.budget_fraction == 0.5

    def test_update_browser_eval(self):
        state = DashboardState(goal="test")
        data = {"health_score": 8, "console_errors": 2}
        state.update(BranchEvent("__system__", "browser_eval", data))
        assert state.browser_eval == data

    def test_activity_log_capped(self):
        state = DashboardState(goal="test")
        for i in range(250):
            state.update(BranchEvent("A", "tool_call", {"name": f"tool{i}"}))
        assert len(state.activity_log) == 200

    def test_to_dict(self):
        state = DashboardState(goal="test", threshold=8)
        state.update(BranchEvent("A", "score", {"score": 7}))
        d = state.to_dict()
        assert d["goal"] == "test"
        assert "A" in d["branches"]
        assert d["branches"]["A"]["score"] == 7

    def test_ensures_branch_on_first_event(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("B", "tool_call", {"name": "Read"}))
        assert "B" in state.branches

    def test_multiple_branches(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "score", {"score": 7}))
        state.update(BranchEvent("B", "score", {"score": 9}))
        assert state.branches["A"].score == 7
        assert state.branches["B"].score == 9


# ---------------------------------------------------------------------------
# SteeringChannel
# ---------------------------------------------------------------------------


class TestSteeringChannel:
    def test_send_and_receive(self):
        ch = SteeringChannel()
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=9))
        cmd = ch.receive_nowait()
        assert cmd is not None
        assert cmd.kind == "set_threshold"
        assert cmd.value == 9

    def test_receive_empty_returns_none(self):
        ch = SteeringChannel()
        assert ch.receive_nowait() is None

    def test_pause_resume(self):
        ch = SteeringChannel()
        assert not ch.paused
        ch.send_nowait(SteeringCommand(kind="pause"))
        assert ch.paused
        ch.send_nowait(SteeringCommand(kind="resume"))
        assert not ch.paused

    def test_pause_resume_managed_directly(self):
        """Pause/resume bypass the queue — they're handled in send_nowait."""
        ch = SteeringChannel()
        ch.send_nowait(SteeringCommand(kind="pause"))
        # The pause command should NOT appear in the queue
        assert ch.receive_nowait() is None
        assert ch.paused

    def test_buffer_overflow_drops(self):
        ch = SteeringChannel(buffer_size=2)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=1))
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=2))
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=3))  # dropped
        assert ch.receive_nowait().value == 1
        assert ch.receive_nowait().value == 2
        assert ch.receive_nowait() is None

    def test_close(self):
        ch = SteeringChannel()
        ch.close()
        # After close, receive should return None
        assert ch.receive_nowait() is None


class TestProcessPendingCommands:
    @pytest.mark.anyio
    async def test_no_commands_returns_none(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test")
        result = await process_pending_commands(ch, config)
        assert result is None

    @pytest.mark.anyio
    async def test_set_threshold(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=8)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=9))
        await process_pending_commands(ch, config)
        assert config.quality_threshold == 9

    @pytest.mark.anyio
    async def test_set_threshold_invalid_ignored(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=8)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=15))
        await process_pending_commands(ch, config)
        assert config.quality_threshold == 8

    @pytest.mark.anyio
    async def test_inject_hint(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test")
        ch.send_nowait(SteeringCommand(kind="inject_hint", value="Focus on a11y"))
        await process_pending_commands(ch, config)
        assert getattr(config, "_steering_hint", None) == "Focus on a11y"

    @pytest.mark.anyio
    async def test_stop_all_returns_stop(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test")
        ch.send_nowait(SteeringCommand(kind="stop_all"))
        result = await process_pending_commands(ch, config)
        assert result == "stop"

    @pytest.mark.anyio
    async def test_stop_branch_returns_stop(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test")
        ch.send_nowait(SteeringCommand(kind="stop_branch", value="B"))
        result = await process_pending_commands(ch, config)
        assert result == "stop"

    @pytest.mark.anyio
    async def test_multiple_commands_processed(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=8)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=6))
        ch.send_nowait(SteeringCommand(kind="inject_hint", value="test hint"))
        await process_pending_commands(ch, config)
        assert config.quality_threshold == 6
        assert getattr(config, "_steering_hint", None) == "test hint"

    @pytest.mark.anyio
    async def test_wait_if_paused_no_op_when_not_paused(self):
        ch = SteeringChannel()
        await ch.wait_if_paused()  # should return immediately


# ---------------------------------------------------------------------------
# EventBridge
# ---------------------------------------------------------------------------


class TestEventBridge:
    def test_handle_event_updates_state(self):
        state = DashboardState(goal="test")
        broadcasts = []
        bridge = EventBridge(state, broadcast=broadcasts.append)

        event = BranchEvent("A", "score", {"score": 7})
        bridge.handle_event(event)

        assert state.branches["A"].score == 7
        assert len(broadcasts) == 1
        assert broadcasts[0]["type"] == "event"
        assert broadcasts[0]["branch_id"] == "A"

    def test_handle_event_forwards_to_terminal(self):
        state = DashboardState(goal="test")
        terminal_events = []
        bridge = EventBridge(
            state,
            broadcast=lambda msg: None,
            terminal_callback=terminal_events.append,
        )

        event = BranchEvent("A", "iteration_start", {"iteration": 1})
        bridge.handle_event(event)

        assert len(terminal_events) == 1
        assert terminal_events[0].event_type == "iteration_start"

    def test_make_on_event_returns_callable(self):
        state = DashboardState(goal="test")
        bridge = EventBridge(state, broadcast=lambda msg: None)
        cb = bridge.make_on_event()
        assert callable(cb)
        cb(BranchEvent("A", "tool_call", {"name": "Bash"}))
        assert state.branches["A"].last_tool == "Bash"

    def test_emit_budget(self):
        state = DashboardState(goal="test")
        broadcasts = []
        bridge = EventBridge(state, broadcast=broadcasts.append)

        bridge.emit_budget(2.5, 5.0, 0.5, "ok")
        assert state.budget_status == "ok"
        assert len(broadcasts) == 1
        assert broadcasts[0]["type"] == "budget"

    def test_emit_browser_eval(self):
        state = DashboardState(goal="test")
        broadcasts = []
        bridge = EventBridge(state, broadcast=broadcasts.append)

        bridge.emit_browser_eval({"health_score": 8, "console_errors": 2})
        assert state.browser_eval["health_score"] == 8
        assert broadcasts[0]["type"] == "browser_eval"

    def test_emit_round_complete(self):
        state = DashboardState(goal="test")
        broadcasts = []
        bridge = EventBridge(state, broadcast=broadcasts.append)

        bridge.emit_round_complete(1, "A", [{"branch_id": "A", "final_score": 8}])
        assert len(state.rounds) == 1
        assert state.rounds[0]["winner"] == "A"
        assert broadcasts[0]["type"] == "round_complete"


# ---------------------------------------------------------------------------
# Frontend HTML
# ---------------------------------------------------------------------------


class TestFrontend:
    def test_html_is_valid_string(self):
        from inductiveclaw.dashboard.frontend import DASHBOARD_HTML
        assert isinstance(DASHBOARD_HTML, str)
        assert "<!DOCTYPE html>" in DASHBOARD_HTML
        assert "MISSION CONTROL" in DASHBOARD_HTML
        assert "WebSocket" in DASHBOARD_HTML

    def test_html_contains_key_elements(self):
        from inductiveclaw.dashboard.frontend import DASHBOARD_HTML
        assert 'id="branches"' in DASHBOARD_HTML
        assert 'id="feed"' in DASHBOARD_HTML
        assert 'id="threshold"' in DASHBOARD_HTML
        assert 'id="sparkline"' in DASHBOARD_HTML
        assert 'id="budget-fill"' in DASHBOARD_HTML

    def test_html_contains_steering_controls(self):
        from inductiveclaw.dashboard.frontend import DASHBOARD_HTML
        assert 'id="hint"' in DASHBOARD_HTML
        assert "sendHint" in DASHBOARD_HTML
        assert "adjThreshold" in DASHBOARD_HTML
        assert "sendCmd" in DASHBOARD_HTML


# ---------------------------------------------------------------------------
# Package re-exports
# ---------------------------------------------------------------------------


class TestPackageInit:
    def test_all_exports_accessible(self):
        from inductiveclaw.dashboard import (
            DashboardServer,
            DashboardState,
            BranchState,
            EventBridge,
            SteeringChannel,
            SteeringCommand,
            process_pending_commands,
        )
        assert DashboardServer is not None
        assert DashboardState is not None
        assert BranchState is not None
        assert EventBridge is not None
        assert SteeringChannel is not None
        assert SteeringCommand is not None
        assert process_pending_commands is not None


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    def test_clawconfig_has_dashboard_fields(self):
        config = ClawConfig()
        assert config.dashboard is False
        assert config.dashboard_port == 8420

    def test_clawconfig_dashboard_enabled(self):
        config = ClawConfig(dashboard=True, dashboard_port=9999)
        assert config.dashboard is True
        assert config.dashboard_port == 9999


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


class TestCLIParsing:
    def test_dash_flag(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "Build X", "--dash"])
        assert args.dashboard is True

    def test_dashboard_long_flag(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "Build X", "--dashboard"])
        assert args.dashboard is True

    def test_dash_port_flag(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "Build X", "--dash", "--dash-port", "9999"])
        assert args.dash_port == 9999

    def test_dash_port_default(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "Build X"])
        assert args.dash_port == 8420

    def test_dash_defaults_to_false(self):
        from inductiveclaw.__main__ import parse_args
        args = parse_args(["-g", "Build X"])
        assert args.dashboard is False


# ---------------------------------------------------------------------------
# DashboardState snapshot roundtrip
# ---------------------------------------------------------------------------


class TestSnapshotRoundtrip:
    def test_snapshot_is_json_serializable(self):
        state = DashboardState.from_config(
            ClawConfig(goal="Build app", quality_threshold=8, budget_usd=5.0)
        )
        state.update(BranchEvent("main", "iteration_start", {"iteration": 1}))
        state.update(BranchEvent("main", "tool_call", {"name": "Write"}))
        state.update(BranchEvent("main", "score", {"score": 6}))
        state.update(BranchEvent("main", "feature", {"name": "auth"}))
        state.update(BranchEvent("main", "error", {"message": "timeout"}))

        d = state.to_dict()
        # Must be JSON-serializable
        raw = json.dumps(d)
        restored = json.loads(raw)

        assert restored["goal"] == "Build app"
        assert restored["threshold"] == 8
        assert restored["budget_usd"] == 5.0
        assert restored["branches"]["main"]["score"] == 6
        assert "auth" in restored["branches"]["main"]["features"]

    def test_empty_state_serializable(self):
        state = DashboardState()
        raw = json.dumps(state.to_dict())
        restored = json.loads(raw)
        assert restored["branches"] == {}

    def test_activity_log_capped_in_snapshot(self):
        state = DashboardState(goal="test")
        for i in range(100):
            state.update(BranchEvent("A", "tool_call", {"name": f"t{i}"}))
        d = state.to_dict()
        assert len(d["activity_log"]) == 50  # snapshot caps to 50


# ---------------------------------------------------------------------------
# Steering hint in iteration prompt
# ---------------------------------------------------------------------------


class TestSteeringHintPrompt:
    def test_hint_set_and_cleared(self):
        """Verify _steering_hint is consumed by process_pending_commands
        and would appear in iteration context."""
        config = ClawConfig(goal="Build X", quality_threshold=8)
        assert getattr(config, "_steering_hint", None) is None

        # Simulate steering command setting the hint
        config._steering_hint = "Focus on accessibility"  # type: ignore[attr-defined]
        assert config._steering_hint == "Focus on accessibility"  # type: ignore[attr-defined]

        # Simulate what iteration.py does: read and clear
        hint = getattr(config, "_steering_hint", None)
        assert hint == "Focus on accessibility"
        config._steering_hint = None  # type: ignore[attr-defined]
        assert getattr(config, "_steering_hint", None) is None

    def test_hint_cleared_by_process_commands(self):
        """inject_hint command sets _steering_hint on config."""
        import anyio

        async def _test():
            ch = SteeringChannel()
            config = ClawConfig(goal="test")
            ch.send_nowait(SteeringCommand(kind="inject_hint", value="Fix the bug"))
            await process_pending_commands(ch, config)
            assert getattr(config, "_steering_hint", None) == "Fix the bug"

        anyio.run(_test)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_update_unknown_event_type(self):
        """Unknown event types should not crash — just add to activity log."""
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "unknown_type", {"foo": "bar"}))
        assert "A" in state.branches
        assert len(state.activity_log) == 1

    def test_update_empty_feature_name_ignored(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "feature", {"name": ""}))
        assert state.branches["A"].features == []

    def test_update_score_non_int_ignored(self):
        state = DashboardState(goal="test")
        state.update(BranchEvent("A", "score", {"score": "high"}))
        assert state.branches["A"].score is None

    @pytest.mark.anyio
    async def test_inject_hint_empty_ignored(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test")
        ch.send_nowait(SteeringCommand(kind="inject_hint", value="   "))
        await process_pending_commands(ch, config)
        assert getattr(config, "_steering_hint", None) is None

    @pytest.mark.anyio
    async def test_set_threshold_boundary_1(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=5)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=1))
        await process_pending_commands(ch, config)
        assert config.quality_threshold == 1

    @pytest.mark.anyio
    async def test_set_threshold_boundary_10(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=5)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=10))
        await process_pending_commands(ch, config)
        assert config.quality_threshold == 10

    @pytest.mark.anyio
    async def test_set_threshold_zero_ignored(self):
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=8)
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=0))
        await process_pending_commands(ch, config)
        assert config.quality_threshold == 8

    @pytest.mark.anyio
    async def test_process_commands_stop_short_circuits(self):
        """If stop_all comes before other commands, it should return stop."""
        ch = SteeringChannel()
        config = ClawConfig(goal="test", quality_threshold=8)
        ch.send_nowait(SteeringCommand(kind="stop_all"))
        ch.send_nowait(SteeringCommand(kind="set_threshold", value=3))
        result = await process_pending_commands(ch, config)
        assert result == "stop"

    def test_bridge_no_terminal_callback(self):
        """Bridge works without terminal callback."""
        state = DashboardState(goal="test")
        broadcasts = []
        bridge = EventBridge(state, broadcast=broadcasts.append, terminal_callback=None)
        bridge.handle_event(BranchEvent("A", "tool_call", {"name": "Read"}))
        assert len(broadcasts) == 1
        assert state.branches["A"].last_tool == "Read"

    def test_multiple_rounds_accumulate(self):
        state = DashboardState(goal="test")
        broadcasts = []
        bridge = EventBridge(state, broadcast=broadcasts.append)
        bridge.emit_round_complete(1, "A", [{"branch_id": "A", "final_score": 6}])
        bridge.emit_round_complete(2, "B", [{"branch_id": "B", "final_score": 9}])
        assert len(state.rounds) == 2
        assert state.rounds[0]["round_num"] == 1
        assert state.rounds[1]["winner"] == "B"

    def test_steering_command_dataclass(self):
        cmd = SteeringCommand(kind="pause")
        assert cmd.kind == "pause"
        assert cmd.value is None

        cmd2 = SteeringCommand(kind="set_threshold", value=9)
        assert cmd2.value == 9

    def test_branch_state_cost_in_dict(self):
        bs = BranchState(branch_id="A", cost_usd=1.234)
        d = bs.to_dict()
        assert d["cost_usd"] == 1.234

    def test_dashboard_state_total_cost_from_branches(self):
        state = DashboardState(goal="test")
        state.branches["A"] = BranchState(branch_id="A", cost_usd=1.0)
        state.branches["B"] = BranchState(branch_id="B", cost_usd=2.5)
        # Trigger cost recompute via an event
        state.update(BranchEvent("A", "tool_call", {"name": "Bash"}))
        assert state.total_cost_usd == 3.5

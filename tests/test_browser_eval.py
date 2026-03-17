"""Tests for browser-based product evaluation."""

from __future__ import annotations

import pytest

from inductiveclaw.browser_eval import (
    BrowserEvalReport,
    InteractionResult,
    KeyBinding,
    KeybindingConflict,
    _detect_conflicts,
    _extract_keys_from_source,
)


# --- Health score computation ---


class TestHealthScore:
    def test_perfect_score_no_issues(self):
        report = BrowserEvalReport(url="http://localhost:3000")
        assert report.compute_health_score() == 10

    def test_console_errors_deduct(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=["err1", "err2"],
        )
        assert report.compute_health_score() == 8

    def test_console_errors_capped_at_4(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=[f"err{i}" for i in range(10)],
        )
        # Deduction capped at 4
        assert report.compute_health_score() == 6

    def test_keybinding_conflicts_deduct_2_each(self):
        conflict = KeybindingConflict(
            key="Space", event_type="keydown",
            handlers=[], severity="critical",
        )
        report = BrowserEvalReport(
            url="http://localhost:3000",
            keybinding_conflicts=[conflict],
        )
        assert report.compute_health_score() == 8

    def test_keybinding_conflicts_capped_at_4(self):
        conflicts = [
            KeybindingConflict(key=f"Key{i}", event_type="keydown",
                               handlers=[], severity="warning")
            for i in range(5)
        ]
        report = BrowserEvalReport(
            url="http://localhost:3000",
            keybinding_conflicts=conflicts,
        )
        # 5 * 2 = 10, but capped at 4
        assert report.compute_health_score() == 6

    def test_network_errors_deduct(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            network_errors=[{"url": "/api", "status": "500", "method": "GET"}],
        )
        assert report.compute_health_score() == 9

    def test_network_errors_capped_at_2(self):
        errors = [
            {"url": f"/api/{i}", "status": "500", "method": "GET"}
            for i in range(5)
        ]
        report = BrowserEvalReport(
            url="http://localhost:3000",
            network_errors=errors,
        )
        assert report.compute_health_score() == 8

    def test_broken_interactions_deduct(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            broken_interactions=[
                InteractionResult(action="click", target="#btn", success=False, error="timeout"),
            ],
            total_interactions=2,
        )
        # broken_ratio = 0.5, int(0.5 * 10) = 5, capped at 2 → score 8
        assert report.compute_health_score() == 8

    def test_all_interactions_broken(self):
        broken = [
            InteractionResult(action="click", target=f"#btn{i}", success=False, error="err")
            for i in range(10)
        ]
        report = BrowserEvalReport(
            url="http://localhost:3000",
            broken_interactions=broken,
            total_interactions=10,
        )
        # broken_ratio = 1.0, int(1.0 * 10) = 10, capped at 2 → score 8
        assert report.compute_health_score() == 8

    def test_score_never_below_zero(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=[f"e{i}" for i in range(10)],      # -4
            keybinding_conflicts=[
                KeybindingConflict(key=f"K{i}", event_type="keydown",
                                   handlers=[], severity="critical")
                for i in range(5)
            ],                                                   # -4
            network_errors=[{"url": f"/{i}", "status": "500", "method": "GET"} for i in range(5)],  # -2
            broken_interactions=[
                InteractionResult(action="click", target="#x", success=False, error="err")
            ],
            total_interactions=1,                                # -2
        )
        assert report.compute_health_score() == 0

    def test_combined_deductions(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=["err1"],                             # -1
            keybinding_conflicts=[
                KeybindingConflict(key="Space", event_type="keydown",
                                   handlers=[], severity="warning"),
            ],                                                   # -2
            network_errors=[{"url": "/api", "status": "404", "method": "GET"}],  # -1
        )
        assert report.compute_health_score() == 6

    def test_zero_total_interactions_no_broken_penalty(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            total_interactions=0,
        )
        assert report.compute_health_score() == 10


# --- Summary building ---


class TestBuildSummary:
    def test_no_issues(self):
        report = BrowserEvalReport(url="http://localhost:3000")
        assert "No issues" in report.build_summary()

    def test_console_errors_mentioned(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=["err1", "err2"],
        )
        summary = report.build_summary()
        assert "2 console error" in summary

    def test_keybinding_conflicts_mentioned(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            keybinding_conflicts=[
                KeybindingConflict(key="Space", event_type="keydown",
                                   handlers=[], severity="critical"),
            ],
        )
        assert "1 keybinding conflict" in report.build_summary()

    def test_multiple_issues(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=["e1"],
            network_errors=[{"url": "/x", "status": "500", "method": "GET"}],
        )
        summary = report.build_summary()
        assert "console error" in summary
        assert "network error" in summary


# --- Markdown output ---


class TestToMarkdown:
    def test_contains_header(self):
        report = BrowserEvalReport(url="http://localhost:3000")
        report.compute_health_score()
        report.build_summary()
        md = report.to_markdown()
        assert "# Browser Evaluation Report" in md
        assert "http://localhost:3000" in md

    def test_contains_health_score(self):
        report = BrowserEvalReport(url="http://localhost:3000")
        report.compute_health_score()
        report.build_summary()
        md = report.to_markdown()
        assert "10/10" in md

    def test_console_errors_section(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            console_errors=["TypeError: x is undefined"],
        )
        report.compute_health_score()
        report.build_summary()
        md = report.to_markdown()
        assert "## Console Errors" in md
        assert "TypeError" in md

    def test_keybinding_conflicts_section(self):
        report = BrowserEvalReport(
            url="http://localhost:3000",
            keybinding_conflicts=[
                KeybindingConflict(
                    key="Space", event_type="keydown",
                    handlers=[
                        KeyBinding(key="Space", event_type="keydown",
                                   handler_id="kb_0", context="document/window"),
                        KeyBinding(key="Space", event_type="keydown",
                                   handler_id="kb_1", context="button#start"),
                    ],
                    severity="critical",
                ),
            ],
        )
        report.compute_health_score()
        report.build_summary()
        md = report.to_markdown()
        assert "## Keybinding Conflicts" in md
        assert "Space" in md
        assert "critical" in md


# --- Key extraction from handler source ---


class TestExtractKeys:
    def test_event_key_comparison(self):
        source = 'if (e.key === "ArrowUp") { jump(); }'
        keys = _extract_keys_from_source(source)
        assert "ArrowUp" in keys

    def test_event_code_comparison(self):
        source = 'if (event.code === "Space") { fire(); }'
        keys = _extract_keys_from_source(source)
        assert "Space" in keys

    def test_keycode_comparison(self):
        source = "if (e.keyCode === 32) { pause(); }"
        keys = _extract_keys_from_source(source)
        assert "32" in keys

    def test_which_comparison(self):
        source = "if (e.which === 27) { close(); }"
        keys = _extract_keys_from_source(source)
        assert "27" in keys

    def test_multiple_keys(self):
        source = '''
        if (e.key === "ArrowUp") { up(); }
        else if (e.key === "ArrowDown") { down(); }
        '''
        keys = _extract_keys_from_source(source)
        assert "ArrowUp" in keys
        assert "ArrowDown" in keys

    def test_no_keys_found(self):
        source = "function handler(e) { console.log(e); }"
        keys = _extract_keys_from_source(source)
        assert keys == []

    def test_single_letter_key(self):
        source = 'if (event.key === "w") { moveForward(); }'
        keys = _extract_keys_from_source(source)
        assert any("w" in k for k in keys)


# --- Conflict detection ---


class TestDetectConflicts:
    def test_no_conflicts_different_keys(self):
        bindings = [
            KeyBinding(key="Space", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_1", context="document/window"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 0

    def test_conflict_same_key_same_event(self):
        bindings = [
            KeyBinding(key="Space", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="Space", event_type="keydown",
                       handler_id="kb_1", context="document/window"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 1
        assert conflicts[0].key == "Space"
        assert len(conflicts[0].handlers) == 2

    def test_no_conflict_different_event_types(self):
        bindings = [
            KeyBinding(key="Space", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="Space", event_type="keyup",
                       handler_id="kb_1", context="document/window"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 0

    def test_severity_critical_same_element(self):
        bindings = [
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_1", context="document/window"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "critical"

    def test_severity_warning_different_elements(self):
        bindings = [
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_1", context="button#submit"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "warning"

    def test_unknown_keys_ignored(self):
        bindings = [
            KeyBinding(key="<unknown>", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="<unknown>", event_type="keydown",
                       handler_id="kb_1", context="document/window"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 0

    def test_multiple_conflicts(self):
        bindings = [
            KeyBinding(key="Space", event_type="keydown",
                       handler_id="kb_0", context="document/window"),
            KeyBinding(key="Space", event_type="keydown",
                       handler_id="kb_1", context="canvas#game"),
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_2", context="document/window"),
            KeyBinding(key="Enter", event_type="keydown",
                       handler_id="kb_3", context="form#login"),
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 2

    def test_three_handlers_same_key(self):
        bindings = [
            KeyBinding(key="Escape", event_type="keydown",
                       handler_id=f"kb_{i}", context=f"ctx_{i}")
            for i in range(3)
        ]
        conflicts = _detect_conflicts(bindings)
        assert len(conflicts) == 1
        assert len(conflicts[0].handlers) == 3

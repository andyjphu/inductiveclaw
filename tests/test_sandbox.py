"""Tests for backends/sandbox.py — path validation and tool sandboxing."""

from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path

import pytest

from inductiveclaw.backends.sandbox import check_tool_sandbox, in_sandbox, write_sandbox_settings


class TestInSandbox:
    def test_file_inside_sandbox(self, tmp_path):
        assert in_sandbox(str(tmp_path / "foo.py"), str(tmp_path)) is True

    def test_file_outside_sandbox(self, tmp_path):
        assert in_sandbox("/etc/passwd", str(tmp_path)) is False

    def test_nested_file_inside(self, tmp_path):
        assert in_sandbox(str(tmp_path / "a" / "b" / "c.py"), str(tmp_path)) is True

    def test_parent_traversal_blocked(self, tmp_path):
        tricky = str(tmp_path / ".." / "etc" / "passwd")
        assert in_sandbox(tricky, str(tmp_path)) is False

    def test_sandbox_root_itself(self, tmp_path):
        assert in_sandbox(str(tmp_path), str(tmp_path)) is True

    def test_symlink_outside(self, tmp_path):
        # Create a symlink inside sandbox pointing outside
        outside = Path(tempfile.mkdtemp())
        link = tmp_path / "sneaky_link"
        try:
            link.symlink_to(outside)
            # The resolved path should be outside
            assert in_sandbox(str(link / "file.txt"), str(tmp_path)) is False
        finally:
            link.unlink(missing_ok=True)
            outside.rmdir()


class TestCheckToolSandbox:
    """Test check_tool_sandbox for various tool types."""

    def test_write_inside_allowed(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Write", {"file_path": str(tmp_path / "test.py")}, str(tmp_path)
        )
        assert allowed is True

    def test_write_outside_blocked(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Write", {"file_path": "/etc/passwd"}, str(tmp_path)
        )
        assert allowed is False
        assert "outside" in reason.lower() or "sandbox" in reason.lower()

    def test_edit_inside_allowed(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Edit", {"file_path": str(tmp_path / "test.py")}, str(tmp_path)
        )
        assert allowed is True

    def test_edit_outside_blocked(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Edit", {"file_path": "/tmp/outside.py"}, str(tmp_path)
        )
        assert allowed is False

    def test_read_inside_allowed(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Read", {"file_path": str(tmp_path / "test.py")}, str(tmp_path)
        )
        assert allowed is True

    def test_read_outside_blocked(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Read", {"file_path": "/etc/shadow"}, str(tmp_path)
        )
        assert allowed is False

    def test_glob_inside_allowed(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Glob", {"pattern": "**/*.py"}, str(tmp_path)
        )
        assert allowed is True

    def test_bash_simple_allowed(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Bash", {"command": "ls -la"}, str(tmp_path)
        )
        assert allowed is True

    def test_bash_sudo_blocked(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Bash", {"command": "sudo rm -rf /"}, str(tmp_path)
        )
        assert allowed is False
        assert "sudo" in reason.lower()

    def test_bash_absolute_path_outside_blocked(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Bash", {"command": "cat /etc/passwd"}, str(tmp_path)
        )
        assert allowed is False

    def test_bash_parent_traversal_blocked(self, tmp_path):
        allowed, reason = check_tool_sandbox(
            "Bash", {"command": "cat ../../etc/passwd"}, str(tmp_path)
        )
        assert allowed is False

    def test_unknown_tool_allowed(self, tmp_path):
        # Unknown tools should be allowed (sandbox is allowlist-based for file tools)
        allowed, reason = check_tool_sandbox(
            "WebSearch", {"query": "test"}, str(tmp_path)
        )
        assert allowed is True


class TestWriteSandboxSettings:
    def test_creates_settings_file(self, tmp_path):
        write_sandbox_settings(str(tmp_path))
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()

        data = json.loads(settings_path.read_text())
        assert "permissions" in data

    def test_creates_claude_md(self, tmp_path):
        write_sandbox_settings(str(tmp_path))
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "sandbox" in content.lower()

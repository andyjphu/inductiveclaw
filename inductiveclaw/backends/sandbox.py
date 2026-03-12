"""Sandbox enforcement utilities shared across backends."""

from __future__ import annotations

import json
import os
from pathlib import Path


def in_sandbox(path: str, sandbox_dir: str) -> bool:
    """Check if a path is inside the sandbox directory."""
    try:
        resolved = str(Path(sandbox_dir).resolve())
        target = str(Path(path).resolve())
        return target == resolved or target.startswith(resolved + os.sep)
    except (ValueError, OSError):
        return False


def check_tool_sandbox(
    tool_name: str, tool_input: dict, sandbox_dir: str,
) -> tuple[bool, str]:
    """Check if a tool call is allowed by sandbox rules.

    Returns (allowed, error_message). error_message is empty if allowed.
    """
    # File tools: path must be inside sandbox
    if tool_name in ("Write", "Edit", "Read"):
        file_path = tool_input.get("file_path", "")
        if file_path and not in_sandbox(file_path, sandbox_dir):
            return False, (
                f"Sandbox: {tool_name} blocked — {file_path} "
                f"is outside sandbox ({sandbox_dir})"
            )

    if tool_name in ("Glob", "Grep"):
        search_path = tool_input.get("path", "")
        if search_path and not in_sandbox(search_path, sandbox_dir):
            return False, (
                f"Sandbox: {tool_name} blocked — {search_path} "
                f"is outside sandbox ({sandbox_dir})"
            )

    # Bash: no sudo, no parent traversal, no absolute paths outside sandbox
    if tool_name == "Bash":
        cmd = tool_input.get("command", "").strip()
        if not cmd:
            return True, ""
        if "sudo" in cmd.split():
            return False, "Sandbox: sudo is not allowed"
        if ".." in cmd:
            return False, "Sandbox: parent directory traversal (..) is not allowed"
        for word in cmd.split():
            if word.startswith("/") and not in_sandbox(word, sandbox_dir):
                return False, f"Sandbox: Bash blocked — {word} is outside sandbox"

    return True, ""


def write_sandbox_settings(project_dir: str) -> None:
    """Write .claude/settings.json and CLAUDE.md for sandbox enforcement.

    This is used by the Claude backend. The settings file is read by all
    Claude CLI processes including sub-agents.
    """
    claude_dir = Path(project_dir) / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"

    resolved_str = str(Path(project_dir).resolve())
    settings = {
        "permissions": {
            "deny": [
                "Read(//**)",
                "Edit(//**)",
                "Write(//**)",
                "Read(../**)",
                "Edit(../**)",
                "Write(../**)",
            ],
            "allow": [
                f"Read(//{resolved_str.lstrip('/')}/**)",
                f"Edit(//{resolved_str.lstrip('/')}/**)",
                f"Write(//{resolved_str.lstrip('/')}/**)",
                "Read(**)",
                "Edit(**)",
                "Write(**)",
                "Glob(**)",
                "Grep(**)",
            ],
        },
    }

    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
            if existing == settings:
                return
        except (json.JSONDecodeError, OSError):
            pass

    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    # CLAUDE.md sandbox rules for sub-agents
    claude_md = Path(project_dir) / "CLAUDE.md"
    sandbox_rules = (
        f"# Sandbox Rules\n\n"
        f"You are running inside a sandboxed InductiveClaw session.\n\n"
        f"**CRITICAL: ALL file operations MUST stay within this directory:**\n"
        f"`{resolved_str}`\n\n"
        f"- NEVER read, write, edit, or create files outside this directory\n"
        f"- NEVER use absolute paths (like /Users/...) — use relative paths only\n"
        f"- NEVER use `..` to access parent directories\n"
        f"- NEVER use `sudo` or modify system files\n"
        f"- NEVER run `find`, `ls`, `cat`, or any command on paths outside this directory\n"
        f"- Install dependencies locally (npm install, pip install in a venv)\n"
        f"- If you need to explore, explore WITHIN this directory only\n"
    )
    if not claude_md.exists() or "Sandbox Rules" not in claude_md.read_text():
        if claude_md.exists():
            existing = claude_md.read_text()
            claude_md.write_text(sandbox_rules + "\n" + existing)
        else:
            claude_md.write_text(sandbox_rules)

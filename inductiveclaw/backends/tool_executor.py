"""Generic tool executor for non-Claude backends.

Routes function-calling tool requests to the pure implementations in
tools_core.py, plus handles built-in file/search/shell tools via
subprocess sandboxed execution.

Claude's backend handles tools natively through the Agent SDK.
OpenAI/Gemini backends call this executor to handle tool calls.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

from ..tools_core import (
    TOOL_SCHEMAS,
    tool_update_backlog,
    tool_self_evaluate,
    tool_take_screenshot,
    tool_write_docs,
    tool_smoke_test,
    tool_propose_idea,
)
from .sandbox import check_tool_sandbox


# Maps iclaw custom tool names to their implementations
_ICLAW_TOOL_HANDLERS: dict[
    str, Callable[..., Awaitable[dict[str, Any]]]
] = {
    "update_backlog": tool_update_backlog,
    "self_evaluate": tool_self_evaluate,
    "take_screenshot": tool_take_screenshot,
    "write_docs": tool_write_docs,
    "smoke_test": tool_smoke_test,
    "propose_idea": tool_propose_idea,
}

# Built-in tools that non-Claude backends can execute directly
BUILTIN_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "bash": {
        "description": "Execute a shell command in the project directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["command"],
        },
    },
    "read_file": {
        "description": "Read the contents of a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file"},
            },
            "required": ["file_path"],
        },
    },
    "write_file": {
        "description": "Write content to a file, creating it if it doesn't exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["file_path", "content"],
        },
    },
    "list_files": {
        "description": "List files matching a glob pattern in the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py')",
                },
            },
            "required": ["pattern"],
        },
    },
    "search_files": {
        "description": "Search file contents for a regex pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "glob": {
                    "type": "string",
                    "description": "File glob to narrow search (e.g. '*.py')",
                },
            },
            "required": ["pattern"],
        },
    },
}


def get_all_tool_schemas() -> dict[str, dict[str, Any]]:
    """Return combined schemas for iclaw + builtin tools."""
    schemas = {}
    for name, schema in TOOL_SCHEMAS.items():
        schemas[name] = schema
    for name, schema in BUILTIN_TOOL_SCHEMAS.items():
        schemas[name] = schema
    return schemas


class ToolExecutor:
    """Executes tool calls for non-Claude backends with sandbox enforcement."""

    def __init__(
        self,
        project_dir: str,
        screenshot_port: int = 3000,
    ) -> None:
        self._project_dir = str(Path(project_dir).resolve())
        self._screenshot_port = screenshot_port

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """Execute a tool call and return the text result.

        Returns a JSON string for structured results, or plain text for
        simple outputs. Errors are returned as text, not raised.
        """
        # iclaw custom tools
        if tool_name in _ICLAW_TOOL_HANDLERS:
            handler = _ICLAW_TOOL_HANDLERS[tool_name]
            kwargs: dict[str, Any] = {
                "project_dir": self._project_dir,
                "args": args,
            }
            # Pass default_port for screenshot/smoke_test
            if tool_name in ("take_screenshot", "smoke_test"):
                kwargs["default_port"] = self._screenshot_port
            try:
                result = await handler(**kwargs)
                return _extract_text(result)
            except Exception as e:
                return f"Error in {tool_name}: {e}"

        # Built-in tools with sandbox checks
        if tool_name == "bash":
            return await self._exec_bash(args)
        if tool_name == "read_file":
            return self._exec_read(args)
        if tool_name == "write_file":
            return self._exec_write(args)
        if tool_name == "list_files":
            return self._exec_list(args)
        if tool_name == "search_files":
            return self._exec_search(args)

        return f"Unknown tool: {tool_name}"

    async def _exec_bash(self, args: dict[str, Any]) -> str:
        command = args.get("command", "")
        if not command:
            return "Error: empty command"

        # Sandbox check
        allowed, reason = check_tool_sandbox("Bash", {"command": command}, self._project_dir)
        if not allowed:
            return f"Blocked: {reason}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self._project_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr] {result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: command timed out (120s)"
        except Exception as e:
            return f"Error running command: {e}"

    def _exec_read(self, args: dict[str, Any]) -> str:
        file_path = args.get("file_path", "")
        if not file_path:
            return "Error: no file_path"

        # Resolve relative to project
        resolved = self._resolve_path(file_path)
        allowed, reason = check_tool_sandbox("Read", {"file_path": resolved}, self._project_dir)
        if not allowed:
            return f"Blocked: {reason}"

        try:
            return Path(resolved).read_text()
        except FileNotFoundError:
            return f"File not found: {file_path}"
        except Exception as e:
            return f"Error reading file: {e}"

    def _exec_write(self, args: dict[str, Any]) -> str:
        file_path = args.get("file_path", "")
        content = args.get("content", "")
        if not file_path:
            return "Error: no file_path"

        resolved = self._resolve_path(file_path)
        allowed, reason = check_tool_sandbox("Write", {"file_path": resolved}, self._project_dir)
        if not allowed:
            return f"Blocked: {reason}"

        try:
            p = Path(resolved)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Wrote {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def _exec_list(self, args: dict[str, Any]) -> str:
        pattern = args.get("pattern", "**/*")
        project = Path(self._project_dir)
        try:
            matches = sorted(str(p.relative_to(project)) for p in project.glob(pattern) if p.is_file())
            if not matches:
                return "(no files match)"
            return "\n".join(matches[:200])
        except Exception as e:
            return f"Error listing files: {e}"

    def _exec_search(self, args: dict[str, Any]) -> str:
        pattern = args.get("pattern", "")
        glob_filter = args.get("glob", "")
        if not pattern:
            return "Error: no pattern"

        cmd = ["grep", "-rn", "-E", pattern, "."]
        if glob_filter:
            cmd = ["grep", "-rn", "-E", pattern, "--include", glob_filter, "."]

        try:
            result = subprocess.run(
                cmd,
                cwd=self._project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip()
            if not output:
                return "(no matches)"
            # Truncate if very long
            lines = output.split("\n")
            if len(lines) > 100:
                return "\n".join(lines[:100]) + f"\n... ({len(lines) - 100} more lines)"
            return output
        except subprocess.TimeoutExpired:
            return "Error: search timed out"
        except Exception as e:
            return f"Error searching: {e}"

    def _resolve_path(self, file_path: str) -> str:
        """Resolve a path relative to project dir if not absolute."""
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(self._project_dir) / p
        return str(p.resolve())


def _extract_text(result: dict[str, Any]) -> str:
    """Extract text from MCP tool result format."""
    content = result.get("content", [])
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item["text"])
    return "\n".join(texts) if texts else json.dumps(result)

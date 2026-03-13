"""Custom MCP tools for InductiveClaw — thin SDK wrapper.

Tool logic lives in tools_core.py. This module registers them with the
Claude Agent SDK's @tool decorator and MCP server.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from claude_agent_sdk import tool, create_sdk_mcp_server

from .tools_core import (
    tool_update_backlog,
    tool_self_evaluate,
    tool_take_screenshot,
    tool_write_docs,
    tool_smoke_test,
    tool_propose_idea,
)

if TYPE_CHECKING:
    from .config import ClawConfig


def create_iclaw_tools(config: ClawConfig):
    """Create and return the custom MCP server with all InductiveClaw tools."""

    project_dir = str(config.project_dir)
    port = config.screenshot_port

    @tool(
        "update_backlog",
        "Update the project backlog. Call after completing a feature or during planning.",
        {
            "completed_item": str,
            "next_priorities": list[str],
            "quality_notes": str,
            "blockers": list[str],
        },
    )
    async def update_backlog(args: dict[str, Any]) -> dict[str, Any]:
        return await tool_update_backlog(project_dir, args)

    @tool(
        "self_evaluate",
        "Critically evaluate the current project quality. Call ONLY after completing "
        "the full review protocol (feature inventory, per-feature testing, visual "
        "inspection of every view, goal alignment check). Scores must reflect actual "
        "testing, not assumptions.",
        {
            "features_tested": list[str],
            "bugs_found": list[str],
            "bugs_fixed": list[str],
            "views_screenshotted": list[str],
            "visual_issues": list[str],
            "missing_features": list[str],
            "functionality_score": int,
            "visual_score": int,
            "code_quality_score": int,
            "completeness_score": int,
            "overall_score": int,
            "critique": str,
            "top_improvements": list[str],
            "ready_to_ship": bool,
        },
    )
    async def self_evaluate(args: dict[str, Any]) -> dict[str, Any]:
        return await tool_self_evaluate(project_dir, args)

    @tool(
        "take_screenshot",
        "Capture a screenshot of the running application for visual evaluation. "
        "For views that require interaction (clicking tabs, opening modals, filling "
        "forms), provide a setup_script with Playwright commands to reach that state.",
        {
            "url": str,
            "full_page": bool,
            "wait_seconds": int,
            "output_path": str,
            "viewport_width": int,
            "viewport_height": int,
            "setup_script": str,
            "label": str,
        },
    )
    async def take_screenshot(args: dict[str, Any]) -> dict[str, Any]:
        return await tool_take_screenshot(project_dir, args, default_port=port)

    @tool(
        "write_docs",
        "Create or update project documentation (README, architecture notes, etc.).",
        {
            "file": str,
            "content": str,
            "mode": str,
        },
    )
    async def write_docs(args: dict[str, Any]) -> dict[str, Any]:
        return await tool_write_docs(project_dir, args)

    @tool(
        "smoke_test",
        "Run an interactive smoke test against the running application. Write a test "
        "script with actions (click, type, press keys, navigate) and assertions "
        "(check visibility, text content, element count, console errors). Returns a "
        "structured pass/fail report. Use this to verify features ACTUALLY work — "
        "especially cross-feature interactions like key bindings across app states.\n\n"
        "Actions: click:SELECTOR, fill:SELECTOR TEXT, press:KEY, type:TEXT, "
        "wait:MS, navigate:URL, hover:SELECTOR\n"
        "Assertions: assert_visible:SELECTOR, assert_not_visible:SELECTOR, "
        "assert_text:SELECTOR EXPECTED, assert_count:SELECTOR N, assert_url:PATTERN, "
        "assert_no_errors, assert_eval:JS_EXPRESSION\n"
        "Lines starting with # are comments.",
        {
            "url": str,
            "test_name": str,
            "script": str,
            "viewport_width": int,
            "viewport_height": int,
        },
    )
    async def smoke_test(args: dict[str, Any]) -> dict[str, Any]:
        return await tool_smoke_test(project_dir, args, default_port=port)

    @tool(
        "propose_idea",
        "Propose a new idea phase. Call this when the current idea is complete "
        "(score >= threshold, ready_to_ship). The new idea gets its own git worktree. "
        "Only call when you genuinely believe the current work is done and a new "
        "direction would be more valuable than more polish.",
        {
            "title": str,
            "description": str,
            "relationship": str,
            "carries_forward": list[str],
        },
    )
    async def propose_idea(args: dict[str, Any]) -> dict[str, Any]:
        return await tool_propose_idea(project_dir, args)

    return create_sdk_mcp_server(
        name="iclaw-tools",
        version="1.0.0",
        tools=[
            update_backlog,
            self_evaluate,
            take_screenshot,
            write_docs,
            smoke_test,
            propose_idea,
        ],
    )

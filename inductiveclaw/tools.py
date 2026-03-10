"""Custom MCP tools for InductiveClaw."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from claude_agent_sdk import tool, create_sdk_mcp_server

if TYPE_CHECKING:
    from .config import ClawConfig


def create_iclaw_tools(config: ClawConfig):
    """Create and return the custom MCP server with all InductiveClaw tools."""

    project = Path(config.project_dir).resolve()

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
        backlog_path = project / "BACKLOG.md"
        existing = backlog_path.read_text() if backlog_path.exists() else ""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        sections = [f"\n---\n### Update — {timestamp}\n"]

        completed = args.get("completed_item")
        if completed:
            sections.append(f"**Completed:** {completed}\n")

        priorities = args.get("next_priorities", [])
        if priorities:
            sections.append("**Next priorities:**")
            for i, p in enumerate(priorities, 1):
                sections.append(f"{i}. {p}")
            sections.append("")

        notes = args.get("quality_notes")
        if notes:
            sections.append(f"**Quality notes:** {notes}\n")

        blockers = args.get("blockers", [])
        if blockers:
            sections.append("**Blockers:**")
            for b in blockers:
                sections.append(f"- {b}")
            sections.append("")

        update_text = "\n".join(sections)

        if not existing:
            content = f"# Backlog\n{update_text}"
        else:
            # Move completed item to Completed section if it exists
            if completed and "## Completed" in existing:
                completed_marker = "## Completed"
                idx = existing.index(completed_marker) + len(completed_marker)
                existing = existing[:idx] + f"\n- [x] {completed}" + existing[idx:]
            elif completed:
                existing += f"\n## Completed\n- [x] {completed}\n"

            content = existing + update_text

        backlog_path.write_text(content)
        summary = f"Backlog updated. " + (f"Completed: {completed}. " if completed else "") + f"{len(priorities)} priorities set."
        return {"content": [{"type": "text", "text": summary}]}

    @tool(
        "self_evaluate",
        "Critically evaluate the current project quality. Be honest — scores drive stop conditions.",
        {
            "functionality_score": int,
            "visual_score": int,
            "code_quality_score": int,
            "uniqueness_score": int,
            "overall_score": int,
            "critique": str,
            "top_improvement": str,
            "ready_to_ship": bool,
        },
    )
    async def self_evaluate(args: dict[str, Any]) -> dict[str, Any]:
        eval_path = project / "EVALUATIONS.md"
        existing = eval_path.read_text() if eval_path.exists() else "# Evaluations\n"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"""
---
### Evaluation — {timestamp}

| Category       | Score |
|----------------|-------|
| Functionality  | {args['functionality_score']}/10 |
| Visual         | {args['visual_score']}/10 |
| Code Quality   | {args['code_quality_score']}/10 |
| Uniqueness     | {args['uniqueness_score']}/10 |
| **Overall**    | **{args['overall_score']}/10** |

**Critique:** {args['critique']}

**Top improvement:** {args['top_improvement']}

**Ready to ship:** {'Yes' if args['ready_to_ship'] else 'No'}
"""
        eval_path.write_text(existing + entry)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "overall_score": args["overall_score"],
                            "ready_to_ship": args["ready_to_ship"],
                            "top_improvement": args["top_improvement"],
                        }
                    ),
                }
            ]
        }

    @tool(
        "take_screenshot",
        "Capture a screenshot of the running application for visual evaluation.",
        {
            "url": str,
            "full_page": bool,
            "wait_seconds": int,
            "output_path": str,
        },
    )
    async def take_screenshot(args: dict[str, Any]) -> dict[str, Any]:
        url = args.get("url", f"http://localhost:{config.screenshot_port}")
        full_page = args.get("full_page", True)
        wait_seconds = args.get("wait_seconds", 3)
        output_path = args.get("output_path", str(project / ".iclaw" / "screenshots" / "latest.png"))

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Playwright is not installed. To enable screenshots:\n"
                            "  pip install playwright && playwright install chromium\n"
                            "Falling back to code-only evaluation."
                        ),
                    }
                ]
            }

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                await page.goto(url, wait_until="networkidle", timeout=15000)
                if wait_seconds > 0:
                    await page.wait_for_timeout(wait_seconds * 1000)
                await page.screenshot(path=str(out), full_page=full_page)
                await browser.close()
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Screenshot failed: {e}"}]}

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Screenshot saved to {output_path}. Use the Read tool to view it.",
                }
            ]
        }

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
        doc_path = project / args["file"]
        mode = args.get("mode", "overwrite")

        if mode == "append" and doc_path.exists():
            existing = doc_path.read_text()
            doc_path.write_text(existing + "\n" + args["content"])
        else:
            doc_path.write_text(args["content"])

        return {
            "content": [
                {"type": "text", "text": f"Wrote {args['file']} ({mode})"}
            ]
        }

    return create_sdk_mcp_server(
        name="iclaw-tools",
        version="1.0.0",
        tools=[update_backlog, self_evaluate, take_screenshot, write_docs],
    )

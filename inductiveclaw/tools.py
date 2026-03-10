"""Custom MCP tools for InductiveClaw."""

from __future__ import annotations

import json
import re
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
        eval_path = project / "EVALUATIONS.md"
        existing = eval_path.read_text() if eval_path.exists() else "# Evaluations\n"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        features = args.get("features_tested", [])
        bugs_found = args.get("bugs_found", [])
        bugs_fixed = args.get("bugs_fixed", [])
        views = args.get("views_screenshotted", [])
        visual_issues = args.get("visual_issues", [])
        missing = args.get("missing_features", [])
        improvements = args.get("top_improvements", [])

        features_md = "\n".join(f"  - {f}" for f in features) if features else "  - (none listed)"
        bugs_found_md = "\n".join(f"  - {b}" for b in bugs_found) if bugs_found else "  - (none)"
        bugs_fixed_md = "\n".join(f"  - {b}" for b in bugs_fixed) if bugs_fixed else "  - (none)"
        views_md = "\n".join(f"  - {v}" for v in views) if views else "  - (none)"
        visual_md = "\n".join(f"  - {v}" for v in visual_issues) if visual_issues else "  - (none)"
        missing_md = "\n".join(f"  - {m}" for m in missing) if missing else "  - (none)"
        improvements_md = "\n".join(f"  {i+1}. {imp}" for i, imp in enumerate(improvements)) if improvements else "  1. (none)"

        entry = f"""
---
### Evaluation — {timestamp}

**Features tested ({len(features)}):**
{features_md}

**Bugs found ({len(bugs_found)}):**
{bugs_found_md}

**Bugs fixed ({len(bugs_fixed)}):**
{bugs_fixed_md}

**Views screenshotted ({len(views)}):**
{views_md}

**Visual issues ({len(visual_issues)}):**
{visual_md}

**Missing features ({len(missing)}):**
{missing_md}

| Category        | Score |
|-----------------|-------|
| Functionality   | {args['functionality_score']}/10 |
| Visual/UX       | {args['visual_score']}/10 |
| Code Quality    | {args['code_quality_score']}/10 |
| Completeness    | {args['completeness_score']}/10 |
| **Overall**     | **{args['overall_score']}/10** |

**Critique:** {args['critique']}

**Top improvements:**
{improvements_md}

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
                            "top_improvements": improvements,
                            "bugs_found": len(bugs_found),
                            "bugs_fixed": len(bugs_fixed),
                            "missing_features": missing,
                        }
                    ),
                }
            ]
        }

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
        url = args.get("url", f"http://localhost:{config.screenshot_port}")
        full_page = args.get("full_page", True)
        wait_seconds = args.get("wait_seconds", 3)
        label = args.get("label", "latest")
        safe_label = re.sub(r'[^\w\-]', '_', label)
        output_path = args.get(
            "output_path",
            str(project / ".iclaw" / "screenshots" / f"{safe_label}.png"),
        )
        width = args.get("viewport_width", 1280)
        height = args.get("viewport_height", 720)
        setup_script = args.get("setup_script", "")

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
                page = await browser.new_page(viewport={"width": width, "height": height})
                await page.goto(url, wait_until="networkidle", timeout=15000)

                # Run optional setup commands to reach a specific UI state
                if setup_script:
                    for line in setup_script.strip().split("\n"):
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("click:"):
                            selector = line[len("click:"):].strip()
                            await page.click(selector, timeout=5000)
                        elif line.startswith("fill:"):
                            parts = line[len("fill:"):].strip().split(" ", 1)
                            if len(parts) == 2:
                                await page.fill(parts[0], parts[1], timeout=5000)
                        elif line.startswith("wait:"):
                            ms = int(line[len("wait:"):].strip())
                            await page.wait_for_timeout(ms)
                        elif line.startswith("hover:"):
                            selector = line[len("hover:"):].strip()
                            await page.hover(selector, timeout=5000)
                        elif line.startswith("select:"):
                            parts = line[len("select:"):].strip().split(" ", 1)
                            if len(parts) == 2:
                                await page.select_option(parts[0], parts[1], timeout=5000)
                        elif line.startswith("navigate:"):
                            nav_url = line[len("navigate:"):].strip()
                            await page.goto(nav_url, wait_until="networkidle", timeout=15000)

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
                    "text": f"Screenshot saved to {output_path} (label: {label}). "
                            f"Use the Read tool to view it and inspect for visual issues.",
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

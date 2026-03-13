"""Pure tool implementations — no SDK imports, no decorators.

Each tool is an async function that takes (project_dir, args) and returns
a dict matching the MCP tool result format:
    {"content": [{"type": "text", "text": "..."}]}

TOOL_SCHEMAS provides JSON-schema-style parameter definitions for each tool,
used by non-Claude backends to register function-calling tools.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# --- Tool schemas for non-Claude backends ---

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "update_backlog": {
        "description": (
            "Update the project backlog. Call after completing a feature "
            "or during planning."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "completed_item": {"type": "string"},
                "next_priorities": {"type": "array", "items": {"type": "string"}},
                "quality_notes": {"type": "string"},
                "blockers": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "self_evaluate": {
        "description": (
            "Critically evaluate the current project quality. Call ONLY after "
            "completing the full review protocol (feature inventory, per-feature "
            "testing, visual inspection of every view, goal alignment check). "
            "Scores must reflect actual testing, not assumptions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "features_tested": {"type": "array", "items": {"type": "string"}},
                "bugs_found": {"type": "array", "items": {"type": "string"}},
                "bugs_fixed": {"type": "array", "items": {"type": "string"}},
                "views_screenshotted": {"type": "array", "items": {"type": "string"}},
                "visual_issues": {"type": "array", "items": {"type": "string"}},
                "missing_features": {"type": "array", "items": {"type": "string"}},
                "functionality_score": {"type": "integer"},
                "visual_score": {"type": "integer"},
                "code_quality_score": {"type": "integer"},
                "completeness_score": {"type": "integer"},
                "overall_score": {"type": "integer"},
                "critique": {"type": "string"},
                "top_improvements": {"type": "array", "items": {"type": "string"}},
                "ready_to_ship": {"type": "boolean"},
            },
            "required": [
                "functionality_score", "visual_score", "code_quality_score",
                "completeness_score", "overall_score", "critique", "ready_to_ship",
            ],
        },
    },
    "take_screenshot": {
        "description": (
            "Capture a screenshot of the running application for visual evaluation. "
            "For views that require interaction (clicking tabs, opening modals, "
            "filling forms), provide a setup_script with Playwright commands to "
            "reach that state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "full_page": {"type": "boolean"},
                "wait_seconds": {"type": "integer"},
                "output_path": {"type": "string"},
                "viewport_width": {"type": "integer"},
                "viewport_height": {"type": "integer"},
                "setup_script": {"type": "string"},
                "label": {"type": "string"},
            },
        },
    },
    "write_docs": {
        "description": (
            "Create or update project documentation (README, architecture notes, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["overwrite", "append"]},
            },
            "required": ["file", "content"],
        },
    },
    "smoke_test": {
        "description": (
            "Run an interactive smoke test against the running application. "
            "Write a test script with actions (click, type, press keys, navigate) "
            "and assertions (check visibility, text content, element count, "
            "console errors). Returns a structured pass/fail report.\n\n"
            "Actions: click:SELECTOR, fill:SELECTOR TEXT, press:KEY, type:TEXT, "
            "wait:MS, navigate:URL, hover:SELECTOR\n"
            "Assertions: assert_visible:SELECTOR, assert_not_visible:SELECTOR, "
            "assert_text:SELECTOR EXPECTED, assert_count:SELECTOR N, "
            "assert_url:PATTERN, assert_no_errors, assert_eval:JS_EXPRESSION\n"
            "Lines starting with # are comments."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "test_name": {"type": "string"},
                "script": {"type": "string"},
                "viewport_width": {"type": "integer"},
                "viewport_height": {"type": "integer"},
            },
            "required": ["script"],
        },
    },
    "propose_idea": {
        "description": (
            "Propose a new idea phase. Call this when the current idea is complete "
            "(score >= threshold, ready_to_ship). The new idea gets its own git "
            "worktree. Only call when you genuinely believe the current work is "
            "done and a new direction would be more valuable than more polish."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "relationship": {"type": "string"},
                "carries_forward": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "description"],
        },
    },
}


# --- Pure tool implementations ---

async def tool_update_backlog(
    project_dir: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Update the project backlog."""
    project = Path(project_dir).resolve()
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
        if completed and "## Completed" in existing:
            completed_marker = "## Completed"
            idx = existing.index(completed_marker) + len(completed_marker)
            existing = existing[:idx] + f"\n- [x] {completed}" + existing[idx:]
        elif completed:
            existing += f"\n## Completed\n- [x] {completed}\n"
        content = existing + update_text

    backlog_path.write_text(content)
    summary = (
        "Backlog updated. "
        + (f"Completed: {completed}. " if completed else "")
        + f"{len(priorities)} priorities set."
    )
    return {"content": [{"type": "text", "text": summary}]}


async def tool_self_evaluate(
    project_dir: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Critically evaluate the current project quality."""
    project = Path(project_dir).resolve()
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
    improvements_md = (
        "\n".join(f"  {i+1}. {imp}" for i, imp in enumerate(improvements))
        if improvements
        else "  1. (none)"
    )

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
                "text": json.dumps({
                    "overall_score": args["overall_score"],
                    "ready_to_ship": args["ready_to_ship"],
                    "top_improvements": improvements,
                    "bugs_found": len(bugs_found),
                    "bugs_fixed": len(bugs_fixed),
                    "missing_features": missing,
                }),
            }
        ]
    }


async def tool_take_screenshot(
    project_dir: str,
    args: dict[str, Any],
    default_port: int = 3000,
) -> dict[str, Any]:
    """Capture a screenshot of the running application."""
    project = Path(project_dir).resolve()
    url = args.get("url", f"http://localhost:{default_port}")
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
            page = await browser.new_page(
                viewport={"width": width, "height": height},
            )
            await page.goto(url, wait_until="networkidle", timeout=15000)

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
                            await page.select_option(
                                parts[0], parts[1], timeout=5000,
                            )
                    elif line.startswith("navigate:"):
                        nav_url = line[len("navigate:"):].strip()
                        await page.goto(
                            nav_url, wait_until="networkidle", timeout=15000,
                        )

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
                "text": (
                    f"Screenshot saved to {output_path} (label: {label}). "
                    f"Use the Read tool to view it and inspect for visual issues."
                ),
            }
        ]
    }


async def tool_write_docs(
    project_dir: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Create or update project documentation."""
    project = Path(project_dir).resolve()
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


async def tool_smoke_test(
    project_dir: str,
    args: dict[str, Any],
    default_port: int = 3000,
) -> dict[str, Any]:
    """Run an interactive smoke test against the running application."""
    project = Path(project_dir).resolve()
    url = args.get("url", f"http://localhost:{default_port}")
    test_name = args.get("test_name", "unnamed test")
    script = args.get("script", "")
    width = args.get("viewport_width", 1280)
    height = args.get("viewport_height", 720)

    if not script.strip():
        return {"content": [{"type": "text", "text": "Error: empty test script."}]}

    try:
        from .smoke import run_smoke_test, format_smoke_report, save_smoke_report
    except ImportError:
        pass

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Playwright is not installed. To enable smoke tests:\n"
                        "  pip install playwright && playwright install chromium"
                    ),
                }
            ]
        }

    try:
        results, console_errors, passed, failed = await run_smoke_test(
            url=url, script=script, width=width, height=height,
        )
        report = format_smoke_report(
            test_name, results, console_errors, passed, failed,
        )
        save_smoke_report(project, test_name, report)
        return {"content": [{"type": "text", "text": report}]}
    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": f"Smoke test failed: {e}"}
            ]
        }


async def tool_propose_idea(
    project_dir: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Propose a new idea phase."""
    project = Path(project_dir).resolve()
    title = args.get("title", "untitled")
    desc = args.get("description", "")
    rel = args.get("relationship", "extension")
    carries = args.get("carries_forward", [])

    proposal_path = project / ".iclaw" / "idea_proposal.json"
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(json.dumps({
        "title": title,
        "description": desc,
        "relationship": rel,
        "carries_forward": carries,
        "proposed_at": datetime.now().isoformat(),
    }, indent=2))

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Idea proposed: '{title}' ({rel}). "
                    f"The outer loop will create a new worktree for this idea. "
                    f"Finish any final housekeeping on the current idea, then "
                    f"the next iteration will start in the new workspace."
                ),
            }
        ]
    }

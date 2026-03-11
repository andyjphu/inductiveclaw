"""Playwright-based smoke test runner for interactive app verification."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


async def _run_action(page: Any, line: str) -> dict[str, Any] | None:
    """Execute a single action command. Returns result dict or None."""
    if line.startswith("click:"):
        selector = line[len("click:"):].strip()
        await page.click(selector, timeout=5000)
    elif line.startswith("fill:"):
        parts = line[len("fill:"):].strip().split(" ", 1)
        if len(parts) == 2:
            await page.fill(parts[0], parts[1], timeout=5000)
    elif line.startswith("press:"):
        key = line[len("press:"):].strip()
        await page.keyboard.press(key)
    elif line.startswith("type:"):
        text = line[len("type:"):].strip()
        await page.keyboard.type(text)
    elif line.startswith("wait:"):
        ms = int(line[len("wait:"):].strip())
        await page.wait_for_timeout(ms)
    elif line.startswith("navigate:"):
        nav_url = line[len("navigate:"):].strip()
        await page.goto(nav_url, wait_until="networkidle", timeout=15000)
    elif line.startswith("hover:"):
        selector = line[len("hover:"):].strip()
        await page.hover(selector, timeout=5000)
    else:
        return None  # Not an action
    return {"status": "ok"}


async def _run_assertion(
    page: Any, line: str, console_errors: list[str]
) -> dict[str, Any]:
    """Execute a single assertion. Returns result with status PASS/FAIL."""
    if line.startswith("assert_visible:"):
        selector = line[len("assert_visible:"):].strip()
        el = await page.query_selector(selector)
        visible = await el.is_visible() if el else False
        if visible:
            return {"status": "PASS"}
        return {"status": "FAIL", "detail": f"'{selector}' not visible or not found"}

    if line.startswith("assert_not_visible:"):
        selector = line[len("assert_not_visible:"):].strip()
        el = await page.query_selector(selector)
        visible = await el.is_visible() if el else False
        if not visible:
            return {"status": "PASS"}
        return {"status": "FAIL", "detail": f"'{selector}' is visible (expected hidden)"}

    if line.startswith("assert_text:"):
        rest = line[len("assert_text:"):].strip()
        parts = rest.split(" ", 1)
        if len(parts) != 2:
            return {"status": "FAIL", "detail": "bad syntax: assert_text:SELECTOR EXPECTED_TEXT"}
        selector, expected = parts
        el = await page.query_selector(selector)
        actual = (await el.text_content() or "").strip() if el else ""
        if expected in actual:
            return {"status": "PASS"}
        return {"status": "FAIL", "detail": f"expected '{expected}' in '{actual[:100]}'"}

    if line.startswith("assert_count:"):
        rest = line[len("assert_count:"):].strip()
        parts = rest.split(" ", 1)
        if len(parts) != 2:
            return {"status": "FAIL", "detail": "bad syntax: assert_count:SELECTOR COUNT"}
        selector, expected_count = parts
        els = await page.query_selector_all(selector)
        actual_count = len(els)
        if actual_count == int(expected_count):
            return {"status": "PASS"}
        return {
            "status": "FAIL",
            "detail": f"expected {expected_count} elements, found {actual_count}",
        }

    if line.startswith("assert_url:"):
        pattern = line[len("assert_url:"):].strip()
        current = page.url
        if pattern in current:
            return {"status": "PASS"}
        return {"status": "FAIL", "detail": f"URL is '{current}', expected to contain '{pattern}'"}

    if line.startswith("assert_no_errors"):
        errors_only = [
            e for e in console_errors
            if e.startswith("[error]") or e.startswith("[uncaught]")
        ]
        if not errors_only:
            return {"status": "PASS"}
        return {
            "status": "FAIL",
            "detail": f"{len(errors_only)} console errors: " + "; ".join(errors_only[:5]),
        }

    if line.startswith("assert_eval:"):
        js_expr = line[len("assert_eval:"):].strip()
        result = await page.evaluate(js_expr)
        if result:
            return {"status": "PASS", "detail": f"returned: {result}"}
        return {"status": "FAIL", "detail": f"expression returned falsy: {result}"}

    return {"status": "FAIL", "detail": f"unknown assertion: {line}"}


async def run_smoke_test(
    url: str,
    script: str,
    width: int = 1280,
    height: int = 720,
) -> tuple[list[dict[str, Any]], list[str], int, int]:
    """Run a smoke test script and return (results, console_errors, passed, failed)."""
    from playwright.async_api import async_playwright

    console_errors: list[str] = []
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})

        page.on(
            "console",
            lambda msg: console_errors.append(f"[{msg.type}] {msg.text}")
            if msg.type in ("error", "warning")
            else None,
        )
        page.on(
            "pageerror",
            lambda err: console_errors.append(f"[uncaught] {err}"),
        )

        await page.goto(url, wait_until="networkidle", timeout=15000)

        for line_num, raw_line in enumerate(script.strip().split("\n"), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                # Try as action first
                action_result = await _run_action(page, line)
                if action_result is not None:
                    results.append({"line": line_num, "action": line, **action_result})
                    continue

                # Try as assertion
                if line.startswith("assert_"):
                    assertion_result = await _run_assertion(page, line, console_errors)
                    desc_key = "assertion"
                    results.append({"line": line_num, desc_key: line, **assertion_result})
                    if assertion_result["status"] == "PASS":
                        passed += 1
                    else:
                        failed += 1
                else:
                    results.append(
                        {"line": line_num, "action": line, "status": "unknown command"}
                    )

            except Exception as e:
                failed += 1
                results.append(
                    {"line": line_num, "action": line, "status": "ERROR", "detail": str(e)}
                )

        await browser.close()

    return results, console_errors, passed, failed


def format_smoke_report(
    test_name: str,
    results: list[dict[str, Any]],
    console_errors: list[str],
    passed: int,
    failed: int,
) -> str:
    """Format smoke test results into a readable report."""
    lines = [f"## Smoke Test: {test_name}\n"]
    lines.append(
        f"**Result: {passed} passed, {failed} failed, "
        f"{len(console_errors)} console messages**\n"
    )

    for r in results:
        status = r["status"]
        desc = r.get("assertion") or r.get("action", "?")
        detail = r.get("detail", "")
        if status == "PASS":
            lines.append(f"  PASS  {desc}")
        elif status == "FAIL":
            lines.append(f"  FAIL  {desc}")
            if detail:
                lines.append(f"        -> {detail}")
        elif status == "ERROR":
            lines.append(f"  ERR   {desc}")
            if detail:
                lines.append(f"        -> {detail}")

    if console_errors:
        lines.append(f"\n**Console output ({len(console_errors)}):**")
        for err in console_errors[:20]:
            lines.append(f"  {err}")
        if len(console_errors) > 20:
            lines.append(f"  ... and {len(console_errors) - 20} more")

    return "\n".join(lines)


def save_smoke_report(project: Path, test_name: str, report: str) -> Path:
    """Save a smoke test report to the .iclaw/smoke-tests directory."""
    report_dir = project / ".iclaw" / "smoke-tests"
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[^\w\-]', '_', test_name)
    report_path = report_dir / f"{safe_name}.txt"
    report_path.write_text(report)
    return report_path

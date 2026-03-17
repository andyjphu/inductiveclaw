"""Browser-based product evaluation engine.

Launches a headless browser, systematically interacts with the built
application, and reports objective findings: console errors, keybinding
conflicts, broken interactions, and network failures.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class KeyBinding:
    """A single keyboard event binding found in the app."""

    key: str
    event_type: str  # keydown, keyup, keypress
    handler_id: str
    context: str  # element description


@dataclass
class KeybindingConflict:
    """Two or more handlers bound to the same key."""

    key: str
    event_type: str
    handlers: list[KeyBinding]
    severity: str  # "critical" or "warning"


@dataclass
class InteractionResult:
    """Result of a single interaction attempt."""

    action: str
    target: str
    success: bool
    error: str | None = None


@dataclass
class BrowserEvalReport:
    """Structured output from a browser evaluation session."""

    url: str
    routes_discovered: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    console_warnings: list[str] = field(default_factory=list)
    network_errors: list[dict[str, str]] = field(default_factory=list)
    keybinding_conflicts: list[KeybindingConflict] = field(default_factory=list)
    all_keybindings: list[KeyBinding] = field(default_factory=list)
    broken_interactions: list[InteractionResult] = field(default_factory=list)
    successful_interactions: int = 0
    total_interactions: int = 0
    screenshots: list[str] = field(default_factory=list)
    health_score: int = 10
    findings_summary: str = ""

    def compute_health_score(self) -> int:
        """Compute objective health score from findings."""
        score = 10
        score -= min(4, len(self.console_errors))
        score -= min(4, len(self.keybinding_conflicts) * 2)
        score -= min(2, len(self.network_errors))
        if self.total_interactions > 0:
            broken_ratio = len(self.broken_interactions) / self.total_interactions
            score -= min(2, int(broken_ratio * 10))
        self.health_score = max(0, score)
        return self.health_score

    def build_summary(self) -> str:
        """Build a human-readable findings summary."""
        parts: list[str] = []
        if self.console_errors:
            parts.append(f"{len(self.console_errors)} console error(s)")
        if self.keybinding_conflicts:
            parts.append(f"{len(self.keybinding_conflicts)} keybinding conflict(s)")
        if self.network_errors:
            parts.append(f"{len(self.network_errors)} network error(s)")
        if self.broken_interactions:
            parts.append(
                f"{len(self.broken_interactions)}/{self.total_interactions} "
                f"interactions failed"
            )
        if not parts:
            parts.append("No issues found")
        self.findings_summary = "; ".join(parts)
        return self.findings_summary

    def to_markdown(self) -> str:
        """Format report as markdown."""
        lines = [
            "# Browser Evaluation Report",
            f"\n**URL:** {self.url}",
            f"**Health Score:** {self.health_score}/10",
            f"**Routes Discovered:** {len(self.routes_discovered)}",
            f"**Interactions:** {self.successful_interactions}/{self.total_interactions} succeeded",
            f"\n**Summary:** {self.findings_summary}",
        ]

        if self.console_errors:
            lines.append("\n## Console Errors")
            for err in self.console_errors[:20]:
                lines.append(f"- {err[:200]}")

        if self.keybinding_conflicts:
            lines.append("\n## Keybinding Conflicts")
            for c in self.keybinding_conflicts:
                lines.append(
                    f"- **{c.key}** ({c.event_type}) — {c.severity}: "
                    f"{len(c.handlers)} handlers"
                )
                for h in c.handlers:
                    lines.append(f"  - {h.context} (handler: {h.handler_id})")

        if self.network_errors:
            lines.append("\n## Network Errors")
            for ne in self.network_errors[:20]:
                lines.append(f"- {ne.get('method', '?')} {ne.get('url', '?')} → {ne.get('status', '?')}")

        if self.broken_interactions:
            lines.append("\n## Broken Interactions")
            for bi in self.broken_interactions[:20]:
                lines.append(f"- {bi.action} `{bi.target}` — {bi.error or 'failed'}")

        if self.routes_discovered:
            lines.append("\n## Discovered Routes")
            for r in self.routes_discovered:
                lines.append(f"- {r}")

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Keybinding interceptor JS
# ---------------------------------------------------------------------------

_KEYBINDING_INTERCEPTOR_JS = """
(function() {
    window.__iclaw_keybindings = [];
    const origAdd = EventTarget.prototype.addEventListener;
    let handlerId = 0;
    EventTarget.prototype.addEventListener = function(type, fn, opts) {
        if (['keydown', 'keyup', 'keypress'].includes(type)) {
            const id = 'kb_' + (handlerId++);
            let el = 'unknown';
            if (this === document || this === window) {
                el = 'document/window';
            } else if (this.tagName) {
                el = this.tagName.toLowerCase();
                if (this.id) el += '#' + this.id;
                else if (this.className && typeof this.className === 'string')
                    el += '.' + this.className.split(' ')[0];
            }
            window.__iclaw_keybindings.push({
                id: id,
                type: type,
                element: el,
                handlerSource: fn.toString().substring(0, 500),
            });
        }
        return origAdd.call(this, type, fn, opts);
    };
})();
"""

# Patterns to extract key names from handler source code
_KEY_PATTERNS = [
    re.compile(r"""['"](?:Key)?([A-Za-z])['"]"""),
    re.compile(r"""['"](?:Arrow(?:Up|Down|Left|Right)|Space|Enter|Escape|Tab)['"]""", re.I),
    re.compile(r"""\.(?:key|code)\s*===?\s*['"]([^'"]+)['"]"""),
    re.compile(r"""\.which\s*===?\s*(\d+)"""),
    re.compile(r"""\.keyCode\s*===?\s*(\d+)"""),
]

# Common interactive keys to test
_TEST_KEYS = [
    "Space", "Enter", "Escape", "Tab",
    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "KeyW", "KeyA", "KeyS", "KeyD",
]


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

async def run_browser_eval(
    url: str,
    *,
    interaction_depth: int = 2,
    check_keybindings: bool = True,
    check_responsive: bool = False,
    screenshot_dir: str | None = None,
    timeout_ms: int = 30_000,
) -> BrowserEvalReport:
    """Launch browser, explore app, return objective findings."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        report = BrowserEvalReport(url=url)
        report.findings_summary = (
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )
        return report

    report = BrowserEvalReport(url=url)
    ss_dir = Path(screenshot_dir) if screenshot_dir else None
    if ss_dir:
        ss_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})

        if check_keybindings:
            await context.add_init_script(_KEYBINDING_INTERCEPTOR_JS)

        page = await context.new_page()

        # Collect console errors and warnings
        def _on_console(msg: Any) -> None:
            if msg.type == "error":
                report.console_errors.append(msg.text)
            elif msg.type == "warning":
                report.console_warnings.append(msg.text)

        def _on_page_error(err: Any) -> None:
            report.console_errors.append(str(err))

        page.on("console", _on_console)
        page.on("pageerror", _on_page_error)

        # Monitor network failures
        def _on_response(response: Any) -> None:
            if response.status >= 400:
                report.network_errors.append({
                    "url": response.url,
                    "status": str(response.status),
                    "method": response.request.method,
                })

        page.on("response", _on_response)

        # Navigate to app
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except Exception as exc:
            report.console_errors.append(f"Failed to load {url}: {exc}")
            report.compute_health_score()
            report.build_summary()
            await browser.close()
            return report

        report.routes_discovered.append(url)

        # Take initial screenshot
        if ss_dir:
            path = str(ss_dir / "initial.png")
            await page.screenshot(path=path, full_page=True)
            report.screenshots.append(path)

        # Discover routes
        discovered = await _discover_routes(page, url)
        report.routes_discovered.extend(discovered)

        # Explore main page
        await _explore_page(page, report, ss_dir, interaction_depth)

        # Visit discovered routes and explore each
        for route in discovered[:10]:  # cap at 10 routes
            try:
                await page.goto(route, wait_until="networkidle", timeout=timeout_ms)
                await _explore_page(page, report, ss_dir, max(1, interaction_depth - 1))
            except Exception:
                pass  # Route may be a hash anchor or dead link

        # Collect keybinding data
        if check_keybindings:
            bindings = await _collect_keybindings(page)
            report.all_keybindings = bindings
            report.keybinding_conflicts = _detect_conflicts(bindings)

        await browser.close()

    report.compute_health_score()
    report.build_summary()
    return report


async def _discover_routes(page: Any, base_url: str) -> list[str]:
    """Find all internal links on the current page."""
    parsed_base = urlparse(base_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

    links: list[str] = await page.evaluate("""() => {
        const anchors = document.querySelectorAll('a[href]');
        return Array.from(anchors).map(a => a.href).filter(h => h.startsWith('http'));
    }""")

    # Filter to same-origin links, deduplicate
    seen: set[str] = {base_url}
    routes: list[str] = []
    for link in links:
        parsed = urlparse(link)
        link_origin = f"{parsed.scheme}://{parsed.netloc}"
        if link_origin == base_origin and link not in seen:
            seen.add(link)
            routes.append(link)

    return routes


async def _explore_page(
    page: Any,
    report: BrowserEvalReport,
    screenshot_dir: Path | None,
    depth: int,
) -> None:
    """Systematically interact with all discoverable elements on a page."""
    if depth <= 0:
        return

    # Query interactive elements
    elements = await page.evaluate("""() => {
        const selectors = 'button, a, input, select, textarea, [role="button"], [onclick], [tabindex]';
        const els = document.querySelectorAll(selectors);
        return Array.from(els).slice(0, 50).map((el, i) => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            role: el.getAttribute('role') || '',
            text: (el.textContent || '').trim().substring(0, 50),
            id: el.id || '',
            className: (typeof el.className === 'string' ? el.className : '').split(' ')[0],
            index: i,
        }));
    }""")

    for el in elements:
        selector = _build_selector(el)
        if not selector:
            continue

        tag = el.get("tag", "")
        el_type = el.get("type", "")

        if tag in ("button", "a") or el.get("role") == "button":
            await _try_interaction(page, report, "click", selector)
        elif tag == "input" and el_type in ("text", "email", "search", "tel", "url", ""):
            test_value = "test@example.com" if el_type == "email" else "test input"
            await _try_interaction(page, report, "fill", selector, test_value)
        elif tag == "textarea":
            await _try_interaction(page, report, "fill", selector, "test content")
        elif tag == "select":
            await _try_interaction(page, report, "select_first", selector)

    # Test keyboard inputs
    for key in _TEST_KEYS:
        await _try_interaction(page, report, "press", key)


async def _try_interaction(
    page: Any,
    report: BrowserEvalReport,
    action: str,
    target: str,
    value: str | None = None,
) -> None:
    """Attempt a single interaction and record the result."""
    report.total_interactions += 1
    try:
        if action == "click":
            await page.click(target, timeout=3000)
        elif action == "fill":
            await page.fill(target, value or "", timeout=3000)
        elif action == "press":
            await page.keyboard.press(target)
        elif action == "select_first":
            # Select the second option (first non-default)
            options = await page.evaluate(
                f"""() => {{
                    const sel = document.querySelector('{target}');
                    if (!sel || sel.options.length < 2) return null;
                    return sel.options[1].value;
                }}"""
            )
            if options:
                await page.select_option(target, options, timeout=3000)

        report.successful_interactions += 1
    except Exception as exc:
        report.broken_interactions.append(
            InteractionResult(
                action=action,
                target=target,
                success=False,
                error=str(exc)[:150],
            )
        )


def _build_selector(el: dict[str, Any]) -> str | None:
    """Build a CSS selector from element info."""
    if el.get("id"):
        return f"#{el['id']}"
    tag = el.get("tag", "")
    cls = el.get("className", "")
    if cls:
        return f"{tag}.{cls}"
    idx = el.get("index", 0)
    selectors = 'button, a, input, select, textarea, [role="button"], [onclick], [tabindex]'
    return f":nth-match({selectors}, {idx + 1})"


async def _collect_keybindings(page: Any) -> list[KeyBinding]:
    """Read intercepted keybinding data from the page."""
    try:
        raw: list[dict[str, str]] = await page.evaluate(
            "() => window.__iclaw_keybindings || []"
        )
    except Exception:
        return []

    bindings: list[KeyBinding] = []
    for entry in raw:
        source = entry.get("handlerSource", "")
        keys = _extract_keys_from_source(source)
        event_type = entry.get("type", "keydown")
        handler_id = entry.get("id", "unknown")
        context = entry.get("element", "unknown")

        if keys:
            for key in keys:
                bindings.append(
                    KeyBinding(
                        key=key,
                        event_type=event_type,
                        handler_id=handler_id,
                        context=context,
                    )
                )
        else:
            # Handler exists but couldn't extract specific keys — record as "any"
            bindings.append(
                KeyBinding(
                    key="<unknown>",
                    event_type=event_type,
                    handler_id=handler_id,
                    context=context,
                )
            )

    return bindings


def _extract_keys_from_source(source: str) -> list[str]:
    """Extract key names from a handler's source code."""
    keys: set[str] = set()
    for pattern in _KEY_PATTERNS:
        for match in pattern.finditer(source):
            # Use capture group if available, otherwise full match
            val = match.group(1) if match.lastindex else match.group(0)
            keys.add(val.strip("'\""))
    return sorted(keys)


def _detect_conflicts(bindings: list[KeyBinding]) -> list[KeybindingConflict]:
    """Group bindings by key+event_type, flag duplicates as conflicts."""
    groups: dict[str, list[KeyBinding]] = defaultdict(list)
    for b in bindings:
        if b.key == "<unknown>":
            continue
        group_key = f"{b.key}:{b.event_type}"
        groups[group_key].append(b)

    conflicts: list[KeybindingConflict] = []
    for group_key, handlers in groups.items():
        if len(handlers) < 2:
            continue
        key, event_type = group_key.rsplit(":", 1)
        # Same element = critical, different elements = warning
        contexts = {h.context for h in handlers}
        severity = "warning" if len(contexts) > 1 else "critical"
        conflicts.append(
            KeybindingConflict(
                key=key,
                event_type=event_type,
                handlers=handlers,
                severity=severity,
            )
        )

    return conflicts

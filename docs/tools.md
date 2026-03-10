# Custom MCP Tools

InductiveClaw registers four custom tools via an in-process MCP server. These extend the Claude Code built-in tools (Bash, Read, Write, Edit, Glob, Grep).

Tools are accessed as `mcp__iclaw-tools__<tool_name>` in the SDK's `allowed_tools` list.

## update_backlog

**Purpose:** Maintain a living `BACKLOG.md` in the project root.

**When called:** After completing each feature and during planning phases.

| Parameter | Type | Description |
|-----------|------|-------------|
| `completed_item` | str | Feature just completed (optional) |
| `next_priorities` | list[str] | Updated priority list |
| `quality_notes` | str | Notes on current quality (optional) |
| `blockers` | list[str] | Known issues / stuck points (optional) |

**Behavior:**
- Appends timestamped update section to BACKLOG.md
- Moves completed items to a `## Completed` section with checkmarks
- Creates the file if it doesn't exist
- Returns summary string

**Outer loop integration:** `_extract_iteration_results()` parses `**Completed:**` lines to populate `tracker.features_completed`.

## self_evaluate

**Purpose:** Force critical quality assessment. Scores drive the stop condition.

| Parameter | Type | Description |
|-----------|------|-------------|
| `functionality_score` | int | 1-10: Does it work? |
| `visual_score` | int | 1-10: Does it look polished? |
| `code_quality_score` | int | 1-10: Clean and well-structured? |
| `uniqueness_score` | int | 1-10: Personality/style? |
| `overall_score` | int | 1-10: Portfolio-worthy? |
| `critique` | str | Honest text critique |
| `top_improvement` | str | Single most impactful next step |
| `ready_to_ship` | bool | Overall readiness |

**Behavior:**
- Appends structured markdown table to `EVALUATIONS.md`
- Returns JSON with `overall_score`, `ready_to_ship`, `top_improvement`

**Outer loop integration:** `_extract_iteration_results()` parses `**Overall** | **N/10**` and `**Ready to ship:** Yes/No` to determine `should_stop`. Stop condition: `overall_score >= config.quality_threshold AND ready_to_ship == True`.

## take_screenshot

**Purpose:** Capture the running application for visual evaluation.

| Parameter | Type | Default |
|-----------|------|---------|
| `url` | str | `http://localhost:{config.screenshot_port}` |
| `full_page` | bool | `True` |
| `wait_seconds` | int | `3` |
| `output_path` | str | `.iclaw/screenshots/latest.png` |

**Behavior:**
- Requires `playwright` (optional dependency)
- Launches headless Chromium, navigates, waits, screenshots
- If Playwright not installed: returns instructions, agent falls back to code-only evaluation
- Saved file can be inspected via the built-in `Read` tool (multimodal)

## write_docs

**Purpose:** Create/update project documentation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `file` | str | Filename relative to project root (e.g. `README.md`) |
| `content` | str | Full file content |
| `mode` | str | `overwrite` (default) or `append` |

Intentionally simple — having it as a named tool makes the agent more likely to write documentation.

## Registration

All tools are bundled via `create_sdk_mcp_server()`:

```python
create_sdk_mcp_server(
    name="iclaw-tools",
    version="1.0.0",
    tools=[update_backlog, self_evaluate, take_screenshot, write_docs],
)
```

The returned `McpSdkServerConfig` is passed to `ClaudeAgentOptions.mcp_servers`.

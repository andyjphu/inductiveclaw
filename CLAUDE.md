# InductiveClaw — Project Rules

## What This Is

Autonomous iterative coding agent wrapping the Claude Agent SDK. CLI tool `iclaw` that continuously builds, verifies, evaluates, and iterates on a software project.

## Project Structure

```
inductiveclaw/
├── pyproject.toml              # Package metadata, deps, CLI entrypoint
├── CLAUDE.md                   # This file — project rules
├── README.md                   # User-facing docs
├── LICENSE                     # MIT
├── dev_install.sh              # Editable install for development
├── docs/                       # Internal documentation
│   ├── architecture.md         # Module graph, data flow, design decisions
│   ├── auth.md                 # OAuth-first auth strategy
│   ├── tools.md                # Custom MCP tool specs
│   ├── iteration-loop.md       # Outer loop, stop conditions, error handling
│   ├── sdk-integration.md      # Claude Agent SDK API reference
│   └── cli.md                  # CLI flags and usage examples
└── inductiveclaw/              # Python package
    ├── __init__.py
    ├── __main__.py             # CLI entrypoint (argparse → config → run)
    ├── auth.py                 # OAuth / API key resolution
    ├── agent.py                # Outer loop, SDK calls, result extraction
    ├── tools.py                # Custom MCP tools (backlog, evaluate, screenshot, docs)
    ├── config.py               # ClawConfig + UsageTracker dataclasses
    ├── display.py              # Rich terminal output
    └── prompts/                # All prompt templates
        ├── __init__.py         # Re-exports SYSTEM_PROMPT, build_iteration_prompt
        ├── system.py           # Loads system.md
        ├── system.md           # System prompt (constant across iterations)
        ├── iteration.py        # Loads .md templates, builds per-iteration prompt
        ├── iteration_first.md  # Template for iteration 1 ({goal})
        ├── iteration_next.md   # Template for iterations 2+ ({goal}, {iteration}, {context})
        ├── eval_trigger.md     # Injected on evaluation iterations
        └── screenshot_trigger.md  # Injected when screenshots enabled
```

## Coding Conventions

- **Python >=3.10.** All files use `from __future__ import annotations`.
- **Async with anyio** — matches the Agent SDK runtime. No raw `asyncio`.
- **No module >300 lines.** Split if approaching.
- **No circular imports.** Dependency graph is strictly layered (see docs/architecture.md).
- **Type hints everywhere.** Use `TYPE_CHECKING` for import-only types.
- **Rich for terminal output** with plain-text fallback if Rich is missing.

## Module Boundaries

- **`auth.py`** — single source of truth for auth. Nothing else touches env vars or tokens.
- **`agent.py`** — the brain. Calls SDK, manages loop. Does NOT know how auth works internally.
- **`tools.py`** — MCP tool definitions only. Business logic stays minimal.
- **`config.py`** — pure data. No logic beyond simple calculations.
- **`display.py`** — all terminal UI. Other modules call display functions, never `print()`.
- **`__main__.py`** — thin CLI glue. No business logic.
- **`prompts/`** — all prompt text lives in `.md` files. Python files load them via `importlib.resources`. Edit the `.md` to change prompts, not the `.py`.

## Key Technical Details

- **SDK package:** `claude-agent-sdk` (import as `claude_agent_sdk`), currently v0.1.48
- **Auth trick:** OAuth = strip `ANTHROPIC_API_KEY` from env so CLI falls through to stored credentials
- **Tool naming:** `mcp__iclaw-tools__<tool_name>` in `allowed_tools`
- **Stop condition:** `overall_score >= threshold AND ready_to_ship == True` (parsed from EVALUATIONS.md)
- **Result extraction:** Regex on EVALUATIONS.md and BACKLOG.md after each iteration
- **Permission mode:** `bypassPermissions` — fully autonomous, no human approval prompts

## Development

```bash
./dev_install.sh               # One-time setup (creates .venv, editable install)
source .venv/bin/activate      # Activate
iclaw --help                   # Verify
python -m build                # Build sdist + wheel
twine check dist/*             # Validate for PyPI
```

## Build Backend

Hatchling. The correct backend path is `hatchling.build` (NOT `hatchling.backends`).

## Don't

- Don't put prompts inline in Python files — they live in `prompts/*.md`.
- Don't import auth internals outside auth.py — use `AuthResult.get_sdk_env()`.
- Don't print directly — use `display.*` functions.
- Don't add deps without updating `pyproject.toml`.
- Don't exceed 300 lines per module.

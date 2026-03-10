# InductiveClaw — Project Rules

## What This Is

Autonomous iterative coding agent wrapping the Claude Agent SDK. Two modes:
- **Interactive** (`iclaw`): REPL with `ClaudeSDKClient`, multi-turn conversation
- **Autonomous** (`iclaw -g "goal"`): Iteration loop that builds until quality threshold

## Project Structure

```
inductiveclaw/
├── pyproject.toml              # Package "iclaw" on PyPI, Python package "inductiveclaw"
├── CLAUDE.md                   # This file — project rules
├── README.md                   # User-facing docs
├── LICENSE                     # MIT
├── dev_install.sh              # pip install -e .
├── docs/                       # Internal documentation
│   ├── architecture.md         # Module graph, data flow, design decisions
│   ├── providers.md            # Provider system, auth modes, cycling
│   ├── tools.md                # Custom MCP tool specs
│   ├── iteration-loop.md       # Outer loop, stop conditions, error handling
│   ├── sdk-integration.md      # Claude Agent SDK API reference
│   ├── cli.md                  # CLI flags, slash commands, examples
│   ├── decisions.md            # Architectural decision records (ADRs)
│   ├── web.md                  # Landing page architecture (web/ submodule)
│   ├── for-human.md            # Prompt phrasing guide for faster iterations
│   └── archive/                # Stale docs kept for reference
│       ├── auth-v0.md          # Original single-provider auth
│       ├── OPENAI_INTEG_PROMPT.md   # OpenAI feature spec (future)
│       └── GEMINI_INTEG_PROMPT.md   # Gemini feature spec (future)
├── web/                        # Landing page (git submodule)
│   ├── app/                    # Next.js 16 App Router
│   ├── components/             # hero, manifesto, terminal, stats, install, footer
│   └── public/                 # Images, favicons
└── inductiveclaw/              # Python package
    ├── __init__.py
    ├── __main__.py             # CLI routing: no -g → interactive, -g → autonomous
    ├── interactive.py          # REPL mode using ClaudeSDKClient
    ├── agent.py                # Autonomous iteration loop
    ├── setup.py                # Guided provider setup flow (--setup, /config)
    ├── tools.py                # Custom MCP tools (backlog, evaluate, screenshot, docs)
    ├── config.py               # ClawConfig + UsageTracker dataclasses
    ├── display.py              # Rich terminal output (both modes)
    ├── providers/              # Multi-provider abstraction
    │   ├── __init__.py         # ProviderRegistry, cycling logic, config persistence
    │   ├── base.py             # BaseProvider ABC, RateLimitTracker, enums
    │   ├── anthropic.py        # Claude via Agent SDK (OAuth + API key)
    │   ├── openai.py           # OpenAI (config stub — future feature)
    │   └── gemini.py           # Gemini (config stub — future feature)
    └── prompts/                # All prompt templates as .md files
        ├── __init__.py
        ├── system.py / system.md           # Autonomous mode system prompt
        ├── interactive.md                  # Interactive mode system prompt
        ├── iteration.py                    # Prompt builder (loads .md templates)
        ├── iteration_first.md / iteration_next.md
        ├── eval_trigger.md / screenshot_trigger.md
```

## Two Modes

### Interactive (default: `iclaw`)
- Uses `ClaudeSDKClient` for multi-turn conversation
- Claude Code-style UX: alt screen, `❯` prompt, `⏺`/`⎿`/`✻` iconography
- prompt_toolkit for input (history, tab completion for slash commands)
- Rich for output (markdown rendering, styled tool calls)
- OS-level sandbox + `can_use_tool` callback (no `bypassPermissions`)
- Ctrl+C interrupts agent mid-work, returns to prompt
- Slash commands: `/help`, `/config`, `/status`, `/cost`, `/clear`, `/quit`
- cwd defaults to `.` (current directory)

### Autonomous (`iclaw -g "goal"`)
- Iteration loop with fresh `query()` calls per iteration
- Custom MCP tools: update_backlog, self_evaluate, take_screenshot, write_docs
- cwd defaults to `./project`

## Provider System

### Architecture
- `providers/base.py` — `BaseProvider` ABC, `ProviderID`, `AuthMode`, `ProviderStatus`, `RateLimitTracker`
- Each provider implements: `get_sdk_env()`, `get_model()`, `is_configured()`, `configure()`, `status_line()`
- `ProviderRegistry` manages all providers, handles cycling, persists config to `~/.config/iclaw/providers.json`

### Cycling
- When rate limited, cycle to next configured provider
- `RateLimitTracker`: 2 rate limit hits within 5 minutes = provider exhausted for the day
- Rate limit detection: check for "rate" + "limit" in error message string

### Provider Selection
- On first run with no config: auto-detect Anthropic OAuth/API key
- If nothing detected: run guided setup (`iclaw --setup`)
- `/config` in interactive mode re-enters setup

## Sandbox

Two-layer defense restricting the agent to the project directory:

1. **OS-level sandbox** (`SandboxSettings` in `ClaudeAgentOptions`):
   - macOS: Seatbelt (sandbox-exec) — kernel-level filesystem write restrictions
   - Linux: bubblewrap
   - `enabled=True`, `autoAllowBashIfSandboxed=True`, `allowUnsandboxedCommands=False`
   - Writes outside project dir blocked by the OS, even under prompt injection

2. **`can_use_tool` callback** (secondary layer):
   - Runs in-process, gates every tool call before the OS sandbox
   - Blocks Write/Edit/Read to paths outside project dir
   - Blocks Bash commands referencing absolute paths outside project dir
   - Blocks `sudo`
   - Provides friendly error messages

**Important:** `bypassPermissions` and `can_use_tool` are mutually exclusive.
`bypassPermissions` tells the CLI to skip all permission checks, so `can_use_tool`
never fires. Interactive mode does NOT use `bypassPermissions`.

System prompts also instruct: no sudo, no global installs, local deps only.

## Coding Conventions

- **Python >=3.10.** All files use `from __future__ import annotations`.
- **Async with anyio** — matches the Agent SDK runtime.
- **No module >300 lines.** Split if approaching.
- **No circular imports.** Dependency graph is strictly layered.
- **Type hints everywhere.** Use `TYPE_CHECKING` for import-only types.
- **Rich for terminal output** with plain-text fallback.

## Module Boundaries

- **`providers/`** — all auth and provider logic. Nothing else touches env vars or API keys.
- **`agent.py`** — autonomous loop brain. Uses `ProviderRegistry` for env/model.
- **`interactive.py`** — REPL brain. Uses `ClaudeSDKClient` + `ProviderRegistry`.
- **`setup.py`** — guided config flow. Reads/writes `ProviderRegistry`.
- **`tools.py`** — MCP tool definitions only.
- **`config.py`** — pure data.
- **`display.py`** — all terminal UI.
- **`__main__.py`** — thin CLI routing.
- **`prompts/`** — all prompt text in `.md` files.

## Key Technical Details

- **PyPI package:** `iclaw`. Python import: `inductiveclaw`.
- **SDK:** `claude-agent-sdk` (import as `claude_agent_sdk`)
- **Tool naming:** `mcp__iclaw-tools__<tool_name>` in `allowed_tools`
- **Stop condition:** `overall_score >= threshold AND ready_to_ship == True`
- **Permission mode:** `bypassPermissions` for autonomous mode; omitted for interactive (uses `can_use_tool` + OS sandbox)
- **Build backend:** `hatchling.build`

## Development

```bash
./dev_install.sh               # pip install -e .
iclaw --help                   # Verify
iclaw --setup                  # Configure providers
iclaw                          # Interactive mode
iclaw -g "Build X"             # Autonomous mode
python -m build && twine check dist/*  # Build for PyPI
```

## Don't

- Don't put prompts inline in Python files — they live in `prompts/*.md`.
- Don't touch env vars outside `providers/`.
- Don't print directly — use `display.*` functions.
- Don't add deps without updating `pyproject.toml`.
- Don't exceed 300 lines per module.
- Don't write files outside the project directory from agent context.

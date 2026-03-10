# Architecture

InductiveClaw has two modes sharing a common provider and display layer.

## Module Dependency Graph

```
__main__.py (CLI routing)
  ├── --setup  → setup.py (guided provider config)
  ├── -g "goal" → agent.py (autonomous loop)
  │                 ├── tools.py (custom MCP server)
  │                 ├── prompts/ (system.md, iteration templates)
  │                 ├── display.py
  │                 ├── config.py (ClawConfig, UsageTracker)
  │                 └── providers/ (env + model for active provider)
  └── (no -g)  → interactive.py (REPL)
                    ├── prompts/interactive.md
                    ├── display.py
                    └── providers/
```

### providers/ (shared by both modes)

```
providers/
├── __init__.py     ProviderRegistry, cycling, config persistence
├── base.py         BaseProvider ABC, RateLimitTracker, enums
├── anthropic.py    Claude (OAuth + API key) — IMPLEMENTED
├── openai.py       OpenAI (config stub, future feature)
└── gemini.py       Gemini (config stub, future feature)
```

No circular dependencies. `config.py`, `providers/base.py` are leaf modules.

## Data Flow

### Autonomous mode
```
CLI args → ClawConfig + ProviderRegistry
  → agent.run(config, registry)
    ├── create_iclaw_tools(config) → MCP server
    ├── registry.active.get_sdk_env() → env dict
    └── for each iteration:
          query(prompt, options) → stream messages
          _extract_iteration_results() → reads BACKLOG.md, EVALUATIONS.md
          on rate limit → registry.handle_rate_limit() → cycle provider
```

### Interactive mode
```
ProviderRegistry → interactive.run_interactive(registry, cwd)
  → enter alt screen
  → ClaudeSDKClient(options) as client
    └── while True:
          prompt_toolkit.prompt_async() → user input
          → slash command: handle locally
          → text: client.query(input)
            → suppress stdin (termios)
            → stream AssistantMessage blocks:
                TextBlock → Rich Markdown render
                ToolUseBlock → ⏺ styled summary
                ToolResultBlock → ⎿ result display
            → restore stdin, drain queued sequences
            → pad to bottom, show separator
          on Ctrl+C during agent work → interrupt, return to prompt
          on /config → run_setup(registry), restart session
          on rate limit → cycle provider, restart session
  → exit alt screen (restore terminal)
```

## Key Design Decisions

### Fresh SDK calls per iteration (autonomous mode)
Each `query()` call resets context. Project state persists on disk (BACKLOG.md, EVALUATIONS.md, source files). Equivalent to automatic `/compact`.

### ClaudeSDKClient for interactive mode
Multi-turn context manager preserves conversation across turns. Session restarts on `/clear`, `/config`, or provider cycling.

### Provider abstraction
Each provider implements `get_sdk_env()` and `get_model()`. The registry handles cycling on rate limits. Config persists to `~/.config/iclaw/providers.json`.

**Current limitation:** Only Anthropic is fully functional. The Agent SDK shells out to the `claude` CLI, so OpenAI and Gemini require separate API client implementations (future feature).

### Sandbox (two-layer defense)

Interactive mode uses two enforcement layers:

1. **OS-level sandbox** — `SandboxSettings(enabled=True, autoAllowBashIfSandboxed=True,
   allowUnsandboxedCommands=False)`. On macOS this uses Apple's Seatbelt (sandbox-exec)
   for kernel-level filesystem write restrictions. Provider-agnostic — works regardless
   of which model drives the agent.

2. **`can_use_tool` callback** — In-process permission gate. Blocks file tools targeting
   paths outside the project dir, blocks Bash with out-of-sandbox absolute paths,
   blocks `sudo`. Provides friendly error messages.

**Critical:** `bypassPermissions` and `can_use_tool` are mutually exclusive. Interactive
mode does NOT use `bypassPermissions` so that `can_use_tool` fires. Autonomous mode
still uses `bypassPermissions` (no `can_use_tool` needed since it's unattended).

System prompts in both modes instruct: no sudo, no global installs, local deps only.

### Interactive UX (Claude Code-style)

Interactive mode uses a layered rendering approach:
- **prompt_toolkit** — async input with history, tab completion, bottom toolbar
- **Rich** — markdown rendering, styled tool calls, panels, tables
- **Alternate screen buffer** — clean launch/exit (terminal content restored)
- **termios stdin suppression** — prevents scroll escape leakage during agent work
- **Tool call display** — `⏺ ToolName(summary)` + `⎿  result` (from `ToolResultBlock`)

See `docs/decisions.md` for rationale on each of these choices.

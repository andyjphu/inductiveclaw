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
  → ClaudeSDKClient(options) as client
    └── while True:
          input → slash command or client.query(input)
          on /config → run_setup(registry), restart session
          on rate limit → cycle provider, restart session
```

## Key Design Decisions

### Fresh SDK calls per iteration (autonomous mode)
Each `query()` call resets context. Project state persists on disk (BACKLOG.md, EVALUATIONS.md, source files). Equivalent to automatic `/compact`.

### ClaudeSDKClient for interactive mode
Multi-turn context manager preserves conversation across turns. Session restarts on `/clear`, `/config`, or provider cycling.

### Provider abstraction
Each provider implements `get_sdk_env()` and `get_model()`. The registry handles cycling on rate limits. Config persists to `~/.config/iclaw/providers.json`.

**Current limitation:** Only Anthropic is fully functional. The Agent SDK shells out to the `claude` CLI, so OpenAI and Gemini require separate API client implementations (future feature).

### Sandbox
Both modes pass `add_dirs=[project_dir]` to restrict file access. System prompts instruct: no sudo, no global installs, local deps only.

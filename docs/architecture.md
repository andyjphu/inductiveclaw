# Architecture

InductiveClaw is structured as six modules with strict separation of concerns. No module exceeds ~300 lines.

## Module Dependency Graph

```
__main__.py
  ├── auth.py        (resolve authentication)
  ├── config.py      (ClawConfig dataclass)
  └── agent.py       (run the loop)
        ├── tools.py     (custom MCP server)
        ├── display.py   (terminal output)
        ├── config.py    (ClawConfig, UsageTracker)
        └── auth.py      (AuthResult.get_sdk_env)
```

No circular dependencies. `config.py` and `auth.py` are leaf modules with no internal imports.

## Data Flow

```
CLI args → ClawConfig → agent.run()
                          │
                          ├── create_iclaw_tools(config) → MCP server
                          ├── auth_result.get_sdk_env() → env dict
                          │
                          └── for each iteration:
                                build_iteration_prompt(config, iteration, tracker)
                                  → prompt string
                                _build_sdk_options(config, tools_server, auth_result)
                                  → ClaudeAgentOptions
                                query(prompt, options)
                                  → stream of AssistantMessage / ResultMessage
                                _extract_iteration_results(config, tracker)
                                  → IterationResult (reads BACKLOG.md, EVALUATIONS.md)
```

## Key Design Decisions

### Fresh SDK calls per iteration (not one long session)
Each `query()` call is an independent conversation. Over 20+ tool calls, context fills with file contents and bash outputs. Fresh calls reset this automatically — equivalent to Claude Code's `/compact` but built-in. Project state persists on disk.

### Custom MCP tools instead of just Bash + Write
Tool names are prompts. A tool called `self_evaluate` with structured score inputs produces far better evaluation than "write scores to a file." Same for `update_backlog` — the schema forces explicit tracking.

### OAuth-first auth
Autonomous loops can run 50+ iterations. On API billing that's $15-75+. On a Max subscription it's flat rate. OAuth-first makes the default cost-effective.

### `anyio` instead of `asyncio`
The Claude Agent SDK uses `anyio` internally. Matching the runtime avoids nested event loop issues.

### `bypassPermissions` mode
InductiveClaw runs fully autonomously. The inner agent needs unrestricted access to Bash, file operations, etc. without human approval prompts.

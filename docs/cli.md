# CLI Reference

## Entry Points

- **Installed:** `iclaw` (via `pyproject.toml` `[project.scripts]`, install with `pip install iclaw`)
- **Module:** `python -m inductiveclaw`

Both call `inductiveclaw.__main__:main()`. Note: InductiveClaw shells out to the Claude Code CLI, so install `claude` (`npm install -g @anthropic-ai/claude-code`) and run `claude login` before launching `iclaw` if you want OAuth.

## Arguments

### Required

| Flag | Description |
|------|-------------|
| `-g, --goal GOAL` | What to build. Passed verbatim to the agent. |

### Project

| Flag | Default | Description |
|------|---------|-------------|
| `-p, --project DIR` | `./project` | Project directory. Created if it doesn't exist. |
| `-m, --model MODEL` | SDK default | Model override (e.g. `claude-sonnet-4-6`). |

### Iteration Control

| Flag | Default | Description |
|------|---------|-------------|
| `-t, --threshold N` | `8` | Quality score (1-10) to stop at. |
| `--max-iterations N` | `100` | Hard cap on outer loop iterations. |
| `--eval-frequency N` | `3` | Run `self_evaluate` every N iterations. |

### Auth

| Flag | Description |
|------|-------------|
| `--use-api-key` | Prefer `ANTHROPIC_API_KEY` env var over OAuth. |
| `--api-key KEY` | Provide an API key directly. |

### Visual

| Flag | Default | Description |
|------|---------|-------------|
| `--no-screenshot` | off | Disable Playwright screenshot evaluation. |
| `--port PORT` | `3000` | Dev server port for screenshots. |
| `--dev-cmd CMD` | auto-detect (currently parsed but unused) | Dev server command (e.g. `npm run dev`). |

### Output

| Flag | Description |
|------|-------------|
| `-q, --quiet` | Suppress verbose agent reasoning output (no effect without `-v`). |
| `-v, --verbose` | Print the agent's reasoning/tool output; `--quiet` disables this mode. |

## Startup Flow

```
parse_args()
  → ClawConfig(...)
  → auth.resolve(prefer_oauth, force_api_key)
  → anyio.run(agent.run, config, auth_result)
```

No business logic in `__main__.py` — it maps args to config and delegates.

## Examples

```bash
# Minimal
iclaw -g "Build a todo app"

# Full control
iclaw -g "Roguelike deckbuilder" -p ./game -m claude-sonnet-4-6 \
  -t 7 --max-iterations 50 --eval-frequency 5 --port 5173 -v

# Resume existing project
iclaw -p ./my-game -g "Add sound effects and polish the UI"

# Non-visual project
iclaw -g "CLI tool for CSV analysis" --no-screenshot -q

# Explicit API key
iclaw --api-key sk-ant-... -g "Chat application"
```

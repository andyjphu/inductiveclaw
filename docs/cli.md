# CLI Reference

## Entry Points

- **Installed:** `iclaw` (via `pyproject.toml [project.scripts]`)
- **Module:** `python -m inductiveclaw`

Both call `inductiveclaw.__main__:main()`.

## Modes

### Interactive (default)
```bash
iclaw                    # REPL in current directory
iclaw -p ./my-project    # REPL in specific directory
```

### Autonomous
```bash
iclaw -g "Build a snake game"              # iterate until quality threshold
iclaw -g "Polish the UI" -p ./my-project   # continue existing project
```

### Setup
```bash
iclaw --setup    # guided provider configuration
```

## Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `-g, --goal GOAL` | *(none)* | What to build. Omit for interactive mode. |
| `--setup` | off | Run guided provider setup |
| `-p, --project DIR` | `.` (interactive) / `./project` (autonomous) | Project directory |
| `-m, --model MODEL` | provider default | Model override |
| `-t, --threshold N` | `8` | Quality score (1-10) to stop at (autonomous only) |
| `--max-iterations N` | `100` | Hard cap on iterations (autonomous only) |
| `--eval-frequency N` | `3` | Self-evaluate every N iterations (autonomous only) |
| `--no-screenshot` | off | Disable Playwright screenshot evaluation |
| `--port PORT` | `3000` | Dev server port for screenshots |
| `--dev-cmd CMD` | auto-detect | Dev server command |
| `-q, --quiet` | off | Minimal output |
| `-v, --verbose` | off | Full agent text output |

## Interactive Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/config` | Re-run provider setup |
| `/status` | Show provider status |
| `/cost` | Show session cost and turns |
| `/clear` | Clear conversation (new session) |
| `/quit` | Exit iclaw |

## Startup Flow

```
parse_args()
  → ProviderRegistry()
  → load saved config or auto-detect Anthropic
  → if no provider: run_setup()
  → if -g: agent.run(config, registry)     # autonomous
  → else:  run_interactive(registry, cwd)   # interactive
```

## Examples

```bash
# Interactive — just start coding
iclaw

# Autonomous — build from scratch
iclaw -g "Roguelike deckbuilder with pixel art"

# Autonomous — resume existing project
iclaw -p ./game -g "Add sound effects and polish the tutorial"

# Quick prototype
iclaw -g "Simple snake game" --threshold 5 --max-iterations 10

# Non-visual project
iclaw -g "CLI for CSV analysis" --no-screenshot -q

# Configure providers
iclaw --setup
```

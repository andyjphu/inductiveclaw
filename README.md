# InductiveClaw

Autonomous iterative coding agent — builds until the vibe is right.

InductiveClaw wraps the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/) in a persistent autonomous loop. Unlike Claude Code, which stops after completing one task and waits for the next prompt, InductiveClaw continuously builds, verifies, evaluates, and iterates on a software project until it reaches a quality threshold or exhausts its budget.

## Installation

```bash
pip install inductiveclaw
```

For screenshot-based visual evaluation (optional):

```bash
pip install inductiveclaw[screenshot]
playwright install chromium
```

## Authentication

InductiveClaw prefers OAuth (your existing Claude Code / Max subscription login) by default, falling back to an API key.

**Option 1 — Max/Pro subscription (recommended):**

```bash
claude login   # one-time setup
iclaw -g "your goal"
```

**Option 2 — API key:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
iclaw -g "your goal"
```

**Option 3 — Explicit key:**

```bash
iclaw --api-key sk-ant-... -g "your goal"
```

## Usage

```bash
# Build a game from scratch
iclaw -g "Build a roguelike deckbuilder with pixel art style"

# Continue on existing project
iclaw -p ./my-game -g "Polish visuals, add sound effects, improve the tutorial"

# Quick prototype with low quality bar
iclaw -g "Simple snake game in the browser" --threshold 5 --max-iterations 10

# Disable screenshots for non-visual projects
iclaw -g "Build a CLI tool for CSV analysis" --no-screenshot
```

## How It Works

1. You give InductiveClaw a goal
2. It initializes the project, creates a backlog, and builds the first feature
3. Each iteration: orient → plan → build → verify → evaluate → document → continue
4. The loop runs until quality threshold is met, max iterations reached, or you interrupt with Ctrl+C

Project state is persisted on disk (`BACKLOG.md`, `EVALUATIONS.md`, source files), so you can stop and resume at any time.

## CLI Reference

```
usage: iclaw [-h] -g GOAL [-p PROJECT] [-m MODEL] [-t THRESHOLD]
             [--max-iterations N] [--eval-frequency N]
             [--use-api-key] [--api-key KEY]
             [--no-screenshot] [--port PORT]
             [--dev-cmd CMD] [-q] [-v]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-g, --goal` | *required* | What to build |
| `-p, --project` | `./project` | Project directory |
| `-m, --model` | SDK default | Model override |
| `-t, --threshold` | `8` | Quality threshold (1-10) |
| `--max-iterations` | `100` | Max outer loop iterations |
| `--eval-frequency` | `3` | Self-evaluate every N iterations |
| `--use-api-key` | off | Prefer API key over OAuth |
| `--api-key` | env | Explicit API key |
| `--no-screenshot` | off | Disable visual evaluation |
| `--port` | `3000` | Dev server port for screenshots |
| `--dev-cmd` | auto | Dev server command |
| `-q, --quiet` | off | Minimal output |
| `-v, --verbose` | off | Full agent output |

## Architecture

```
inductiveclaw/
├── __init__.py
├── __main__.py     # CLI entrypoint (argparse)
├── auth.py         # OAuth-first authentication
├── agent.py        # Outer autonomous loop + Agent SDK calls
├── tools.py        # Custom MCP tools (backlog, evaluate, screenshot, docs)
├── config.py       # Configuration + usage tracking
└── display.py      # Terminal output formatting (Rich)
```

## License

MIT

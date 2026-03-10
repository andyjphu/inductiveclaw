# InductiveClaw

Autonomous iterative coding agent — builds until the vibe is right.

InductiveClaw wraps the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/) in a persistent autonomous loop. Unlike Claude Code, which stops after completing one task and waits for the next prompt, InductiveClaw continuously builds, verifies, evaluates, and iterates on a software project until it reaches a quality threshold or exhausts its budget.

## Installation

```bash
pip install iclaw
```

For screenshot-based visual evaluation (optional):

```bash
pip install iclaw[screenshot]
playwright install chromium
```

Requires the Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) because the Agent SDK shells out to `claude`. Run `claude login` once if you plan to use a Max/Pro subscription.

## Setup

On first run, iclaw auto-detects your Claude Code login. You can also run guided setup:

```bash
iclaw --setup
```

This walks you through configuring providers (currently Anthropic/Claude; OpenAI and Gemini are planned future features).

> Anthropic has blocked third-party projects from routing Max/Pro subscription OAuth tokens through unofficial API gateways. Using `claude login` locally for personal dev is fine, but keep your usage personal and off public-facing services.

## Usage

### Interactive mode (default)

```bash
iclaw                          # REPL in current directory
iclaw -p ./my-project          # REPL in specific directory
```

Type `/help` for available commands, `/config` to change providers, `/quit` to exit.

### Autonomous mode

```bash
# Build a game from scratch
iclaw -g "Build a roguelike deckbuilder with pixel art style"

# Continue on existing project
iclaw -p ./my-game -g "Polish visuals, add sound effects"

# Quick prototype with low quality bar
iclaw -g "Simple snake game in the browser" --threshold 5 --max-iterations 10

# Non-visual project
iclaw -g "Build a CLI tool for CSV analysis" --no-screenshot
```

## How It Works

**Interactive mode:** A conversational REPL (like Claude Code) with multi-turn context. The agent has access to Bash, file tools, and your project directory.

**Autonomous mode:**
1. You give it a goal
2. It initializes the project, creates a backlog, and builds the first feature
3. Each iteration: orient, plan, build, verify, evaluate, document, continue
4. Stops when quality threshold is met, max iterations reached, or Ctrl+C

Project state persists on disk (`BACKLOG.md`, `EVALUATIONS.md`, source files), so you can stop and resume.

## CLI Reference

```
iclaw [-g GOAL] [--setup] [-p DIR] [-m MODEL] [-t N]
      [--max-iterations N] [--eval-frequency N]
      [--no-screenshot] [--port PORT] [-q] [-v]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-g, --goal` | *(none)* | What to build (omit for interactive mode) |
| `--setup` | off | Run guided provider setup |
| `-p, --project` | `.` / `./project` | Project directory |
| `-m, --model` | provider default | Model override |
| `-t, --threshold` | `8` | Quality threshold 1-10 (autonomous) |
| `--max-iterations` | `100` | Max iterations (autonomous) |
| `--eval-frequency` | `3` | Evaluate every N iterations |
| `--no-screenshot` | off | Disable visual evaluation |
| `--port` | `3000` | Dev server port for screenshots |
| `-q, --quiet` | off | Minimal output |
| `-v, --verbose` | off | Full agent output |

## Architecture

```
inductiveclaw/
├── __init__.py
├── __main__.py        # CLI routing (interactive vs autonomous)
├── interactive.py     # REPL mode (ClaudeSDKClient)
├── agent.py           # Autonomous iteration loop
├── setup.py           # Guided provider setup
├── tools.py           # Custom MCP tools
├── config.py          # Configuration + usage tracking
├── display.py         # Terminal output (Rich)
├── providers/         # Multi-provider abstraction
│   ├── anthropic.py   # Claude (implemented)
│   ├── openai.py      # Future feature
│   └── gemini.py      # Future feature
└── prompts/           # Prompt templates (.md files)
```

## Landing Page

The `web/` submodule contains the project landing page — a Next.js 16 app with scroll-driven animations, an Art Nouveau-inspired philosophy section, and an animated terminal demo. See `docs/web.md` for architecture details.

## Future Features

- **OpenAI Codex** — Codex app-server and API key integration
- **Gemini** — Google OAuth and API key integration
- **Provider cycling** — automatic failover between providers on rate limits

## License

MIT

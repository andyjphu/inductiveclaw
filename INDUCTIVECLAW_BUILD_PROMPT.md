# InductiveClaw — Full Build Prompt

> **What this is:** A complete Claude Code build prompt for an autonomous iterative coding agent called InductiveClaw. Hand this entire document to Claude Code and say "build this."

---

## Project Overview

InductiveClaw is a Python CLI tool (`iclaw`) that wraps the Claude Agent SDK in a persistent autonomous loop. Unlike Claude Code, which stops after completing one feature and waits for the next prompt, InductiveClaw continuously builds, verifies, evaluates, documents, and iterates on a software project until it reaches a quality threshold or exhausts its budget.

The name reflects the core mechanism: inductive reasoning applied with sharp, relentless execution. Each iteration observes the current state, induces what to build next, and claws forward.

**Core behavior:** You give it a goal like "Build a roguelike deckbuilder with pixel art style." It initializes the project, creates a backlog, builds the first feature, runs it, evaluates it, updates the backlog, and immediately starts the next feature — over and over — without human intervention.

**Key design constraint:** InductiveClaw uses the official `claude-agent-sdk` Python package, which shells out to the Claude Code CLI under the hood. Authentication uses OAuth (the user's existing Claude Code login / Max subscription) by default, falling back to API key if OAuth isn't available. This means InductiveClaw can run on a Max subscription's subsidized tokens rather than pay-per-token API billing.

---

## Architecture

The codebase follows clean separation of concerns. There are five modules plus a CLI entrypoint. No module should exceed ~300 lines. All async, using `anyio` as the runtime.

```
inductiveclaw/
├── pyproject.toml
├── README.md
├── inductiveclaw/
│   ├── __init__.py
│   ├── __main__.py          # CLI entrypoint (argparse)
│   ├── auth.py              # All authentication logic lives here
│   ├── agent.py             # The outer autonomous loop + Agent SDK calls
│   ├── tools.py             # Custom MCP tools (screenshot, evaluate, backlog)
│   ├── config.py            # Configuration dataclass + usage tracking
│   └── display.py           # Terminal output formatting + progress display
```

### Module Responsibilities

**`auth.py`** — Single source of truth for authentication. All auth decisions happen here. Nothing else in the codebase touches environment variables related to auth or knows how tokens work.

**`agent.py`** — The brain. Contains the outer iteration loop and constructs prompts for each iteration. Calls the Agent SDK's `query()` or `ClaudeSDKClient`. Decides when to stop (quality threshold, budget, max iterations, user interrupt). Does NOT know how auth works — it receives a configured options object from auth.

**`tools.py`** — Custom MCP tools registered via the Agent SDK's `@tool` decorator and `create_sdk_mcp_server`. These extend Claude's built-in tools (Bash, Read, Write, Edit, Glob, Grep) with InductiveClaw-specific capabilities.

**`config.py`** — Pure data. The `ClawConfig` dataclass and the `UsageTracker`. No logic beyond simple calculations.

**`display.py`** — All terminal UI. Rich-formatted output, progress bars, iteration headers, summaries. The rest of the codebase calls display functions rather than printing directly.

**`__main__.py`** — Thin CLI layer. Parses args, constructs config, calls `auth.resolve()` to get auth options, passes everything to `agent.run()`. No business logic.

---

## Module 1: `auth.py`

### Purpose

Resolve authentication for the Agent SDK. The strategy is:

1. **Try OAuth first** — Check if the user has an existing Claude Code login (Max/Pro subscription). This is the preferred path because it uses subsidized subscription tokens.
2. **Fall back to API key** — If OAuth isn't available, check for `ANTHROPIC_API_KEY` in the environment.
3. **If neither works** — Print clear instructions telling the user to either run `claude login` to authenticate Claude Code, or set `ANTHROPIC_API_KEY`.

### How OAuth Works

The Claude Code CLI stores OAuth tokens when a user logs in via `claude login`. When the Agent SDK calls the CLI, if no `ANTHROPIC_API_KEY` is set in the environment, the CLI falls through to OAuth and uses the subscription.

So "using OAuth" from InductiveClaw's perspective means: **strip `ANTHROPIC_API_KEY` from the environment before invoking the Agent SDK.** That's the core trick.

### Implementation Details

```python
class AuthMethod(enum.Enum):
    OAUTH = "oauth"       # Max/Pro subscription via Claude Code login
    API_KEY = "api_key"   # Direct API key

@dataclass
class AuthResult:
    method: AuthMethod
    env_overrides: dict[str, str]   # env vars to SET when calling Agent SDK
    env_removals: list[str]         # env vars to REMOVE when calling Agent SDK
    display_name: str               # e.g. "Max subscription (OAuth)" for display

def resolve(prefer_oauth: bool = True, force_api_key: str | None = None) -> AuthResult:
    """
    Resolve authentication. Called once at startup.

    Logic:
    1. If force_api_key is provided (via --api-key flag), use it directly.
    2. If prefer_oauth is True (default):
       a. Check if Claude Code CLI is installed (shutil.which("claude"))
       b. Check if OAuth token exists (~/.claude/ directory has credential files)
       c. If both exist, return AuthResult with OAUTH method
          - env_removals = ["ANTHROPIC_API_KEY"]  (force CLI to use OAuth)
       d. If not, fall through to API key
    3. Check for ANTHROPIC_API_KEY in environment
    4. If nothing works, raise AuthError with helpful instructions
    """
```

### Checking OAuth Availability

To verify the user has a valid Claude Code login without actually making an API call:

1. Check `shutil.which("claude")` — CLI must be installed
2. Check for credential storage:
   - macOS: Check if keychain has Claude Code credentials (or just check `~/.claude/` directory exists with files)
   - Linux: Check `~/.claude/` for credential files
3. Optionally, run `claude --version` to verify the CLI works

Don't try to read or parse the OAuth tokens directly — that's the CLI's job. Just verify the CLI exists and has been logged into.

### Applying Auth to Agent SDK

The `AuthResult` is applied by modifying the environment before calling the SDK:

```python
def get_sdk_env(auth_result: AuthResult) -> dict:
    """Return a modified copy of os.environ for Agent SDK calls."""
    env = os.environ.copy()
    for key in auth_result.env_removals:
        env.pop(key, None)
    env.update(auth_result.env_overrides)
    return env
```

The agent module uses this when constructing subprocess environments or when the SDK needs env configuration.

### Important Edge Cases

- User has BOTH an API key and OAuth. Default behavior: prefer OAuth (subscription). Flag `--use-api-key` overrides this.
- User has OAuth but token is expired. The Claude Code CLI handles token refresh automatically — InductiveClaw doesn't need to manage this.
- User is on free tier (no Pro/Max). OAuth will still work but they'll hit rate limits fast. Display a warning.
- Claude Code CLI is installed but user never ran `claude login`. The CLI will fail at runtime. Catch this error in the agent loop and surface a helpful message.

---

## Module 2: `config.py`

### ClawConfig Dataclass

```python
@dataclass
class ClawConfig:
    project_dir: str = "./project"
    goal: str = ""                          # Required — what to build
    model: str | None = None                # None = let Agent SDK pick default
    max_iterations: int = 100               # Outer loop cap
    quality_threshold: int = 8              # 1-10, stop when overall score >= this
    max_turns_per_iteration: int = 30       # Inner tool-use turns per SDK call
    auto_screenshot: bool = True            # Enable screenshot evaluation tool
    screenshot_port: int = 3000             # Dev server port for screenshots
    dev_server_cmd: str | None = None       # e.g. "npm run dev" — auto-detected if None
    verbose: bool = True
    eval_frequency: int = 3                 # Run self_evaluate every N iterations
```

### UsageTracker

Tracks iteration state and quality progression. The Agent SDK abstracts away token counting, so instead of tracking dollars, track what matters: iteration count, features completed, quality trajectory.

```python
@dataclass
class UsageTracker:
    iterations_completed: int = 0
    features_completed: list[str] = field(default_factory=list)
    last_quality_score: int | None = None
    quality_history: list[int] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    errors: list[str] = field(default_factory=list)
```

If the user is on OAuth/subscription, cost tracking is irrelevant — they're paying flat rate. If on API key, the Agent SDK doesn't expose granular token counts anyway.

---

## Module 3: `tools.py`

### Custom MCP Tools

These are registered as in-process MCP servers using `@tool` decorator and `create_sdk_mcp_server`. They extend Claude's built-in Bash/Read/Write/Edit/Glob/Grep tools.

#### Tool: `update_backlog`

**Purpose:** Maintain a living `BACKLOG.md` file in the project root. Called after completing each feature and during planning.

**Input schema:**
```python
{
    "completed_item": str | None,      # Feature just completed (optional)
    "next_priorities": list[str],       # Updated priority list
    "quality_notes": str | None,        # Notes on current quality
    "blockers": list[str] | None        # Known issues / stuck points
}
```

**Behavior:**
- Reads existing BACKLOG.md if present
- Appends a timestamped update section
- If completed_item is provided, moves it to the "Completed" section
- Writes the updated file back
- Returns a summary string

#### Tool: `self_evaluate`

**Purpose:** Force the agent to critically assess project quality. Returns structured scores that the outer loop uses to decide whether to stop.

**Input schema:**
```python
{
    "functionality_score": int,     # 1-10: Does it work? Features complete?
    "visual_score": int,            # 1-10: Does it look polished and unique?
    "code_quality_score": int,      # 1-10: Clean, well-structured, documented?
    "uniqueness_score": int,        # 1-10: Does it have personality/style?
    "overall_score": int,           # 1-10: Would you put this on your portfolio?
    "critique": str,                # Honest text critique
    "top_improvement": str,         # Single most impactful next improvement
    "ready_to_ship": bool           # Overall assessment
}
```

**Behavior:**
- Appends evaluation to `EVALUATIONS.md` in project root
- Returns JSON with the scores so the outer loop can parse it
- The outer loop checks `overall_score >= config.quality_threshold` and `ready_to_ship`

#### Tool: `take_screenshot`

**Purpose:** Capture a screenshot of the running application for visual evaluation. Uses Playwright.

**Input schema:**
```python
{
    "url": str,                     # Default: "http://localhost:{config.screenshot_port}"
    "full_page": bool,              # Default: True
    "wait_seconds": int,            # Wait for page to render (default: 3)
    "output_path": str              # Where to save (default: ".iclaw/screenshots/latest.png")
}
```

**Behavior:**
- Checks if Playwright is installed; if not, prints a message and returns a text-only fallback
- Launches headless Chromium
- Navigates to URL, waits, takes screenshot
- Saves to output_path
- Returns the file path as a string
- The agent can then use the built-in `Read` tool to read the image file and visually evaluate it

**Installation note:** Playwright requires `playwright install chromium`. The tool should handle this gracefully — if not installed, the tool returns an error message suggesting the agent install it via Bash, or skip visual evaluation and rely on code review only.

#### Tool: `write_docs`

**Purpose:** Create or update project documentation (README, architecture notes, etc.)

**Input schema:**
```python
{
    "file": str,                    # "README.md", "ARCHITECTURE.md", etc.
    "content": str,                 # Full file content
    "mode": str                     # "overwrite" or "append"
}
```

This is intentionally simple — it's basically a named write, but having it as a separate tool makes the agent more likely to write docs (tool names are prompts).

### MCP Server Registration

All custom tools are bundled into a single in-process MCP server:

```python
def create_iclaw_tools(config: ClawConfig):
    """Create and return the custom MCP server with all InductiveClaw tools."""

    @tool("update_backlog", "...", {...})
    async def update_backlog(args): ...

    @tool("self_evaluate", "...", {...})
    async def self_evaluate(args): ...

    @tool("take_screenshot", "...", {...})
    async def take_screenshot(args): ...

    @tool("write_docs", "...", {...})
    async def write_docs(args): ...

    return create_sdk_mcp_server(
        name="iclaw-tools",
        version="1.0.0",
        tools=[update_backlog, self_evaluate, take_screenshot, write_docs]
    )
```

---

## Module 4: `agent.py`

### The Outer Loop

This is the heart of InductiveClaw. It calls the Agent SDK repeatedly, each call being one "iteration" where the agent can make many tool calls.

```python
async def run(config: ClawConfig, auth_result: AuthResult):
    """Main autonomous loop."""

    tracker = UsageTracker()
    tools_server = create_iclaw_tools(config)
    env = get_sdk_env(auth_result)

    display.show_banner(config, auth_result)

    Path(config.project_dir).mkdir(parents=True, exist_ok=True)

    for iteration in range(1, config.max_iterations + 1):
        display.show_iteration_header(iteration, tracker)

        prompt = build_iteration_prompt(config, iteration, tracker)
        options = build_sdk_options(config, tools_server, env)

        try:
            result = await run_single_iteration(prompt, options, config, tracker)
        except KeyboardInterrupt:
            display.show_interrupted()
            break
        except Exception as e:
            tracker.errors.append(f"Iteration {iteration}: {e}")
            display.show_error(iteration, e)
            continue

        tracker.iterations_completed = iteration

        # Check stop conditions
        if result.should_stop:
            display.show_quality_reached(tracker)
            break

    display.show_summary(tracker)
```

### Building SDK Options

```python
def build_sdk_options(config, tools_server, env) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        # Built-in tools from Claude Code
        allowed_tools=[
            "Bash", "Read", "Write", "Edit", "Glob", "Grep", "LS",
            # Custom tools
            "mcp__iclaw-tools__update_backlog",
            "mcp__iclaw-tools__self_evaluate",
            "mcp__iclaw-tools__take_screenshot",
            "mcp__iclaw-tools__write_docs",
        ],
        permission_mode="acceptEdits",     # Auto-accept file writes
        cwd=str(Path(config.project_dir).resolve()),
        max_turns=config.max_turns_per_iteration,
        mcp_servers={"iclaw-tools": tools_server},
        system_prompt=build_system_prompt(config),
        # Load project CLAUDE.md if it exists
        setting_sources=["project"],
    )
```

### System Prompt

The system prompt is set once and stays constant across iterations. It defines WHO the agent is and HOW it should behave. The per-iteration prompt (the user message) changes each iteration with current state.

```
SYSTEM_PROMPT = """
You are InductiveClaw, an autonomous iterative development agent. You build
software through continuous iteration — you NEVER stop after one feature.

## Your Identity
You are a solo developer on an unlimited game jam. You have taste, you care
about craft, and you ship. You're not writing homework — you're building
something you'd be proud to put on your portfolio.

## Your Workflow (every iteration)
1. ORIENT — Read BACKLOG.md and scan existing code to understand current state
2. PLAN — Pick the single highest-impact thing to build or improve next
3. BUILD — Write clean, production-quality code with real comments
4. VERIFY — Run the code. If it's a web app, start the server. Check for errors.
5. EVALUATE — Every few features, use self_evaluate to honestly score quality
6. DOCUMENT — Update BACKLOG.md with what you did and what's next
7. CONTINUE — You are not done. Pick the next thing.

## Quality Standards
- Code: Clean architecture, consistent style, meaningful names, real comments
- Visual: No placeholder text, no ugly defaults, unique personality/style
- Testing: Run what you build. Fix errors before moving on.
- Docs: Keep BACKLOG.md and README.md current. Write like a human.
- Industry standard: The result should feel like it belongs on itch.io or a
  polished GitHub repo, not a tutorial exercise.

## Rules
- Always check existing code before writing (avoid duplication)
- Always run code after writing it (catch errors immediately)
- If stuck on a bug for >3 attempts, note it in BACKLOG.md and move on
- Build incrementally — working skeleton first, then features, then polish
- When you evaluate visual quality, use take_screenshot if available, then
  Read the screenshot file to inspect it visually
- Prefer small, focused files over monolithic ones
- Commit to a unique aesthetic direction early and maintain it

## What You Are NOT
- You are NOT answering a question
- You are NOT completing a single task
- You are NOT writing a code snippet
- You ARE building a complete project autonomously over many iterations
"""
```

### Per-Iteration Prompt

This changes each iteration. It's the "user message" in the Agent SDK call.

```python
def build_iteration_prompt(config: ClawConfig, iteration: int, tracker: UsageTracker) -> str:

    if iteration == 1:
        return f"""
GOAL: {config.goal}

This is iteration 1. The project directory may be empty or may have existing files.

Your first tasks:
1. Check if there are existing files (use LS and Glob)
2. If empty: initialize the project structure, create BACKLOG.md with a
   prioritized feature list of 8-15 items, and build the first core feature
3. If files exist: read BACKLOG.md, orient yourself, and continue where
   the previous session left off
4. After building, run the code to verify it works
5. Update BACKLOG.md

Go. Do not ask for clarification — make decisions and build.
"""

    # Iterations 2+
    parts = [f"GOAL: {config.goal}\n"]
    parts.append(f"This is iteration {iteration}.")

    if tracker.features_completed:
        recent = tracker.features_completed[-5:]  # Last 5
        parts.append(f"Recently completed: {', '.join(recent)}")

    if tracker.last_quality_score is not None:
        parts.append(f"Last quality score: {tracker.last_quality_score}/10")
        if tracker.last_quality_score < config.quality_threshold:
            gap = config.quality_threshold - tracker.last_quality_score
            parts.append(f"Need {gap} more points to reach threshold.")

    if tracker.errors:
        recent_errors = tracker.errors[-2:]
        parts.append(f"Recent errors to be aware of: {'; '.join(recent_errors)}")

    # Trigger evaluation periodically
    if iteration % config.eval_frequency == 0:
        parts.append(
            "\nThis is an evaluation iteration. After making progress, "
            "use self_evaluate to score the current state. Be critical and honest."
        )

    # Trigger screenshot periodically (if enabled)
    if config.auto_screenshot and iteration % config.eval_frequency == 0:
        parts.append(
            "If the project has a visual component, use take_screenshot to "
            "capture the current state, then Read the screenshot to evaluate "
            "visual quality."
        )

    parts.append(
        "\nRead BACKLOG.md, pick the highest-impact next item, build it, "
        "verify it runs, and update the backlog. Do not stop early."
    )

    return "\n".join(parts)
```

### Processing Iteration Results

```python
@dataclass
class IterationResult:
    should_stop: bool = False
    features_completed: list[str] = field(default_factory=list)
    quality_score: int | None = None

async def run_single_iteration(prompt, options, config, tracker) -> IterationResult:
    """Run one Agent SDK call and extract results."""

    result = IterationResult()

    async for message in query(prompt=prompt, options=options):
        # Display agent activity
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    display.show_agent_text(block.text)

        # Check for ResultMessage (SDK final output)
        if hasattr(message, "result") and message.result:
            display.show_result(message.result)

    # After iteration, read BACKLOG.md and EVALUATIONS.md to extract state
    # (The agent writes to these files via custom tools during the iteration)
    result = await extract_iteration_results(config, tracker)

    return result

async def extract_iteration_results(config, tracker) -> IterationResult:
    """Read project files to determine what happened in this iteration."""
    result = IterationResult()

    eval_path = Path(config.project_dir) / "EVALUATIONS.md"
    if eval_path.exists():
        content = eval_path.read_text()
        # Parse the most recent evaluation block for overall_score
        # Look for "Overall: N/10" pattern in the last evaluation section
        # Update tracker.last_quality_score and tracker.quality_history

    backlog_path = Path(config.project_dir) / "BACKLOG.md"
    if backlog_path.exists():
        content = backlog_path.read_text()
        # Parse completed items from the latest update section
        # Append new completions to tracker.features_completed

    return result
```

---

## Module 5: `display.py`

### Terminal Output

Use `rich` library for formatted output. If rich isn't available, fall back to plain print.

Key display functions:

- `show_banner(config, auth)` — Startup box with project dir, goal, auth method, settings. Include the InductiveClaw ASCII logo or styled name.
- `show_iteration_header(n, tracker)` — Separator line with iteration number, features count, last score
- `show_agent_text(text)` — Truncated preview of agent's thinking (first 200 chars + "...")
- `show_tool_call(name, summary)` — "🔧 Bash: npm install..." style lines
- `show_feature_completed(name)` — "✅ Completed: particle effects"
- `show_error(iteration, error)` — "✗ Error in iteration 5: ..."
- `show_quality_reached(tracker)` — "🎉 Quality threshold reached!"
- `show_interrupted()` — "🛑 Interrupted by user"
- `show_summary(tracker)` — Final box with total iterations, features, quality score history, duration

Keep output concise. The agent produces a LOT of text via tool calls — don't echo all of it. Show enough to know what's happening without flooding the terminal.

---

## Module 6: `__main__.py`

### CLI Interface

```
usage: iclaw [-h] -g GOAL [-p PROJECT] [-m MODEL] [-t THRESHOLD]
             [--max-iterations N] [--eval-frequency N]
             [--use-api-key] [--api-key KEY]
             [--no-screenshot] [--port PORT]
             [--dev-cmd CMD] [-q] [-v]

InductiveClaw — Autonomous iterative coding agent

required:
  -g, --goal GOAL           What to build (required)

project:
  -p, --project DIR         Project directory (default: ./project)
  -m, --model MODEL         Model override (default: SDK default)

iteration control:
  -t, --threshold N         Quality threshold 1-10 (default: 8)
  --max-iterations N        Max outer loop iterations (default: 100)
  --eval-frequency N        Evaluate every N iterations (default: 3)

auth:
  --use-api-key             Prefer API key over OAuth even if OAuth available
  --api-key KEY             Explicit API key (overrides environment)

visual:
  --no-screenshot           Disable screenshot evaluation
  --port PORT               Dev server port for screenshots (default: 3000)
  --dev-cmd CMD             Dev server command (auto-detected if omitted)

output:
  -q, --quiet               Minimal output
  -v, --verbose             Full agent output (very noisy)
```

### Entrypoint Flow

```python
def main():
    args = parse_args()
    config = ClawConfig(
        project_dir=args.project,
        goal=args.goal,
        model=args.model,
        quality_threshold=args.threshold,
        max_iterations=args.max_iterations,
        eval_frequency=args.eval_frequency,
        auto_screenshot=not args.no_screenshot,
        screenshot_port=args.port,
        dev_server_cmd=args.dev_cmd,
        verbose=args.verbose if not args.quiet else False,
    )

    # Auth resolution — single call, single place
    auth_result = auth.resolve(
        prefer_oauth=not args.use_api_key,
        force_api_key=args.api_key,
    )

    # Run the loop
    anyio.run(agent.run, config, auth_result)
```

---

## `pyproject.toml`

```toml
[project]
name = "inductiveclaw"
version = "0.1.0"
description = "Autonomous iterative coding agent — builds until the vibe is right"
requires-python = ">=3.10"
dependencies = [
    "claude-agent-sdk>=0.1.0",
    "anyio>=4.0",
    "rich>=13.0",
]

[project.optional-dependencies]
screenshot = ["playwright>=1.40"]

[project.scripts]
iclaw = "inductiveclaw.__main__:main"
```

---

## Key Design Decisions Explained

### Why fresh SDK calls per iteration instead of one long session?

Context window management. Each Agent SDK call is a conversation. Over 20+ tool calls, the conversation history fills up with file contents, bash outputs, etc. Starting a new call each iteration resets this. The project state is persisted on disk (code files, BACKLOG.md, EVALUATIONS.md) so nothing is lost.

This is the equivalent of Claude Code's `/compact` but automatic.

### Why custom MCP tools instead of just Bash + Write?

Tool names are prompts. When the agent sees a tool called `self_evaluate` with a structured schema requiring scores 1-10, it's far more likely to actually evaluate quality than if you just tell it "write your evaluation to a file." Same with `update_backlog` — the structured input forces it to explicitly track completed items and next priorities.

### Why OAuth-first auth?

The whole motivation for InductiveClaw is running autonomous loops. On API billing, a 50-iteration session could cost $15-75+. On a Max subscription ($200/month), it's included. OAuth-first makes the default experience cost-effective.

### Why `anyio` instead of `asyncio`?

The Claude Agent SDK uses `anyio` internally. Matching the runtime avoids potential issues with nested event loops.

---

## Error Handling Strategy

### Agent SDK Errors

- `CLINotFoundError` — Claude Code CLI not installed. Surface this clearly with install instructions.
- `ProcessError` — CLI process crashed. Log it, continue to next iteration. If it happens 3 times in a row, stop and surface the error.
- `CLIConnectionError` — Auth issue mid-session. Re-run auth resolution and retry once.

### Tool Errors

- Screenshot tool failures (Playwright not installed, server not running) — Non-fatal. Agent falls back to code-only evaluation.
- File read/write failures — Let the Agent SDK's built-in error handling propagate. The agent will see the error and adapt.

### Graceful Shutdown

- Catch `KeyboardInterrupt` (Ctrl+C) — Set a flag, let current SDK call finish, then stop the outer loop cleanly. Show summary.
- Catch `SIGTERM` — Same behavior.
- Never hard-kill mid-file-write.

---

## Testing Plan

After building, verify the following manually:

1. **Auth flow:** Run with only OAuth (no API key set). Verify it uses subscription.
2. **Auth flow:** Run with `--use-api-key`. Verify it uses API key.
3. **Auth flow:** Run with no auth at all. Verify helpful error message.
4. **Basic loop:** `iclaw -g "Create a single HTML page that says hello world" --max-iterations 3 --threshold 5`
5. **Backlog tracking:** After run, check that BACKLOG.md has timestamped entries with completed items.
6. **Evaluation:** After run, check that EVALUATIONS.md has structured scores.
7. **Interrupt:** Start a run, Ctrl+C during iteration, verify clean shutdown and summary display.
8. **Screenshot tool:** Run with a web project, verify screenshot is captured and agent reads it.
9. **Resume:** Run once, stop, run again in same project dir. Verify agent reads existing BACKLOG.md and continues.

---

## Example Usage

```bash
# Install
pip install inductiveclaw

# Build a game from scratch (uses Max subscription by default)
iclaw -g "Build a roguelike deckbuilder with pixel art style and procedural dungeon generation"

# Continue on existing project
iclaw -p ./my-game -g "Polish visuals, add sound effects, improve the tutorial"

# Quick prototype with low quality bar
iclaw -g "Simple snake game in the browser" --threshold 5 --max-iterations 10

# Use API key explicitly
iclaw -g "Multiplayer chat app" --api-key sk-ant-...

# Disable screenshots for non-visual projects
iclaw -g "Build a CLI tool for CSV analysis" --no-screenshot
```

---

## What Success Looks Like

When InductiveClaw is working correctly, you should be able to:

1. Type one command with a goal
2. Walk away
3. Come back to a working, documented, polished project with a BACKLOG.md showing 10-20 completed features, an EVALUATIONS.md showing quality improving over iterations, a README explaining how to run it, and code that actually works when you run it

The project should look like something a skilled developer built over a weekend, not like an AI spit out a single file.

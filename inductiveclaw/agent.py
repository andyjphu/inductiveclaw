"""The outer autonomous loop and Agent SDK integration."""

from __future__ import annotations

import re
import signal
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
)
from claude_agent_sdk.types import TextBlock, ToolUseBlock

from . import display
from .auth import AuthResult
from .config import ClawConfig, UsageTracker
from .tools import create_iclaw_tools

SYSTEM_PROMPT = """\
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

MAX_CONSECUTIVE_ERRORS = 3


@dataclass
class IterationResult:
    should_stop: bool = False
    features_completed: list[str] = field(default_factory=list)
    quality_score: int | None = None


def build_iteration_prompt(config: ClawConfig, iteration: int, tracker: UsageTracker) -> str:
    if iteration == 1:
        return (
            f"GOAL: {config.goal}\n\n"
            "This is iteration 1. The project directory may be empty or may have existing files.\n\n"
            "Your first tasks:\n"
            "1. Check if there are existing files (use Glob)\n"
            "2. If empty: initialize the project structure, create BACKLOG.md with a\n"
            "   prioritized feature list of 8-15 items, and build the first core feature\n"
            "3. If files exist: read BACKLOG.md, orient yourself, and continue where\n"
            "   the previous session left off\n"
            "4. After building, run the code to verify it works\n"
            "5. Update BACKLOG.md\n\n"
            "Go. Do not ask for clarification — make decisions and build."
        )

    parts = [f"GOAL: {config.goal}", f"This is iteration {iteration}."]

    if tracker.features_completed:
        recent = tracker.features_completed[-5:]
        parts.append(f"Recently completed: {', '.join(recent)}")

    if tracker.last_quality_score is not None:
        parts.append(f"Last quality score: {tracker.last_quality_score}/10")
        gap = config.quality_threshold - tracker.last_quality_score
        if gap > 0:
            parts.append(f"Need {gap} more points to reach threshold.")

    if tracker.errors:
        recent_errors = tracker.errors[-2:]
        parts.append(f"Recent errors to be aware of: {'; '.join(recent_errors)}")

    if iteration % config.eval_frequency == 0:
        parts.append(
            "\nThis is an evaluation iteration. After making progress, "
            "use self_evaluate to score the current state. Be critical and honest."
        )

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


def _build_sdk_options(
    config: ClawConfig,
    tools_server: object,
    auth_result: AuthResult,
) -> ClaudeAgentOptions:
    opts = ClaudeAgentOptions(
        allowed_tools=[
            "Bash", "Read", "Write", "Edit", "Glob", "Grep",
            "mcp__iclaw-tools__update_backlog",
            "mcp__iclaw-tools__self_evaluate",
            "mcp__iclaw-tools__take_screenshot",
            "mcp__iclaw-tools__write_docs",
        ],
        permission_mode="bypassPermissions",
        cwd=str(Path(config.project_dir).resolve()),
        max_turns=config.max_turns_per_iteration,
        mcp_servers={"iclaw-tools": tools_server},
        system_prompt=SYSTEM_PROMPT,
        env=auth_result.get_sdk_env(),
    )
    if config.model:
        opts.model = config.model
    return opts


async def _run_single_iteration(
    prompt: str,
    options: ClaudeAgentOptions,
    config: ClawConfig,
    tracker: UsageTracker,
    verbose: bool,
) -> IterationResult:
    """Run one Agent SDK call and extract results."""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    if verbose:
                        display.show_agent_text(block.text)
                elif isinstance(block, ToolUseBlock):
                    display.show_tool_call(block.name, str(block.input)[:100])

        if isinstance(message, ResultMessage):
            if hasattr(message, "result") and message.result:
                display.show_result(str(message.result))

    return _extract_iteration_results(config, tracker)


def _extract_iteration_results(config: ClawConfig, tracker: UsageTracker) -> IterationResult:
    """Read project files to determine what happened in this iteration."""
    result = IterationResult()
    project = Path(config.project_dir)

    # Parse latest evaluation
    eval_path = project / "EVALUATIONS.md"
    if eval_path.exists():
        content = eval_path.read_text()
        # Find all "Overall" scores
        scores = re.findall(r"\*\*Overall\*\*\s*\|\s*\*\*(\d+)/10\*\*", content)
        if scores:
            score = int(scores[-1])
            tracker.last_quality_score = score
            tracker.quality_history.append(score)
            result.quality_score = score
            if score >= config.quality_threshold:
                # Also check ready_to_ship in the last evaluation block
                ship_matches = re.findall(r"\*\*Ready to ship:\*\*\s*(Yes|No)", content)
                if ship_matches and ship_matches[-1] == "Yes":
                    result.should_stop = True

    # Parse completed items from backlog
    backlog_path = project / "BACKLOG.md"
    if backlog_path.exists():
        content = backlog_path.read_text()
        completed = re.findall(r"\*\*Completed:\*\*\s*(.+)", content)
        for item in completed:
            item = item.strip()
            if item and item not in tracker.features_completed:
                tracker.features_completed.append(item)
                display.show_feature_completed(item)

    return result


async def run(config: ClawConfig, auth_result: AuthResult) -> None:
    """Main autonomous loop."""
    tracker = UsageTracker()
    tools_server = create_iclaw_tools(config)

    display.show_banner(config, auth_result)

    Path(config.project_dir).mkdir(parents=True, exist_ok=True)

    interrupted = False
    consecutive_errors = 0

    def handle_interrupt(sig, frame):
        nonlocal interrupted
        interrupted = True

    prev_handler = signal.signal(signal.SIGINT, handle_interrupt)
    prev_term = signal.signal(signal.SIGTERM, handle_interrupt)

    try:
        for iteration in range(1, config.max_iterations + 1):
            if interrupted:
                display.show_interrupted()
                break

            display.show_iteration_header(iteration, tracker)

            prompt = build_iteration_prompt(config, iteration, tracker)
            options = _build_sdk_options(config, tools_server, auth_result)

            try:
                result = await _run_single_iteration(
                    prompt, options, config, tracker, config.verbose
                )
                consecutive_errors = 0
            except KeyboardInterrupt:
                display.show_interrupted()
                break
            except CLINotFoundError:
                display.show_error(
                    iteration,
                    Exception("Claude Code CLI not found. Install it: npm install -g @anthropic-ai/claude-code"),
                )
                break
            except CLIConnectionError as e:
                consecutive_errors += 1
                tracker.errors.append(f"Iteration {iteration}: Connection error — {e}")
                display.show_error(iteration, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    display.show_error(iteration, Exception(f"{MAX_CONSECUTIVE_ERRORS} consecutive errors, stopping."))
                    break
                continue
            except ProcessError as e:
                consecutive_errors += 1
                tracker.errors.append(f"Iteration {iteration}: Process error — {e}")
                display.show_error(iteration, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    display.show_error(iteration, Exception(f"{MAX_CONSECUTIVE_ERRORS} consecutive errors, stopping."))
                    break
                continue
            except Exception as e:
                consecutive_errors += 1
                tracker.errors.append(f"Iteration {iteration}: {e}")
                display.show_error(iteration, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    break
                continue

            tracker.iterations_completed = iteration

            if result.should_stop:
                display.show_quality_reached(tracker)
                break
    finally:
        signal.signal(signal.SIGINT, prev_handler)
        signal.signal(signal.SIGTERM, prev_term)

    display.show_summary(tracker)

# The Iteration Loop

## Overview

The outer loop in `agent.py` calls `query()` repeatedly. Each call is one "iteration" where the inner agent can make up to `max_turns_per_iteration` tool calls.

```
for iteration in 1..max_iterations:
    prompt  = build_iteration_prompt(config, iteration, tracker)
    options = _build_sdk_options(config, tools_server, auth_result)
    result  = await _run_single_iteration(prompt, options, ...)
    if result.should_stop: break
```

## Prompt Structure

**System prompt** (constant across iterations): Defines identity, workflow, quality standards, rules. Set via `ClaudeAgentOptions.system_prompt`.

**Iteration prompt** (changes each iteration): The "user message" passed to `query()`.

### Iteration 1
- States the goal
- Checks for existing files (resume support)
- If empty: init project, create BACKLOG.md with 8-15 items, build first feature
- If files exist: read BACKLOG.md and continue

### Iterations 2+
- States the goal and iteration number
- Lists recently completed features (last 5)
- Reports last quality score and gap to threshold
- Lists recent errors
- On evaluation iterations (every `eval_frequency`): triggers `self_evaluate`
- On evaluation iterations with `auto_screenshot`: triggers `take_screenshot`
- Always ends with: "Read BACKLOG.md, pick highest-impact, build, verify, update"

## Stop Conditions

The loop stops when any of these are true:

1. **Quality threshold reached:** `overall_score >= quality_threshold AND ready_to_ship == True`
2. **Max iterations exhausted:** `iteration >= max_iterations`
3. **User interrupt:** Ctrl+C / SIGTERM — graceful shutdown, shows summary
4. **Consecutive errors:** 3 SDK errors in a row (CLIConnectionError, ProcessError, etc.)
5. **CLI not found:** Immediate stop with install instructions

## Error Handling

| Error | Behavior |
|-------|----------|
| `CLINotFoundError` | Stop immediately, print install instructions |
| `CLIConnectionError` | Log, increment consecutive counter, continue |
| `ProcessError` | Log, increment consecutive counter, continue |
| Generic `Exception` | Log, increment consecutive counter, continue |
| `KeyboardInterrupt` | Clean shutdown, show summary |

Consecutive error counter resets after any successful iteration.

## Result Extraction

After each iteration, `_extract_iteration_results()` reads files the inner agent wrote:

- **EVALUATIONS.md** — regex for `**Overall** | **N/10**` and `**Ready to ship:** Yes/No`
- **BACKLOG.md** — regex for `**Completed:** ...` lines

This is the bridge between the inner agent's tool calls and the outer loop's control logic.

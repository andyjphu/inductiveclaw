# Design Decisions

Record of architectural decisions made during InductiveClaw development,
with rationale and alternatives considered.

---

## D001: OS-Level Sandbox over Permission-Only Sandbox

**Date:** 2026-03-10
**Status:** Adopted

### Context

The agent was writing files outside the project directory (e.g. `/Users/.../calculator/`
when sandboxed to `/Users/.../sandbox/`). The initial approach used `add_dirs=[cwd]` +
system prompt instructions + `bypassPermissions`, which provided no enforcement.

### Approaches Considered

1. **Prompt-only sandbox** — Tell the agent "don't write outside the project dir."
   - No enforcement. Agent can ignore instructions (and did).

2. **`can_use_tool` callback** — SDK callback that gates every tool call.
   - Requires `permission_mode` NOT be `bypassPermissions` (they're mutually exclusive
     in practice — bypass tells the CLI to skip permission checks entirely, so the
     callback never fires).
   - Good for clean error messages but runs in-process, not at OS level.

3. **OS-level sandbox (Seatbelt/bubblewrap)** — The CLI's built-in `sandbox` option.
   - Kernel-level filesystem write restrictions. Even prompt injection can't escape.
   - `autoAllowBashIfSandboxed=True` auto-approves Bash since the OS constrains it.
   - `allowUnsandboxedCommands=False` blocks `dangerouslyDisableSandbox` escape hatch.

### Decision

Use **OS-level sandbox as the primary layer** + **`can_use_tool` as a secondary layer**.

The OS sandbox (via `SandboxSettings`) handles enforcement. The `can_use_tool` callback
provides friendlier error messages and catches obvious violations before they hit the OS
sandbox (like blocking `sudo`).

### Consequences

- Removed `permission_mode="bypassPermissions"` from interactive mode
- Agent can no longer auto-approve all tool calls — the `can_use_tool` callback must
  explicitly allow each one
- Bash commands inside the sandbox are auto-approved by the OS sandbox
- Future providers (OpenAI, Gemini) get the same sandbox for free — it's provider-agnostic

---

## D002: No Alternate Screen Buffer Without Full TUI

**Date:** 2026-03-10
**Status:** Adopted (with caveats)

### Context

Tried using the terminal's alternate screen buffer (`\033[?1049h`) to give iclaw a clean
slate on launch and restore terminal content on exit (like Claude Code). However, scroll
events in the alt screen generate arrow key escape sequences (`^[[B`) that leak to stdout
during agent work (when prompt_toolkit isn't consuming stdin).

### Approaches Considered

1. **Alt screen + `termios` stdin suppression** — Suppress echo and canonical mode during
   agent work, drain stdin after. This prevents `^[[B` from printing.
2. **No alt screen** — Just print in the normal terminal buffer.
3. **Full TUI framework (Textual/Ink)** — Would handle all input properly but massive scope.

### Decision

Use alt screen + `termios` suppression + stdin draining. This gets us Claude Code-like
clean launch/exit while preventing scroll artifacts.

- `_suppress_stdin()` — disables echo + canonical mode during agent response
- `_drain_stdin()` — discards queued escape sequences before returning to prompt_toolkit
- `_pad_to_bottom()` — pushes cursor near terminal bottom so prompt sits above toolbar

### Consequences

- Scrolling during agent work does nothing visible (input is suppressed)
- User can't type ahead while agent is working (acceptable trade-off)
- Alt screen means terminal content is restored on exit

---

## D003: prompt_toolkit for Input, Rich for Output

**Date:** 2026-03-10
**Status:** Adopted

### Context

Needed readline-like editing, command history, and tab completion for slash commands.
Raw `input()` provides none of these.

### Decision

- **prompt_toolkit** for input: async-compatible (`prompt_async`), history, completion,
  bottom toolbar, styled prompt
- **Rich** for output: markdown rendering, styled text, panels, tables

### Key details

- Must use `prompt_async()` (not `prompt()`) since we're in an async event loop
- Bottom toolbar styled with `PTStyle({"bottom-toolbar": "noinherit dim"})` to avoid
  reverse-video highlight
- Slash command completion via `WordCompleter`

---

## D004: Claude Code-Style Tool Call Display

**Date:** 2026-03-10
**Status:** Adopted

### Context

Initially suppressed all tool calls in interactive mode. Then realized Claude Code shows
them — just in a clean, compact format, not as raw dicts.

### Decision

Show tool calls with Claude Code iconography:
- `⏺ Bash(ls -la)` — tool name + summarized input
- `⎿  output here` — tool result with nested prefix
- `✻ thinking...` — static indicator when agent starts working

The SDK's `ToolResultBlock` (in `AssistantMessage.content`) provides tool output with
`content` (string or list) and `is_error` flag.

### Consequences

- Users see what the agent is doing without noise
- Tool results truncated to 5 lines with overflow count
- Errors shown in red

---

## D005: `bypassPermissions` and `can_use_tool` Are Mutually Exclusive

**Date:** 2026-03-10
**Status:** Lesson learned

### Context

Set `permission_mode="bypassPermissions"` alongside `can_use_tool` callback, expecting
both to work. The callback never fired because `bypassPermissions` tells the CLI to skip
ALL permission checks — the `can_use_tool` request is never sent to the SDK.

### Lesson

If you want programmatic permission control via `can_use_tool`, do NOT set
`bypassPermissions`. The permission mode must be `"default"` (or omitted) for the CLI
to route permission requests to the callback.

---

## D006: Ctrl+C Interrupts Agent Mid-Work

**Date:** 2026-03-10
**Status:** Adopted

### Decision

Wrap the agent response loop in `try/except KeyboardInterrupt`. When Ctrl+C fires during
agent work, it stops immediately and shows `⏹ interrupted`, then returns to the prompt.
Ctrl+C at the prompt exits iclaw entirely.

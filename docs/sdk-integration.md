# Claude Agent SDK Integration

## Package

`claude-agent-sdk` (import as `claude_agent_sdk`). Shells out to the Claude Code CLI.

**Current limitation:** The SDK only supports Claude models. OpenAI and Gemini providers will need separate API client implementations.

## Key Imports

```python
# One-shot queries (autonomous mode)
from claude_agent_sdk import query, ClaudeAgentOptions

# Multi-turn sessions (interactive mode)
from claude_agent_sdk import ClaudeSDKClient

# Message types
from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk.types import (
    TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock,
    StreamEvent,
    TaskStartedMessage, TaskProgressMessage, TaskNotificationMessage,
    SystemMessage,
)

# Sandbox and permissions
from claude_agent_sdk.types import (
    SandboxSettings,
    PermissionResultAllow, PermissionResultDeny,
    ToolPermissionContext,
)

# Custom tools
from claude_agent_sdk import tool, create_sdk_mcp_server

# Errors
from claude_agent_sdk import CLINotFoundError, CLIConnectionError, ProcessError
```

## ClaudeAgentOptions Fields We Use

| Field | Value | Purpose |
|-------|-------|---------|
| `allowed_tools` | Built-ins + `mcp__iclaw-tools__*` | Auto-approve tools |
| `permission_mode` | `"bypassPermissions"` (autonomous) / omitted (interactive) | Permission handling |
| `sandbox` | `SandboxSettings(enabled=True, ...)` | OS-level sandbox (interactive) |
| `can_use_tool` | `_make_sandbox_guard(cwd)` | Permission callback (interactive) |
| `include_partial_messages` | `True` (interactive) | Enable token-by-token streaming |
| `cwd` | Resolved project dir | Working directory |
| `add_dirs` | `[project_dir]` | Context directories |
| `max_turns` | `config.max_turns_per_iteration` (30) | Cap tool calls per iteration |
| `mcp_servers` | `{"iclaw-tools": server}` | Custom tool server (autonomous only) |
| `system_prompt` | Loaded from `.md` file | Agent identity and rules |
| `env` | `provider.get_sdk_env()` | Auth env from active provider |
| `model` | `config.model` or `provider.get_model()` | Model override |

## Message Types

The SDK yields 6 message types. Interactive mode handles all of them:

### AssistantMessage
Content blocks: `TextBlock`, `ThinkingBlock`, `ToolUseBlock`, `ToolResultBlock`.
Also has `.error` field (one of: `authentication_failed`, `billing_error`, `rate_limit`, `invalid_request`, `server_error`, `unknown`).

### ResultMessage (end of turn)
- `.total_cost_usd` — cumulative cost
- `.num_turns` — tool call turns used
- `.duration_ms` / `.duration_api_ms` — total and API-only latency
- `.usage` — `{"input_tokens": N, "output_tokens": N}` token counts
- `.stop_reason` — `"end_turn"`, `"max_tokens"`, `"tool_use"`, etc.
- `.is_error` — whether the turn ended in error
- `.result` / `.structured_output` — final output (if using `output_format`)

### StreamEvent (token-by-token)
Enabled by `include_partial_messages=True`. Raw Anthropic API stream events:
- `content_block_delta` with `text_delta` — live text output
- `content_block_delta` with `thinking_delta` — thinking tokens (not displayed)
- `content_block_delta` with `input_json_delta` — tool input tokens (not displayed)

### TaskStartedMessage
Fires when a sub-agent task starts. Fields: `task_id`, `description`, `task_type`.

### TaskProgressMessage
Periodic updates during sub-agent work. Fields: `description`, `last_tool_name`, `usage` (tokens, tool_uses, duration_ms).

### TaskNotificationMessage
Fires when a sub-agent completes/fails/stops. Fields: `status` (`completed`/`failed`/`stopped`), `summary`, `usage`.

## Autonomous Mode: `query()`

Async generator yielding all message types:

```python
async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock): ...
            elif isinstance(block, ToolUseBlock): ...
    if isinstance(message, ResultMessage):
        # .total_cost_usd, .num_turns, .session_id, .usage, .stop_reason
```

## Interactive Mode: `ClaudeSDKClient`

Async context manager for multi-turn conversation:

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("user input")
    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            # Token-by-token text
        elif isinstance(message, AssistantMessage):
            # Full blocks (when streaming disabled or for non-text)
        elif isinstance(message, TaskStartedMessage):
            # Sub-agent started
        elif isinstance(message, TaskProgressMessage):
            # Sub-agent progress
        elif isinstance(message, TaskNotificationMessage):
            # Sub-agent done
        elif isinstance(message, ResultMessage):
            # End of turn — cost, tokens, stop reason
```

## Sandbox and Permissions

### OS-Level Sandbox

```python
sandbox: SandboxSettings = {
    "enabled": True,                    # Seatbelt (macOS) / bubblewrap (Linux)
    "autoAllowBashIfSandboxed": True,   # Auto-approve Bash (OS constrains it)
    "allowUnsandboxedCommands": False,   # Block dangerouslyDisableSandbox escape
}
opts = ClaudeAgentOptions(sandbox=sandbox, ...)
```

### `can_use_tool` Callback

```python
async def guard(tool_name, tool_input, context) -> PermissionResultAllow | PermissionResultDeny:
    if _path_outside_sandbox(tool_input.get("file_path", "")):
        return PermissionResultDeny(behavior="deny", message="Outside sandbox")
    return PermissionResultAllow(behavior="allow")

opts = ClaudeAgentOptions(can_use_tool=guard, ...)
```

**Critical:** `bypassPermissions` suppresses `can_use_tool`. Don't combine them.

## Custom Tool Pattern

```python
@tool("name", "description", {"param": type})
async def my_tool(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": "result"}]}

server = create_sdk_mcp_server(name="server-name", version="1.0.0", tools=[my_tool])
```

Tool names in `allowed_tools`: `mcp__{server_name}__{tool_name}`.

## Other Options Not Yet Used

| Option | Purpose |
|--------|---------|
| `thinking` | `ThinkingConfig` — control extended thinking budget |
| `effort` | `"low"` / `"medium"` / `"high"` / `"max"` — thinking effort |
| `output_format` | JSON schema for structured output |
| `enable_file_checkpointing` | Track file changes, enable `rewind_files()` |
| `hooks` | Pre/Post tool execution hooks |
| `agents` | Custom agent definitions (sub-agents) |
| `continue_conversation` | Resume previous session |
| `max_budget_usd` | Hard cost cap |
| `fallback_model` | Model to use if primary fails |

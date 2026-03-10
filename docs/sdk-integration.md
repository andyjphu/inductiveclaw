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
from claude_agent_sdk.types import TextBlock, ToolUseBlock

# Custom tools
from claude_agent_sdk import tool, create_sdk_mcp_server

# Errors
from claude_agent_sdk import CLINotFoundError, CLIConnectionError, ProcessError
```

## ClaudeAgentOptions Fields We Use

| Field | Value | Purpose |
|-------|-------|---------|
| `allowed_tools` | Built-ins + `mcp__iclaw-tools__*` | Auto-approve tools |
| `permission_mode` | `"bypassPermissions"` | Fully autonomous |
| `cwd` | Resolved project dir | Working directory |
| `add_dirs` | `[project_dir]` | Restrict file access to project |
| `max_turns` | `config.max_turns_per_iteration` (30) | Cap tool calls per iteration |
| `mcp_servers` | `{"iclaw-tools": server}` | Custom tool server (autonomous only) |
| `system_prompt` | Loaded from `.md` file | Agent identity and rules |
| `env` | `provider.get_sdk_env()` | Auth env from active provider |
| `model` | `config.model` or `provider.get_model()` | Model override |

## Autonomous Mode: `query()`

Async generator yielding `AssistantMessage` and `ResultMessage`:

```python
async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock): ...
            elif isinstance(block, ToolUseBlock): ...
    if isinstance(message, ResultMessage):
        # .total_cost_usd, .num_turns, .session_id
```

## Interactive Mode: `ClaudeSDKClient`

Async context manager for multi-turn conversation:

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("user input")
    async for message in client.receive_response():
        ...
```

## Custom Tool Pattern

```python
@tool("name", "description", {"param": type})
async def my_tool(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": "result"}]}

server = create_sdk_mcp_server(name="server-name", version="1.0.0", tools=[my_tool])
```

Tool names in `allowed_tools`: `mcp__{server_name}__{tool_name}`.

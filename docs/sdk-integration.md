# Claude Agent SDK Integration

## Package

`claude-agent-sdk` (import as `claude_agent_sdk`). Shells out to the Claude Code CLI under the hood.

## Key Imports

```python
# Core
from claude_agent_sdk import query, ClaudeAgentOptions

# Message types (yielded by query())
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
| `allowed_tools` | Built-ins + `mcp__iclaw-tools__*` | Auto-approve these tools |
| `permission_mode` | `"bypassPermissions"` | Fully autonomous operation |
| `cwd` | Resolved project dir | Working directory for the inner agent |
| `max_turns` | `config.max_turns_per_iteration` (30) | Cap tool calls per iteration |
| `mcp_servers` | `{"iclaw-tools": server}` | Custom tool server |
| `system_prompt` | `SYSTEM_PROMPT` constant | Agent identity and rules |
| `env` | `auth_result.get_sdk_env()` | Modified env for auth |
| `model` | `config.model` (optional) | Model override |

## Message Stream

`query()` is an async generator yielding:

1. **`AssistantMessage`** — contains `content: list[TextBlock | ToolUseBlock | ...]`
   - `TextBlock.text` — agent's reasoning/output
   - `ToolUseBlock.name` / `ToolUseBlock.input` — tool calls
2. **`ResultMessage`** — final message with `result`, `duration_ms`, `num_turns`, `total_cost_usd`, `session_id`

## Custom Tool Pattern

```python
@tool("name", "description", {"param": type})
async def my_tool(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": "result"}]}

server = create_sdk_mcp_server(name="server-name", version="1.0.0", tools=[my_tool])
```

Tool names in `allowed_tools` follow the pattern `mcp__{server_name}__{tool_name}`.

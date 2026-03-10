# Authentication

## Resolution Order

1. **Explicit key** (`--api-key sk-ant-...`) — used directly, overrides everything
2. **OAuth** (default) — uses Claude Code CLI's stored credentials from `claude login`
3. **Environment key** (`ANTHROPIC_API_KEY`) — fallback if OAuth unavailable
4. **Error** — prints instructions for all three options

> Note: OAuth resolution is heuristic—InductiveClaw only checks that `claude` is on `PATH` and that `~/.claude` exists. It does not validate the token itself, so install and log in with `claude` before relying on OAuth.

## How OAuth Works

The Claude Code CLI stores OAuth tokens when a user logs in via `claude login`. When the Agent SDK shells out to the CLI, if no `ANTHROPIC_API_KEY` is in the environment, the CLI uses OAuth.

InductiveClaw's OAuth strategy: **strip `ANTHROPIC_API_KEY` from the environment** before calling the SDK. The `AuthResult.env_removals` list handles this. Installing the `claude` CLI (`npm install -g @anthropic-ai/claude-code`) and running `claude login` is required for OAuth/shelling out to work.

## AuthResult Structure

```python
@dataclass
class AuthResult:
    method: AuthMethod          # OAUTH or API_KEY
    env_overrides: dict         # env vars to SET (e.g. explicit API key)
    env_removals: list[str]     # env vars to REMOVE (e.g. strip key for OAuth)
    display_name: str           # human-readable label for banner
```

`AuthResult.get_sdk_env()` returns a modified `os.environ` copy with overrides applied and removals stripped. This dict is passed to `ClaudeAgentOptions.env`.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Both OAuth and API key available | Prefers OAuth (subscription). `--use-api-key` overrides. |
| OAuth token expired | CLI handles refresh automatically — not our concern. |
| Free tier (no Max/Pro) | OAuth works but hits rate limits fast. |
| CLI installed, never logged in | CLI fails at runtime. Agent loop catches and surfaces helpful message. |
| No auth at all | `AuthError` raised at startup with clear instructions. |

## CLI Flags

- `--use-api-key` — prefer environment `ANTHROPIC_API_KEY` over OAuth
- `--api-key KEY` — provide a key directly (not read from env)

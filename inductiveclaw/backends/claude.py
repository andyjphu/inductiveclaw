"""Claude Agent SDK backend — wraps ClaudeSDKClient and query()."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
    query,
)
from claude_agent_sdk.types import (
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    StreamEvent,
    TaskStartedMessage,
    TaskProgressMessage,
    TaskNotificationMessage,
    SystemMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
    SandboxSettings,
)

from .base import (
    AgentContentBlock,
    AgentMessage,
    AgentResult,
    AgentStreamEvent,
    AgentTaskNotification,
    AgentTaskProgress,
    AgentTaskStarted,
    AgentTextBlock,
    AgentThinkingBlock,
    AgentToolResultBlock,
    AgentToolUseBlock,
    AutonomousBackend,
    AutonomousMessage,
    BackendConnectionError,
    BackendNotFoundError,
    BackendProcessError,
    BackendRateLimitError,
    InteractiveBackend,
    InteractiveMessage,
)
from .sandbox import check_tool_sandbox, write_sandbox_settings


# --- Translation helpers ---

def _is_rate_limit(e: Exception) -> bool:
    err = str(e).lower()
    return "rate" in err and "limit" in err


def _translate_assistant(msg: AssistantMessage) -> AgentMessage:
    blocks = []
    for block in msg.content:
        if isinstance(block, TextBlock):
            blocks.append(AgentTextBlock(text=block.text))
        elif isinstance(block, ToolUseBlock):
            blocks.append(AgentToolUseBlock(
                name=block.name,
                input=block.input if isinstance(block.input, dict) else {},
            ))
        elif isinstance(block, ThinkingBlock):
            blocks.append(AgentThinkingBlock(thinking=block.thinking))
        elif isinstance(block, ToolResultBlock):
            blocks.append(AgentToolResultBlock(content=block.content, is_error=block.is_error))
    return AgentMessage(content=blocks, error=getattr(msg, "error", None))


def _translate_result(msg: ResultMessage) -> AgentResult:
    return AgentResult(
        stop_reason=msg.stop_reason,
        cost_usd=msg.total_cost_usd,
        num_turns=msg.num_turns,
        duration_ms=msg.duration_api_ms,
        usage=msg.usage,
        session_id=msg.session_id,
        is_error=msg.is_error,
        result=str(msg.result) if hasattr(msg, "result") and msg.result else None,
    )


def _translate_stream_event(msg: StreamEvent) -> AgentStreamEvent:
    event = msg.event
    event_type = event.get("type", "")
    block_type = ""
    delta_type = ""
    text = ""
    tool_name = ""

    if event_type == "content_block_start":
        cb = event.get("content_block", {})
        block_type = cb.get("type", "")
        if block_type == "tool_use":
            tool_name = cb.get("name", "")
    elif event_type == "content_block_delta":
        delta = event.get("delta", {})
        delta_type = delta.get("type", "")
        text = delta.get("text", "")

    return AgentStreamEvent(
        event_type=event_type,
        block_type=block_type,
        delta_type=delta_type,
        text=text,
        tool_name=tool_name,
    )


def _translate_interactive(msg: object) -> InteractiveMessage | None:
    if isinstance(msg, StreamEvent):
        return _translate_stream_event(msg)
    if isinstance(msg, AssistantMessage):
        return _translate_assistant(msg)
    if isinstance(msg, TaskStartedMessage):
        return AgentTaskStarted(description=msg.description, task_type=msg.task_type)
    if isinstance(msg, TaskProgressMessage):
        return AgentTaskProgress(
            description=msg.description,
            last_tool_name=msg.last_tool_name,
            usage=msg.usage,
        )
    if isinstance(msg, TaskNotificationMessage):
        return AgentTaskNotification(status=msg.status, summary=msg.summary)
    if isinstance(msg, ResultMessage):
        return _translate_result(msg)
    if isinstance(msg, SystemMessage):
        return None
    return None


def _wrap_error(e: Exception) -> Exception:
    """Convert SDK exceptions to backend error types."""
    if isinstance(e, CLINotFoundError):
        return BackendNotFoundError(str(e))
    if _is_rate_limit(e):
        return BackendRateLimitError(str(e))
    if isinstance(e, (CLIConnectionError, ProcessError)):
        err = BackendProcessError(
            str(e),
            exit_code=getattr(e, "exit_code", None),
        )
        return err
    return e


# --- Sandbox guard (Claude-specific, uses SDK permission types) ---

def _make_sandbox_guard(project_dir: str) -> Any:
    """Create a can_use_tool callback for the Claude Agent SDK."""

    async def guard(
        tool_name: str,
        tool_input: dict,
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        allowed, reason = check_tool_sandbox(tool_name, tool_input, project_dir)
        if allowed:
            return PermissionResultAllow(behavior="allow")
        return PermissionResultDeny(behavior="deny", message=reason)

    return guard


# --- Autonomous backend ---

class ClaudeAutonomousBackend(AutonomousBackend):
    """Wraps claude_agent_sdk.query() for autonomous mode."""

    def __init__(
        self,
        *,
        system_prompt: str,
        allowed_tools: list[str],
        cwd: str,
        env: dict[str, str],
        model: str | None = None,
        max_turns: int = 30,
        mcp_servers: dict[str, Any] | None = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._allowed_tools = allowed_tools
        self._cwd = cwd
        self._env = env
        self._model = model
        self._max_turns = max_turns
        self._mcp_servers = mcp_servers or {}

    async def run_iteration(self, prompt: str) -> AsyncIterator[AutonomousMessage]:
        opts = ClaudeAgentOptions(
            allowed_tools=self._allowed_tools,
            permission_mode="bypassPermissions",
            cwd=self._cwd,
            add_dirs=[self._cwd],
            max_turns=self._max_turns,
            mcp_servers=self._mcp_servers,
            system_prompt=self._system_prompt,
            env=self._env,
        )
        if self._model:
            opts.model = self._model

        try:
            async for message in query(prompt=prompt, options=opts):
                if isinstance(message, AssistantMessage):
                    yield _translate_assistant(message)
                elif isinstance(message, ResultMessage):
                    yield _translate_result(message)
        except Exception as e:
            raise _wrap_error(e) from e


# --- Interactive backend ---

class ClaudeInteractiveBackend(InteractiveBackend):
    """Wraps ClaudeSDKClient for interactive mode."""

    def __init__(
        self,
        *,
        system_prompt: str,
        cwd: str,
        env: dict[str, str],
        model: str | None = None,
        resume: str | None = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._cwd = cwd
        self._env = env
        self._model = model
        self._resume = resume
        self._client: ClaudeSDKClient | None = None
        self._session_id: str | None = None

    async def start(self) -> None:
        write_sandbox_settings(self._cwd)

        sandbox: SandboxSettings = {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
        }

        opts = ClaudeAgentOptions(
            allowed_tools=[],
            cwd=self._cwd,
            add_dirs=[self._cwd],
            system_prompt=self._system_prompt,
            env=self._env,
            sandbox=sandbox,
            can_use_tool=_make_sandbox_guard(self._cwd),
            include_partial_messages=True,
        )
        if self._model:
            opts.model = self._model
        if self._resume:
            opts.resume = self._resume

        self._client = ClaudeSDKClient(options=opts)
        await self._client.__aenter__()

    async def send_message(self, message: str) -> None:
        assert self._client is not None
        try:
            await self._client.query(message)
        except Exception as e:
            raise _wrap_error(e) from e

    async def receive(self) -> AsyncIterator[InteractiveMessage]:
        assert self._client is not None
        try:
            async for msg in self._client.receive_response():
                translated = _translate_interactive(msg)
                if translated is not None:
                    if isinstance(translated, AgentResult) and translated.session_id:
                        self._session_id = translated.session_id
                    yield translated
        except Exception as e:
            raise _wrap_error(e) from e

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

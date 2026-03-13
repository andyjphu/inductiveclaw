"""OpenAI backend — uses the OpenAI Python SDK for chat completions + tool calling."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional

from .base import (
    AgentMessage, AgentResult, AgentTextBlock, AgentToolUseBlock,
    AgentToolResultBlock, AgentStreamEvent, AgentTaskStarted,
    AutonomousBackend, AutonomousMessage, BackendConnectionError,
    BackendRateLimitError, InteractiveBackend, InteractiveMessage,
)
from .costs import estimate_cost
from .tool_executor import ToolExecutor, get_all_tool_schemas


def _build_openai_tools() -> list[dict[str, Any]]:
    """Convert our tool schemas to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": schema["description"],
                "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for name, schema in get_all_tool_schemas().items()
    ]


def _parse_tool_args(tc: Any) -> dict[str, Any]:
    try:
        return json.loads(tc.function.arguments)
    except json.JSONDecodeError:
        return {}


def _serialize_tool_calls(tool_calls: list) -> list[dict[str, Any]]:
    return [
        {"id": tc.id, "type": "function",
         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
        for tc in tool_calls
    ]


def _translate_response(msg: Any) -> tuple[list, list]:
    """Parse an OpenAI assistant message into (blocks, tool_calls)."""
    blocks = []
    if msg.content:
        blocks.append(AgentTextBlock(text=msg.content))
    tool_calls = msg.tool_calls or []
    for tc in tool_calls:
        blocks.append(AgentToolUseBlock(name=tc.function.name, input=_parse_tool_args(tc)))
    return blocks, tool_calls


def _extract_usage(response: Any) -> Optional[dict[str, int]]:
    if response.usage:
        return {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }
    return None


def _wrap_error(e: Exception) -> Exception:
    err_str = str(e).lower()
    if "rate" in err_str and "limit" in err_str:
        return BackendRateLimitError(str(e))
    if "connect" in type(e).__name__.lower() or "timeout" in type(e).__name__.lower():
        return BackendConnectionError(str(e))
    return e


class OpenAIAutonomousBackend(AutonomousBackend):
    """OpenAI chat completions with tool-calling loop for autonomous mode."""

    def __init__(self, *, system_prompt: str, project_dir: str, env: dict[str, str],
                 model: str = "o3", max_turns: int = 30, screenshot_port: int = 3000) -> None:
        self._system_prompt = system_prompt
        self._env = env
        self._model = model
        self._max_turns = max_turns
        self._executor = ToolExecutor(project_dir, screenshot_port=screenshot_port)

    async def run_iteration(self, prompt: str) -> AsyncIterator[AutonomousMessage]:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI backend requires 'openai'. Install: pip install iclaw[openai]"
            ) from None

        client = openai.AsyncOpenAI(api_key=self._env.get("OPENAI_API_KEY"))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]
        tools = _build_openai_tools()
        turns = 0

        try:
            while turns < self._max_turns:
                turns += 1
                response = await client.chat.completions.create(
                    model=self._model, messages=messages,
                    tools=tools or None, tool_choice="auto" if tools else None,
                )
                choice = response.choices[0]
                blocks, tool_calls = _translate_response(choice.message)
                yield AgentMessage(content=blocks)

                if not tool_calls:
                    break

                messages.append({
                    "role": "assistant", "content": choice.message.content,
                    "tool_calls": _serialize_tool_calls(tool_calls),
                })
                for tc in tool_calls:
                    result_text = await self._executor.execute(
                        tc.function.name, _parse_tool_args(tc),
                    )
                    yield AgentMessage(content=[AgentToolResultBlock(content=result_text)])
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})

                if choice.finish_reason == "stop":
                    break
        except Exception as e:
            raise _wrap_error(e) from e

        usage = _extract_usage(response)
        yield AgentResult(
            stop_reason=choice.finish_reason or "stop", num_turns=turns,
            usage=usage, cost_usd=estimate_cost(self._model, usage),
        )


class OpenAIInteractiveBackend(InteractiveBackend):
    """OpenAI chat completions for interactive mode with conversation history."""

    def __init__(self, *, system_prompt: str, project_dir: str, env: dict[str, str],
                 model: str = "o3", screenshot_port: int = 3000) -> None:
        self._system_prompt = system_prompt
        self._env = env
        self._model = model
        self._executor = ToolExecutor(project_dir, screenshot_port=screenshot_port)
        self._messages: list[dict[str, Any]] = []
        self._session_id: Optional[str] = None
        self._client: Any = None

    async def start(self) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI backend requires 'openai'. Install: pip install iclaw[openai]"
            ) from None
        self._client = openai.AsyncOpenAI(api_key=self._env.get("OPENAI_API_KEY"))
        self._session_id = f"openai-{uuid.uuid4().hex[:8]}"
        self._messages = [{"role": "system", "content": self._system_prompt}]

    async def send_message(self, message: str) -> None:
        self._messages.append({"role": "user", "content": message})

    async def receive(self) -> AsyncIterator[InteractiveMessage]:
        assert self._client is not None
        tools = _build_openai_tools()
        yield AgentTaskStarted(description="Thinking...")

        try:
            for _ in range(30):
                response = await self._client.chat.completions.create(
                    model=self._model, messages=self._messages,
                    tools=tools or None, tool_choice="auto" if tools else None,
                )
                choice = response.choices[0]
                blocks, tool_calls = _translate_response(choice.message)

                if choice.message.content:
                    yield AgentStreamEvent(
                        event_type="content_block_delta",
                        delta_type="text_delta", text=choice.message.content,
                    )
                yield AgentMessage(content=blocks)

                if not tool_calls:
                    break

                self._messages.append({
                    "role": "assistant", "content": choice.message.content,
                    "tool_calls": _serialize_tool_calls(tool_calls),
                })
                for tc in tool_calls:
                    result_text = await self._executor.execute(
                        tc.function.name, _parse_tool_args(tc),
                    )
                    yield AgentMessage(content=[AgentToolResultBlock(content=result_text)])
                    self._messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result_text},
                    )
                if choice.finish_reason == "stop":
                    break
        except Exception as e:
            raise _wrap_error(e) from e

        usage = _extract_usage(response)
        yield AgentResult(
            stop_reason="end_turn", usage=usage,
            session_id=self._session_id, cost_usd=estimate_cost(self._model, usage),
        )

    async def close(self) -> None:
        self._client = None
        self._messages = []

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

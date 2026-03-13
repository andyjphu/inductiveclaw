"""OpenAI backend — uses the OpenAI Python SDK for chat completions + tool calling."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional

from .base import (
    AgentMessage,
    AgentResult,
    AgentTextBlock,
    AgentToolUseBlock,
    AgentToolResultBlock,
    AgentStreamEvent,
    AgentTaskStarted,
    AutonomousBackend,
    AutonomousMessage,
    BackendConnectionError,
    BackendRateLimitError,
    InteractiveBackend,
    InteractiveMessage,
)
from .costs import estimate_cost
from .tool_executor import ToolExecutor, get_all_tool_schemas


def _build_openai_tools() -> list[dict[str, Any]]:
    """Convert our tool schemas to OpenAI function-calling format."""
    tools = []
    for name, schema in get_all_tool_schemas().items():
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": schema["description"],
                "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
            },
        })
    return tools


def _is_rate_limit(e: Exception) -> bool:
    err_str = str(e).lower()
    return "rate" in err_str and "limit" in err_str


def _wrap_error(e: Exception) -> Exception:
    """Convert OpenAI SDK exceptions to backend error types."""
    if _is_rate_limit(e):
        return BackendRateLimitError(str(e))
    # Check for common connection errors
    err_type = type(e).__name__
    if "connect" in err_type.lower() or "timeout" in err_type.lower():
        return BackendConnectionError(str(e))
    return e


class OpenAIAutonomousBackend(AutonomousBackend):
    """OpenAI chat completions with tool-calling loop for autonomous mode."""

    def __init__(
        self,
        *,
        system_prompt: str,
        project_dir: str,
        env: dict[str, str],
        model: str = "o3",
        max_turns: int = 30,
        screenshot_port: int = 3000,
    ) -> None:
        self._system_prompt = system_prompt
        self._project_dir = project_dir
        self._env = env
        self._model = model
        self._max_turns = max_turns
        self._executor = ToolExecutor(project_dir, screenshot_port=screenshot_port)

    async def run_iteration(self, prompt: str) -> AsyncIterator[AutonomousMessage]:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI backend requires the 'openai' package. "
                "Install it with: pip install iclaw[openai]"
            ) from None

        api_key = self._env.get("OPENAI_API_KEY")
        client = openai.AsyncOpenAI(api_key=api_key)

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
                    model=self._model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                )

                choice = response.choices[0]
                assistant_msg = choice.message

                # Translate to our message types
                blocks = []
                if assistant_msg.content:
                    blocks.append(AgentTextBlock(text=assistant_msg.content))

                tool_calls = assistant_msg.tool_calls or []
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    blocks.append(AgentToolUseBlock(
                        name=tc.function.name,
                        input=args,
                    ))

                yield AgentMessage(content=blocks)

                # If no tool calls, we're done
                if not tool_calls:
                    break

                # Execute tools and feed results back
                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                })

                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    result_text = await self._executor.execute(
                        tc.function.name, args,
                    )

                    # Yield tool result as message
                    yield AgentMessage(content=[
                        AgentToolResultBlock(content=result_text),
                    ])

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })

                if choice.finish_reason == "stop":
                    break

        except Exception as e:
            raise _wrap_error(e) from e

        # Yield final result
        usage = None
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        yield AgentResult(
            stop_reason=choice.finish_reason or "stop",
            num_turns=turns,
            usage=usage,
            cost_usd=estimate_cost(self._model, usage),
        )


class OpenAIInteractiveBackend(InteractiveBackend):
    """OpenAI chat completions for interactive mode with conversation history."""

    def __init__(
        self,
        *,
        system_prompt: str,
        project_dir: str,
        env: dict[str, str],
        model: str = "o3",
        screenshot_port: int = 3000,
    ) -> None:
        self._system_prompt = system_prompt
        self._project_dir = project_dir
        self._env = env
        self._model = model
        self._executor = ToolExecutor(project_dir, screenshot_port=screenshot_port)
        self._messages: list[dict[str, Any]] = []
        self._session_id: Optional[str] = None
        self._client: Any = None
        self._pending_response: Any = None

    async def start(self) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI backend requires the 'openai' package. "
                "Install it with: pip install iclaw[openai]"
            ) from None

        api_key = self._env.get("OPENAI_API_KEY")
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._session_id = f"openai-{uuid.uuid4().hex[:8]}"
        self._messages = [
            {"role": "system", "content": self._system_prompt},
        ]

    async def send_message(self, message: str) -> None:
        self._messages.append({"role": "user", "content": message})

    async def receive(self) -> AsyncIterator[InteractiveMessage]:
        assert self._client is not None

        tools = _build_openai_tools()
        max_tool_rounds = 30

        yield AgentTaskStarted(description="Thinking...")

        try:
            for _round in range(max_tool_rounds):
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=self._messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                )

                choice = response.choices[0]
                assistant_msg = choice.message

                # Yield text content
                blocks = []
                if assistant_msg.content:
                    blocks.append(AgentTextBlock(text=assistant_msg.content))

                    # Also yield as stream event for display compatibility
                    yield AgentStreamEvent(
                        event_type="content_block_delta",
                        delta_type="text_delta",
                        text=assistant_msg.content,
                    )

                tool_calls = assistant_msg.tool_calls or []
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    blocks.append(AgentToolUseBlock(name=tc.function.name, input=args))

                yield AgentMessage(content=blocks)

                if not tool_calls:
                    break

                # Record assistant message with tool calls
                self._messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                })

                # Execute each tool and feed results back
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    result_text = await self._executor.execute(
                        tc.function.name, args,
                    )

                    yield AgentMessage(content=[
                        AgentToolResultBlock(content=result_text),
                    ])

                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })

                if choice.finish_reason == "stop":
                    break

        except Exception as e:
            raise _wrap_error(e) from e

        # Yield result
        usage = None
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        yield AgentResult(
            stop_reason="end_turn",
            usage=usage,
            session_id=self._session_id,
            cost_usd=estimate_cost(self._model, usage),
        )

    async def close(self) -> None:
        self._client = None
        self._messages = []

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

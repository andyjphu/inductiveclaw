"""Gemini backend — uses the google-genai SDK for chat completions + tool calling."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional

from .base import (
    AgentMessage, AgentResult, AgentTextBlock, AgentToolUseBlock,
    AgentToolResultBlock, AgentStreamEvent, AgentTaskStarted,
    AutonomousBackend, AutonomousMessage, BackendConnectionError,
    BackendRateLimitError, InteractiveBackend, InteractiveMessage,
)
from .tool_executor import ToolExecutor, get_all_tool_schemas


def _build_gemini_tools() -> list[dict[str, Any]]:
    """Convert our tool schemas to Gemini function declarations."""
    declarations = []
    for name, schema in get_all_tool_schemas().items():
        declarations.append({
            "name": name,
            "description": schema["description"],
            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
        })
    return declarations


def _is_rate_limit(e: Exception) -> bool:
    err_str = str(e).lower()
    return "rate" in err_str and "limit" in err_str


def _wrap_error(e: Exception) -> Exception:
    if _is_rate_limit(e):
        return BackendRateLimitError(str(e))
    err_type = type(e).__name__
    if "connect" in err_type.lower() or "timeout" in err_type.lower():
        return BackendConnectionError(str(e))
    return e


class GeminiAutonomousBackend(AutonomousBackend):
    """Google Gemini with function-calling loop for autonomous mode."""

    def __init__(
        self,
        *,
        system_prompt: str,
        project_dir: str,
        env: dict[str, str],
        model: str = "gemini-2.5-pro",
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
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "Gemini backend requires the 'google-genai' package. "
                "Install it with: pip install iclaw[gemini]"
            ) from None

        api_key = self._env.get("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)

        tool_declarations = _build_gemini_tools()
        tools = types.Tool(function_declarations=tool_declarations)
        config = types.GenerateContentConfig(
            tools=[tools],
            system_instruction=self._system_prompt,
        )

        contents: list[Any] = [prompt]
        turns = 0

        try:
            while turns < self._max_turns:
                turns += 1

                response = await client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )

                candidate = response.candidates[0]
                parts = candidate.content.parts

                # Translate response parts to our message types
                blocks = []
                function_calls = []

                for part in parts:
                    if part.text:
                        blocks.append(AgentTextBlock(text=part.text))
                    if part.function_call:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        blocks.append(AgentToolUseBlock(name=fc.name, input=args))
                        function_calls.append(fc)

                yield AgentMessage(content=blocks)

                # If no function calls, we're done
                if not function_calls:
                    break

                # Add assistant response to conversation
                contents.append(candidate.content)

                # Execute each tool and feed results back
                function_response_parts = []
                for fc in function_calls:
                    args = dict(fc.args) if fc.args else {}
                    result_text = await self._executor.execute(fc.name, args)

                    yield AgentMessage(content=[
                        AgentToolResultBlock(content=result_text),
                    ])

                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result_text},
                        )
                    )

                contents.append(
                    types.Content(role="user", parts=function_response_parts)
                )

        except Exception as e:
            raise _wrap_error(e) from e

        # Yield final result
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "input_tokens": getattr(um, "prompt_token_count", 0),
                "output_tokens": getattr(um, "candidates_token_count", 0),
            }

        yield AgentResult(
            stop_reason="stop",
            num_turns=turns,
            usage=usage,
        )


class GeminiInteractiveBackend(InteractiveBackend):
    """Google Gemini for interactive mode with conversation history."""

    def __init__(
        self,
        *,
        system_prompt: str,
        project_dir: str,
        env: dict[str, str],
        model: str = "gemini-2.5-pro",
        screenshot_port: int = 3000,
    ) -> None:
        self._system_prompt = system_prompt
        self._project_dir = project_dir
        self._env = env
        self._model = model
        self._executor = ToolExecutor(project_dir, screenshot_port=screenshot_port)
        self._contents: list[Any] = []
        self._session_id: Optional[str] = None
        self._client: Any = None
        self._config: Any = None

    async def start(self) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "Gemini backend requires the 'google-genai' package. "
                "Install it with: pip install iclaw[gemini]"
            ) from None

        api_key = self._env.get("GEMINI_API_KEY")
        self._client = genai.Client(api_key=api_key)
        self._session_id = f"gemini-{uuid.uuid4().hex[:8]}"

        tool_declarations = _build_gemini_tools()
        tools = types.Tool(function_declarations=tool_declarations)
        self._config = types.GenerateContentConfig(
            tools=[tools],
            system_instruction=self._system_prompt,
        )
        self._contents = []

    async def send_message(self, message: str) -> None:
        self._contents.append(message)

    async def receive(self) -> AsyncIterator[InteractiveMessage]:
        assert self._client is not None

        from google.genai import types

        max_tool_rounds = 30

        yield AgentTaskStarted(description="Thinking...")

        try:
            for _round in range(max_tool_rounds):
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=self._contents,
                    config=self._config,
                )

                candidate = response.candidates[0]
                parts = candidate.content.parts

                blocks = []
                function_calls = []

                for part in parts:
                    if part.text:
                        blocks.append(AgentTextBlock(text=part.text))
                        yield AgentStreamEvent(
                            event_type="content_block_delta",
                            delta_type="text_delta",
                            text=part.text,
                        )
                    if part.function_call:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        blocks.append(AgentToolUseBlock(name=fc.name, input=args))
                        function_calls.append(fc)

                yield AgentMessage(content=blocks)

                if not function_calls:
                    break

                # Add assistant response to conversation
                self._contents.append(candidate.content)

                # Execute tools and send results back
                function_response_parts = []
                for fc in function_calls:
                    args = dict(fc.args) if fc.args else {}
                    result_text = await self._executor.execute(fc.name, args)

                    yield AgentMessage(content=[
                        AgentToolResultBlock(content=result_text),
                    ])

                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result_text},
                        )
                    )

                self._contents.append(
                    types.Content(role="user", parts=function_response_parts)
                )

        except Exception as e:
            raise _wrap_error(e) from e

        # Yield result
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "input_tokens": getattr(um, "prompt_token_count", 0),
                "output_tokens": getattr(um, "candidates_token_count", 0),
            }

        yield AgentResult(
            stop_reason="end_turn",
            usage=usage,
            session_id=self._session_id,
        )

    async def close(self) -> None:
        self._client = None
        self._contents = []

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

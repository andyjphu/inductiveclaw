"""Tests for the OpenAI backend — mock the OpenAI SDK to test the tool loop."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anyio

from inductiveclaw.backends.openai import (
    OpenAIAutonomousBackend,
    OpenAIInteractiveBackend,
    _build_openai_tools,
    _wrap_error,
)
from inductiveclaw.backends.base import (
    AgentMessage, AgentResult, AgentTextBlock, AgentToolUseBlock,
    AgentToolResultBlock, BackendRateLimitError, BackendConnectionError,
)


class TestBuildOpenAITools:
    def test_returns_list(self):
        tools = _build_openai_tools()
        assert isinstance(tools, list)
        assert len(tools) == 11  # 6 iclaw + 5 builtins

    def test_tool_format(self):
        tools = _build_openai_tools()
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


class TestWrapError:
    def test_rate_limit_detected(self):
        err = _wrap_error(Exception("Rate limit exceeded"))
        assert isinstance(err, BackendRateLimitError)

    def test_rate_limit_case_insensitive(self):
        err = _wrap_error(Exception("RATE LIMIT reached"))
        assert isinstance(err, BackendRateLimitError)

    def test_non_rate_limit_passes_through(self):
        original = ValueError("some error")
        err = _wrap_error(original)
        assert err is original


# --- Mock OpenAI response objects ---

def _make_message(content=None, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def _make_tool_call(name, args_dict, call_id="call_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args_dict)
    return tc


def _make_response(content=None, tool_calls=None, finish_reason="stop"):
    response = MagicMock()
    choice = MagicMock()
    choice.message = _make_message(content=content, tool_calls=tool_calls)
    choice.finish_reason = finish_reason
    response.choices = [choice]
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    return response


class TestOpenAIAutonomousBackend:
    def test_simple_text_response(self, tmp_path):
        """Model responds with text only, no tool calls."""
        mock_response = _make_response(content="Hello world", tool_calls=None)

        async def run():
            with patch("inductiveclaw.backends.openai.openai") as mock_openai:
                mock_client = AsyncMock()
                mock_openai.AsyncOpenAI.return_value = mock_client
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

                # Patch the import
                import inductiveclaw.backends.openai as oai_module
                original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

                backend = OpenAIAutonomousBackend(
                    system_prompt="test",
                    project_dir=str(tmp_path),
                    env={"OPENAI_API_KEY": "test"},
                    model="o3",
                )

                messages = []
                async for msg in backend.run_iteration("test prompt"):
                    messages.append(msg)

                return messages

        # We need to mock the openai import inside run_iteration
        # Since openai is imported at the top of the module, we can mock it directly
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            import sys
            mock_openai = sys.modules["openai"]
            mock_client = AsyncMock()
            mock_openai.AsyncOpenAI.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            backend = OpenAIAutonomousBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"OPENAI_API_KEY": "test"},
                model="o3",
            )

            messages = anyio.run(self._collect, backend, "test prompt")

        # Should have AgentMessage + AgentResult
        assert len(messages) >= 2
        assert isinstance(messages[0], AgentMessage)
        assert len(messages[0].content) == 1
        assert isinstance(messages[0].content[0], AgentTextBlock)
        assert messages[0].content[0].text == "Hello world"
        assert isinstance(messages[-1], AgentResult)
        assert messages[-1].cost_usd is not None

    def test_tool_call_then_response(self, tmp_path):
        """Model makes a tool call, gets result, then responds with text."""
        tc = _make_tool_call("read_file", {"file_path": "hello.py"})
        response1 = _make_response(content=None, tool_calls=[tc], finish_reason="tool_calls")
        response2 = _make_response(content="File contents shown", tool_calls=None)

        # Create the file the tool will read
        (tmp_path / "hello.py").write_text("print('hi')")

        with patch.dict("sys.modules", {"openai": MagicMock()}):
            import sys
            mock_openai = sys.modules["openai"]
            mock_client = AsyncMock()
            mock_openai.AsyncOpenAI.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[response1, response2]
            )

            backend = OpenAIAutonomousBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"OPENAI_API_KEY": "test"},
                model="o3",
            )

            messages = anyio.run(self._collect, backend, "read hello.py")

        # Should have: tool_call msg, tool_result msg, text msg, result
        tool_use_msgs = [m for m in messages if isinstance(m, AgentMessage)
                         and any(isinstance(b, AgentToolUseBlock) for b in m.content)]
        tool_result_msgs = [m for m in messages if isinstance(m, AgentMessage)
                            and any(isinstance(b, AgentToolResultBlock) for b in m.content)]
        results = [m for m in messages if isinstance(m, AgentResult)]

        assert len(tool_use_msgs) >= 1
        assert len(tool_result_msgs) >= 1
        assert len(results) == 1

    @staticmethod
    async def _collect(backend, prompt):
        messages = []
        async for msg in backend.run_iteration(prompt):
            messages.append(msg)
        return messages


class TestOpenAIInteractiveBackend:
    def test_start_creates_session(self, tmp_path):
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            backend = OpenAIInteractiveBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"OPENAI_API_KEY": "test"},
                model="o3",
            )

            anyio.run(backend.start)
            assert backend.session_id is not None
            assert backend.session_id.startswith("openai-")

    def test_send_message_appends(self, tmp_path):
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            backend = OpenAIInteractiveBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"OPENAI_API_KEY": "test"},
                model="o3",
            )

            anyio.run(backend.start)
            anyio.run(backend.send_message, "hello")
            # System message + user message
            assert len(backend._messages) == 2
            assert backend._messages[1]["role"] == "user"
            assert backend._messages[1]["content"] == "hello"

    def test_close_clears_state(self, tmp_path):
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            backend = OpenAIInteractiveBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"OPENAI_API_KEY": "test"},
                model="o3",
            )

            anyio.run(backend.start)
            anyio.run(backend.close)
            assert backend._client is None
            assert backend._messages == []

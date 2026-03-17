"""Tests for the Gemini backend — mock the google-genai SDK to test the tool loop."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anyio

from inductiveclaw.backends.gemini import (
    GeminiAutonomousBackend,
    GeminiInteractiveBackend,
    _build_gemini_tools,
    _wrap_error,
)
from inductiveclaw.backends.base import (
    AgentMessage, AgentResult, AgentTextBlock, AgentToolUseBlock,
    AgentToolResultBlock, BackendRateLimitError,
)


class TestBuildGeminiTools:
    def test_returns_list(self):
        tools = _build_gemini_tools()
        assert isinstance(tools, list)
        assert len(tools) == 12  # 7 iclaw + 5 builtins

    def test_declaration_format(self):
        tools = _build_gemini_tools()
        for decl in tools:
            assert "name" in decl
            assert "description" in decl
            assert "parameters" in decl


class TestGeminiWrapError:
    def test_rate_limit(self):
        err = _wrap_error(Exception("rate limit exceeded"))
        assert isinstance(err, BackendRateLimitError)

    def test_passthrough(self):
        original = ValueError("other error")
        err = _wrap_error(original)
        assert err is original


# --- Mock Gemini response objects ---

def _make_text_part(text):
    part = MagicMock()
    part.text = text
    part.function_call = None
    return part


def _make_function_call_part(name, args_dict):
    part = MagicMock()
    part.text = None
    fc = MagicMock()
    fc.name = name
    fc.args = args_dict
    part.function_call = fc
    return part


def _make_gemini_response(parts, has_usage=True):
    response = MagicMock()
    candidate = MagicMock()
    content = MagicMock()
    content.parts = parts
    candidate.content = content
    response.candidates = [candidate]
    if has_usage:
        um = MagicMock()
        um.prompt_token_count = 100
        um.candidates_token_count = 50
        response.usage_metadata = um
    else:
        response.usage_metadata = None
    return response


class TestGeminiAutonomousBackend:
    def test_simple_text_response(self, tmp_path):
        """Model responds with text, no function calls."""
        response = _make_gemini_response([_make_text_part("Hello from Gemini")])

        # Mock the google.genai module
        mock_genai = MagicMock()
        mock_types = MagicMock()
        mock_genai_client = MagicMock()
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=response)
        mock_genai.Client.return_value = mock_genai_client

        with patch.dict("sys.modules", {
            "google": MagicMock(),
            "google.genai": mock_genai,
        }):
            # Patch the imports inside the method
            import sys
            sys.modules["google"].genai = mock_genai
            sys.modules["google.genai"] = mock_genai
            sys.modules["google.genai"].types = mock_types

            backend = GeminiAutonomousBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"GEMINI_API_KEY": "test"},
                model="gemini-2.5-pro",
            )

            messages = anyio.run(self._collect, backend, "test prompt")

        assert len(messages) >= 2
        assert isinstance(messages[0], AgentMessage)
        assert any(isinstance(b, AgentTextBlock) for b in messages[0].content)
        assert isinstance(messages[-1], AgentResult)
        assert messages[-1].cost_usd is not None

    def test_function_call_then_response(self, tmp_path):
        """Model calls a tool, gets result, then responds."""
        (tmp_path / "test.py").write_text("# test file")

        fc_part = _make_function_call_part("read_file", {"file_path": "test.py"})
        response1 = _make_gemini_response([fc_part])
        response2 = _make_gemini_response([_make_text_part("I read the file")])

        mock_genai = MagicMock()
        mock_types = MagicMock()
        mock_types.Tool.return_value = MagicMock()
        mock_types.GenerateContentConfig.return_value = MagicMock()
        mock_types.Part.from_function_response.return_value = MagicMock()
        mock_types.Content.return_value = MagicMock()

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=[response1, response2]
        )
        mock_genai.Client.return_value = mock_client

        with patch.dict("sys.modules", {
            "google": MagicMock(),
            "google.genai": mock_genai,
        }):
            import sys
            sys.modules["google"].genai = mock_genai
            sys.modules["google.genai"] = mock_genai
            sys.modules["google.genai"].types = mock_types

            backend = GeminiAutonomousBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"GEMINI_API_KEY": "test"},
                model="gemini-2.5-pro",
            )

            messages = anyio.run(self._collect, backend, "read test.py")

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


class TestGeminiInteractiveBackend:
    def test_start_creates_session(self, tmp_path):
        mock_genai = MagicMock()
        mock_types = MagicMock()

        with patch.dict("sys.modules", {
            "google": MagicMock(),
            "google.genai": mock_genai,
        }):
            import sys
            sys.modules["google"].genai = mock_genai
            sys.modules["google.genai"] = mock_genai
            sys.modules["google.genai"].types = mock_types

            backend = GeminiInteractiveBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"GEMINI_API_KEY": "test"},
                model="gemini-2.5-pro",
            )

            anyio.run(backend.start)
            assert backend.session_id is not None
            assert backend.session_id.startswith("gemini-")

    def test_close_clears_state(self, tmp_path):
        mock_genai = MagicMock()
        mock_types = MagicMock()

        with patch.dict("sys.modules", {
            "google": MagicMock(),
            "google.genai": mock_genai,
        }):
            import sys
            sys.modules["google"].genai = mock_genai
            sys.modules["google.genai"] = mock_genai
            sys.modules["google.genai"].types = mock_types

            backend = GeminiInteractiveBackend(
                system_prompt="test",
                project_dir=str(tmp_path),
                env={"GEMINI_API_KEY": "test"},
                model="gemini-2.5-pro",
            )

            anyio.run(backend.start)
            anyio.run(backend.close)
            assert backend._client is None
            assert backend._contents == []

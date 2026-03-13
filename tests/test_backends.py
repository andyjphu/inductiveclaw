"""Tests for backend factory, message types, and provider routing."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import anyio

from inductiveclaw.backends.base import (
    AgentMessage, AgentResult, AgentTextBlock, AgentToolUseBlock,
    AgentThinkingBlock, AgentToolResultBlock, AgentStreamEvent,
    AgentTaskStarted, AgentTaskProgress, AgentTaskNotification,
    AutonomousBackend, InteractiveBackend,
    BackendError, BackendNotFoundError, BackendConnectionError,
    BackendRateLimitError, BackendProcessError,
)
from inductiveclaw.backends import create_autonomous_backend, create_interactive_backend
from inductiveclaw.providers.base import BaseProvider, ProviderID, AuthMode, ProviderConfig, ProviderStatus


# --- Message type tests ---

class TestMessageTypes:
    def test_agent_text_block(self):
        block = AgentTextBlock(text="hello")
        assert block.text == "hello"

    def test_agent_tool_use_block(self):
        block = AgentToolUseBlock(name="bash", input={"command": "ls"})
        assert block.name == "bash"
        assert block.input == {"command": "ls"}

    def test_agent_thinking_block(self):
        block = AgentThinkingBlock(thinking="hmm...")
        assert block.thinking == "hmm..."

    def test_agent_tool_result_block(self):
        block = AgentToolResultBlock(content="output", is_error=False)
        assert block.content == "output"
        assert block.is_error is False

    def test_agent_tool_result_error(self):
        block = AgentToolResultBlock(content="failed", is_error=True)
        assert block.is_error is True

    def test_agent_message_default(self):
        msg = AgentMessage()
        assert msg.content == []
        assert msg.error is None

    def test_agent_message_with_blocks(self):
        msg = AgentMessage(content=[
            AgentTextBlock(text="hi"),
            AgentToolUseBlock(name="bash", input={}),
        ])
        assert len(msg.content) == 2

    def test_agent_result_defaults(self):
        result = AgentResult()
        assert result.stop_reason is None
        assert result.cost_usd is None
        assert result.is_error is False

    def test_agent_result_full(self):
        result = AgentResult(
            stop_reason="end_turn",
            cost_usd=0.05,
            num_turns=3,
            duration_ms=1500,
            usage={"input_tokens": 1000, "output_tokens": 500},
            session_id="sess-123",
            is_error=False,
            result="done",
        )
        assert result.cost_usd == 0.05
        assert result.num_turns == 3
        assert result.session_id == "sess-123"

    def test_stream_event(self):
        event = AgentStreamEvent(
            event_type="content_block_delta",
            delta_type="text_delta",
            text="hello",
        )
        assert event.text == "hello"

    def test_task_started(self):
        ts = AgentTaskStarted(description="Working...")
        assert ts.description == "Working..."

    def test_task_progress(self):
        tp = AgentTaskProgress(last_tool_name="bash")
        assert tp.last_tool_name == "bash"

    def test_task_notification(self):
        tn = AgentTaskNotification(status="completed", summary="Done")
        assert tn.status == "completed"


# --- Error hierarchy tests ---

class TestErrors:
    def test_error_hierarchy(self):
        assert issubclass(BackendNotFoundError, BackendError)
        assert issubclass(BackendConnectionError, BackendError)
        assert issubclass(BackendRateLimitError, BackendError)
        assert issubclass(BackendProcessError, BackendError)

    def test_process_error_exit_code(self):
        err = BackendProcessError("failed", exit_code=1)
        assert err.exit_code == 1
        assert "failed" in str(err)

    def test_process_error_no_exit_code(self):
        err = BackendProcessError("failed")
        assert err.exit_code is None


# --- Mock provider for factory tests ---

class MockProvider(BaseProvider):
    id = ProviderID.OPENAI
    display_name = "Mock"

    def __init__(self, backend_type: str = "openai"):
        super().__init__()
        self._backend_type = backend_type

    def get_sdk_env(self):
        return {"OPENAI_API_KEY": "test-key"}

    def get_model(self):
        return "test-model"

    def is_configured(self):
        return True

    def configure(self, config):
        pass

    def status_line(self):
        return "mock"

    def get_backend_type(self):
        return self._backend_type


class TestBackendFactory:
    def test_openai_autonomous_creates_backend(self):
        provider = MockProvider("openai")
        backend = create_autonomous_backend(
            provider=provider,
            system_prompt="test",
            allowed_tools=["bash"],
            cwd="/tmp",
        )
        assert backend is not None
        assert hasattr(backend, "run_iteration")

    def test_openai_interactive_creates_backend(self):
        provider = MockProvider("openai")
        backend = create_interactive_backend(
            provider=provider,
            system_prompt="test",
            cwd="/tmp",
        )
        assert backend is not None
        assert hasattr(backend, "start")
        assert hasattr(backend, "send_message")
        assert hasattr(backend, "receive")
        assert hasattr(backend, "close")

    def test_gemini_autonomous_creates_backend(self):
        provider = MockProvider("gemini")
        provider.id = ProviderID.GEMINI
        # Override get_model for gemini
        provider.get_model = lambda: "gemini-2.5-pro"
        backend = create_autonomous_backend(
            provider=provider,
            system_prompt="test",
            allowed_tools=[],
            cwd="/tmp",
        )
        assert backend is not None

    def test_gemini_interactive_creates_backend(self):
        provider = MockProvider("gemini")
        provider.id = ProviderID.GEMINI
        provider.get_model = lambda: "gemini-2.5-pro"
        backend = create_interactive_backend(
            provider=provider,
            system_prompt="test",
            cwd="/tmp",
        )
        assert backend is not None

    def test_claude_raises_without_sdk(self):
        provider = MockProvider("claude")
        # Claude backend needs claude_agent_sdk which isn't installed
        with pytest.raises(Exception):
            create_autonomous_backend(
                provider=provider,
                system_prompt="test",
                allowed_tools=[],
                cwd="/tmp",
            )

    def test_unknown_backend_raises(self):
        provider = MockProvider("unknown_provider")
        with pytest.raises(NotImplementedError):
            create_autonomous_backend(
                provider=provider,
                system_prompt="test",
                allowed_tools=[],
                cwd="/tmp",
            )

    def test_unknown_interactive_raises(self):
        provider = MockProvider("unknown_provider")
        with pytest.raises(NotImplementedError):
            create_interactive_backend(
                provider=provider,
                system_prompt="test",
                cwd="/tmp",
            )


# --- Provider tests ---

class TestProviders:
    def test_openai_provider_backend_type(self):
        from inductiveclaw.providers.openai import OpenAIProvider
        p = OpenAIProvider()
        assert p.get_backend_type() == "openai"

    def test_gemini_provider_backend_type(self):
        from inductiveclaw.providers.gemini import GeminiProvider
        p = GeminiProvider()
        assert p.get_backend_type() == "gemini"

    def test_anthropic_provider_backend_type(self):
        from inductiveclaw.providers.anthropic import AnthropicProvider
        p = AnthropicProvider()
        assert p.get_backend_type() == "claude"

    def test_openai_provider_default_model(self):
        from inductiveclaw.providers.openai import OpenAIProvider
        p = OpenAIProvider()
        assert p.get_model() == "o3"

    def test_gemini_provider_default_model(self):
        from inductiveclaw.providers.gemini import GeminiProvider
        p = GeminiProvider()
        assert p.get_model() == "gemini-2.5-pro"

    def test_openai_configure_api_key(self):
        from inductiveclaw.providers.openai import OpenAIProvider
        p = OpenAIProvider()
        p.configure(ProviderConfig(
            provider_id=ProviderID.OPENAI,
            auth_mode=AuthMode.OPENAI_API_KEY,
            api_key="sk-test-123",
            enabled=True,
        ))
        assert p.is_configured() is True
        assert p.status == ProviderStatus.CONNECTED
        env = p.get_sdk_env()
        assert env["OPENAI_API_KEY"] == "sk-test-123"

    def test_gemini_configure_api_key(self):
        from inductiveclaw.providers.gemini import GeminiProvider
        p = GeminiProvider()
        p.configure(ProviderConfig(
            provider_id=ProviderID.GEMINI,
            auth_mode=AuthMode.GEMINI_API_KEY,
            api_key="gem-test-123",
            enabled=True,
        ))
        assert p.is_configured() is True
        assert p.status == ProviderStatus.CONNECTED
        env = p.get_sdk_env()
        assert env["GEMINI_API_KEY"] == "gem-test-123"

    def test_provider_not_configured_by_default(self):
        from inductiveclaw.providers.openai import OpenAIProvider
        p = OpenAIProvider()
        assert p.is_configured() is False
        assert p.status == ProviderStatus.NOT_CONFIGURED

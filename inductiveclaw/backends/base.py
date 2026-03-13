"""Provider-agnostic backend protocol and message types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Optional, Union


# --- Errors ---

class BackendError(Exception):
    """Base error for backend operations."""


class BackendNotFoundError(BackendError):
    """Backend CLI or binary not found."""


class BackendConnectionError(BackendError):
    """Connection to backend failed."""


class BackendRateLimitError(BackendError):
    """Rate limited by the provider."""


class BackendProcessError(BackendError):
    """Backend process error."""

    def __init__(self, message: str, exit_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --- Unified message types ---

@dataclass
class AgentTextBlock:
    text: str


@dataclass
class AgentToolUseBlock:
    name: str
    input: dict[str, Any]


@dataclass
class AgentThinkingBlock:
    thinking: str


@dataclass
class AgentToolResultBlock:
    content: Any  # str, list, or None
    is_error: bool = False


AgentContentBlock = Union[
    AgentTextBlock, AgentToolUseBlock, AgentThinkingBlock, AgentToolResultBlock
]


@dataclass
class AgentMessage:
    """A full assistant message with content blocks."""

    content: list[AgentContentBlock] = field(default_factory=list)
    error: str | None = None


@dataclass
class AgentStreamEvent:
    """Real-time streaming event for interactive mode."""

    event_type: str  # "content_block_start", "content_block_delta", "content_block_stop"
    block_type: str = ""  # "text", "tool_use", "thinking"
    delta_type: str = ""  # "text_delta", "thinking_delta", "input_json_delta"
    text: str = ""
    tool_name: str = ""


@dataclass
class AgentTaskStarted:
    description: str | None = None
    task_type: str | None = None


@dataclass
class AgentTaskProgress:
    description: str | None = None
    last_tool_name: str | None = None
    usage: dict[str, Any] | None = None


@dataclass
class AgentTaskNotification:
    status: str = ""  # "completed", "failed", "stopped"
    summary: str | None = None


@dataclass
class AgentResult:
    """End-of-turn result with metadata."""

    stop_reason: str | None = None
    cost_usd: float | None = None
    num_turns: int | None = None
    duration_ms: int | None = None
    usage: dict[str, int] | None = None
    session_id: str | None = None
    is_error: bool = False
    result: str | None = None


# Type aliases
AutonomousMessage = Union[AgentMessage, AgentResult]

InteractiveMessage = Union[
    AgentStreamEvent,
    AgentMessage,
    AgentTaskStarted,
    AgentTaskProgress,
    AgentTaskNotification,
    AgentResult,
]


# --- Backend ABCs ---

class AutonomousBackend(ABC):
    """Backend for autonomous mode (stateless per-iteration queries)."""

    @abstractmethod
    def run_iteration(self, prompt: str) -> AsyncIterator[AutonomousMessage]:
        """Run one iteration. Yields AgentMessages and a final AgentResult."""
        ...


class InteractiveBackend(ABC):
    """Backend for interactive mode (persistent session)."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize the backend session."""

    @abstractmethod
    async def send_message(self, message: str) -> None:
        """Send a user message to start an agent turn."""

    @abstractmethod
    def receive(self) -> AsyncIterator[InteractiveMessage]:
        """Yield streaming events and messages for the current turn."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Shut down the backend."""

    @property
    @abstractmethod
    def session_id(self) -> str | None:
        """Current session ID for resume capability."""

    def get_messages(self) -> list[dict[str, Any]] | None:
        """Return serializable message history for persistence.

        Returns None for backends that manage state externally (Claude).
        Override in backends that maintain local conversation history.
        """
        return None

    def restore_messages(self, messages: list[dict[str, Any]]) -> None:
        """Restore message history from a previous session.

        No-op for backends that manage state externally (Claude).
        Override in backends that maintain local conversation history.
        """

    async def __aenter__(self) -> InteractiveBackend:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

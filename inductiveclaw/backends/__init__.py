"""Backend abstraction — factory functions for creating provider-specific backends."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

from .base import (
    AutonomousBackend,
    InteractiveBackend,
    # Re-export error types for convenience
    BackendError,
    BackendConnectionError,
    BackendNotFoundError,
    BackendProcessError,
    BackendRateLimitError,
    # Re-export message types
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
)

if TYPE_CHECKING:
    from ..providers.base import BaseProvider

__all__ = [
    "AutonomousBackend",
    "InteractiveBackend",
    "create_autonomous_backend",
    "create_interactive_backend",
    # Errors
    "BackendError",
    "BackendConnectionError",
    "BackendNotFoundError",
    "BackendProcessError",
    "BackendRateLimitError",
    # Message types
    "AgentContentBlock",
    "AgentMessage",
    "AgentResult",
    "AgentStreamEvent",
    "AgentTaskNotification",
    "AgentTaskProgress",
    "AgentTaskStarted",
    "AgentTextBlock",
    "AgentThinkingBlock",
    "AgentToolResultBlock",
    "AgentToolUseBlock",
]


def create_autonomous_backend(
    *,
    provider: BaseProvider,
    system_prompt: str,
    allowed_tools: list[str],
    cwd: str,
    model: str | None = None,
    max_turns: int = 30,
    mcp_servers: dict[str, Any] | None = None,
) -> AutonomousBackend:
    """Create an autonomous backend for the given provider."""
    backend_type = provider.get_backend_type()
    resolved_cwd = str(Path(cwd).resolve())

    if backend_type == "claude":
        from .claude import ClaudeAutonomousBackend

        return ClaudeAutonomousBackend(
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            cwd=resolved_cwd,
            env=provider.get_sdk_env(),
            model=model,
            max_turns=max_turns,
            mcp_servers=mcp_servers or {},
        )

    raise NotImplementedError(
        f"Backend '{backend_type}' is not yet implemented. "
        f"Install the provider's optional dependencies and try again."
    )


def create_interactive_backend(
    *,
    provider: BaseProvider,
    system_prompt: str,
    cwd: str,
    model: str | None = None,
    resume: str | None = None,
) -> InteractiveBackend:
    """Create an interactive backend for the given provider."""
    backend_type = provider.get_backend_type()
    resolved_cwd = str(Path(cwd).resolve())

    if backend_type == "claude":
        from .claude import ClaudeInteractiveBackend

        return ClaudeInteractiveBackend(
            system_prompt=system_prompt,
            cwd=resolved_cwd,
            env=provider.get_sdk_env(),
            model=model,
            resume=resume,
        )

    raise NotImplementedError(
        f"Backend '{backend_type}' is not yet implemented. "
        f"Install the provider's optional dependencies and try again."
    )

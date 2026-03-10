"""Authentication resolution for the Agent SDK."""

from __future__ import annotations

import enum
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


class AuthMethod(enum.Enum):
    OAUTH = "oauth"
    API_KEY = "api_key"


class AuthError(Exception):
    """Raised when no authentication method is available."""


@dataclass
class AuthResult:
    method: AuthMethod
    env_overrides: dict[str, str] = field(default_factory=dict)
    env_removals: list[str] = field(default_factory=list)
    display_name: str = ""

    def get_sdk_env(self) -> dict[str, str]:
        """Return a modified copy of os.environ for Agent SDK calls."""
        env = os.environ.copy()
        for key in self.env_removals:
            env.pop(key, None)
        env.update(self.env_overrides)
        return env


def _has_claude_cli() -> bool:
    return shutil.which("claude") is not None


def _has_oauth_credentials() -> bool:
    claude_dir = Path.home() / ".claude"
    if not claude_dir.is_dir():
        return False
    # Check for any credential files
    return any(claude_dir.iterdir())


def resolve(
    prefer_oauth: bool = True,
    force_api_key: str | None = None,
) -> AuthResult:
    """Resolve authentication. Called once at startup."""

    # Explicit API key override
    if force_api_key:
        return AuthResult(
            method=AuthMethod.API_KEY,
            env_overrides={"ANTHROPIC_API_KEY": force_api_key},
            display_name="API key (explicit)",
        )

    # Try OAuth first
    if prefer_oauth and _has_claude_cli() and _has_oauth_credentials():
        return AuthResult(
            method=AuthMethod.OAUTH,
            env_removals=["ANTHROPIC_API_KEY"],
            display_name="Max/Pro subscription (OAuth)",
        )

    # Fall back to environment API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return AuthResult(
            method=AuthMethod.API_KEY,
            display_name="API key (environment)",
        )

    # Nothing available
    raise AuthError(
        "No authentication method available.\n\n"
        "Option 1: Log in to Claude Code (recommended for Max/Pro subscribers):\n"
        "  claude login\n\n"
        "Option 2: Set an API key:\n"
        "  export ANTHROPIC_API_KEY=sk-ant-...\n\n"
        "Option 3: Pass an API key directly:\n"
        "  iclaw --api-key sk-ant-... -g 'your goal'"
    )

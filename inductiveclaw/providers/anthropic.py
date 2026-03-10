"""Anthropic/Claude provider."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .base import (
    AuthMode,
    BaseProvider,
    ProviderConfig,
    ProviderID,
    ProviderStatus,
)


class AnthropicProvider(BaseProvider):
    id = ProviderID.ANTHROPIC
    display_name = "Claude (Anthropic)"

    def __init__(self) -> None:
        super().__init__()
        self._auth_mode: AuthMode | None = None
        self._api_key: str | None = None

    def get_sdk_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self._auth_mode == AuthMode.OAUTH:
            env.pop("ANTHROPIC_API_KEY", None)
        elif self._api_key:
            env["ANTHROPIC_API_KEY"] = self._api_key
        return env

    def get_model(self) -> str | None:
        return None  # use SDK default

    def is_configured(self) -> bool:
        if self._auth_mode == AuthMode.OAUTH:
            return _has_claude_cli() and _has_oauth_credentials()
        if self._auth_mode == AuthMode.API_KEY:
            return bool(self._api_key or os.environ.get("ANTHROPIC_API_KEY"))
        return False

    def configure(self, config: ProviderConfig) -> None:
        self._auth_mode = config.auth_mode
        self._api_key = config.api_key
        if self.is_configured():
            self.status = ProviderStatus.CONNECTED

    def auto_detect(self) -> bool:
        """Try to auto-detect auth without explicit config."""
        if _has_claude_cli() and _has_oauth_credentials():
            self._auth_mode = AuthMode.OAUTH
            self.status = ProviderStatus.CONNECTED
            return True
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            self._auth_mode = AuthMode.API_KEY
            self._api_key = api_key
            self.status = ProviderStatus.CONNECTED
            return True
        return False

    def status_line(self) -> str:
        if self.status == ProviderStatus.CONNECTED:
            if self._auth_mode == AuthMode.OAUTH:
                return "connected (Max/Pro OAuth)"
            return "connected (API key)"
        if self.status == ProviderStatus.EXHAUSTED:
            return "exhausted (rate limited)"
        return "not configured"


def _has_claude_cli() -> bool:
    return shutil.which("claude") is not None


def _has_oauth_credentials() -> bool:
    claude_dir = Path.home() / ".claude"
    if not claude_dir.is_dir():
        return False
    return any(claude_dir.iterdir())

"""Gemini provider."""

from __future__ import annotations

import os
from pathlib import Path

from .base import (
    AuthMode,
    BaseProvider,
    ProviderConfig,
    ProviderID,
    ProviderStatus,
)


class GeminiProvider(BaseProvider):
    id = ProviderID.GEMINI
    display_name = "Gemini (Google)"

    def __init__(self) -> None:
        super().__init__()
        self._auth_mode: AuthMode | None = None
        self._api_key: str | None = None

    def get_sdk_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self._api_key:
            env["GEMINI_API_KEY"] = self._api_key
        return env

    def get_model(self) -> str | None:
        return "gemini-2.5-pro"

    def is_configured(self) -> bool:
        if self._auth_mode == AuthMode.GOOGLE_OAUTH:
            return _has_google_oauth_credentials()
        if self._auth_mode == AuthMode.GEMINI_API_KEY:
            return bool(self._api_key or os.environ.get("GEMINI_API_KEY"))
        return False

    def configure(self, config: ProviderConfig) -> None:
        self._auth_mode = config.auth_mode
        self._api_key = config.api_key
        if self.is_configured():
            self.status = ProviderStatus.CONNECTED

    def status_line(self) -> str:
        if self.status == ProviderStatus.CONNECTED:
            if self._auth_mode == AuthMode.GOOGLE_OAUTH:
                return "connected (Google OAuth)"
            return "connected (API key)"
        if self.status == ProviderStatus.EXHAUSTED:
            return "exhausted (rate limited)"
        return "not configured"

    def get_backend_type(self) -> str:
        return "gemini"


def _has_google_oauth_credentials() -> bool:
    """Check if Google OAuth client_secret.json exists."""
    config_dir = Path.home() / ".config" / "iclaw"
    return (config_dir / "client_secret.json").exists()


# Pros/cons text used by setup flow
GOOGLE_OAUTH_INFO = """\
Google Cloud OAuth (Desktop App)
  Pros: Up to 1,000 requests/day on free tier (vs ~250 with API key).
        60 RPM vs 15 RPM. No per-token cost on free tier.
  Cons: Requires one-time Google Cloud Console setup (~5 min).
        You create a project, enable the Generative Language API,
        and download a client_secret.json. Browser-based auth.
  Best for: Heavy free-tier usage, research workflows.

  Setup steps:
    1. Go to https://console.cloud.google.com/
    2. Create a new project (e.g. "iclaw-gemini")
    3. APIs & Services > Library > enable "Generative Language API"
    4. APIs & Services > Credentials > Create Credentials > OAuth client ID
    5. Application type: Desktop app. Name: "iclaw"
    6. Download the JSON, rename to client_secret.json
    7. Place it at: ~/.config/iclaw/client_secret.json"""

GEMINI_API_KEY_INFO = """\
Gemini API Key
  Pros: Simplest setup — get a key from https://aistudio.google.com/apikey
        No Google Cloud project needed. Works immediately.
  Cons: Lower rate limits (~250 req/day, 15 RPM on free tier).
        Google may use your data to improve models on free tier.
  Best for: Quick setup, light usage, testing."""

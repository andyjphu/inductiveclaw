"""OpenAI/Codex provider."""

from __future__ import annotations

import os
import shutil

from .base import (
    AuthMode,
    BaseProvider,
    ProviderConfig,
    ProviderID,
    ProviderStatus,
)


class OpenAIProvider(BaseProvider):
    id = ProviderID.OPENAI
    display_name = "OpenAI (Codex)"

    def __init__(self) -> None:
        super().__init__()
        self._auth_mode: AuthMode | None = None
        self._api_key: str | None = None

    def get_sdk_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # For API key mode, pass the key; Agent SDK model override handles routing
        if self._api_key:
            env["OPENAI_API_KEY"] = self._api_key
        return env

    def get_model(self) -> str | None:
        # When using OpenAI, override the model
        return "o3"

    def is_configured(self) -> bool:
        if self._auth_mode == AuthMode.CODEX_APP_SERVER:
            return shutil.which("codex") is not None
        if self._auth_mode == AuthMode.OPENAI_API_KEY:
            return bool(self._api_key or os.environ.get("OPENAI_API_KEY"))
        return False

    def configure(self, config: ProviderConfig) -> None:
        self._auth_mode = config.auth_mode
        self._api_key = config.api_key
        if self.is_configured():
            self.status = ProviderStatus.CONNECTED

    def status_line(self) -> str:
        if self.status == ProviderStatus.CONNECTED:
            if self._auth_mode == AuthMode.CODEX_APP_SERVER:
                return "connected (Codex app-server)"
            return "connected (API key)"
        if self.status == ProviderStatus.EXHAUSTED:
            return "exhausted (rate limited)"
        return "not configured"

    def get_backend_type(self) -> str:
        return "openai"


# Pros/cons text used by setup flow
CODEX_APP_SERVER_INFO = """\
Codex App Server (ChatGPT subscription)
  Pros: Uses your ChatGPT Plus/Pro subscription — no per-token billing.
        Official integration path via OpenAI's documented app-server flow.
  Cons: Requires `codex` CLI installed (npm install -g @openai/codex).
        Spawns a Node.js subprocess. Auth is browser-based.
  Best for: Interactive use with a ChatGPT subscription."""

OPENAI_API_KEY_INFO = """\
OpenAI API Key
  Pros: Simple setup — just paste your key. No extra dependencies.
        Works in CI/automation. Predictable pay-per-token billing.
  Cons: Costs money per token. No subscription access.
  Best for: Automation, CI, or when you want explicit billing control."""

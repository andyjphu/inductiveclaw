"""Provider registry and cycling logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .base import (
    AuthMode,
    BaseProvider,
    ProviderConfig,
    ProviderID,
    ProviderStatus,
)
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .gemini import GeminiProvider

if TYPE_CHECKING:
    pass

__all__ = [
    "AuthMode",
    "BaseProvider",
    "ProviderConfig",
    "ProviderID",
    "ProviderRegistry",
    "ProviderStatus",
]

CONFIG_DIR = Path.home() / ".config" / "iclaw"
PROVIDERS_FILE = CONFIG_DIR / "providers.json"


class ProviderRegistry:
    """Manages all providers and handles cycling on rate limits."""

    def __init__(self) -> None:
        self.providers: dict[ProviderID, BaseProvider] = {
            ProviderID.ANTHROPIC: AnthropicProvider(),
            ProviderID.OPENAI: OpenAIProvider(),
            ProviderID.GEMINI: GeminiProvider(),
        }
        self._active_id: ProviderID | None = None
        self._cycle_order: list[ProviderID] = []
        self.cycle_enabled: bool = False

    @property
    def active(self) -> BaseProvider | None:
        if self._active_id is None:
            return None
        return self.providers[self._active_id]

    @property
    def active_id(self) -> ProviderID | None:
        return self._active_id

    def set_active(self, provider_id: ProviderID) -> None:
        self._active_id = provider_id

    def enable_cycling(self, order: list[ProviderID] | None = None) -> None:
        """Enable provider cycling on rate limits."""
        self.cycle_enabled = True
        if order:
            self._cycle_order = order
        else:
            # Default: all configured providers
            self._cycle_order = [
                pid for pid, p in self.providers.items()
                if p.status == ProviderStatus.CONNECTED
            ]

    def handle_rate_limit(self) -> BaseProvider | None:
        """Called when current provider is rate limited.

        Records the hit, checks if exhausted, and cycles if enabled.
        Returns the new active provider, or None if all exhausted.
        """
        if self._active_id is None:
            return None

        current = self.providers[self._active_id]
        exhausted = current.rate_limiter.record_hit()

        if exhausted:
            current.status = ProviderStatus.EXHAUSTED

        if not self.cycle_enabled:
            return None if exhausted else current

        # Try next provider in cycle order
        for pid in self._cycle_order:
            provider = self.providers[pid]
            if provider.status == ProviderStatus.CONNECTED:
                self._active_id = pid
                return provider

        return None  # all exhausted

    def configured_providers(self) -> list[BaseProvider]:
        return [p for p in self.providers.values() if p.is_configured()]

    def load_config(self) -> bool:
        """Load saved provider configuration. Returns True if config exists."""
        if not PROVIDERS_FILE.exists():
            return False

        try:
            data = json.loads(PROVIDERS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return False

        for entry in data.get("providers", []):
            try:
                pid = ProviderID(entry["provider_id"])
                config = ProviderConfig(
                    provider_id=pid,
                    auth_mode=AuthMode(entry["auth_mode"]) if entry.get("auth_mode") else None,
                    api_key=entry.get("api_key"),
                    extra=entry.get("extra", {}),
                    enabled=entry.get("enabled", False),
                )
                self.providers[pid].configure(config)
            except (ValueError, KeyError):
                continue

        # Restore active provider
        active = data.get("active")
        if active:
            try:
                self._active_id = ProviderID(active)
            except ValueError:
                pass

        # Restore cycle setting
        self.cycle_enabled = data.get("cycle_enabled", False)
        cycle_order = data.get("cycle_order", [])
        if cycle_order:
            self._cycle_order = [ProviderID(x) for x in cycle_order if x in [p.value for p in ProviderID]]

        return True

    def save_config(self) -> None:
        """Persist provider configuration."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        entries = []
        for pid, provider in self.providers.items():
            if not provider.is_configured():
                continue
            entry: dict = {"provider_id": pid.value, "enabled": True}
            # Extract auth mode and key from provider internals
            if hasattr(provider, "_auth_mode") and provider._auth_mode:
                entry["auth_mode"] = provider._auth_mode.value
            if hasattr(provider, "_api_key") and provider._api_key:
                entry["api_key"] = provider._api_key
            entries.append(entry)

        data = {
            "providers": entries,
            "active": self._active_id.value if self._active_id else None,
            "cycle_enabled": self.cycle_enabled,
            "cycle_order": [p.value for p in self._cycle_order],
        }

        PROVIDERS_FILE.write_text(json.dumps(data, indent=2))

    def auto_detect(self) -> None:
        """Try to auto-detect Anthropic provider."""
        anthropic = self.providers[ProviderID.ANTHROPIC]
        if isinstance(anthropic, AnthropicProvider):
            anthropic.auto_detect()

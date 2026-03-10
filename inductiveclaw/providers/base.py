"""Base provider abstraction."""

from __future__ import annotations

import enum
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderID(enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"


class AuthMode(enum.Enum):
    # Anthropic
    OAUTH = "oauth"
    API_KEY = "api_key"
    # OpenAI
    CODEX_APP_SERVER = "codex_app_server"
    OPENAI_API_KEY = "openai_api_key"
    # Gemini
    GOOGLE_OAUTH = "google_oauth"
    GEMINI_API_KEY = "gemini_api_key"


class ProviderStatus(enum.Enum):
    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    RATE_LIMITED = "rate_limited"
    EXHAUSTED = "exhausted"  # rate limited 2x in 5 min


@dataclass
class RateLimitTracker:
    """Track rate limit hits. 2 hits within 5 minutes = exhausted for the day."""

    hits: list[float] = field(default_factory=list)  # timestamps
    exhausted: bool = False

    def record_hit(self) -> bool:
        """Record a rate limit hit. Returns True if now exhausted."""
        now = time.time()
        self.hits.append(now)
        # Check for 2 hits within 5 minutes
        recent = [t for t in self.hits if now - t < 300]
        self.hits = recent  # prune old hits
        if len(recent) >= 2:
            self.exhausted = True
        return self.exhausted

    def reset(self) -> None:
        self.hits.clear()
        self.exhausted = False


@dataclass
class ProviderConfig:
    """Stored configuration for a single provider."""

    provider_id: ProviderID
    auth_mode: AuthMode | None = None
    api_key: str | None = None
    extra: dict = field(default_factory=dict)  # provider-specific config
    enabled: bool = False


class BaseProvider(ABC):
    """Abstract base for all providers."""

    id: ProviderID
    display_name: str
    rate_limiter: RateLimitTracker

    def __init__(self) -> None:
        self.rate_limiter = RateLimitTracker()
        self._status = ProviderStatus.NOT_CONFIGURED

    @property
    def status(self) -> ProviderStatus:
        if self.rate_limiter.exhausted:
            return ProviderStatus.EXHAUSTED
        return self._status

    @status.setter
    def status(self, value: ProviderStatus) -> None:
        self._status = value

    @abstractmethod
    def get_sdk_env(self) -> dict[str, str]:
        """Return env dict for Agent SDK calls."""

    @abstractmethod
    def get_model(self) -> str | None:
        """Return the model string for this provider, or None for SDK default."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this provider has valid configuration."""

    @abstractmethod
    def configure(self, config: ProviderConfig) -> None:
        """Apply stored configuration."""

    @abstractmethod
    def status_line(self) -> str:
        """One-line status for display."""

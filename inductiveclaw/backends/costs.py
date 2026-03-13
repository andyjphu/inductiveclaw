"""Token-based cost estimation for non-Claude backends.

Claude's SDK provides cost directly. OpenAI and Gemini report token
counts, so we estimate cost from published pricing. Prices are per
million tokens and may become stale — this is a best-effort estimate.

Update prices here when providers change their pricing.
"""

from __future__ import annotations

from typing import Any, Optional


# Prices per 1M tokens (input, output) in USD
# Last updated: 2025-05
_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "o3": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # Gemini (pay-as-you-go tier)
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}


def estimate_cost(
    model: str,
    usage: Optional[dict[str, Any]],
) -> Optional[float]:
    """Estimate USD cost from token usage.

    Returns None if model pricing is unknown or usage is missing.
    """
    if not usage:
        return None

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    if input_tokens == 0 and output_tokens == 0:
        return None

    # Try exact match first, then prefix match
    pricing = _PRICING.get(model)
    if pricing is None:
        for key in _PRICING:
            if model.startswith(key):
                pricing = _PRICING[key]
                break

    if pricing is None:
        return None

    input_price, output_price = pricing
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return round(cost, 6)

"""Tests for backends/costs.py — token-based cost estimation."""

from __future__ import annotations

import pytest

from inductiveclaw.backends.costs import estimate_cost


class TestEstimateCost:
    def test_openai_o3(self):
        cost = estimate_cost("o3", {"input_tokens": 1000, "output_tokens": 500})
        assert cost is not None
        assert cost > 0
        # o3: $2/M input, $8/M output -> (1000*2 + 500*8) / 1M = 0.006
        assert abs(cost - 0.006) < 0.0001

    def test_openai_gpt4o_mini(self):
        cost = estimate_cost("gpt-4o-mini", {"input_tokens": 10000, "output_tokens": 5000})
        assert cost is not None
        # $0.15/M input, $0.60/M output -> (10000*0.15 + 5000*0.60) / 1M = 0.0045
        assert abs(cost - 0.0045) < 0.0001

    def test_gemini_25_pro(self):
        cost = estimate_cost("gemini-2.5-pro", {"input_tokens": 1000, "output_tokens": 500})
        assert cost is not None
        # $1.25/M input, $10/M output -> (1000*1.25 + 500*10) / 1M = 0.00625
        assert abs(cost - 0.00625) < 0.0001

    def test_gemini_25_flash(self):
        cost = estimate_cost("gemini-2.5-flash", {"input_tokens": 100000, "output_tokens": 50000})
        assert cost is not None
        assert cost > 0

    def test_unknown_model_returns_none(self):
        cost = estimate_cost("totally-unknown-model-xyz", {"input_tokens": 1000, "output_tokens": 500})
        assert cost is None

    def test_none_usage_returns_none(self):
        cost = estimate_cost("o3", None)
        assert cost is None

    def test_empty_usage_returns_none(self):
        cost = estimate_cost("o3", {})
        assert cost is None

    def test_zero_tokens_returns_none(self):
        cost = estimate_cost("o3", {"input_tokens": 0, "output_tokens": 0})
        assert cost is None

    def test_only_input_tokens(self):
        cost = estimate_cost("o3", {"input_tokens": 1000000, "output_tokens": 0})
        assert cost is not None
        # $2/M * 1M = $2
        assert abs(cost - 2.0) < 0.01

    def test_only_output_tokens(self):
        cost = estimate_cost("o3", {"input_tokens": 0, "output_tokens": 1000000})
        assert cost is not None
        # $8/M * 1M = $8
        assert abs(cost - 8.0) < 0.01

    def test_prefix_match(self):
        # Model names that start with a known prefix should match
        cost = estimate_cost("gpt-4o-2024-08-06", {"input_tokens": 1000, "output_tokens": 500})
        # Should match "gpt-4o" pricing
        assert cost is not None

    def test_large_token_counts(self):
        cost = estimate_cost("o3", {"input_tokens": 100000000, "output_tokens": 50000000})
        assert cost is not None
        assert cost > 0

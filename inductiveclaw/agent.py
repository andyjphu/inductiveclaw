"""Autonomous mode entry point — thin wrapper around agent_worker.run_branch."""

from __future__ import annotations

from pathlib import Path

from . import display
from .agent_worker import run_branch
from .budget import BudgetTracker
from .config import ClawConfig
from .providers import ProviderRegistry


async def run(config: ClawConfig, registry: ProviderRegistry) -> None:
    """Run the autonomous loop in single-branch mode."""
    budget = BudgetTracker(budget_usd=config.budget_usd)

    display.show_banner(config, registry)
    Path(config.project_dir).mkdir(parents=True, exist_ok=True)

    result = await run_branch(config, registry, budget)

    display.show_summary(result.tracker)

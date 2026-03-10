"""Prompt templates for InductiveClaw agent iterations."""

from .system import SYSTEM_PROMPT
from .iteration import build_iteration_prompt

__all__ = ["SYSTEM_PROMPT", "build_iteration_prompt"]

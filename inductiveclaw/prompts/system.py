"""System prompt — loaded from system.md."""

from importlib.resources import files

SYSTEM_PROMPT = files(__package__).joinpath("system.md").read_text()

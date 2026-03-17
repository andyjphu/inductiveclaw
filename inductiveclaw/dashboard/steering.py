"""Steering channel — async-safe command queue between dashboard and agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio

if TYPE_CHECKING:
    from ..config import ClawConfig


@dataclass
class SteeringCommand:
    """A steering command from the dashboard."""
    kind: str  # pause, resume, set_threshold, inject_hint, stop_branch, stop_all
    value: Any = None


class SteeringChannel:
    """Async-safe command queue using anyio memory streams.

    The dashboard writes commands via send_nowait(), the agent loop reads via
    receive_nowait() at the top of each iteration.

    Pause/resume uses a dedicated Event — when paused, the iteration loop
    awaits ``wait_if_paused()`` which blocks until resume is received.
    """

    def __init__(self, buffer_size: int = 64) -> None:
        self._send, self._recv = anyio.create_memory_object_stream[SteeringCommand](
            max_buffer_size=buffer_size,
        )
        self._paused = False
        self._resume_event: anyio.Event | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def send_nowait(self, cmd: SteeringCommand) -> None:
        """Non-blocking send — called from the WS handler."""
        # Handle pause/resume directly to avoid race conditions
        if cmd.kind == "pause":
            self._paused = True
            self._resume_event = anyio.Event()
        elif cmd.kind == "resume":
            self._paused = False
            if self._resume_event is not None:
                self._resume_event.set()
                self._resume_event = None
        else:
            try:
                self._send.send_nowait(cmd)
            except anyio.WouldBlock:
                pass  # drop if buffer full

    def receive_nowait(self) -> SteeringCommand | None:
        """Non-blocking receive — called from the iteration loop."""
        try:
            return self._recv.receive_nowait()
        except (anyio.WouldBlock, anyio.ClosedResourceError, anyio.EndOfStream):
            return None

    async def wait_if_paused(self) -> None:
        """Block until resumed. No-op if not paused."""
        if self._paused and self._resume_event is not None:
            await self._resume_event.wait()

    def close(self) -> None:
        self._send.close()
        self._recv.close()


async def process_pending_commands(
    channel: SteeringChannel,
    config: ClawConfig,
) -> str | None:
    """Drain all pending steering commands and apply them.

    Returns ``"stop"`` if the run should terminate, otherwise ``None``.
    Called at the top of each iteration in ``run_branch``.
    """
    while True:
        cmd = channel.receive_nowait()
        if cmd is None:
            break

        if cmd.kind == "set_threshold":
            if isinstance(cmd.value, int) and 1 <= cmd.value <= 10:
                config.quality_threshold = cmd.value

        elif cmd.kind == "inject_hint":
            if isinstance(cmd.value, str) and cmd.value.strip():
                config._steering_hint = cmd.value.strip()  # type: ignore[attr-defined]

        elif cmd.kind in ("stop_all", "stop_branch"):
            return "stop"

    # Block if paused (pause/resume handled directly in channel)
    await channel.wait_if_paused()

    return None

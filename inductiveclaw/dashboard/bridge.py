"""Event bridge — connects BranchEvent callbacks to the dashboard."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..agent_worker import BranchEvent
    from .state import DashboardState


class EventBridge:
    """Receives BranchEvents, updates DashboardState, and broadcasts to WS clients.

    Also composes with the existing terminal display callback so both
    the terminal and the dashboard receive events simultaneously.
    """

    def __init__(
        self,
        state: DashboardState,
        broadcast: Callable[[dict[str, Any]], None],
        terminal_callback: Callable[[BranchEvent], None] | None = None,
    ) -> None:
        self._state = state
        self._broadcast = broadcast
        self._terminal_cb = terminal_callback

    def handle_event(self, event: BranchEvent) -> None:
        """Process a BranchEvent — update state, broadcast, and forward to terminal."""
        # Update aggregate state
        self._state.update(event)

        # Broadcast to all WebSocket clients
        msg = _event_to_message(event)
        self._broadcast(msg)

        # Forward to terminal display (if present)
        if self._terminal_cb is not None:
            self._terminal_cb(event)

    def make_on_event(self) -> Callable[[BranchEvent], None]:
        """Return a callback suitable for run_branch(on_event=...)."""
        return self.handle_event

    def emit_budget(self, spent: float, budget: float | None, fraction: float | None, status: str) -> None:
        """Emit a budget update event."""
        from ..agent_worker import BranchEvent
        data = {"spent": spent, "budget": budget, "fraction": fraction, "status": status}
        event = BranchEvent(branch_id="__system__", event_type="budget", data=data)
        self._state.update(event)
        self._broadcast({"type": "budget", "data": data})

    def emit_browser_eval(self, report_data: dict[str, Any]) -> None:
        """Emit a browser evaluation report event."""
        from ..agent_worker import BranchEvent
        event = BranchEvent(branch_id="__system__", event_type="browser_eval", data=report_data)
        self._state.update(event)
        self._broadcast({"type": "browser_eval", "data": report_data})

    def emit_round_complete(self, round_num: int, winner_id: str, results: list[dict[str, Any]]) -> None:
        """Emit a tournament round completion event."""
        data = {"round_num": round_num, "winner": winner_id, "results": results}
        self._state.rounds.append(data)
        self._broadcast({"type": "round_complete", "data": data})


def _event_to_message(event: BranchEvent) -> dict[str, Any]:
    """Convert a BranchEvent to a JSON-serializable WS message."""
    return {
        "type": "event",
        "branch_id": event.branch_id,
        "event": event.event_type,
        "data": event.data,
    }

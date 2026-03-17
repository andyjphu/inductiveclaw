"""WebSocket server — serves dashboard HTML and streams real-time events."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .bridge import EventBridge
    from .state import DashboardState
    from .steering import SteeringChannel, SteeringCommand

logger = logging.getLogger(__name__)


class DashboardServer:
    """Single-port server: HTTP for the HTML page, WebSocket for events + steering.

    Usage::

        server = DashboardServer(state, bridge, steering, port=8420)
        await server.start()
        # ... run agent ...
        await server.stop()
    """

    def __init__(
        self,
        state: DashboardState,
        bridge: EventBridge,
        steering: SteeringChannel,
        port: int = 8420,
    ) -> None:
        self.state = state
        self.bridge = bridge
        self.steering = steering
        self.port = port
        self._clients: set[Any] = set()
        self._server: Any = None
        self._broadcast_queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the WebSocket server in a background task."""
        try:
            import websockets  # type: ignore[import-untyped]
            import websockets.asyncio.server  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "Dashboard requires the websockets package.\n"
                "Install it with: pip install iclaw[dashboard]"
            )

        # Wire the bridge broadcast to our queue
        self.bridge._broadcast = self._enqueue_broadcast

        from .frontend import DASHBOARD_HTML

        async def handler(ws: Any) -> None:
            self._clients.add(ws)
            try:
                # Send full state snapshot on connect
                snapshot = json.dumps({"type": "snapshot", "data": self.state.to_dict()})
                await ws.send(snapshot)

                # Receive steering commands
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        self._handle_steering(msg, ws)
                    except (json.JSONDecodeError, KeyError):
                        pass
            finally:
                self._clients.discard(ws)

        async def process_request(path: str, headers: Any) -> Any:
            """Serve HTML on regular HTTP GET, upgrade to WS otherwise."""
            # websockets 12+ uses the handler; this is for older versions
            return None

        # Use websockets.asyncio.server for modern API
        self._server = await websockets.asyncio.server.serve(
            handler,
            "0.0.0.0",
            self.port,
            process_request=self._http_handler(DASHBOARD_HTML),
        )

        # Start broadcast worker
        self._task = asyncio.create_task(self._broadcast_worker())
        logger.info("Dashboard server started on port %d", self.port)

    async def stop(self) -> None:
        """Gracefully shut down the server."""
        if self._task:
            self._task.cancel()
            self._task = None
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def _enqueue_broadcast(self, msg: dict[str, Any]) -> None:
        """Enqueue a message for broadcast (thread/task safe)."""
        try:
            raw = json.dumps(msg, default=str)
            self._broadcast_queue.put_nowait(raw)
        except Exception:
            pass

    async def _broadcast_worker(self) -> None:
        """Background task that drains the queue and sends to all clients."""
        while True:
            try:
                raw = await self._broadcast_queue.get()
                if self._clients:
                    await asyncio.gather(
                        *(self._safe_send(ws, raw) for ws in set(self._clients)),
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @staticmethod
    async def _safe_send(ws: Any, data: str) -> None:
        try:
            await ws.send(data)
        except Exception:
            pass

    def _handle_steering(self, msg: dict[str, Any], ws: Any) -> None:
        """Parse a steering command from the dashboard and enqueue it."""
        from .steering import SteeringCommand

        kind = msg.get("type", "")
        value = msg.get("value") or msg.get("text") or msg.get("branch_id")

        if kind in ("pause", "resume", "stop_all"):
            self.steering.send_nowait(SteeringCommand(kind=kind))
            if kind == "pause":
                self.state.paused = True
            elif kind == "resume":
                self.state.paused = False
        elif kind == "set_threshold":
            self.steering.send_nowait(SteeringCommand(kind=kind, value=value))
            if isinstance(value, int) and 1 <= value <= 10:
                self.state.threshold = value
        elif kind == "inject_hint":
            self.steering.send_nowait(SteeringCommand(kind=kind, value=value))
        elif kind == "stop_branch":
            self.steering.send_nowait(SteeringCommand(kind=kind, value=value))
        else:
            return

        # Send ack
        ack = json.dumps({"type": "ack", "command": kind, "status": "accepted"})
        asyncio.create_task(self._safe_send(ws, ack))

    @staticmethod
    def _http_handler(html: str) -> Any:
        """Return a process_request handler that serves HTML for non-WS requests."""
        from http import HTTPStatus
        try:
            from websockets.http11 import Response  # type: ignore[import-untyped]
        except ImportError:
            Response = None

        def handler(path: str, request: Any) -> Any:
            """Serve the dashboard HTML on GET /."""
            # For websockets 12+, return a Response to short-circuit the WS upgrade
            if Response is not None:
                return Response(
                    HTTPStatus.OK,
                    "OK",
                    {
                        "Content-Type": "text/html; charset=utf-8",
                        "Cache-Control": "no-cache",
                    },
                    html.encode("utf-8"),
                )
            return None

        return handler

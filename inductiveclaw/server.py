"""Dev server lifecycle management.

Handles starting, stopping, and auto-detecting development servers
so browser evaluation tools can test the running application.
"""

from __future__ import annotations

import asyncio
import json
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DevServerHandle:
    """Handle to a running dev server process."""

    process: subprocess.Popen[str]
    port: int
    cmd: str

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    async def stop(self) -> None:
        """Graceful shutdown: SIGTERM, wait 5s, SIGKILL if needed."""
        await stop_dev_server(self)


async def is_port_ready(
    port: int, host: str = "localhost", timeout: float = 1.0
) -> bool:
    """Check if a server is responding on the given port via TCP connect."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def detect_dev_command(project_dir: str) -> tuple[str, int] | None:
    """Auto-detect dev server command from project files.

    Checks in order:
    1. package.json scripts.dev / scripts.start
    2. index.html (python -m http.server)
    3. manage.py (Django)
    4. app.py / main.py (Flask/FastAPI)

    Returns (command, expected_port) or None.
    """
    p = Path(project_dir)

    # Node.js projects
    pkg = p / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            scripts = data.get("scripts", {})
            for script_name in ("dev", "start"):
                if script_name in scripts:
                    port = _extract_port(scripts[script_name]) or 3000
                    return (f"npm run {script_name}", port)
        except (json.JSONDecodeError, KeyError):
            pass

    # Static HTML
    if (p / "index.html").exists():
        return ("python -m http.server 3000", 3000)

    # Django
    if (p / "manage.py").exists():
        return ("python manage.py runserver 3000", 3000)

    # Flask / FastAPI
    for entry in ("app.py", "main.py"):
        if (p / entry).exists():
            return (f"python {entry}", 8000)

    return None


def _extract_port(script_cmd: str) -> int | None:
    """Try to extract a port number from a dev script command string."""
    import re

    # Match common patterns: --port 3001, -p 8080, :3000, PORT=3001
    for pattern in (
        r"--port\s+(\d+)",
        r"-p\s+(\d+)",
        r":(\d{4,5})\b",
        r"PORT[=\s]+(\d+)",
    ):
        m = re.search(pattern, script_cmd)
        if m:
            return int(m.group(1))
    return None


async def start_dev_server(
    cmd: str,
    port: int,
    cwd: str,
    *,
    timeout_seconds: int = 30,
) -> DevServerHandle:
    """Start a dev server process and wait for the port to become ready.

    Raises TimeoutError if the server doesn't start within timeout_seconds.
    """
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        if sys.platform != "win32"
        else None,
    )

    handle = DevServerHandle(process=process, port=port, cmd=cmd)

    # Poll for port readiness with exponential backoff
    delay = 0.3
    elapsed = 0.0
    while elapsed < timeout_seconds:
        if process.poll() is not None:
            # Process exited — read stderr for diagnostics
            stderr = process.stderr.read() if process.stderr else ""
            msg = f"Dev server exited with code {process.returncode}"
            if stderr:
                msg += f": {stderr[:200]}"
            raise RuntimeError(msg)

        if await is_port_ready(port):
            return handle

        await asyncio.sleep(delay)
        elapsed += delay
        delay = min(delay * 1.5, 2.0)

    # Timed out — kill and raise
    await stop_dev_server(handle)
    raise TimeoutError(
        f"Dev server '{cmd}' did not become ready on port {port} "
        f"within {timeout_seconds}s"
    )


async def stop_dev_server(handle: DevServerHandle) -> None:
    """Gracefully stop a dev server: SIGTERM, wait 5s, SIGKILL if needed."""
    proc = handle.process
    if proc.poll() is not None:
        return  # Already dead

    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except OSError:
        pass  # Process already gone


async def ensure_server(
    project_dir: str,
    port: int,
    cmd: str | None = None,
) -> DevServerHandle | None:
    """Start a dev server if the port is not already responding.

    Returns a DevServerHandle if a server was started (caller must stop it),
    or None if the port was already occupied (server managed externally).
    """
    if await is_port_ready(port):
        return None  # Already running

    if cmd is None:
        detected = detect_dev_command(project_dir)
        if detected is None:
            return None  # Can't auto-detect, skip
        cmd, port = detected

    return await start_dev_server(cmd, port, project_dir)

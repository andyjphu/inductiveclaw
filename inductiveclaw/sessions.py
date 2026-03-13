"""Session persistence — save and resume interactive sessions."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path.home() / ".config" / "iclaw" / "sessions"
INDEX_FILE = SESSIONS_DIR / "index.json"
DEFAULT_RETENTION_DAYS = 30
MAX_TOOL_RESULT_LEN = 10_000


@dataclass
class SessionRecord:
    """Metadata and state for a persisted session."""

    session_id: str
    backend_type: str  # "claude", "openai", "gemini"
    provider_id: str  # "anthropic", "openai", "gemini"
    model: str
    cwd: str
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    total_cost_usd: float = 0.0
    total_turns: int = 0
    title: str = ""
    messages: list[dict[str, Any]] | None = None  # None for Claude
    version: int = 1


class SessionStore:
    """Manages session persistence to ~/.config/iclaw/sessions/."""

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._dir = sessions_dir or SESSIONS_DIR
        self._index_file = self._dir / "index.json"

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        # Restrict permissions on sessions dir (conversations may contain code)
        try:
            os.chmod(self._dir, 0o700)
        except OSError:
            pass

    def _session_path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("..", "_")
        return self._dir / f"{safe_id}.json"

    # --- CRUD ---

    def save(self, record: SessionRecord) -> None:
        """Save a session record to disk and update the index."""
        self._ensure_dir()
        record.updated_at = datetime.now().isoformat()

        # Truncate large tool results to keep files manageable
        data = asdict(record)
        if data.get("messages"):
            data["messages"] = _truncate_messages(data["messages"])

        self._session_path(record.session_id).write_text(
            json.dumps(data, indent=2, default=str)
        )
        self._update_index(record)

    def load(self, session_id: str) -> SessionRecord | None:
        """Load a session record from disk."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            # Filter to known fields only
            known = {f for f in SessionRecord.__dataclass_fields__}
            return SessionRecord(**{k: v for k, v in data.items() if k in known})
        except (json.JSONDecodeError, TypeError, OSError):
            return None

    def delete(self, session_id: str) -> bool:
        """Delete a session record from disk and the index."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            self._remove_from_index(session_id)
            return True
        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return session summaries sorted by most recently updated."""
        if not self._index_file.exists():
            self._rebuild_index()
        try:
            data = json.loads(self._index_file.read_text())
            sessions = data.get("sessions", [])
            sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
            return sessions
        except (json.JSONDecodeError, OSError):
            return []

    # --- Index management ---

    def _update_index(self, record: SessionRecord) -> None:
        """Upsert a session entry in the index file."""
        index = self._load_index()
        entry = _index_entry(record)

        # Upsert
        for i, existing in enumerate(index):
            if existing.get("session_id") == record.session_id:
                index[i] = entry
                break
        else:
            index.append(entry)

        self._write_index(index)

    def _remove_from_index(self, session_id: str) -> None:
        """Remove a session entry from the index file."""
        index = self._load_index()
        index = [s for s in index if s.get("session_id") != session_id]
        self._write_index(index)

    def _rebuild_index(self) -> None:
        """Scan session files to rebuild the index."""
        self._ensure_dir()
        index: list[dict[str, Any]] = []
        for path in self._dir.glob("*.json"):
            if path.name == "index.json":
                continue
            try:
                data = json.loads(path.read_text())
                index.append({
                    "session_id": data.get("session_id", path.stem),
                    "backend_type": data.get("backend_type", ""),
                    "provider_id": data.get("provider_id", ""),
                    "model": data.get("model", ""),
                    "title": data.get("title", ""),
                    "cwd": data.get("cwd", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "total_cost_usd": data.get("total_cost_usd", 0.0),
                    "total_turns": data.get("total_turns", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
        self._write_index(index)

    def _load_index(self) -> list[dict[str, Any]]:
        if not self._index_file.exists():
            return []
        try:
            data = json.loads(self._index_file.read_text())
            return data.get("sessions", [])
        except (json.JSONDecodeError, OSError):
            return []

    def _write_index(self, index: list[dict[str, Any]]) -> None:
        self._ensure_dir()
        self._index_file.write_text(
            json.dumps({"sessions": index}, indent=2, default=str)
        )

    # --- Cleanup ---

    def cleanup(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        """Remove sessions older than retention_days. Returns count removed."""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        removed = 0

        for path in list(self._dir.glob("*.json")):
            if path.name == "index.json":
                continue
            try:
                data = json.loads(path.read_text())
                updated = data.get("updated_at", "")
                if updated and updated < cutoff:
                    path.unlink()
                    removed += 1
            except (json.JSONDecodeError, OSError):
                continue

        if removed:
            self._rebuild_index()
        return removed

    # --- Helpers ---

    @staticmethod
    def extract_title(user_message: str) -> str:
        """Extract session title from first user message."""
        title = user_message.strip().split("\n")[0][:80]
        return title or "Untitled session"


def _index_entry(record: SessionRecord) -> dict[str, Any]:
    """Create an index entry from a session record (no messages)."""
    return {
        "session_id": record.session_id,
        "backend_type": record.backend_type,
        "provider_id": record.provider_id,
        "model": record.model,
        "title": record.title,
        "cwd": record.cwd,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "total_cost_usd": record.total_cost_usd,
        "total_turns": record.total_turns,
    }


def _truncate_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Truncate large tool result content to keep session files manageable."""
    truncated = []
    for msg in messages:
        msg = dict(msg)  # shallow copy
        content = msg.get("content")
        if isinstance(content, str) and len(content) > MAX_TOOL_RESULT_LEN:
            msg["content"] = content[:MAX_TOOL_RESULT_LEN] + "\n... (truncated)"
        truncated.append(msg)
    return truncated


def export_transcript(record: SessionRecord, output_dir: str) -> str:
    """Write a human-readable markdown transcript of a session."""
    filename = f"session-{record.session_id[:12]}.md"
    path = Path(output_dir) / filename

    lines = [
        f"# Session: {record.title}",
        "",
        f"- **Provider**: {record.provider_id} ({record.model})",
        f"- **Started**: {record.created_at}",
        f"- **Cost**: ${record.total_cost_usd:.4f}",
        f"- **Turns**: {record.total_turns}",
        "",
        "---",
        "",
    ]

    if record.messages:
        for msg in record.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "system":
                continue
            if role == "user":
                lines.append(f"## User\n\n{content}\n")
            elif role == "assistant":
                lines.append(f"## Assistant\n\n{content}\n")
            elif role == "tool":
                preview = str(content)[:500] if content else ""
                lines.append(f"### Tool Result\n\n```\n{preview}\n```\n")
    else:
        lines.append(
            "*(Claude session — transcript not available, "
            "conversation managed by SDK)*\n"
        )

    path.write_text("\n".join(lines))
    return str(path)

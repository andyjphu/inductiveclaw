"""Tests for session persistence — SessionStore CRUD, index, cleanup, and backend roundtrips."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from inductiveclaw.sessions import (
    SessionRecord,
    SessionStore,
    export_transcript,
    _truncate_messages,
)


@pytest.fixture
def tmp_sessions_dir(tmp_path: Path) -> Path:
    """Create a temporary sessions directory."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def store(tmp_sessions_dir: Path) -> SessionStore:
    """Create a SessionStore backed by a temp directory."""
    return SessionStore(sessions_dir=tmp_sessions_dir)


def _make_record(
    session_id: str = "test-123",
    backend_type: str = "openai",
    provider_id: str = "openai",
    model: str = "o3",
    title: str = "Test session",
    messages: list | None = None,
    **kwargs,
) -> SessionRecord:
    now = datetime.now().isoformat()
    return SessionRecord(
        session_id=session_id,
        backend_type=backend_type,
        provider_id=provider_id,
        model=model,
        cwd="/tmp/test",
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
        total_cost_usd=kwargs.get("total_cost_usd", 0.05),
        total_turns=kwargs.get("total_turns", 3),
        title=title,
        messages=messages,
    )


# --- SessionStore CRUD ---


class TestSessionStoreSave:
    def test_save_creates_file(self, store: SessionStore, tmp_sessions_dir: Path):
        record = _make_record()
        store.save(record)
        assert (tmp_sessions_dir / "test-123.json").exists()

    def test_save_updates_index(self, store: SessionStore):
        record = _make_record()
        store.save(record)
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "test-123"

    def test_save_sanitizes_session_id(self, store: SessionStore, tmp_sessions_dir: Path):
        record = _make_record(session_id="a/b/../c")
        store.save(record)
        assert (tmp_sessions_dir / "a_b___c.json").exists()

    def test_save_truncates_large_messages(self, store: SessionStore, tmp_sessions_dir: Path):
        big_content = "x" * 20000
        record = _make_record(messages=[{"role": "tool", "content": big_content}])
        store.save(record)
        data = json.loads((tmp_sessions_dir / "test-123.json").read_text())
        saved_content = data["messages"][0]["content"]
        assert len(saved_content) < 20000
        assert "truncated" in saved_content


class TestSessionStoreLoad:
    def test_load_returns_record(self, store: SessionStore):
        record = _make_record(title="My session")
        store.save(record)
        loaded = store.load("test-123")
        assert loaded is not None
        assert loaded.session_id == "test-123"
        assert loaded.title == "My session"
        assert loaded.total_cost_usd == 0.05

    def test_load_nonexistent_returns_none(self, store: SessionStore):
        assert store.load("nonexistent") is None

    def test_load_corrupt_file_returns_none(self, store: SessionStore, tmp_sessions_dir: Path):
        (tmp_sessions_dir / "corrupt.json").write_text("NOT JSON{{{")
        assert store.load("corrupt") is None

    def test_load_with_messages(self, store: SessionStore):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        record = _make_record(messages=msgs)
        store.save(record)
        loaded = store.load("test-123")
        assert loaded is not None
        assert loaded.messages is not None
        assert len(loaded.messages) == 2
        assert loaded.messages[0]["role"] == "user"

    def test_load_claude_session_null_messages(self, store: SessionStore):
        record = _make_record(backend_type="claude", messages=None)
        store.save(record)
        loaded = store.load("test-123")
        assert loaded is not None
        assert loaded.messages is None

    def test_load_ignores_unknown_fields(self, store: SessionStore, tmp_sessions_dir: Path):
        data = {
            "session_id": "test-extra",
            "backend_type": "openai",
            "provider_id": "openai",
            "model": "o3",
            "cwd": "/tmp",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
            "unknown_field": "should be ignored",
        }
        (tmp_sessions_dir / "test-extra.json").write_text(json.dumps(data))
        loaded = store.load("test-extra")
        assert loaded is not None
        assert loaded.session_id == "test-extra"


class TestSessionStoreDelete:
    def test_delete_removes_file(self, store: SessionStore, tmp_sessions_dir: Path):
        record = _make_record()
        store.save(record)
        assert store.delete("test-123")
        assert not (tmp_sessions_dir / "test-123.json").exists()

    def test_delete_updates_index(self, store: SessionStore):
        store.save(_make_record(session_id="a"))
        store.save(_make_record(session_id="b"))
        store.delete("a")
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "b"

    def test_delete_nonexistent_returns_false(self, store: SessionStore):
        assert not store.delete("nonexistent")


class TestSessionStoreList:
    def test_list_empty(self, store: SessionStore):
        assert store.list_sessions() == []

    def test_list_sorted_by_updated_at(self, store: SessionStore):
        store.save(_make_record(session_id="old", updated_at="2025-01-01T00:00:00"))
        store.save(_make_record(session_id="new", updated_at="2026-03-13T00:00:00"))
        sessions = store.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "new"
        assert sessions[1]["session_id"] == "old"

    def test_list_multiple_sessions(self, store: SessionStore):
        for i in range(5):
            store.save(_make_record(session_id=f"s{i}", title=f"Session {i}"))
        sessions = store.list_sessions()
        assert len(sessions) == 5


# --- Index management ---


class TestIndexRebuild:
    def test_rebuild_from_orphaned_files(self, store: SessionStore, tmp_sessions_dir: Path):
        # Write session files without index
        for sid in ["a", "b", "c"]:
            data = {
                "session_id": sid,
                "backend_type": "openai",
                "provider_id": "openai",
                "model": "o3",
                "title": f"Session {sid}",
                "cwd": "/tmp",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            }
            (tmp_sessions_dir / f"{sid}.json").write_text(json.dumps(data))

        sessions = store.list_sessions()
        assert len(sessions) == 3

    def test_rebuild_skips_corrupt_files(self, store: SessionStore, tmp_sessions_dir: Path):
        (tmp_sessions_dir / "good.json").write_text(json.dumps({
            "session_id": "good",
            "backend_type": "openai",
            "provider_id": "openai",
            "model": "o3",
            "cwd": "/tmp",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }))
        (tmp_sessions_dir / "bad.json").write_text("NOT JSON{{{")

        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "good"

    def test_upsert_existing_session(self, store: SessionStore):
        record = _make_record(total_turns=1)
        store.save(record)
        record.total_turns = 5
        store.save(record)
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["total_turns"] == 5


# --- Cleanup ---


class TestCleanup:
    def test_cleanup_removes_old_sessions(self, store: SessionStore, tmp_sessions_dir: Path):
        # Write old session file directly (save() overwrites updated_at)
        old_time = (datetime.now() - timedelta(days=40)).isoformat()
        old_data = {
            "session_id": "old", "backend_type": "openai", "provider_id": "openai",
            "model": "o3", "cwd": "/tmp", "created_at": old_time,
            "updated_at": old_time, "total_cost_usd": 0.0, "total_turns": 0,
            "title": "Old session", "messages": None, "version": 1,
        }
        (tmp_sessions_dir / "old.json").write_text(json.dumps(old_data))
        store.save(_make_record(session_id="new"))

        removed = store.cleanup(retention_days=30)
        assert removed == 1
        assert store.load("old") is None
        assert store.load("new") is not None

    def test_cleanup_respects_retention(self, store: SessionStore):
        recent_time = (datetime.now() - timedelta(days=5)).isoformat()
        store.save(_make_record(session_id="recent", updated_at=recent_time))

        removed = store.cleanup(retention_days=30)
        assert removed == 0
        assert store.load("recent") is not None

    def test_cleanup_returns_zero_when_empty(self, store: SessionStore):
        assert store.cleanup() == 0


# --- Title extraction ---


class TestExtractTitle:
    def test_single_line(self):
        assert SessionStore.extract_title("Build a REST API") == "Build a REST API"

    def test_multiline_takes_first(self):
        assert SessionStore.extract_title("Line one\nLine two\nLine three") == "Line one"

    def test_truncates_long_title(self):
        long = "x" * 200
        title = SessionStore.extract_title(long)
        assert len(title) == 80

    def test_empty_returns_untitled(self):
        assert SessionStore.extract_title("") == "Untitled session"
        assert SessionStore.extract_title("   ") == "Untitled session"


# --- Message truncation ---


class TestTruncateMessages:
    def test_short_messages_unchanged(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = _truncate_messages(msgs)
        assert result[0]["content"] == "hello"

    def test_long_content_truncated(self):
        msgs = [{"role": "tool", "content": "x" * 20000}]
        result = _truncate_messages(msgs)
        assert len(result[0]["content"]) < 20000
        assert "truncated" in result[0]["content"]

    def test_non_string_content_unchanged(self):
        msgs = [{"role": "assistant", "content": None}]
        result = _truncate_messages(msgs)
        assert result[0]["content"] is None

    def test_does_not_mutate_original(self):
        original = [{"role": "tool", "content": "x" * 20000}]
        _truncate_messages(original)
        assert len(original[0]["content"]) == 20000


# --- Export transcript ---


class TestExportTranscript:
    def test_export_creates_file(self, tmp_path: Path):
        record = _make_record(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )
        filepath = export_transcript(record, str(tmp_path))
        assert Path(filepath).exists()
        content = Path(filepath).read_text()
        assert "# Session: Test session" in content
        assert "## User" in content
        assert "## Assistant" in content

    def test_export_claude_session_no_messages(self, tmp_path: Path):
        record = _make_record(backend_type="claude", messages=None)
        filepath = export_transcript(record, str(tmp_path))
        content = Path(filepath).read_text()
        assert "transcript not available" in content

    def test_export_skips_system_messages(self, tmp_path: Path):
        record = _make_record(messages=[
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ])
        filepath = export_transcript(record, str(tmp_path))
        content = Path(filepath).read_text()
        assert "You are helpful" not in content
        assert "## User" in content


# --- OpenAI backend get_messages / restore_messages ---


class TestOpenAIMessageRoundtrip:
    def test_get_messages_returns_copy(self):
        from inductiveclaw.backends.openai import OpenAIInteractiveBackend

        backend = OpenAIInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="o3",
        )
        backend._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        msgs = backend.get_messages()
        assert msgs is not None
        assert len(msgs) == 3
        # Verify it's a copy
        msgs.append({"role": "user", "content": "extra"})
        assert len(backend._messages) == 3

    def test_restore_messages(self):
        from inductiveclaw.backends.openai import OpenAIInteractiveBackend

        backend = OpenAIInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="o3",
        )
        stored = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        backend.restore_messages(stored)
        assert len(backend._messages) == 3
        assert backend._messages[1]["content"] == "hello"

    def test_get_messages_empty_returns_none(self):
        from inductiveclaw.backends.openai import OpenAIInteractiveBackend

        backend = OpenAIInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="o3",
        )
        backend._messages = []
        assert backend.get_messages() is None


# --- Gemini backend get_messages / restore_messages ---


class TestGeminiMessageRoundtrip:
    def test_serialize_user_text(self):
        from inductiveclaw.backends.gemini import GeminiInteractiveBackend

        backend = GeminiInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="gemini-2.5-pro",
        )
        backend._contents = ["hello world"]
        msgs = backend.get_messages()
        assert msgs is not None
        assert len(msgs) == 1
        assert msgs[0]["type"] == "user_text"
        assert msgs[0]["text"] == "hello world"

    def test_serialize_content_with_text(self):
        from inductiveclaw.backends.gemini import GeminiInteractiveBackend

        # Mock a Content object with text part
        part = MagicMock()
        part.text = "Some response"
        part.function_call = None
        part.function_response = None
        content = MagicMock()
        content.parts = [part]
        content.role = "model"

        backend = GeminiInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="gemini-2.5-pro",
        )
        backend._contents = [content]
        msgs = backend.get_messages()
        assert msgs is not None
        assert len(msgs) == 1
        assert msgs[0]["type"] == "content"
        assert msgs[0]["role"] == "model"
        assert msgs[0]["parts"][0]["type"] == "text"
        assert msgs[0]["parts"][0]["text"] == "Some response"

    def test_serialize_function_call(self):
        from inductiveclaw.backends.gemini import GeminiInteractiveBackend

        part = MagicMock()
        part.text = None
        part.function_call = MagicMock()
        part.function_call.name = "read_file"
        part.function_call.args = {"path": "/tmp/test.txt"}
        part.function_response = None
        content = MagicMock()
        content.parts = [part]
        content.role = "model"

        backend = GeminiInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="gemini-2.5-pro",
        )
        backend._contents = [content]
        msgs = backend.get_messages()
        assert msgs is not None
        assert msgs[0]["parts"][0]["type"] == "function_call"
        assert msgs[0]["parts"][0]["name"] == "read_file"
        assert msgs[0]["parts"][0]["args"]["path"] == "/tmp/test.txt"

    def test_serialize_function_response(self):
        from inductiveclaw.backends.gemini import GeminiInteractiveBackend

        part = MagicMock()
        part.text = None
        part.function_call = None
        part.function_response = MagicMock()
        part.function_response.name = "read_file"
        part.function_response.response = {"result": "file contents"}
        content = MagicMock()
        content.parts = [part]
        content.role = "user"

        backend = GeminiInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="gemini-2.5-pro",
        )
        backend._contents = [content]
        msgs = backend.get_messages()
        assert msgs is not None
        assert msgs[0]["parts"][0]["type"] == "function_response"
        assert msgs[0]["parts"][0]["name"] == "read_file"

    def test_empty_contents_returns_none(self):
        from inductiveclaw.backends.gemini import GeminiInteractiveBackend

        backend = GeminiInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="gemini-2.5-pro",
        )
        backend._contents = []
        assert backend.get_messages() is None

    def test_mixed_contents(self):
        from inductiveclaw.backends.gemini import GeminiInteractiveBackend

        # Mix of string (user text) and Content objects
        text_part = MagicMock()
        text_part.text = "response"
        text_part.function_call = None
        text_part.function_response = None
        content = MagicMock()
        content.parts = [text_part]
        content.role = "model"

        backend = GeminiInteractiveBackend(
            system_prompt="test", project_dir="/tmp", env={}, model="gemini-2.5-pro",
        )
        backend._contents = ["user message", content]
        msgs = backend.get_messages()
        assert msgs is not None
        assert len(msgs) == 2
        assert msgs[0]["type"] == "user_text"
        assert msgs[1]["type"] == "content"


# --- Base backend defaults ---


class TestBaseBackendDefaults:
    def test_get_messages_returns_none(self):
        from inductiveclaw.backends.base import InteractiveBackend

        # InteractiveBackend is abstract, but get_messages/restore_messages are concrete
        # Test via a minimal mock that inherits the defaults
        class _TestBackend(InteractiveBackend):
            async def start(self): pass
            async def send_message(self, message): pass
            async def receive(self): yield  # type: ignore
            async def close(self): pass
            @property
            def session_id(self): return None

        backend = _TestBackend()
        assert backend.get_messages() is None

    def test_restore_messages_is_noop(self):
        from inductiveclaw.backends.base import InteractiveBackend

        class _TestBackend(InteractiveBackend):
            async def start(self): pass
            async def send_message(self, message): pass
            async def receive(self): yield  # type: ignore
            async def close(self): pass
            @property
            def session_id(self): return None

        backend = _TestBackend()
        backend.restore_messages([{"role": "user", "content": "test"}])  # Should not raise

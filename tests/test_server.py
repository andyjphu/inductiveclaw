"""Tests for dev server lifecycle management."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inductiveclaw.server import (
    DevServerHandle,
    _extract_port,
    detect_dev_command,
    is_port_ready,
    ensure_server,
    start_dev_server,
    stop_dev_server,
)


# --- Port extraction ---


class TestExtractPort:
    def test_double_dash_port(self):
        assert _extract_port("vite --port 3001") == 3001

    def test_short_flag(self):
        assert _extract_port("serve -p 8080") == 8080

    def test_colon_port(self):
        assert _extract_port("http://localhost:4200") == 4200

    def test_env_port(self):
        assert _extract_port("PORT=5000 node server.js") == 5000

    def test_no_port(self):
        assert _extract_port("node server.js") is None

    def test_short_number_not_matched(self):
        # Numbers with fewer than 4 digits shouldn't match the colon pattern
        assert _extract_port("step:3") is None


# --- Dev command detection ---


class TestDetectDevCommand:
    def test_package_json_dev_script(self, tmp_path: Path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "scripts": {"dev": "vite --port 3001"}
        }))
        result = detect_dev_command(str(tmp_path))
        assert result is not None
        cmd, port = result
        assert cmd == "npm run dev"
        assert port == 3001

    def test_package_json_start_script(self, tmp_path: Path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "scripts": {"start": "react-scripts start"}
        }))
        result = detect_dev_command(str(tmp_path))
        assert result is not None
        cmd, port = result
        assert cmd == "npm run start"
        assert port == 3000

    def test_package_json_dev_preferred_over_start(self, tmp_path: Path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "scripts": {"dev": "vite", "start": "node build/index.js"}
        }))
        result = detect_dev_command(str(tmp_path))
        assert result is not None
        assert result[0] == "npm run dev"

    def test_index_html_fallback(self, tmp_path: Path):
        (tmp_path / "index.html").write_text("<html></html>")
        result = detect_dev_command(str(tmp_path))
        assert result is not None
        cmd, port = result
        assert "http.server" in cmd
        assert port == 3000

    def test_django_manage_py(self, tmp_path: Path):
        (tmp_path / "manage.py").write_text("#!/usr/bin/env python")
        result = detect_dev_command(str(tmp_path))
        assert result is not None
        assert "manage.py" in result[0]

    def test_flask_app_py(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("from flask import Flask")
        result = detect_dev_command(str(tmp_path))
        assert result is not None
        assert "app.py" in result[0]
        assert result[1] == 8000

    def test_empty_dir_returns_none(self, tmp_path: Path):
        assert detect_dev_command(str(tmp_path)) is None

    def test_invalid_package_json(self, tmp_path: Path):
        (tmp_path / "package.json").write_text("not json")
        assert detect_dev_command(str(tmp_path)) is None

    def test_package_json_no_scripts(self, tmp_path: Path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "test"}))
        # Falls through to check other files
        assert detect_dev_command(str(tmp_path)) is None


# --- Port readiness ---


class TestIsPortReady:
    @pytest.mark.asyncio
    async def test_closed_port_returns_false(self):
        # Use a port that's almost certainly not in use
        assert await is_port_ready(49999, timeout=0.2) is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        assert await is_port_ready(49998, timeout=0.05) is False


# --- DevServerHandle ---


class TestDevServerHandle:
    def test_url_property(self):
        proc = MagicMock(spec=subprocess.Popen)
        handle = DevServerHandle(process=proc, port=3000, cmd="npm run dev")
        assert handle.url == "http://localhost:3000"

    def test_url_custom_port(self):
        proc = MagicMock(spec=subprocess.Popen)
        handle = DevServerHandle(process=proc, port=8080, cmd="python app.py")
        assert handle.url == "http://localhost:8080"


# --- Stop server ---


class TestStopDevServer:
    @pytest.mark.asyncio
    async def test_already_dead(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = 0  # Already exited
        handle = DevServerHandle(process=proc, port=3000, cmd="test")
        await stop_dev_server(handle)
        proc.terminate.assert_not_called()

    @pytest.mark.asyncio
    async def test_terminate_succeeds(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None  # Still running
        proc.wait.return_value = 0
        handle = DevServerHandle(process=proc, port=3000, cmd="test")
        await stop_dev_server(handle)
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_terminate_timeout_kills(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        handle = DevServerHandle(process=proc, port=3000, cmd="test")
        await stop_dev_server(handle)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()


# --- Ensure server ---


class TestEnsureServer:
    @pytest.mark.asyncio
    async def test_port_already_occupied(self):
        with patch("inductiveclaw.server.is_port_ready", return_value=True):
            result = await ensure_server("/tmp/project", 3000)
            assert result is None

    @pytest.mark.asyncio
    async def test_no_cmd_no_detection(self, tmp_path: Path):
        with patch("inductiveclaw.server.is_port_ready", return_value=False):
            result = await ensure_server(str(tmp_path), 3000)
            assert result is None  # Can't auto-detect, returns None

    @pytest.mark.asyncio
    async def test_auto_detect_and_start(self, tmp_path: Path):
        (tmp_path / "index.html").write_text("<html></html>")
        mock_handle = MagicMock(spec=DevServerHandle)
        with (
            patch("inductiveclaw.server.is_port_ready", return_value=False),
            patch("inductiveclaw.server.start_dev_server", return_value=mock_handle) as mock_start,
        ):
            result = await ensure_server(str(tmp_path), 3000)
            assert result is mock_handle
            mock_start.assert_called_once()

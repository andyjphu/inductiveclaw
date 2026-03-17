"""Tests for backends/tool_executor.py — generic tool dispatch."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import anyio

from inductiveclaw.backends.tool_executor import ToolExecutor, get_all_tool_schemas


class TestGetAllToolSchemas:
    def test_returns_both_iclaw_and_builtin(self):
        schemas = get_all_tool_schemas()
        # 7 iclaw tools + 5 builtins
        assert len(schemas) == 12

    def test_iclaw_tools_present(self):
        schemas = get_all_tool_schemas()
        iclaw_tools = ["update_backlog", "self_evaluate", "take_screenshot",
                       "write_docs", "smoke_test", "propose_idea"]
        for name in iclaw_tools:
            assert name in schemas, f"Missing iclaw tool: {name}"
            assert "description" in schemas[name]
            assert "parameters" in schemas[name]

    def test_builtin_tools_present(self):
        schemas = get_all_tool_schemas()
        builtins = ["bash", "read_file", "write_file", "list_files", "search_files"]
        for name in builtins:
            assert name in schemas, f"Missing builtin tool: {name}"

    def test_schemas_have_valid_structure(self):
        schemas = get_all_tool_schemas()
        for name, schema in schemas.items():
            assert isinstance(schema["description"], str), f"{name} description not str"
            assert isinstance(schema["parameters"], dict), f"{name} parameters not dict"
            assert schema["parameters"].get("type") == "object", f"{name} params not object type"


class TestToolExecutorBuiltins:
    """Test the built-in tools (bash, read, write, list, search)."""

    @pytest.fixture
    def executor(self, tmp_path):
        return ToolExecutor(str(tmp_path))

    @pytest.fixture
    def project(self, tmp_path):
        # Create some test files
        (tmp_path / "hello.py").write_text("print('hello')\n")
        (tmp_path / "world.py").write_text("print('world')\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("# nested\n")
        return tmp_path

    def test_bash_simple_command(self, executor, project):
        async def run():
            return await executor.execute("bash", {"command": "echo hello"})
        result = anyio.run(run)
        assert "hello" in result

    def test_bash_empty_command(self):
        async def run():
            ex = ToolExecutor("/tmp")
            return await ex.execute("bash", {"command": ""})
        result = anyio.run(run)
        assert "error" in result.lower() or "empty" in result.lower()

    def test_bash_sudo_blocked(self, executor, project):
        async def run():
            return await executor.execute("bash", {"command": "sudo ls"})
        result = anyio.run(run)
        assert "blocked" in result.lower() or "sudo" in result.lower()

    def test_read_file(self, executor, project):
        async def run():
            return await executor.execute("read_file", {"file_path": "hello.py"})
        result = anyio.run(run)
        assert "print('hello')" in result

    def test_read_file_absolute(self, executor, project):
        async def run():
            return await executor.execute("read_file", {"file_path": str(project / "hello.py")})
        result = anyio.run(run)
        assert "print('hello')" in result

    def test_read_file_not_found(self, executor, project):
        async def run():
            return await executor.execute("read_file", {"file_path": "nonexistent.py"})
        result = anyio.run(run)
        assert "not found" in result.lower()

    def test_read_file_outside_sandbox(self, executor, project):
        async def run():
            return await executor.execute("read_file", {"file_path": "/etc/passwd"})
        result = anyio.run(run)
        assert "blocked" in result.lower()

    def test_write_file(self, executor, project):
        async def run():
            return await executor.execute("write_file", {
                "file_path": "new_file.py",
                "content": "# new file\nprint('created')\n",
            })
        result = anyio.run(run)
        assert "wrote" in result.lower()
        assert (project / "new_file.py").exists()
        assert "print('created')" in (project / "new_file.py").read_text()

    def test_write_file_creates_dirs(self, executor, project):
        async def run():
            return await executor.execute("write_file", {
                "file_path": "deep/nested/dir/file.py",
                "content": "# deep\n",
            })
        result = anyio.run(run)
        assert (project / "deep" / "nested" / "dir" / "file.py").exists()

    def test_write_file_outside_sandbox(self, executor, project):
        async def run():
            return await executor.execute("write_file", {
                "file_path": "/tmp/evil.py",
                "content": "# evil\n",
            })
        result = anyio.run(run)
        assert "blocked" in result.lower()

    def test_list_files(self, executor, project):
        async def run():
            return await executor.execute("list_files", {"pattern": "*.py"})
        result = anyio.run(run)
        assert "hello.py" in result
        assert "world.py" in result

    def test_list_files_recursive(self, executor, project):
        async def run():
            return await executor.execute("list_files", {"pattern": "**/*.py"})
        result = anyio.run(run)
        assert "hello.py" in result
        assert "nested.py" in result

    def test_list_files_no_match(self, executor, project):
        async def run():
            return await executor.execute("list_files", {"pattern": "*.xyz"})
        result = anyio.run(run)
        assert "no files" in result.lower()

    def test_search_files(self, executor, project):
        async def run():
            return await executor.execute("search_files", {"pattern": "hello"})
        result = anyio.run(run)
        assert "hello" in result

    def test_search_files_with_glob(self, executor, project):
        async def run():
            return await executor.execute("search_files", {"pattern": "print", "glob": "*.py"})
        result = anyio.run(run)
        assert "print" in result

    def test_search_files_no_match(self, executor, project):
        async def run():
            return await executor.execute("search_files", {"pattern": "zzzzzznotfound"})
        result = anyio.run(run)
        assert "no match" in result.lower()

    def test_unknown_tool(self, executor, project):
        async def run():
            return await executor.execute("nonexistent_tool", {})
        result = anyio.run(run)
        assert "unknown" in result.lower()


class TestToolExecutorIclawTools:
    """Test iclaw custom tools through the executor."""

    @pytest.fixture
    def executor(self, tmp_path):
        return ToolExecutor(str(tmp_path))

    def test_update_backlog(self, tmp_path):
        executor = ToolExecutor(str(tmp_path))
        async def run():
            return await executor.execute("update_backlog", {
                "completed_item": "Built feature X",
                "next_priorities": ["Feature Y", "Feature Z"],
                "quality_notes": "Looking good",
                "blockers": [],
            })
        result = anyio.run(run)
        assert "backlog updated" in result.lower()
        assert (tmp_path / "BACKLOG.md").exists()
        content = (tmp_path / "BACKLOG.md").read_text()
        assert "Built feature X" in content
        assert "Feature Y" in content

    def test_self_evaluate(self, tmp_path):
        executor = ToolExecutor(str(tmp_path))
        async def run():
            return await executor.execute("self_evaluate", {
                "features_tested": ["auth", "dashboard"],
                "bugs_found": ["login bug"],
                "bugs_fixed": ["login bug"],
                "views_screenshotted": ["home"],
                "visual_issues": [],
                "missing_features": [],
                "functionality_score": 8,
                "visual_score": 7,
                "code_quality_score": 8,
                "completeness_score": 9,
                "overall_score": 8,
                "critique": "Good progress",
                "top_improvements": ["Add tests"],
                "ready_to_ship": False,
            })
        result = anyio.run(run)
        parsed = json.loads(result)
        assert parsed["overall_score"] == 8
        assert parsed["ready_to_ship"] is False
        assert (tmp_path / "EVALUATIONS.md").exists()

    def test_write_docs(self, tmp_path):
        executor = ToolExecutor(str(tmp_path))
        async def run():
            return await executor.execute("write_docs", {
                "file": "README.md",
                "content": "# Test Project\nHello world",
                "mode": "overwrite",
            })
        result = anyio.run(run)
        assert "wrote" in result.lower()
        assert (tmp_path / "README.md").exists()
        assert "Hello world" in (tmp_path / "README.md").read_text()

    def test_write_docs_append(self, tmp_path):
        (tmp_path / "README.md").write_text("# Existing\n")
        executor = ToolExecutor(str(tmp_path))
        async def run():
            return await executor.execute("write_docs", {
                "file": "README.md",
                "content": "## New Section",
                "mode": "append",
            })
        result = anyio.run(run)
        content = (tmp_path / "README.md").read_text()
        assert "# Existing" in content
        assert "## New Section" in content

    def test_propose_idea(self, tmp_path):
        executor = ToolExecutor(str(tmp_path))
        async def run():
            return await executor.execute("propose_idea", {
                "title": "Better auth",
                "description": "Add OAuth2 support",
                "relationship": "extension",
                "carries_forward": ["user model"],
            })
        result = anyio.run(run)
        assert "idea proposed" in result.lower()
        proposal_path = tmp_path / ".iclaw" / "idea_proposal.json"
        assert proposal_path.exists()
        data = json.loads(proposal_path.read_text())
        assert data["title"] == "Better auth"

    def test_smoke_test_empty_script(self, tmp_path):
        executor = ToolExecutor(str(tmp_path))
        async def run():
            return await executor.execute("smoke_test", {"script": ""})
        result = anyio.run(run)
        assert "empty" in result.lower()

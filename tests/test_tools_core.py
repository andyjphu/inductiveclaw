"""Tests for tools_core.py — pure tool implementations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import anyio

from inductiveclaw.tools_core import (
    TOOL_SCHEMAS,
    tool_update_backlog,
    tool_self_evaluate,
    tool_write_docs,
    tool_propose_idea,
)


class TestToolSchemas:
    def test_all_tools_present(self):
        expected = {"update_backlog", "self_evaluate", "take_screenshot",
                    "write_docs", "smoke_test", "propose_idea",
                    "browser_evaluate"}
        assert set(TOOL_SCHEMAS.keys()) == expected

    def test_schemas_have_required_fields(self):
        for name, schema in TOOL_SCHEMAS.items():
            assert "description" in schema, f"{name} missing description"
            assert "parameters" in schema, f"{name} missing parameters"
            assert schema["parameters"]["type"] == "object", f"{name} params not object"
            assert "properties" in schema["parameters"], f"{name} missing properties"

    def test_self_evaluate_has_required_fields(self):
        schema = TOOL_SCHEMAS["self_evaluate"]
        required = schema["parameters"].get("required", [])
        assert "overall_score" in required
        assert "ready_to_ship" in required
        assert "critique" in required


class TestToolUpdateBacklog:
    def test_creates_new_backlog(self, tmp_path):
        async def run():
            return await tool_update_backlog(str(tmp_path), {
                "completed_item": "Feature A",
                "next_priorities": ["Feature B", "Feature C"],
                "quality_notes": "Good progress",
                "blockers": ["API rate limit"],
            })
        result = anyio.run(run)
        text = result["content"][0]["text"]
        assert "backlog updated" in text.lower()

        backlog = (tmp_path / "BACKLOG.md").read_text()
        assert "Feature A" in backlog
        assert "Feature B" in backlog
        assert "Feature C" in backlog
        assert "Good progress" in backlog
        assert "API rate limit" in backlog

    def test_appends_to_existing(self, tmp_path):
        (tmp_path / "BACKLOG.md").write_text("# Backlog\n\n## Completed\n")
        async def run():
            return await tool_update_backlog(str(tmp_path), {
                "completed_item": "Feature X",
                "next_priorities": [],
            })
        anyio.run(run)
        backlog = (tmp_path / "BACKLOG.md").read_text()
        assert "## Completed" in backlog
        assert "Feature X" in backlog

    def test_no_completed_item(self, tmp_path):
        async def run():
            return await tool_update_backlog(str(tmp_path), {
                "next_priorities": ["Do stuff"],
            })
        result = anyio.run(run)
        text = result["content"][0]["text"]
        assert "backlog updated" in text.lower()


class TestToolSelfEvaluate:
    def test_creates_evaluation(self, tmp_path):
        async def run():
            return await tool_self_evaluate(str(tmp_path), {
                "features_tested": ["auth"],
                "bugs_found": ["crash on login"],
                "bugs_fixed": ["crash on login"],
                "views_screenshotted": ["home"],
                "visual_issues": [],
                "missing_features": ["search"],
                "functionality_score": 7,
                "visual_score": 8,
                "code_quality_score": 9,
                "completeness_score": 6,
                "overall_score": 7,
                "critique": "Needs search feature",
                "top_improvements": ["Add search", "Fix nav"],
                "ready_to_ship": False,
            })
        result = anyio.run(run)
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["overall_score"] == 7
        assert parsed["ready_to_ship"] is False
        assert parsed["bugs_found"] == 1
        assert parsed["bugs_fixed"] == 1
        assert "search" in parsed["missing_features"]

        eval_content = (tmp_path / "EVALUATIONS.md").read_text()
        assert "7/10" in eval_content
        assert "Needs search feature" in eval_content

    def test_appends_multiple_evaluations(self, tmp_path):
        base_args = {
            "features_tested": [], "bugs_found": [], "bugs_fixed": [],
            "views_screenshotted": [], "visual_issues": [], "missing_features": [],
            "functionality_score": 5, "visual_score": 5, "code_quality_score": 5,
            "completeness_score": 5, "overall_score": 5,
            "critique": "First eval", "top_improvements": [], "ready_to_ship": False,
        }
        async def run():
            await tool_self_evaluate(str(tmp_path), base_args)
            args2 = dict(base_args)
            args2["overall_score"] = 8
            args2["critique"] = "Second eval"
            await tool_self_evaluate(str(tmp_path), args2)

        anyio.run(run)
        content = (tmp_path / "EVALUATIONS.md").read_text()
        assert "First eval" in content
        assert "Second eval" in content
        assert content.count("Evaluation —") == 2


class TestToolWriteDocs:
    def test_overwrite(self, tmp_path):
        async def run():
            return await tool_write_docs(str(tmp_path), {
                "file": "README.md",
                "content": "# Hello",
                "mode": "overwrite",
            })
        result = anyio.run(run)
        assert "wrote" in result["content"][0]["text"].lower()
        assert (tmp_path / "README.md").read_text() == "# Hello"

    def test_append(self, tmp_path):
        (tmp_path / "README.md").write_text("# Old\n")
        async def run():
            return await tool_write_docs(str(tmp_path), {
                "file": "README.md",
                "content": "## New",
                "mode": "append",
            })
        anyio.run(run)
        content = (tmp_path / "README.md").read_text()
        assert "# Old" in content
        assert "## New" in content


class TestToolProposeIdea:
    def test_creates_proposal(self, tmp_path):
        async def run():
            return await tool_propose_idea(str(tmp_path), {
                "title": "New Direction",
                "description": "Rewrite the frontend",
                "relationship": "rewrite",
                "carries_forward": ["API", "auth"],
            })
        result = anyio.run(run)
        assert "idea proposed" in result["content"][0]["text"].lower()

        proposal = json.loads(
            (tmp_path / ".iclaw" / "idea_proposal.json").read_text()
        )
        assert proposal["title"] == "New Direction"
        assert proposal["relationship"] == "rewrite"
        assert "API" in proposal["carries_forward"]

"""Tests for high-level orchestration tools.

Covers: derive, intent_execute, list_patterns, tool_categories, tool_recommend.
"""
# ruff: noqa: F821  # MockMCP from conftest.py

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src is on path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit_mcp.tools import orchestration  # noqa: E402

# MockMCP is provided by conftest.py


class TestDeriveTool:
    """Tests for derive() high-level derivation entry point."""

    def test_derive_creates_session_and_plan(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        derive = mcp.tools["derive"]

        result = derive(
            goal="derive temperature-corrected elimination",
            given=["C = C0 * exp(-k*t)", "k = k_ref * exp(Ea/R * (1/T_ref - 1/T))"],
            assumptions=["k is positive", "t is positive"],
            domain="pharmacokinetics",
            pattern="conservation+constitutive",
        )

        assert result["success"] is True
        assert result["session_name"] == "derive_temperature_corrected_elimination"
        assert result["domain"] == "pharmacokinetics"
        assert result["pattern"] == "conservation+constitutive"
        assert result["formulas_loaded"] == 2
        assert result["plan"]["recommended_steps"]
        assert result["recommended_next_steps"]

    def test_derive_without_given_still_creates_session(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        derive = mcp.tools["derive"]

        result = derive(
            goal="simplify the expression x squared plus 2x plus 1",
            domain="general",
        )

        assert result["success"] is True
        assert result["formulas_loaded"] == 0
        assert result["recommended_next_steps"]

    def test_derive_unknown_pattern_defaults_to_direct_manipulation(self, fresh_manager):
        _ = fresh_manager
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        derive = mcp.tools["derive"]

        result = derive(
            goal="do something",
            pattern="totally-unknown-pattern",
        )

        assert result["success"] is True
        assert result["pattern"] == "direct-manipulation"


class TestIntentExecuteTool:
    """Tests for intent_execute() natural language router."""

    def test_intent_derive(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        intent_execute = mcp.tools["intent_execute"]

        result = intent_execute("derive Navier-Stokes equations from conservation laws")

        assert result["success"] is True
        assert result["intent_type"] == "derive"
        assert any(t["tool"] == "derive" for t in result["recommended_tool_chain"])

    def test_intent_simplify(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        intent_execute = mcp.tools["intent_execute"]

        result = intent_execute("simplify this expression", expression="x**2 + 2*x + 1")

        assert result["success"] is True
        assert result["intent_type"] == "simplify"
        assert any(
            t["tool"] == "math" and t["operation"] == "simplify"
            for t in result["recommended_tool_chain"]
        )

    def test_intent_solve(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        intent_execute = mcp.tools["intent_execute"]

        result = intent_execute("solve for x", expression="x**2 - 4 = 0", variable="x")

        assert result["success"] is True
        assert result["intent_type"] == "solve"
        assert any(
            t["tool"] == "math" and t["operation"] == "solve"
            for t in result["recommended_tool_chain"]
        )

    def test_intent_unrecognized(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        intent_execute = mcp.tools["intent_execute"]

        result = intent_execute("make me a sandwich")

        assert result["success"] is True
        assert result["recommended_tool_chain"]


class TestListPatternsTool:
    """Tests for list_patterns() tool."""

    def test_list_patterns_returns_patterns(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        list_patterns = mcp.tools["list_patterns"]

        result = list_patterns()

        assert "patterns" in result
        assert len(result["patterns"]) >= 6
        pattern_names = {p["name"] for p in result["patterns"]}
        assert "conservation+constitutive" in pattern_names
        assert "operator-correspondence" in pattern_names


class TestToolCategoriesTool:
    """Tests for tool_categories() tool."""

    def test_tool_categories_returns_categories(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        tool_categories = mcp.tools["tool_categories"]

        result = tool_categories()

        assert "categories" in result
        category_names = {c["name"] for c in result["categories"]}
        assert "High-Level Orchestration" in category_names
        assert "Unified Math" in category_names


class TestToolRecommendTool:
    """Tests for tool_recommend() tool."""

    def test_recommend_simplify(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        tool_recommend = mcp.tools["tool_recommend"]

        result = tool_recommend("simplify a polynomial")

        assert result["success"] is True
        assert any(r["tool"] == "math" for r in result["recommendations"])

    def test_recommend_unrecognized(self):
        mcp = MockMCP()
        orchestration.register_orchestration_tools(mcp)
        tool_recommend = mcp.tools["tool_recommend"]

        result = tool_recommend("do something weird")

        assert result["success"] is True
        assert any(r["tool"] == "intent_execute" for r in result["recommendations"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for unified session tools: goal-aware derivation and recommendations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit_mcp.tools import math as math_tools  # noqa: E402
from symkit_mcp.tools import orchestration as orchestration_tools  # noqa: E402
from symkit_mcp.tools import session as session_tools  # noqa: E402

# MockMCP is provided by conftest.py


def _register_all_tools(mcp: Any) -> None:
    """Register session, math, and orchestration tools."""
# ruff: noqa: F821  # MockMCP from conftest.py
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    orchestration_tools.register_orchestration_tools(mcp)


class TestGoalTools:
    def test_set_goal_requires_session(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["session_set_goal"]("solve for x")
        assert result["success"] is False
        assert "No active session" in result["error"]

    def test_set_goal_parses_and_recommends(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("test")
        result = mcp.tools["session_set_goal"]("solve for x in x**2 + b*x + c")
        assert result["success"] is True
        assert result["goal"]["target_form"] == "solve_for_x"

        rec = mcp.tools["session_suggest_formulas"]()
        assert rec["success"] is True
        assert isinstance(rec["recommendations"], list)

    def test_suggest_formulas_with_explicit_goal(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("test")
        mcp.tools["session_set_goal"]("derive navier stokes equations")
        result = mcp.tools["session_suggest_formulas"]()
        assert result["success"] is True
        assert isinstance(result["recommendations"], list)

    def test_suggest_formulas_without_goal_or_session(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("test")
        result = mcp.tools["session_suggest_formulas"]()
        assert result["success"] is False
        assert "No goal set" in result["error"]

    def test_suggest_next_steps_without_session(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["session_show"]()
        assert result["success"] is False
        assert "No active session" in result["error"]

    def test_suggest_next_steps_with_goal(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("test")
        mcp.tools["session_load_formula"]("x**2 + 2*x + 1")
        mcp.tools["session_set_goal"]("derive x**2 + 2*x + 1")
        result = mcp.tools["session_show"]()
        assert result["success"] is True
        assert "next_steps" in result
        assert result["progress"]["has_goal"] is True


class TestOrchestrationDerive:
    def test_derive_auto_selects_pattern(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["derive"](
            "derive Navier-Stokes equations from conservation laws",
            domain="fluid_dynamics",
        )
        assert result["success"] is True
        assert result["pattern"] == "conservation+constitutive"
        assert result["goal"]["domain"] == "fluid_dynamics"
        assert "recommended_next_steps" in result
        assert "progress" in result

    def test_derive_with_target_expression(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["derive"](
            "derive the quadratic",
            given=["x**2 + 2*x + 1"],
            target_expression="x**2 + 2*x + 1",
            auto_load=True,
        )
        assert result["success"] is True
        assert result["progress"]["matches_target"] is True
        assert result["progress"]["progress_score"] == 1.0

    def test_derive_with_explicit_pattern(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["derive"](
            "derive energy equation",
            pattern="variational",
            domain="general",
        )
        assert result["success"] is True
        assert result["pattern"] == "variational"


class TestSessionGoalIntegration:
    def test_session_start_accepts_goal(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["session_start"](
            "ns_derivation",
            domain="fluid_dynamics",
            goal="derive incompressible NS equations",
        )
        assert result["success"] is True
        assert result["goal"] is not None
        assert result["goal"]["domain"] == "fluid_dynamics"

    def test_session_show_includes_goal_progress(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"](
            "show_test",
            goal="derive x**2 + 2*x + 1",
        )
        mcp.tools["session_load_formula"]("x**2 + 2*x + 1")
        result = mcp.tools["session_show"](show_steps=True)
        assert result["success"] is True
        # session_show returns goal-aware next steps and pattern
        assert "next_steps" in result
        assert "pattern_used" in result

    def test_session_explain_includes_goal(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"](
            "explain_test",
            goal="derive x**2 + 2*x + 1",
        )
        mcp.tools["session_load_formula"]("x**2 + 2*x + 1")
        result = mcp.tools["session_explain"](level="medium")
        assert result["success"] is True
        assert "summary" in result
        text = result["summary"]
        assert "Goal" in text or "goal" in text

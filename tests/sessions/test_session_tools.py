"""Tests for session management tools, including session_show enhancements and session_explain."""

from __future__ import annotations

import pytest

from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# MockMCP is provided by conftest.py

def _register_all_tools(mcp):
    """Register session and math tools so they can interact."""
# ruff: noqa: F821  # MockMCP from conftest.py
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)

class TestSessionShowEnhanced:
    """Tests for enhanced session_show output."""

    def test_session_show_without_session(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["session_show"]()

        assert result["success"] is False
        assert "No active session" in result["error"]

    def test_session_show_with_next_steps_and_risks(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        # Start a session with a loaded expression
        mcp.tools["session_start"](
            name="test_derivation",
            domain="fluid_dynamics",
            pattern="conservation+constitutive",
        )
        mcp.tools["math"]("parse", "rho*u**2 + p", session=True)

        result = mcp.tools["session_show"]()

        assert result["success"] is True
        assert "next_steps" in result
        assert "risks" in result
        assert "pattern_used" in result
        assert "pattern_description" in result
        assert result["pattern_used"] == "conservation+constitutive"
        assert "Next steps" in result["display_text"]
        assert "Risks / Notes" in result["display_text"]

    def test_session_show_no_expression(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        mcp.tools["session_start"]("empty_test")

        result = mcp.tools["session_show"]()

        assert result["success"] is True
        assert result["latex"] == ""

class TestSessionExplain:
    """Tests for session_explain tool."""

    def test_session_explain_without_session(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["session_explain"]()

        assert result["success"] is False
        assert "No active session" in result["error"]

    def test_session_explain_short_summary(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"](name="explain_test", domain="quantum_mechanics")
        mcp.tools["math"]("diff", "x**3", variable="x", session=True)

        result = mcp.tools["session_explain"](level="short")

        assert result["success"] is True
        assert result["level"] == "short"
        assert result["session_name"] == "explain_test"
        assert result["domain"] == "quantum_mechanics"
        assert "3 x^{2}" in result["summary"] or "3*x**2" in result["summary"]

    def test_session_explain_detailed(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"](name="explain_test", description="derive simple power law")
        mcp.tools["math"]("diff", "x**3", variable="x", session=True)

        result = mcp.tools["session_explain"](level="detailed")

        assert result["success"] is True
        assert result["level"] == "detailed"
        assert "Derivation steps" in result["summary"]
        assert "Current result" in result["summary"]

    def test_session_explain_focus_assumptions(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"](name="focus_test")
        mcp.tools["math"]("diff", "x**3", variable="x", session=True)

        result = mcp.tools["session_explain"](focus="assumptions")

        assert result["success"] is True
        assert result["focus"] == "assumptions"
        assert "All recorded assumptions" in result["summary"]

class TestListAssumptionsLevels:
    """list_assumptions accepts "merged" as an alias for the default merged
    view (run-014: the docstring said "None for merged" but the literal string
    was rejected)."""

    def test_merged_alias_accepted(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        from symkit_mcp.tools.assumptions import register_assumption_tools

        register_assumption_tools(mcp)
        mcp.tools["session_start"](name="lvl_test")
        merged_default = mcp.tools["list_assumptions"]()
        merged_alias = mcp.tools["list_assumptions"](level="merged")
        assert merged_default["success"] is True
        assert merged_alias["success"] is True
        assert merged_alias["level"] == "merged"
        assert merged_alias["assumptions"] == merged_default["assumptions"]

    def test_unknown_level_still_rejected(self, fresh_session_manager):
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        from symkit_mcp.tools.assumptions import register_assumption_tools

        register_assumption_tools(mcp)
        mcp.tools["session_start"](name="lvl_test2")
        result = mcp.tools["list_assumptions"](level="bogus")
        assert result["success"] is False
        assert "Invalid level" in result["error"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for session management tools, including session_show enhancements and session_explain."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src is on path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit_mcp.tools import math as math_tools  # noqa: E402
from symkit_mcp.tools import session as session_tools  # noqa: E402

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

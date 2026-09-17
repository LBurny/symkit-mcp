"""Round-15 (task-13 C-01/D4): suspect identities must surface at session level.

A step whose recorded difference is nonzero can be ``status: verified`` (the
operator ran faithfully) while carrying ``details.suspect_identity``.  The
session summary silently dropped that flag, so ``overall: verified`` read as
"the identities hold".  ``session_verify_session`` and ``session_complete`` must
list the affected step numbers and warn, without changing the ``overall``
calculation.
"""

from __future__ import annotations

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_verify_session_surfaces_suspect_step(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("suspect_surface")
    # task-13 #4 / r19 F1: a genuine A - B; (x+y)^2 - (x^2 + y^2) is 2xy, false.
    tools["math"](operation="simplify", expression="(x + y)**2 - (x**2 + y**2)", session=True)

    result = tools["session_verify_session"]()
    assert result["overall"] == "verified"  # polarity is unchanged
    assert result["failed"] == 0
    assert result["suspect_identity_steps"] == [1]
    assert any("suspect_identity_steps" in w for w in result.get("warnings", []))


def test_complete_surfaces_suspect_step(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("suspect_complete")
    tools["math"](operation="simplify", expression="(x + y)**2 - (x**2 + y**2)", session=True)

    result = tools["session_complete"](auto_save=False)
    summary = result["verification_summary"]
    assert summary["suspect_identity_steps"] == [1]
    assert any("suspect_identity_steps" in w for w in summary.get("warnings", []))


def test_clean_session_reports_empty_suspect_list(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("clean_surface")
    tools["math"](operation="simplify", expression="x + x", session=True)

    result = tools["session_verify_session"]()
    assert result["suspect_identity_steps"] == []
    assert not result.get("warnings")

    complete = tools["session_complete"](auto_save=False)
    assert complete["verification_summary"]["suspect_identity_steps"] == []
    assert not any("suspect_identity_steps" in w for w in complete.get("warnings", []))


def test_suspect_step_keeps_verified_status(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("suspect_status")
    tools["math"](operation="simplify", expression="(x + y)**2 - (x**2 + y**2)", session=True)
    session = _state.get_session()
    assert session is not None
    assert '"suspect_identity": "unreduced"' in session.steps[0].verification_result

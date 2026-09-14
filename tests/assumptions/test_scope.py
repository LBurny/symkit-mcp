"""Session-scoped assumptions (r16 task-20 S-2).

Assumptions set inside a session must be reclaimed when that session ends and
must never leak into a different session's math context.  The legacy
no-session global behaviour is preserved: ``assume`` before ``session_start``
is adopted by the next session.
"""

from __future__ import annotations

from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    register_assumption_tools(mcp)
    return mcp.tools


def test_assumptions_do_not_leak_into_a_new_session(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()

    tools["session_start"]("lagrange")
    tools["assume"]({"x": "positive", "y": "positive", "z": "positive"})
    assert tools["show_assumptions"]()["assumptions"]

    tools["session_start"]("probe2")
    assert tools["show_assumptions"]()["assumptions"] == {}

    res = tools["math"](
        operation="solve", expression="x**2 - 4", variable="x", session=False
    )
    assert res["success"], res
    assert res.get("filtered_by_assumptions", []) == []


def test_ending_a_session_reclaims_its_assumptions(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()

    tools["session_start"]("reclaim")
    tools["assume"]({"x": "positive"})
    assert tools["show_assumptions"]()["assumptions"]

    tools["session_abort"]()
    assert tools["show_assumptions"]()["assumptions"] == {}


def test_global_assumptions_are_adopted_by_the_next_session(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()

    tools["assume"]({"w": "positive"})
    tools["session_start"]("adopt")

    assert tools["show_assumptions"]()["assumptions"].get("w", {}).get("positive") is True
    assert tools["math"](
        operation="simplify", expression="sqrt(w**2)", session=False
    )["expression"] == "w"

"""Goal tracking: explicit target variables and whole-history solve detection.

Regression for the run-005/006 progress mis-reports:
- goal text extraction is heuristic; callers need an explicit
  ``target_variables`` override on session_start / session_set_goal;
- "solve for X" only inspected the CURRENT expression, so a follow-up evalf
  step (which legitimately moves the current expression onward) false-reported
  "Not yet solved for X" even though X had been isolated in an earlier step.
"""

from __future__ import annotations

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py


def _make_tools():
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_session_start_accepts_explicit_target_variables(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    res = tools["session_start"](
        "tv_start",
        goal="derive the terminal velocity of a falling sphere",
        target_variables=["v_t", "m"],
    )
    assert res["success"], res
    # Explicit list wins verbatim over the heuristic text extraction.
    assert res["goal"]["target_variables"] == ["v_t", "m"]


def test_session_set_goal_accepts_explicit_target_variables(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("tv_goal")
    res = tools["session_set_goal"](
        "derive the terminal velocity of a falling sphere",
        target_variables=["v_t"],
    )
    assert res["success"], res
    assert res["goal"]["target_variables"] == ["v_t"]
    sess = _state.get_session()
    assert sess is not None
    assert sess.goal is not None
    assert sess.goal.target_variables == ["v_t"]


def test_solve_for_detected_from_step_history_after_current_moves_on(
    fresh_session_manager,
):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("solve_track", goal="solve for v_t")
    solved = tools["math"](
        operation="solve",
        expression="v_t**2 - 1",
        variable="v_t",
    )
    assert solved["success"], solved
    # A later step moves the current expression to a plain number; the goal
    # tracker must still see that v_t was isolated in an earlier step.
    moved = tools["math"](operation="evalf", expression="pi")
    assert moved["success"], moved

    sess = _state.get_session()
    assert sess is not None
    assert not hasattr(sess.current_expression, "lhs")  # current is a Float
    progress = sess.compute_progress()
    assert progress["matches_target"] is True
    assert not any("Not yet solved" in g for g in progress["remaining_gaps"])
    assert not any("Missing target variables" in g for g in progress["remaining_gaps"])

    done = sess.complete()
    assert done["target_reached"] is True

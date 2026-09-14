"""solve must not silently drop the trivial root 0, and must disclose filtering.

r14 task-15: with ``I`` registered positive, ``math("solve",
"I*(beta*S/N - gamma)", variable="I")`` returned "No solution found for I"
even though the factored equation plainly has the root ``I = 0`` (the
disease-free equilibrium). SymPy cancels the ``I`` factor because the positive
assumption implies ``I != 0``, dropping the zero root with no warning.

r14 lane-B D7: solve also dropped whole root families (negative roots under a
positive assumption) with no hint that assumptions had filtered them.
"""

from __future__ import annotations

from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_solve_restores_factored_zero_root_under_positive_assumption(
    fresh_session_manager,
):
    """The ``I = 0`` root of ``I*(beta*S/N - gamma)`` survives a positive
    assumption on I and the assumption filtering is disclosed."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="I*(beta*S/N - gamma)",
        variable="I",
        assumptions=["I positive"],
        session=False,
    )
    assert res["success"], res
    assert "0" in res["all_solutions"], res
    assert res["solution"] == "0", res
    # The positive assumption excluded 0; that must be stated, not silent.
    assert res.get("filtered_by_assumptions") == ["0"], res
    assert res.get("warnings"), res


def test_solve_zero_root_without_assumptions_has_no_filtering(fresh_session_manager):
    """Stateless solve already returns the zero root; no filtering is reported."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="I*(beta*S/N - gamma)",
        variable="I",
        session=False,
    )
    assert res["success"], res
    assert "0" in res["all_solutions"], res
    assert res.get("filtered_by_assumptions") == [], res


def test_solve_discloses_negative_root_filtered_by_positive_assumption(
    fresh_session_manager,
):
    """``x**2 - 4`` with x positive still promotes 2 (unchanged semantics) but
    now reports the -2 root the assumption filtered away."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="x**2 - 4",
        variable="x",
        assumptions=["x positive"],
        session=False,
    )
    assert res["success"], res
    assert res["solution"] == "2", res
    assert not any("-2" in s for s in res["all_solutions"]), res
    assert "-2" in res["filtered_by_assumptions"], res

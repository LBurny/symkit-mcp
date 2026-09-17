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
    assumption on I and the assumption filtering is disclosed.

    r19 F22: the restored root is *kept* in ``all_solutions`` and disclosed as
    restored — it must not simultaneously be reported as filtered, and the
    headline must be the non-excluded root rather than a Boolean
    (``Eq(I, 0)`` auto-evaluates to ``False`` when I is positive)."""
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
    # A restored root is not also counted as filtered.
    assert res.get("filtered_by_assumptions") == [], res
    assert res["solution"] not in res["filtered_by_assumptions"], res
    # The headline is a proper Eq, never the Boolean SymPy collapses it to.
    assert res["expression"].startswith("Eq(I,"), res
    assert res["expression"] not in ("True", "False"), res
    # The zero root's exclusion-and-restore is stated, not silent.
    assert any("restored" in w for w in res["warnings"]), res


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


def test_system_solve_applies_assumptions_like_scalar(fresh_session_manager):
    """r16 task-20 S-3: a system solve must apply active assumptions, not
    return positive-violating equilibria such as ``(0, 0, 12, 0)`` silently."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="x+y+z-12, -lam+y*z, -lam+x*z, -lam+x*y",
        variable="x,y,z,lam",
        assumptions=["x positive", "y positive", "z positive"],
        session=False,
    )
    assert res["success"], res
    assert res["all_solutions"] == ["(4, 4, 4, 16)"], res
    assert "(0, 0, 12, 0)" in res["filtered_by_assumptions"], res
    assert any("x positive" in warning for warning in res["warnings"]), res


def test_multi_solution_solve_flags_headline_bias(fresh_session_manager):
    """r16 task-04/07/10/20: ``solution`` shows only the first root; >1 solution
    must warn and point at ``all_solutions``."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="x+y+z-12, -lam+y*z, -lam+x*z, -lam+x*y",
        variable="x,y,z,lam",
        session=False,
    )
    assert res["success"], res
    assert len(res["all_solutions"]) == 4, res
    assert any(
        "first of 4 solutions" in warning for warning in res["warnings"]
    ), res
    assert any("all_solutions" in warning for warning in res["warnings"]), res


def test_scalar_solve_with_two_roots_warns_about_headline(fresh_session_manager):
    """r22 task-07 (probe S13): a scalar quadratic keeps both roots in
    ``all_solutions`` while the headline shows one — that must be disclosed,
    like the system path already does ("first of N solutions")."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="s**2 + (R/L)*s + 1/(L*C) = 0",
        variable="s",
        session=False,
    )
    assert res["success"], res
    assert len(res["all_solutions"]) == 2, res
    assert any("all_solutions" in warning for warning in res["warnings"]), res

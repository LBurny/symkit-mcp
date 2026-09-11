"""The math dispatcher must consume or explicitly flag every parameter.

Fail-loud discipline: parameters that do not apply to the requested
operation produce a warning instead of being silently ignored; assumption
clauses accept both ``"x is positive"`` and ``"x positive"`` and malformed
clauses produce warnings rather than vanishing.
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


def test_evalf_applies_substitution(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="evalf",
        expression="sqrt(2*g*m/(rho*C_d*A))",
        substitution={"m": 1, "g": 9.81, "rho": 1.225, "C_d": 0.47, "A": 0.5},
        session=False,
    )
    assert res["success"], res
    assert abs(float(res["expression"]) - 8.25557877930607) < 1e-9


def test_two_word_assumption_format_applies(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="v_t**2 - 1 == 0",
        variable="v_t",
        assumptions=["v_t positive"],
        session=False,
    )
    assert res["success"], res
    assert res["solution"] == "1"


def test_three_word_assumption_format_still_applies(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="v_t**2 - 1 == 0",
        variable="v_t",
        assumptions=["v_t is positive"],
        session=False,
    )
    assert res["success"], res
    assert res["solution"] == "1"


def test_malformed_assumption_produces_warning(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify", expression="x + x", assumptions=["banana"], session=False
    )
    assert res["success"]
    assert any("banana" in w for w in res.get("warnings", []))


def test_unused_parameter_produces_warning(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify", expression="x + x", point="3", session=False
    )
    assert res["success"]
    assert any("'point'" in w and "simplify" in w for w in res.get("warnings", []))


def test_default_valued_parameters_do_not_warn(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="simplify", expression="x + x", order=1, direction="+-", session=False
    )
    assert res["success"]
    assert not res.get("warnings")


def test_evalf_substitution_with_context_assumptions(fresh_session_manager):
    """Regression (run-008): assumptions persist in the shared context (via the
    explicit assume() tool); evalf then parsed the expression with
    assumption-bearing symbols while substitution keys were plain symbols, so
    subs silently no-opped and the result kept free symbols. Substitute must
    behave the same either way. (Assumption scoping, run-013: a session=false
    call's per-call assumptions no longer seed the context, so stateless
    callers seed via assume() instead.)"""
    _ = fresh_session_manager
    tools = _tools()
    seeded = tools["assume"]({"m": "positive", "k": "positive", "c": "positive"})
    assert seeded["success"], seeded
    for op in ("evalf", "substitute"):
        res = tools["math"](
            operation=op,
            expression="sqrt(4*m*k - c**2)/(2*m)",
            substitution={"m": "1", "k": "10", "c": "0.4"},
            session=False,
        )
        assert res["success"], res
        assert abs(float(res["expression"]) - 3.15594676761190) < 1e-9


def test_solve_prefers_positive_root_when_params_positive(fresh_session_manager):
    """Regression (run-011/run-012): solve presented the negative root as the
    main ``solution`` (positive root only in ``all_solutions``) even though the
    parameters carried positive assumptions. The representative solution must
    prefer the provably positive root; ``all_solutions`` stays complete."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="solve",
        expression="omega*L - 1/(omega*C)",
        variable="omega",
        assumptions=["L positive", "C positive"],
        session=False,
    )
    assert res["success"], res
    assert not res["solution"].startswith("-"), res["solution"]
    assert "sqrt" in res["solution"]
    assert len(res["all_solutions"]) == 2


def test_series_keeps_big_o_term(fresh_session_manager):
    """Regression (run-011): the series result silently dropped the O(x**n)
    term, reporting a bare polynomial as if it were exact."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="series",
        expression="exp(-x)",
        variable="x",
        point="0",
        order=4,
        session=False,
    )
    assert res["success"], res
    assert "O(x**4)" in res["expression"]

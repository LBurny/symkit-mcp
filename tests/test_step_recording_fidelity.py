"""Step recording must archive the same object that was returned to the client.

Regression net for the archive/response divergence where the recorded step
was re-parsed from ``str(result)`` and function notation like ``v(t)`` was
corrupted into ``t*v`` in the session JSON while the live response was right.
"""

from __future__ import annotations

import sympy as sp

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


def test_dsolve_step_archive_matches_response(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("ode_check", goal="solve dv/dt = -k*v for v")
    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="v",
        with_respect_to="t",
    )
    assert res["success"], res
    sess = _state.get_session()
    assert sess is not None
    step = sess.steps[-1]
    # Archive and response describe the same object.
    assert step.output_expression == res["expression"]
    # Function notation survives into the archive (no t*v corruption).
    assert "Function('v')" in step.output_srepr
    assert "Mul(Symbol('t'), Symbol('v'))" not in step.output_srepr


def test_solve_returns_bare_solution_field(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("solve_check")
    res = tools["math"](
        operation="solve",
        expression="1/2*rho*C_d*A*v_t**2 == m*g",
        variable="v_t",
    )
    assert res["success"], res
    sol = res["solution"]
    # Bare RHS: never wrapped in Eq(...), consistent with the expression field.
    assert not sol.startswith("Eq(")
    assert res["expression"] == f"Eq(v_t, {sol})"
    assert "solution_latex" in res
    # The bare solution really solves the original equation.
    v_t, rho, C_d, A, m, g = sp.symbols("v_t rho C_d A m g")
    residual = sp.simplify(
        (rho * C_d * A * v_t**2 / 2 - m * g).subs(v_t, sp.sympify(sol))
    )
    assert residual == 0


def test_math_response_has_no_internal_keys(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("leak_check")
    res = tools["math"](operation="simplify", expression="x**2 + 2*x + x**2")
    assert res["success"]
    assert not any(k.startswith("_") for k in res)


def test_substitute_step_records_live_object(fresh_session_manager):
    _ = fresh_session_manager
    tools = _make_tools()
    tools["session_start"]("subs_check")
    res = tools["math"](
        operation="substitute",
        expression="Derivative(y(x), x) + y(x)",
        substitution={"y(x)": "0"},
    )
    assert res["success"], res
    assert res["expression"] == "0"
    sess = _state.get_session()
    assert sess is not None
    # Input archive keeps y(x) function notation, not x*y.
    assert "y(x)" in sess.steps[-1].input_expressions["original"]

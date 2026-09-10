"""dsolve input handling: Leibniz notation, non-ODE rejection, initial conditions.

Regression (run-012): ``dV/dt`` was silently parsed as ``Symbol('dV') /
Symbol('dt')`` and dsolve returned an algebraic rearrangement
``Eq(V(t), -C*R*dV/dt)`` with ``success=true`` — the worst failure mode.
Leibniz notation must now parse into real ``Derivative`` terms, input without
any derivative must be rejected loudly, and initial conditions must be
appliable via the ``ics`` parameter instead of a 3-call manual workaround.
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


def test_dsolve_accepts_leibniz_first_order(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="R*C*dV/dt + V",
        variable="V",
        with_respect_to="t",
        session=False,
    )
    assert res["success"], res
    expr = res["expression"]
    assert expr.startswith("Eq(V(t)")
    assert "exp(" in expr
    assert "C1" in expr
    # The Leibniz tokens must not survive as bogus free symbols.
    assert "dV" not in expr and "dt" not in expr


def test_dsolve_accepts_leibniz_second_order(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="d^2x/dt^2 + x",
        variable="x",
        with_respect_to="t",
        session=False,
    )
    assert res["success"], res
    assert "sin(t)" in res["expression"]
    assert "cos(t)" in res["expression"]


def test_dsolve_rejects_expression_without_derivative(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="x + 1",
        variable="x",
        with_respect_to="t",
        session=False,
    )
    assert not res["success"]
    assert "derivative" in res["error"].lower()


def test_dsolve_applies_initial_conditions(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="diff(V,t) + V/(R*C)",
        variable="V",
        with_respect_to="t",
        ics={"V(0)": "V_0"},
        session=False,
    )
    assert res["success"], res
    assert "C1" not in res["expression"]
    assert "V_0" in res["expression"]
    assert "exp(" in res["expression"]


def test_dsolve_ics_with_leibniz_notation(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="R*C*dV/dt + V",
        variable="V",
        with_respect_to="t",
        ics={"V(0)": "V_0"},
        session=False,
    )
    assert res["success"], res
    assert "C1" not in res["expression"]
    assert "V_0" in res["expression"]


def test_dsolve_ics_rejects_malformed_key(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="diff(V,t) + V",
        variable="V",
        with_respect_to="t",
        ics={"zero": "V_0"},
        session=False,
    )
    assert not res["success"]
    assert "V(0)" in res["error"]

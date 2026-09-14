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


def test_dsolve_ics_derivative_initial_condition(fresh_session_manager):
    """Regression (run-018): second-order ODEs need a velocity initial value,
    but every notation the agent tried was rejected with
    "Cannot parse initial condition 'x'(0)'". Prime notation is now accepted."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="d^2x/dt^2 + 4*x",
        variable="x",
        with_respect_to="t",
        ics={"x(0)": "x_0", "x'(0)": "v_0"},
        session=False,
    )
    assert res["success"], res
    assert "C1" not in res["expression"] and "C2" not in res["expression"]
    assert "x_0" in res["expression"]
    assert "v_0" in res["expression"]


def test_dsolve_rejects_coupled_ode_with_extra_undefined_function(
    fresh_session_manager,
):
    """r14 task-15: the SIR infection equation names a second undefined
    function ``S(t)``. SymPy's namespace silently rewrote ``S(t)`` to ``t``
    (``SingletonRegistry.__call__``), so dsolve returned a fake closed form
    ``Eq(I(t), C1*exp(t*(-gamma + beta*t/(2*N))))`` with success=true. An
    undefined function sharing a term with the dependent variable couples a
    second equation in; that must fail loud, naming ``S(t)``."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="Derivative(I(t),t) - beta*S(t)*I(t)/N + gamma*I(t)",
        variable="I",
        with_respect_to="t",
        session=False,
    )
    assert not res["success"], res
    assert "S(t)" in res["error"], res
    assert "system" in res["error"].lower()


def test_dsolve_still_accepts_additive_forcing_function(fresh_session_manager):
    """The coupling check must not reject a non-homogeneous ODE whose extra
    undefined function is a forcing term (``f(t)`` alone in an additive
    term); dsolve solves that shape and the answer must keep ``f(t)``."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t) + f(t)",
        variable="v",
        with_respect_to="t",
        session=False,
    )
    assert res["success"], res
    assert "f(t)" in res["expression"], res["expression"]


def test_dsolve_applies_session_assumptions_to_ode(fresh_session_manager):
    """Regression (run-018): _parse_ode ignored context assumptions, so dsolve
    of m*x'' + k*x with k,m positive returned the complex-root form
    exp(-t*sqrt(-k/m)) instead of the trig form."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("ode_assump")
    res = tools["math"](
        operation="dsolve",
        expression="m*d^2x/dt^2 + k*x",
        variable="x",
        with_respect_to="t",
        assumptions=["m positive", "k positive"],
        session=True,
    )
    assert res["success"], res
    assert "sin" in res["expression"] or "cos" in res["expression"], res["expression"]
    assert "sqrt(-k" not in res["expression"]

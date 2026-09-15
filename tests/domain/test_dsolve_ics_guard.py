"""r18 A1: ``dsolve`` with ``ics`` on a hard linear ODE must not wedge the server.

``sympy.dsolve(eq, y(t), ics=...)`` solves the integration constants with
``solve`` against the nested-radical characteristic roots of
``y''' - 7y'' + 16y' - 13y = 0`` and never returns (>90 s under the probe cap,
>900 s live).  The MCP server is a single process, so that blocks every other
tool.  A bounded linear solve on the general solution returns the correct
particular solution in milliseconds; past the operation budget the call refuses
with a structured reason.
"""

from __future__ import annotations

import threading
from typing import Any

import sympy as sp

from symkit.domain.dsolve_ics import DSOLVE_ICS_OPS_CAP, dsolve_with_ics
from symkit.infrastructure.sympy_engine import SymPyEngine

_HANG_TIMEOUT = 60.0
_TIMED_OUT = object()


def _run_bounded(func: Any, timeout: float = _HANG_TIMEOUT) -> Any:
    """Run ``func`` in a daemon thread; return ``_TIMED_OUT`` if it never ends."""
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = func()
        except Exception as exc:  # surfaced to the caller
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return _TIMED_OUT
    if "error" in box:
        raise box["error"]
    return box["value"]


def _hard_ode() -> tuple[sp.Symbol, sp.Function, sp.Equality]:
    t = sp.Symbol("t")
    y = sp.Function("y")
    equation = sp.Eq(
        sp.Derivative(y(t), (t, 3))
        - 7 * sp.Derivative(y(t), (t, 2))
        + 16 * sp.Derivative(y(t), t)
        - 13 * y(t),
        0,
    )
    return t, y, equation


def _hard_ics(t: sp.Symbol, y: sp.Function) -> dict[Any, Any]:
    return {
        y(0): sp.Integer(0),
        sp.Derivative(y(t), t).subs(t, 0): sp.Integer(0),
        sp.Derivative(y(t), (t, 2)).subs(t, 0): sp.Integer(1),
    }


def test_bounded_ics_solve_returns_and_satisfies_conditions() -> None:
    t, y, equation = _hard_ode()
    outcome = _run_bounded(
        lambda: dsolve_with_ics(equation, y, t, _hard_ics(t, y))
    )
    assert outcome is not _TIMED_OUT, "dsolve_with_ics wedged on the r18 A1 ODE"
    solution, reason = outcome
    assert reason is None, reason
    assert bool(sp.checkodesol(equation, solution)[0])
    for order, expected in ((0, 0), (1, 0), (2, 1)):
        # Numeric check: sp.simplify on the radical first-derivative at 0 spins.
        residual = sp.N(
            sp.diff(solution.rhs, t, order).subs(t, 0) - expected, 20
        )
        assert abs(complex(residual)) < 1e-12, (order, residual)


def test_general_solution_without_ics_is_unchanged() -> None:
    t, y, equation = _hard_ode()
    general, reason = dsolve_with_ics(equation, y, t, None)
    assert reason is None
    names = {str(s) for s in general.rhs.free_symbols}
    assert {"C1", "C2", "C3"} <= names


def test_first_order_ics_still_applied() -> None:
    t = sp.Symbol("t")
    R, C, V_0 = sp.symbols("R C V_0")
    cap = sp.Function("cap")
    equation = sp.Eq(sp.Derivative(cap(t), t) + cap(t) / (R * C), 0)
    solution, reason = dsolve_with_ics(equation, cap, t, {cap(0): V_0})
    assert reason is None
    assert not solution.rhs.has(sp.Symbol("C1"))
    assert sp.simplify(solution.rhs - V_0 * sp.exp(-t / (C * R))) == 0


def test_second_order_ics_still_applied() -> None:
    t = sp.Symbol("t")
    x = sp.Function("x")
    x_0, v_0 = sp.symbols("x_0 v_0")
    equation = sp.Eq(sp.Derivative(x(t), (t, 2)) + 4 * x(t), 0)
    ics = {x(0): x_0, sp.Derivative(x(t), t).subs(t, 0): v_0}
    solution, reason = dsolve_with_ics(equation, x, t, ics)
    assert reason is None
    expected = v_0 * sp.sin(2 * t) / 2 + x_0 * sp.cos(2 * t)
    assert sp.simplify(solution.rhs - expected) == 0


def test_over_budget_refuses_with_a_structured_reason(monkeypatch: Any) -> None:
    t, y, equation = _hard_ode()
    monkeypatch.setattr("symkit.domain.dsolve_ics.DSOLVE_ICS_OPS_CAP", 0)
    solution, reason = dsolve_with_ics(equation, y, t, _hard_ics(t, y))
    assert solution is not None
    assert reason is not None
    assert "bound" in reason and "wedge" in reason
    assert DSOLVE_ICS_OPS_CAP > 0


def test_nonlinear_in_constants_falls_back_to_sympy() -> None:
    t = sp.Symbol("t")
    y = sp.Function("y")
    equation = sp.Eq(sp.Derivative(y(t), t), y(t) ** 2)
    solution, reason = dsolve_with_ics(equation, y, t, {y(0): sp.Integer(1)})
    assert reason is None
    assert sp.simplify(solution.rhs - 1 / (1 - t)) == 0


def test_engine_dsolve_with_ics_returns_and_is_valid() -> None:
    engine = SymPyEngine()
    ode = engine.parse(
        "Derivative(y(t),(t,3)) - 7*Derivative(y(t),(t,2)) + 16*Derivative(y(t),t)"
        " - 13*y(t)",
        None,
    )
    assert ode.is_valid, ode.error
    t = sp.Symbol("t")
    y = sp.Function("y")
    out = _run_bounded(
        lambda: engine.dsolve(ode, "y", "t", None, ics=_hard_ics(t, y))
    )
    assert out is not _TIMED_OUT, "engine.dsolve wedged on the r18 A1 ODE"
    assert out.is_valid, out.error

"""r18 A3: ``evalf`` with a large-integer substitution must evaluate numerically.

``math("evalf", "(1 + 1/n)**n", substitution={"n": "1000000"})`` never returns
(>60 s): the dispatcher substitutes exactly first, building
``(1000001/1000000)**1000000`` -- a ~6-million-digit rational -- and ``evalf``
then spins on it.  Large integer substitutions are evaluated through
``evalf(subs=...)`` instead.  Integer substitutions up to 10**4, float
substitutions and every previously working case keep their exact-route values.
"""

from __future__ import annotations

import threading
from typing import Any

import sympy as sp

from symkit.infrastructure.numeric_eval import numeric_evalf
from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

_HANG_TIMEOUT = 30.0
_TIMED_OUT = object()


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools


def _run_bounded(func: Any, timeout: float = _HANG_TIMEOUT) -> Any:
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


def test_numeric_evalf_accepts_a_large_integer_substitution() -> None:
    n = sp.Symbol("n")
    value, _warnings = numeric_evalf((1 + 1 / n) ** n, {n: sp.Integer(10**6)})
    assert abs(float(value) - 2.71828046931938) < 1e-9


def test_boundary_integer_values_match_the_exact_route() -> None:
    n = sp.Symbol("n")
    expr = (1 + 1 / n) ** n
    for k in (10**3, 10**4, 10**5):
        expected = expr.subs({n: sp.Integer(k)}).doit().evalf()
        got, _warnings = numeric_evalf(expr, {n: sp.Integer(k)})
        assert str(got) == str(expected), (k, got, expected)


def test_evalf_large_integer_substitution_returns_promptly() -> None:
    tools = _tools()
    out = _run_bounded(
        lambda: tools["math"](
            operation="evalf",
            expression="(1 + 1/n)**n",
            substitution={"n": "1000000"},
            session=False,
        )
    )
    assert out is not _TIMED_OUT, "evalf wedged on the n=10**6 substitution"
    assert out["success"], out
    assert abs(float(out["expression"]) - 2.71828046931938) < 1e-9


def test_required_boundary_value_is_unchanged() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="(1 + 1/n)**n",
        substitution={"n": "100000"},
        session=False,
    )
    assert out["success"], out
    assert out["expression"] == "2.71826823717449"


def test_float_control_value_is_unchanged() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="(1 + 1/n)**n",
        substitution={"n": "1000000.0"},
        session=False,
    )
    assert out["success"], out
    assert out["expression"] == "2.71828046909575"


def test_existing_substitution_case_is_unchanged() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="sqrt(2*g*m/(rho*C_d*A))",
        substitution={"m": 1, "g": 9.81, "rho": 1.225, "C_d": 0.47, "A": 0.5},
        session=False,
    )
    assert out["success"], out
    assert out["expression"] == "8.25557877930607"


def test_malformed_substitution_still_errors() -> None:
    out = _tools()["math"](
        operation="evalf",
        expression="x",
        substitution={"x": "("},
        session=False,
    )
    assert not out["success"]

"""Nested definite integrals must never come back with a spurious variable.

r15 task-07: ``math(integrate, "Integral(sigma_*y**2, (y, ±..., ), (x, -R, R))")``
returned ``success:true`` with ``pi*R**4*sigma_*x/4`` — a fabricated factor
``x`` — because the engine re-integrated an already-definite integral over its
own bound variable. The value must be correct or the call must fail
structurally, never silently return a result carrying a free variable that was
not free in the input.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit_mcp.tools import math as math_tools

# MockMCP is provided by conftest.py

_NESTED = (
    "Integral(sigma_*y**2, (y, -sqrt(R**2-x**2), sqrt(R**2-x**2)), (x, -R, R))"
)


def _math_tool() -> Any:
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_nested_definite_integral_returns_the_correct_value() -> None:
    result = _math_tool()(
        "integrate",
        _NESTED,
        assumptions=["R positive", "sigma_ positive"],
        session=False,
    )
    assert result["success"] is True, result
    assert result["expression"] == "pi*R**4*sigma_/4", result


def test_nested_definite_integral_never_returns_a_pseudo_variable() -> None:
    result = _math_tool()("integrate", _NESTED, session=False)
    if result["success"]:
        value = sp.sympify(result["expression"])
        # ``x`` was a bound variable, so it must not leak out as free.
        assert not value.has(sp.Symbol("x")), result
    else:
        # Without assumptions SymPy may not produce a closed form; then the
        # call must fail loud rather than hand back a wrong expression.
        assert result.get("error")
        assert "integral" in result["error"].lower()

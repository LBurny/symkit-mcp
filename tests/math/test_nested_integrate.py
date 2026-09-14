"""r16 task-06: an inline nested integral must return its exact value, not ×x.

The parser evaluates ``integrate(integrate(f, (y, ...)), (x, ...))`` through
SymPy's own ``integrate``; the dispatcher then re-integrated that already
evaluated constant in the default variable and silently returned the correct
value multiplied by ``x`` (``pi*R**4*sigma/2`` -> ``pi*R**4*sigma*x/2``).
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit_mcp.tools import math as math_tools

# MockMCP is provided by conftest.py

_CASES = (
    ("integrate(integrate(sigma*r**3, (r,0,R)), (theta,0,2*pi))", "pi*R**4*sigma/2"),
    ("integrate(integrate(1, (x,0,1)), (y,0,1))", "1"),
    ("integrate(integrate(x, (x,0,1)), (y,0,1))", "1/2"),
    ("integrate(integrate(1, (x,0,1)), (theta,0,2*pi))", "2*pi"),
    ("integrate(integrate(6*x**2*y, (y,0,1)), (x,0,1))", "1"),
    ("integrate(integrate(6*x**3*y**2, (y,0,1)), (x,0,1))", "1/2"),
    ("integrate(integrate(6*x**2*y, (x,0,1)), (y,0,1))", "1"),
)


def _math_tool() -> Any:
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_inline_nested_integrals_return_exact_values() -> None:
    math = _math_tool()
    for expression, expected in _CASES:
        result = math("integrate", expression, session=False)
        assert result["success"] is True, result
        assert result["expression"] == expected, (expression, result)


def test_inline_nested_integral_has_no_spurious_free_variable() -> None:
    math = _math_tool()
    result = math(
        "integrate",
        "integrate(integrate(6*x**2*y, (y,0,1)), (x,0,1))",
        session=False,
    )
    value = sp.sympify(result["expression"])
    assert value.free_symbols == set(), result


def test_integral_object_form_unchanged() -> None:
    math = _math_tool()
    result = math("integrate", "Integral(x**2, (x,0,1))", session=False)
    assert result["success"] is True, result
    assert result["expression"] == "1/3", result


def test_outer_limits_parameter_form_unchanged() -> None:
    math = _math_tool()
    result = math(
        "integrate",
        "integrate(6*x**2*y, (y,0,1))",
        variable="x",
        lower="0",
        upper="1",
        session=False,
    )
    assert result["success"] is True, result
    assert result["expression"] == "1", result


def test_unresolvable_inline_integral_fails_loud() -> None:
    math = _math_tool()
    result = math("integrate", "Integral(x**x, x)", session=False)
    assert result["success"] is False, result
    assert "integral" in result["error"].lower(), result

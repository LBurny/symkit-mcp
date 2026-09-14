"""``limit`` must evaluate embedded derivatives, never treat them as constants.

r15 task-01: ``math(limit, "diff((x**2 - 1)**2, x, 2)/x**2", x, oo)`` returned
``0`` because the unevaluated ``Derivative`` was treated as a constant in ``x``.
The true value is ``12``. An expression whose derivatives/integrals cannot be
evaluated must fail structurally, not silently return a wrong constant.
"""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools

# MockMCP is provided by conftest.py


def _math_tool() -> Any:
    # ruff: noqa: F821  # MockMCP from conftest.py
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_limit_evaluates_an_embedded_derivative() -> None:
    result = _math_tool()(
        "limit",
        "diff((x**2 - 1)**2, x, 2)/x**2",
        variable="x",
        point="oo",
        session=False,
    )
    assert result["success"] is True, result
    assert result["expression"] == "12", result


def test_limit_does_not_treat_an_embedded_derivative_as_constant() -> None:
    result = _math_tool()(
        "limit",
        "diff((x**2 - 1)**2, x, 2)/x**2",
        variable="x",
        point="oo",
        session=False,
    )
    assert result.get("expression") != "0", result


def test_unevaluable_derivative_gives_a_structured_error() -> None:
    result = _math_tool()(
        "limit", "diff(f(x), x)", variable="x", point="oo", session=False
    )
    assert result["success"] is False, result
    assert "derivative" in result["error"].lower()


def test_plain_limit_still_works() -> None:
    result = _math_tool()(
        "limit", "sin(x)/x", variable="x", point="0", session=False
    )
    assert result["success"] is True, result
    assert result["expression"] == "1", result

"""``Matrix(...)**n`` must evaluate (or fail loud) through ``math()``.

r14 black-box (task-05): ``Matrix(...)**2`` / ``**-1`` inside a compound
expression killed the whole call with an uncaught
``TypeError: unsupported operand type(s) for +: 'ImmutableDenseMatrix' and 'int'``.
The parser left ``Matrix**n`` as an unevaluated ``Pow``; ``simplify`` then
touched ``base - 1`` while probing assumptions and crashed.  Integer matrix
powers are now folded during parsing.
"""

from __future__ import annotations

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools

B = "Matrix([[1,2],[3,4]])"


def _math():
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_matrix_square_evaluates() -> None:
    result = _math()("simplify", f"{B}**2", session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.Matrix([[7, 10], [15, 22]])


def test_matrix_negative_power_is_the_inverse() -> None:
    result = _math()("simplify", f"{B}**-1", session=False)

    assert result["success"] is True, result
    got = sp.sympify(result["expression"])
    assert got == sp.Matrix([[1, 2], [3, 4]]).inv()
    assert sp.simplify(got - sp.Matrix([[1, 2], [3, 4]]).inv()) == sp.zeros(2, 2)


def test_matrix_power_difference_does_not_crash() -> None:
    """The exact shape that crashed: two ``**-1`` terms subtracted."""
    expr = f"{B}**-1 - Matrix([[2,1],[1,3]])**-1"
    result = _math()("simplify", expr, session=False)

    assert result["success"] is True, result


def test_cayley_hamilton_power_residual_is_zero_matrix() -> None:
    expr = f"{B}**2 - 5*{B} - 2*Matrix([[1,0],[0,1]])"
    result = _math()("simplify", expr, session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.zeros(2, 2)


def test_non_square_matrix_power_is_structured_error() -> None:
    """An unsupported power must return success:false, never raise."""
    result = _math()("simplify", "Matrix([[1,2,3],[4,5,6]])**2", session=False)

    assert result["success"] is False
    assert result.get("error")

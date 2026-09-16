"""Matrix operations through ``math()``: inv chains, powers, evalf, list literals.

Merged from four micro files that each pinned one matrix-op defect:

- Nested attribute calls (``Matrix(...).inv()``) — r14 black-box (task-05): a
  lone chain parsed, but inside a compound expression the parser died with
  ``Cannot parse: 'Attribute' object has no attribute 'id'`` (an internal SymPy
  ``EvaluateFalseTransformer`` bug); attribute chains have no unevaluated form,
  so the parser retries with normal evaluation.
- ``Matrix(...)**n`` — r14 black-box (task-05): compound integer powers killed
  the call with ``TypeError: unsupported operand type(s) for +:
  'ImmutableDenseMatrix' and 'int'`` because the parser left the power
  unevaluated; integer matrix powers are now folded during parsing.
- ``evalf`` on symbolic matrix expressions — ``MatAdd`` kept the ``Identity``
  term unabsorbed and ``.evalf()`` recursed on it (2026-09-12 pure-formula
  round); expanding with ``as_explicit()`` collapses the term.
- List literals — 2026-09-14: ``evalf("[1/1.168, 2+2]")`` died with
  ``'list' object has no attribute 'evalf'``; the parser turns bracket
  literals into matrices so the tool answers instead of leaking.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools

A = "Matrix([[1,2,3],[4,5,6],[7,8,10]])"
B = "Matrix([[1,2],[3,4]])"
C = "Matrix([[2,1],[1,3]])"

# (B*C)^-1 - C^-1 * B^-1 must be the zero matrix.
NESTED_INV_DIFFERENCE = f"({B}*{C}).inv() - {C}.inv()*{B}.inv()"


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_nested_inv_inside_simplify_expression() -> None:
    result = _math()("simplify", NESTED_INV_DIFFERENCE, session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.zeros(2, 2)


def test_nested_inv_inside_evalf() -> None:
    result = _math()("evalf", f"{B}.inv()", session=False)

    assert result["success"] is True, result
    got = sp.sympify(result["expression"])
    assert got == sp.Matrix([[1, 2], [3, 4]]).inv().evalf()


def test_nested_inv_inside_det() -> None:
    result = _math()("det", f"{B}.inv()", session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.Rational(-1, 2)


def test_inv_method_call_times_matrix() -> None:
    result = _math()("simplify", f"{B}.inv()*{B}", session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.eye(2)


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
    expr = f"{B}**-1 - {C}**-1"
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


class TestEvalfMatrixExpressions:
    def test_identity_term_does_not_crash(self):
        result = _math()(
            operation="evalf",
            expression=f"{A}*{A} - 16*{A} + 3*Identity(3)",
        )

        assert result["success"] is True, result
        assert "17." in result["expression"] or "17" in result["expression"]

    def test_cayley_hamilton_residual_is_the_zero_matrix(self):
        result = _math()(
            operation="evalf",
            expression=f"{A}*{A}*{A} - 16*{A}*{A} - 12*{A} + 3*Identity(3)",
        )

        assert result["success"] is True, result
        assert "0" in result["expression"]
        assert "17" not in result["expression"]

    def test_plain_matrix_arithmetic_still_evaluates(self):
        result = _math()(operation="evalf", expression=f"{A}*{A}")

        assert result["success"] is True
        assert "30." in result["expression"]


class TestListLiteralToolSurface:
    def test_evalf_flat_list(self) -> None:
        result = _math()("evalf", "[1/1.168, 2+2]", session=False)
        assert result["success"] is True, result

    def test_simplify_flat_list(self) -> None:
        result = _math()("simplify", "[1/1.168, 2+2]", session=False)
        assert result["success"] is True, result

    def test_evalf_matrix_grid(self) -> None:
        result = _math()("evalf", "[[1, 2], [3, 4]]", session=False)
        assert result["success"] is True, result

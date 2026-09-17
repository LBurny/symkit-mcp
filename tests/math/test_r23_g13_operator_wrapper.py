"""G13: the operation name repeated inside its own expression (r23 acceptance re-run).

A client that writes ``operation="det"`` together with
``expression="det(Matrix([[...]]))"`` sent the same operation twice: the parser
already applied the call, and the request then applied the operation to its own
result.  ``det`` crashed with a leaked ``TypeError: Data type not understood``;
``diff`` silently returned the second derivative; ``eigenvals`` silently returned
nothing.  The wrapper is now stripped, and a non-matrix operand for a matrix
operation is refused with an actionable message instead of the SymPy TypeError.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools._operator_input import normalize_operator_input


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


class TestRedundantWrapperDet:
    def test_det_wrapper_is_not_applied_twice(self) -> None:
        """The operator's verbatim failing call (r23 task-04 step 1)."""
        result = _math()(
            "det",
            "det(Matrix([[1 - lam, 1], [1, -lam]]))",
            session=False,
        )

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == sp.Symbol("lam") ** 2 - sp.Symbol("lam") - 1

    def test_det_of_row_grid_wrapper(self) -> None:
        result = _math()("det", "det([[1, 2], [3, 4]])", session=False)

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == -2

    def test_det_without_wrapper_still_evaluates(self) -> None:
        result = _math()("det", "[[1, 2], [3, 4]]", session=False)

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == -2


class TestRedundantWrapperOtherOps:
    def test_diff_wrapper_yields_first_derivative(self) -> None:
        """``diff(x**3)`` used to return the second derivative (6*x)."""
        result = _math()("diff", "diff(x**3)", session=False)

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == 3 * sp.Symbol("x") ** 2

    def test_diff_wrapper_carries_the_variable(self) -> None:
        """``diff(sin(t), t)`` used to return -sin(t) (derivative wrt x)."""
        result = _math()("diff", "diff(sin(t), t)", session=False)

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == sp.cos(sp.Symbol("t"))

    def test_eigenvals_wrapper_is_not_emptied(self) -> None:
        """``eigenvals(Matrix(...))`` used to return an empty tuple."""
        result = _math()("eigenvals", "eigenvals(Matrix([[2, 1], [1, 2]]))", session=False)

        assert result["success"] is True, result
        assert "3" in result["expression"]

    def test_inv_wrapper_is_not_double_inverted(self) -> None:
        """Inverting an already-inverted matrix used to return the input."""
        result = _math()("inv", "inv(Matrix([[2, 1], [1, 3]]))", session=False)

        assert result["success"] is True, result
        assert sp.Matrix(sp.sympify(result["expression"])) == sp.Matrix(
            [[sp.Rational(3, 5), sp.Rational(-1, 5)], [sp.Rational(-1, 5), sp.Rational(2, 5)]]
        )


class TestWrapperPassthrough:
    def test_call_inside_a_larger_expression_is_untouched(self) -> None:
        """Only a whole-expression call is the redundant-wrapper shape."""
        result = _math()("simplify", "det([[1, 2], [3, 4]]) + x", session=False)

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == sp.Symbol("x") - 2

    def test_multi_argument_call_is_left_to_the_parser(self) -> None:
        """``integrate(x**2, x)`` keeps its own variable and evaluates."""
        result = _math()("integrate", "integrate(x**2, x)", session=False)

        assert result["success"] is True, result
        assert sp.sympify(result["expression"]) == sp.Symbol("x") ** 3 / 3


class TestNonMatrixOperandMessage:
    def test_det_of_scalar_reports_the_expected_input(self) -> None:
        result = _math()("det", "x + 1", session=False)

        assert result["success"] is False
        assert "expects a matrix" in result["error"]
        assert "Matrix([[" in result["error"]
        assert "Data type not understood" not in result["error"]

    def test_eigenvals_of_scalar_reports_the_expected_input(self) -> None:
        result = _math()("eigenvals", "x + 1", session=False)

        assert result["success"] is False
        assert "expects a matrix" in result["error"]


class TestWrapperScanner:
    """The scanner must only fire on a call that wraps the entire expression."""

    def test_trailing_text_is_not_a_wrapper(self) -> None:
        assert normalize_operator_input("det", "det(x) + 1", None) == ("det(x) + 1", None)

    def test_trailing_whitespace_still_wraps(self) -> None:
        assert normalize_operator_input("det", "  det( x )  ", None) == ("x", None)

    def test_nested_call_is_found_as_one_argument(self) -> None:
        text = "det(Matrix([[1 - lam, 1], [1, -lam]]))"
        assert normalize_operator_input("det", text, None) == (
            "Matrix([[1 - lam, 1], [1, -lam]])",
            None,
        )

    def test_different_operation_name_is_untouched(self) -> None:
        assert normalize_operator_input("det", "inv(M)", None) == ("inv(M)", None)

    def test_two_arguments_without_a_bare_tail_pass_through(self) -> None:
        text = "diff(sin(x), x + 1)"
        assert normalize_operator_input("diff", text, None) == (text, None)

    def test_unbalanced_parenthesis_passes_through(self) -> None:
        assert normalize_operator_input("det", "det(x", None) == ("det(x", None)

    def test_explicit_variable_wins_over_the_call_tail(self) -> None:
        assert normalize_operator_input("diff", "diff(sin(t), t)", "x") == ("sin(t)", "x")

    def test_non_string_input_passes_through(self) -> None:
        payload = {"srepr": "Symbol('x')"}
        assert normalize_operator_input("det", payload, None) == (payload, None)


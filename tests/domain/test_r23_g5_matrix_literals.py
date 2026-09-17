"""r23 acceptance G5: ``[[...]]`` matrix literals must parse at every entry.

SymPy's parser turns a bracket list into a Python list only when the literal is
the *whole* expression; embedded in a larger expression (``[[..]]**-1 * [[..]]``)
or on an ``Eq`` side (``M = [[..]]``) the list reaches ``sympify`` and dies with
``SympifyError``.  The parser now normalizes a top-level row-grid literal to the
``Matrix([...])`` constructor, so ``det``, ``simplify`` and
``session_record_step`` see the exact same syntax.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.expr_repair import normalize_matrix_literals
from symkit.domain.expression_parser import parse_expression_string


class TestNormalizeMatrixLiteralsUnit:
    def test_grid_becomes_matrix_constructor(self) -> None:
        assert normalize_matrix_literals("[[1,2],[3,4]]") == "Matrix([[1,2],[3,4]])"

    def test_embedded_literals_both_rewritten(self) -> None:
        got = normalize_matrix_literals("[[1,2],[3,4]]**-1 * [[1,1],[1,0]]")
        assert got == "Matrix([[1,2],[3,4]])**-1 * Matrix([[1,1],[1,0]])"

    def test_existing_matrix_constructor_is_not_double_wrapped(self) -> None:
        src = "Matrix([[1,2],[3,4]])**-1 * Matrix([[1,1],[1,0]])"
        assert normalize_matrix_literals(src) == src
        spaced = "Matrix( [[1,2],[3,4]] )"
        assert normalize_matrix_literals(spaced) == spaced

    def test_flat_list_untouched(self) -> None:
        assert normalize_matrix_literals("[1,2,3]") == "[1,2,3]"

    def test_symbolic_rows_rewritten(self) -> None:
        assert (
            normalize_matrix_literals("[[a, b], [c, d]]")
            == "Matrix([[a, b], [c, d]])"
        )

    def test_empty_literal_raises_clear_error(self) -> None:
        try:
            normalize_matrix_literals("[]")
        except ValueError as exc:
            assert "empty" in str(exc).lower()
        else:  # pragma: no cover
            raise AssertionError("expected ValueError for an empty list literal")

    def test_jagged_literal_raises_clear_error(self) -> None:
        try:
            normalize_matrix_literals("[[1,2],[3]]")
        except ValueError as exc:
            assert "row" in str(exc).lower()
        else:  # pragma: no cover
            raise AssertionError("expected ValueError for a jagged list literal")


class TestParseEntryPoints:
    def test_embedded_grid_product_parses(self) -> None:
        expr, error = parse_expression_string(
            "[[1, 2], [3, 4]]**-1 * [[1, 1], [1, 0]]"
        )
        assert error is None, error
        assert sp.Matrix(expr) == sp.Matrix([[-1, -2], [1, sp.Rational(3, 2)]])

    def test_embedded_grid_matches_matrix_constructor_verbatim(self) -> None:
        bracket, bracket_err = parse_expression_string(
            "[[1, 2], [3, 4]]**-1 * [[1, 1], [1, 0]]"
        )
        ctor, ctor_err = parse_expression_string(
            "Matrix([[1, 2], [3, 4]])**-1 * Matrix([[1, 1], [1, 0]])"
        )
        assert bracket_err is None and ctor_err is None
        assert sp.srepr(bracket) == sp.srepr(ctor)

    def test_definition_with_matrix_rhs_parses(self) -> None:
        expr, error = parse_expression_string("M = [[1,1],[1,0]]")
        ctor, ctor_err = parse_expression_string("M = Matrix([[1,1],[1,0]])")
        # A bare symbol never equals a concrete matrix, so SymPy folds the Eq
        # to False (both spellings); the recorded-claim layer rebuilds it.
        assert error is None and ctor_err is None
        assert sp.srepr(expr) == sp.srepr(ctor)
        assert expr is sp.false

    def test_symbolic_grid_parses(self) -> None:
        expr, error = parse_expression_string("[[1-L,1],[1,-L]]")
        assert error is None, error
        assert isinstance(expr, sp.MatrixBase)

    def test_bare_grid_still_a_matrix(self) -> None:
        expr, error = parse_expression_string("[[1, 2], [3, 4]]")
        assert error is None, error
        assert isinstance(expr, sp.MatrixBase)
        assert expr.shape == (2, 2)

    def test_flat_list_is_still_column_matrix(self) -> None:
        expr, error = parse_expression_string("[1, 2, 3]")
        assert error is None, error
        assert isinstance(expr, sp.MatrixBase)
        assert expr.shape == (3, 1)

    def test_comma_tuple_guard_unchanged(self) -> None:
        expr, error = parse_expression_string("x + y, z")
        assert error is None, error
        assert isinstance(expr, tuple)

    def test_empty_literal_returns_error_not_exception(self) -> None:
        expr, error = parse_expression_string("[]")
        assert expr is None
        assert error is not None
        assert "empty" in error.lower()

    def test_jagged_literal_returns_clear_error(self) -> None:
        expr, error = parse_expression_string("[[1,2],[3]]")
        assert expr is None
        assert error is not None
        assert "row" in error.lower()

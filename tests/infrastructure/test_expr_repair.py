"""Regression tests for the r23 parser repairs (F1, F2, F3).

- F1: ``evaluate=False`` distributed ``Pow(Matrix, -1)`` element-wise over a
  right-hand matrix (a "block broadcast"): ``Matrix(A)**-1 * Matrix(B)`` and a
  symbolic ``P**-1 * M * P``.  Matrices are eager, so a matrix-touched parse is
  redone with normal evaluation.
- F2: ``inv`` is not a SymPy name, so ``inv(Matrix)`` stayed a symbolic
  undefined function; concrete matrix arguments are evaluated, symbolic ones
  keep their undefined-function semantics.
- F3: ``numeric_evalf`` crashed on a Python tuple (``(1/2, 1/3)``).
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.expression_parser import parse_expression_string
from symkit.infrastructure.numeric_eval import numeric_evalf


class TestMatrixProductF1:
    def test_concrete_matrix_quotient_is_true_multiplication(self) -> None:
        expr, error = parse_expression_string(
            "Matrix([[1, 2], [3, 4]])**-1 * Matrix([[1, 1], [1, 0]])"
        )

        assert error is None
        assert sp.Matrix(expr) == sp.Matrix([[-1, -2], [1, sp.Rational(3, 2)]])

    def test_symbolic_matrix_bindings_multiply(self) -> None:
        phi, psi = sp.symbols("phi psi")
        p_mat = sp.Matrix([[phi, psi], [1, 1]])
        m_mat = sp.Matrix([[1, 1], [1, 0]])

        expr, error = parse_expression_string(
            "P**-1 * M * P", local_dict={"P": p_mat, "M": m_mat}
        )

        assert error is None
        residual = sp.Matrix(expr) - p_mat.inv() * m_mat * p_mat
        assert sp.simplify(residual) == sp.zeros(2, 2)

    def test_symbolic_product_is_diagonal_at_eigenvalues(self) -> None:
        phi, psi = sp.symbols("phi psi")
        p_mat = sp.Matrix([[phi, psi], [1, 1]])
        m_mat = sp.Matrix([[1, 1], [1, 0]])

        expr, error = parse_expression_string(
            "P**-1 * M * P", local_dict={"P": p_mat, "M": m_mat}
        )

        assert error is None
        values = {phi: (1 + sp.sqrt(5)) / 2, psi: (1 - sp.sqrt(5)) / 2}
        got = sp.simplify(sp.Matrix(expr).subs(values))
        assert got == sp.diag(values[phi], values[psi])

    def test_integer_matrix_power_unchanged(self) -> None:
        expr, error = parse_expression_string("Matrix([[1, 1], [1, 0]])**5")

        assert error is None
        assert sp.Matrix(expr) == sp.Matrix([[8, 5], [5, 3]])


class TestInvRepairF2:
    def test_inv_of_concrete_matrix_evaluates(self) -> None:
        expr, error = parse_expression_string("inv(Matrix([[2, 1], [1, 3]]))")

        assert error is None
        assert sp.Matrix(expr) == sp.Matrix([[2, 1], [1, 3]]).inv()

    def test_nested_inv_returns_the_original_matrix(self) -> None:
        expr, error = parse_expression_string("inv(inv(Matrix([[2, 1], [1, 3]])))")

        assert error is None
        assert sp.Matrix(expr) == sp.Matrix([[2, 1], [1, 3]])

    def test_symbolic_inv_keeps_undefined_function_semantics(self) -> None:
        expr, error = parse_expression_string("inv(x)")

        assert error is None
        assert str(expr) == "inv(x)"


class TestNumericEvalfTupleF3:
    def test_tuple_is_evaluated_element_wise(self) -> None:
        value, warnings = numeric_evalf((sp.Rational(1, 2), sp.Rational(1, 3)))

        assert warnings == []
        assert isinstance(value, sp.Tuple)
        assert float(value[0]) == 0.5
        assert abs(float(value[1]) - 1 / 3) < 1e-12

    def test_list_is_evaluated_element_wise(self) -> None:
        value, warnings = numeric_evalf([sp.pi, sp.Rational(1, 4)])

        assert warnings == []
        assert isinstance(value, sp.Tuple)
        assert abs(float(value[0]) - 3.14159265) < 1e-6

"""Verification of differentiation-to-constant and matrix-valued steps.

Both defects come from the 2026-09-12 pure-formula black-box round
(`symkit-mcp-test-pure`):

* A derivative that lands on a *non-zero constant* was rejected outright.
  ``diff(2*x, x) = 2`` is correct -- reverse integration gives
  ``integral(2, x) = 2*x``, which is the input -- yet the verifier short-circuited
  before that check and reported FAILED. Five such steps turned task-04's whole
  chain into ``overall: failed``.
* ``is_numerically_zero`` only understood scalars, so a matrix step whose
  difference was literally the zero matrix was reported as changing the
  expression. Matrix-valued steps could never pass.
"""

from __future__ import annotations

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.step_verifier import StepVerifier, is_numerically_zero
from symkit.domain.value_objects import VerificationStatus


def _step(operation: OperationType, original: str, output: str, command: str = "") -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="verification under test",
        input_expressions={"original": original},
        output_expression=output,
        output_latex=output,
        sympy_command=command,
    )


class TestDerivativeReachingAConstant:
    """Reverse integration must get to decide, not a free-symbol shortcut."""

    def test_derivative_of_linear_term_is_verified(self):
        step = _step(OperationType.DIFFERENTIATE, "2*x", "2", "diff(expr, x)")

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.VERIFIED, result.message

    def test_second_derivative_reaching_a_constant_is_verified(self):
        step = _step(
            OperationType.DIFFERENTIATE, "x**2", "2", "diff(expr, x, 2)"
        )

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.VERIFIED, result.message

    def test_derivative_of_a_constant_still_verifies(self):
        step = _step(OperationType.DIFFERENTIATE, "5", "0", "diff(expr, x)")

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.VERIFIED, result.message

    def test_wrong_constant_derivative_still_fails(self):
        step = _step(OperationType.DIFFERENTIATE, "2*x", "3", "diff(expr, x)")

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is not VerificationStatus.VERIFIED


class TestMatrixValuedSteps:
    """A zero-matrix difference is still zero."""

    def test_zero_matrix_is_numerically_zero(self):
        import sympy as sp

        assert is_numerically_zero(sp.zeros(2, 2)) is True
        assert is_numerically_zero(sp.Matrix([[1, 0], [0, 0]])) is False

    def test_symbolic_matrix_expression_that_is_zero(self):
        import sympy as sp

        a = sp.Matrix([[1, 2], [3, 4]])

        assert is_numerically_zero(sp.expand(a - a)) is True

    def test_identity_substitution_step_verifies(self):
        step = _step(
            OperationType.SIMPLIFY,
            "Matrix([[1, 2], [3, 4]])",
            "Matrix([[1, 2], [3, 4]])",
        )

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.VERIFIED, result.message

    def test_changed_matrix_still_fails(self):
        step = _step(
            OperationType.SIMPLIFY,
            "Matrix([[1, 2], [3, 4]])",
            "Matrix([[1, 2], [3, 5]])",
        )

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.FAILED

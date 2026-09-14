"""Regression tests for the simplify/expand ``suspect_identity`` semantics.

Black-box round 14 (task-11): the per-step verifier only checked operator
fidelity — that ``simplify``/``expand`` faithfully rewrote its recorded input —
so a recorded difference ``A - B`` whose simplification came out nonzero
(``-8*sin(x)**4 + 6*sin(x)**2``, or the probe residual ``-2``) was still
stamped ``verified: expressions are equal`` and read as "this step is
mathematically correct".

Black-box round 15 (task-13) split that flag in two, and round 16 (task-08)
corrected the polarity further: an operator step over a *plain* difference form
(``A - B``, not an ``Eq``) never asserts an identity — the user may just be
asking for a simplification — so it must never be graded ``"numeric"``/FALSE.
Such steps carry only ``suspect_identity == "unreduced"`` (the difference did
not reduce to zero; unproven, not disproven) and keep ``status: verified``.  A
false identity is confirmed only through an explicit equation assertion (see
``test_step_verifier_eq_content.py``), where it FAILS the step.

The difference detection is deliberately conservative: an ordinary sum
(``x**2 + x``, ``x**2 - 1``), a difference whose negated term is a bare symbol
or a pure number, and a faithfully simplified arithmetic expression must never
be marked suspect.
"""

from __future__ import annotations

import pytest

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


@pytest.fixture
def verifier():
    return StepVerifier()


def _make_step(
    operation: OperationType,
    input_expression: str,
    output_expression: str,
    sympy_command: str = "",
) -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="suspect-identity test step",
        input_expressions={"original": input_expression},
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command=sympy_command,
    )


def _make_archived_step(
    operation: OperationType,
    input_expression: str,
    output_expression: str,
) -> DerivationStep:
    """Mirror the live recorder: ``input_srepr`` carries the live parsed input."""
    import sympy as sp

    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    output, _ = parse_expression_string(output_expression, convert_equation=True)
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="archived suspect-identity test step",
        input_expressions={"original": str(parsed)},
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command="",
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(output),
    )


class TestSuspectIdentity:
    def test_nonzero_residual_on_difference_is_unreduced_not_false(self, verifier):
        # task-11 E2: cos(2x) = 1 - 2*sin(2x)**2 is false; the faithful
        # simplification is the nonzero residual -8 sin^4 x + 6 sin^2 x.  A
        # plain difference form is not an asserted identity, so the verdict is
        # "unreduced" and never "the identity is FALSE" (task-08 W1).
        step = _make_step(
            OperationType.SIMPLIFY,
            "cos(2*x) - (1 - 2*sin(2*x)**2)",
            "-8*sin(x)**4 + 6*sin(x)**2",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED  # polarity unchanged
        assert result.details.get("suspect_identity") == "unreduced"
        assert "asserted identity is FALSE" not in result.message
        assert "did not reduce to zero" in result.message
        assert "matches the recomputed operator result" in result.message

    def test_false_identity_residual_minus_two_is_unreduced(self, verifier):
        # task-11 probe: cos(4x) - (8 sin^4 - 8 sin^2 + 3) simplifies to -2.
        step = _make_step(
            OperationType.SIMPLIFY,
            "cos(4*x) - (8*sin(x)**4 - 8*sin(x)**2 + 3)",
            "-2",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "asserted identity is FALSE" not in result.message

    def test_zero_residual_on_difference_is_not_suspect(self, verifier):
        # cos(2x) = cos^2 x - sin^2 x is a true identity: output 0.
        step = _make_step(
            OperationType.SIMPLIFY,
            "cos(2*x) - (cos(x)**2 - sin(x)**2)",
            "0",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details
        assert result.message.endswith("output matches the recomputed operator result")

    def test_expand_nonzero_difference_is_unreduced(self, verifier):
        step = _make_step(
            OperationType.EXPAND,
            "(x + y)**2 - x**2 - y**2",
            "2*x*y",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "asserted identity is FALSE" not in result.message

    def test_surd_difference_is_unreduced(self, verifier):
        # task-13 #6: sqrt(a^2 + b^2) = a + b is false (a=3, b=4 -> -2), but a
        # plain difference form cannot assert that; the verdict is unproven.
        step = _make_step(
            OperationType.SIMPLIFY,
            "sqrt(a**2 + b**2) - (a + b)",
            "-a - b + sqrt(a**2 + b**2)",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "asserted identity is FALSE" not in result.message

    def test_unevaluated_derivative_difference_is_unreduced(self, verifier):
        # task-02/13: the residual is symbolically nonzero only because the
        # Derivative never evaluated; substitution cannot sample f(2), so the
        # verdict must be "unproven, not disproven" — never FALSE.
        step = _make_step(
            OperationType.SIMPLIFY,
            "Derivative(f(x), x) - cos(x)",
            "Derivative(f(x), x) - cos(x)",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "unproven, not disproven" in result.message
        assert "FALSE" not in result.message

    def test_euler_alias_difference_is_not_marked(self, verifier):
        # task-03 step 64: the parser protects ``E`` as a symbol, so the literal
        # expression is -E + e.  The negated term is a bare symbol: the verifier
        # cannot call this a false identity, and it must not.
        step = _make_step(
            OperationType.SIMPLIFY, "-E + exp(1)", "-E + exp(1)"
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert "suspect_identity" not in result.details
        assert "FALSE" not in result.message

    def test_leading_negative_term_is_not_a_difference_form(self, verifier):
        # round-lean task-02 W-1: ``-x**2 + x*(x + 1)`` simplifies to ``x``; the
        # residual is identically zero, yet the recorded form was read as an
        # asserted difference (a *leading* negated compound) and the verifier
        # emitted "the difference did not reduce to zero ... numerically nonzero
        # at tested points" — both assertions false for a correct step.  A
        # difference claim has a non-negative operand *before* the negated one;
        # a leading negative is ordinary algebra.
        step = _make_archived_step(
            OperationType.SIMPLIFY, "-x**2 + x*(x + 1)", "x"
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details
        assert "did not reduce to zero" not in result.message
        assert result.message.endswith("output matches the recomputed operator result")

    def test_numeric_arithmetic_difference_is_not_marked(self, verifier):
        # task-06 step 9: 6x*6y - 1*(-3)^2 -> 36xy - 9 is a faithful
        # simplification, not a proposition.  The negated term is purely
        # numeric, so it must not be read as an identity claim.
        step = _make_archived_step(
            OperationType.SIMPLIFY,
            "6*x*6*y - 1*(-3)**2",
            "36*x*y - 9",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details

    @pytest.mark.parametrize(
        "input_expression, output_expression",
        [
            ("x**2 + x", "x*(x + 1)"),
            ("x**2 + 1", "x**2 + 1"),
            ("x**2 - 1", "(x - 1)*(x + 1)"),
            ("2*x + 1", "2*x + 1"),
        ],
    )
    def test_non_difference_forms_are_not_marked(
        self, verifier, input_expression, output_expression
    ):
        step = _make_step(OperationType.SIMPLIFY, input_expression, output_expression)
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details
        assert result.message.endswith("output matches the recomputed operator result")

    def test_factor_of_nonzero_difference_is_not_marked(self, verifier):
        # round-complex task-01 step 12: ``factor(c^2*S - b^2*S)`` ->
        # ``-(b-c)*(b+c)*S`` is a complete answer, not a failed identity.  A
        # factorization is never an identity assertion, so it must not carry
        # the "difference did not reduce to zero" warning.
        step = _make_step(
            OperationType.FACTOR,
            "c**2*Subs(Derivative(f(_xi_1), (_xi_1, 2)), _xi_1, -c*t + x)"
            " - b**2*Subs(Derivative(f(_xi_1), (_xi_1, 2)), _xi_1, -c*t + x)",
            "-(b - c)*(b + c)*Subs(Derivative(f(_xi_1), (_xi_1, 2)), _xi_1, -c*t + x)",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details
        assert "did not reduce to zero" not in result.message
        assert result.message.endswith("output matches the recomputed operator result")

    def test_simplify_of_same_difference_is_still_marked(self, verifier):
        # The factor exemption is scoped to FACTOR alone: the same recording
        # under ``simplify`` still earns the unproven-difference warning.
        step = _make_step(
            OperationType.SIMPLIFY,
            "cos(2*x) - (1 - 2*sin(2*x)**2)",
            "-8*sin(x)**4 + 6*sin(x)**2",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.details.get("suspect_identity") == "unreduced"


class TestSuspectIdentityArchived:
    """The live recorder archives ``input_srepr``; ``safe_load_expression``
    flattens ``-(A - B)`` on reload, so the detection must read the archive."""

    def test_archived_nonzero_difference_is_unreduced(self, verifier):
        step = _make_archived_step(
            OperationType.SIMPLIFY,
            "cos(2*x) - (1 - 2*sin(2*x)**2)",
            "-8*sin(x)**4 + 6*sin(x)**2",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"
        assert "asserted identity is FALSE" not in result.message

    def test_archived_non_difference_not_marked(self, verifier):
        step = _make_archived_step(
            OperationType.SIMPLIFY, "x**2 - 1", "(x - 1)*(x + 1)"
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert "suspect_identity" not in result.details

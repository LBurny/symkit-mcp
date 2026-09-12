"""Substitution-step verification fidelity.

Two defects found by the 2026-09-12 complex-derivation black-box round
(`symkit-mcp-test-complex`):

* An already-computed expression holds *evaluated* arithmetic
  (``Rational(1, 2)``), while the substitution key is re-parsed from a string
  where the user parser leaves ``/2`` as an unevaluated ``Pow(2, -1)``.
  ``subs`` matches structurally, so the key silently fails to apply, the
  reconstructed expectation keeps the un-substituted term, and a correct step
  is reported FAILED — dragging the whole chain to ``overall: failed``.
* A substitution whose keys cannot apply at all still reported
  "Substitution verified", so the verified count says nothing about whether
  anything was substituted.
"""

from __future__ import annotations

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


def _substitution_step(
    original: str,
    replacement_map: str,
    output_expression: str,
    *,
    input_srepr: str = "",
    output_srepr: str = "",
) -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=OperationType.SUBSTITUTE,
        description="substitution under test",
        input_expressions={"original": original, "replacement_map": replacement_map},
        input_srepr=input_srepr,
        output_expression=output_expression,
        output_latex=output_expression,
        output_srepr=output_srepr,
        sympy_command="math('substitute', ...)",
    )


class TestCompoundKeyStructuralMatch:
    """A compound key must apply to the archived (evaluated) expression."""

    def test_divided_exponent_key_matches_archived_expression(self):
        """``exp(-k*t/2)`` must match ``Rational(-1, 2)`` in the archive.

        The replacement is deliberately a fresh symbol: if the key fails to
        apply, the reconstructed expectation keeps ``exp(-k*t/2)`` and cannot
        reduce to the output, which is exactly the false FAILED observed in
        the wild.
        """
        step = _substitution_step(
            original="C1*exp(-k*t/2) + 1",
            replacement_map='{"C1": "2", "exp(-k*t/2)": "u"}',
            output_expression="2*u + 1",
            input_srepr=(
                "Add(Mul(Symbol('C1'), exp(Mul(Rational(-1, 2), "
                "Symbol('k'), Symbol('t')))), Integer(1))"
            ),
            output_srepr="Add(Mul(Integer(2), Symbol('u')), Integer(1))",
        )

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.VERIFIED, (
            f"correct substitution was not verified: {result.message}"
        )

    def test_symbol_keys_still_verify(self):
        """Regression guard: the ordinary symbol-key path is unaffected."""
        step = _substitution_step(
            original="a*x + b*y",
            replacement_map='{"a": "1", "b": "2"}',
            output_expression="x + 2*y",
        )

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is VerificationStatus.VERIFIED


class TestNoOpSubstitutionIsNotVerified:
    """Nothing substituted must not read as a passed check."""

    def test_key_absent_from_expression_is_not_verified(self):
        step = _substitution_step(
            original="x + y",
            replacement_map='{"z": "1"}',
            output_expression="x + y",
        )

        result = StepVerifier().verify_step(step, prior_expr=None)

        assert result.status is not VerificationStatus.VERIFIED
        assert result.status is VerificationStatus.INCONCLUSIVE

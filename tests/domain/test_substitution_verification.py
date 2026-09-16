"""Substitution-step verification fidelity.

Merged from two files on verifier fidelity of value-carrying steps:

Substitution (2026-09-12 complex-derivation black-box round,
``symkit-mcp-test-complex``):

* An already-computed expression holds *evaluated* arithmetic
  (``Rational(1, 2)``), while the substitution key is re-parsed from a string
  where the user parser leaves ``/2`` as an unevaluated ``Pow(2, -1)``.
  ``subs`` matches structurally, so the key silently fails to apply, the
  reconstructed expectation keeps the un-substituted term, and a correct step
  is reported FAILED — dragging the whole chain to ``overall: failed``.
* A substitution whose keys cannot apply at all still reported
  "Substitution verified", so the verified count says nothing about whether
  anything was substituted.

``evalf`` (r18 A2): ``math("evalf", "v*t", substitution={"v": "3", "t": "4"})``
returns ``12.0000000000000``, but ``session_verify_step`` answered
``inconclusive`` with "evalf output does not match the numeric evaluation of
its input": the verifier recomputed the *unsubstituted* input. The recorded
substitution lives on the step as ``input_substitution`` and must be applied
before the numeric anchor is recomputed.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import sympy as sp

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


# evalf substitution replay (r18 A2).
def _evalf_step(
    expression: str,
    substitution: dict[str, str] | None,
    output: sp.Basic,
) -> DerivationStep:
    parsed = sp.sympify(expression)
    inputs = {"operation": "evalf", "original": expression}
    if substitution:
        inputs["input_substitution"] = json.dumps(substitution)
    return DerivationStep(
        step_number=1,
        operation=OperationType.EVALF,
        description=f"evalf: {expression}",
        input_expressions=inputs,
        output_expression=str(output),
        output_latex=sp.latex(output),
        sympy_command="N(expr)",
        output_srepr=sp.srepr(output),
        input_srepr=sp.srepr(parsed),
    )


def test_evalf_with_substitution_verifies() -> None:
    step = _evalf_step("v*t", {"v": "3", "t": "4"}, sp.Float("12.0000000000000"))
    result = StepVerifier().verify_step(step)
    assert result.status is VerificationStatus.VERIFIED, result.details


def test_evalf_symbolic_square_plus_one_verifies() -> None:
    step = _evalf_step("x**2 + 1", {"x": "2"}, sp.Float("5.00000000000000"))
    result = StepVerifier().verify_step(step)
    assert result.status is VerificationStatus.VERIFIED, result.details


def test_evalf_without_substitution_still_verifies() -> None:
    step = _evalf_step("2*pi", None, sp.Float("6.28318530717959"))
    result = StepVerifier().verify_step(step)
    assert result.status is VerificationStatus.VERIFIED, result.details


def test_wrong_evalf_output_is_still_flagged() -> None:
    """Applying the substitution must not weaken the check: 3*4 != 99."""
    step = _evalf_step("v*t", {"v": "3", "t": "4"}, sp.Float("99.0"))
    result = StepVerifier().verify_step(step)
    assert result.status is VerificationStatus.FAILED, result


def test_large_integer_substitution_does_not_wedge_the_verifier() -> None:
    """Replaying the point exactly would rebuild the r18 A3 giant rational."""
    step = _evalf_step(
        "(1 + 1/n)**n", {"n": "1000000"}, sp.Float("2.71828046931938")
    )
    box: dict[str, Any] = {}

    def run() -> None:
        box["value"] = StepVerifier().verify_step(step)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(30.0)
    assert not thread.is_alive(), "the evalf verifier wedged on a large substitution"
    result = box["value"]
    assert result.status is VerificationStatus.VERIFIED, result.details

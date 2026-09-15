"""r18 A2: the ``evalf`` step verifier must replay the step's substitution.

``math("evalf", "v*t", substitution={"v": "3", "t": "4"})`` returns
``12.0000000000000``, but ``session_verify_step`` answered ``inconclusive``
with ``"evalf output does not match the numeric evaluation of its input"`` and
``details.expected == "t*v"``: the verifier recomputed the *unsubstituted*
input.  The recorded substitution lives on the step as ``input_substitution``
and must be applied before the numeric anchor is recomputed.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus


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

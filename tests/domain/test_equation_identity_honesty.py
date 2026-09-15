"""r18 honesty regression: ``equation_identity`` and recorded equations.

Defect B1a (orchestrator round 18): for
``math("simplify", "Eq(sqrt(a*b), sqrt(a)*sqrt(b))", assumptions=["a is complex",
"b is complex"])`` the engine left the equation unreduced, yet the step's
``details.equation_identity`` reported ``is_identity: true`` / ``verdict: TRUE``.
The identity is false for complex ``a, b`` (branch cuts); the old code promoted
agreement at assumption-compatible (positive-real) samples to a proof.

Required semantics: a ``TRUE`` verdict rests on an *exact* symbolic zero
(``diff == 0`` after reduction), never on sampling.  Sampling may only downgrade
an unreduced difference to ``UNKNOWN``.  The same promotion verified a
*recorded* false equation through ``recorded_step_verdict`` (the audit8
claim-4 path), which is pinned here as well.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.final_result import (
    boolean_equation_verdict,
    equation_identity,
    recorded_step_verdict,
)
from symkit.domain.value_objects import VerificationStatus


class TestEquationIdentityRequiresExactZero:
    """A TRUE verdict must rest on an exact symbolic zero (B1a)."""

    def test_complex_branch_cut_identity_is_not_certified(self) -> None:
        a, b = sp.symbols("a b", complex=True)
        result = equation_identity(sp.Eq(sp.sqrt(a * b), sp.sqrt(a) * sp.sqrt(b)))
        assert result["verdict"] == "UNKNOWN"
        assert result["is_identity"] is None
        assert "tested points" in result["numeric_evidence"]

    def test_complex_branch_cut_identity_recorded_stays_inconclusive(self) -> None:
        a, b = sp.symbols("a b", complex=True)
        status, message = recorded_step_verdict(
            sp.Eq(sp.sqrt(a * b), sp.sqrt(a) * sp.sqrt(b))
        )
        assert status == VerificationStatus.INCONCLUSIVE
        assert "Identity verified" not in message
        assert "unproven, not disproven" in message

    def test_sqrt_square_false_identity_is_not_true(self) -> None:
        a = sp.Symbol("a")
        result = equation_identity(sp.Eq(a, sp.sqrt(a**2)))
        assert result["verdict"] in {"FALSE", "UNKNOWN"}

    def test_true_trig_identity_still_certifies_exactly(self) -> None:
        x = sp.Symbol("x")
        result = equation_identity(sp.Eq(sp.sin(x) ** 2 + sp.cos(x) ** 2, 1))
        assert result["verdict"] == "TRUE"
        assert result["is_identity"] is True
        assert result["difference"] == "0"

    def test_true_buried_trig_identity_reduces_exactly(self) -> None:
        # Plain simplify does not expand cos(6*x); the trig-aware reduction
        # reaches an exact zero, so the TRUE verdict stays honest (task-17).
        x = sp.Symbol("x")
        result = equation_identity(
            sp.Eq(
                sp.cos(6 * x),
                32 * sp.cos(x) ** 6 - 48 * sp.cos(x) ** 4 + 18 * sp.cos(x) ** 2 - 1,
            )
        )
        assert result["verdict"] == "TRUE"
        assert result["difference"] == "0"

    def test_false_polynomial_identity_is_false(self) -> None:
        a, b = sp.symbols("a b")
        result = equation_identity(sp.Eq((a + b) ** 2, a**2 + b**2))
        assert result["verdict"] == "FALSE"
        assert result["is_identity"] is False

    def test_scaled_equation_still_reports_false(self) -> None:
        # ``Eq(2*x, 3*x)`` is not an identity (only x = 0); the numeric path
        # still falsifies it after the conditioning fix.
        x = sp.Symbol("x")
        result = equation_identity(sp.Eq(2 * x, 3 * x))
        assert result["verdict"] == "FALSE"

    def test_numeric_contradiction_is_false(self) -> None:
        result = equation_identity(sp.Eq(1, 2, evaluate=False))
        assert result["verdict"] == "FALSE"


class TestBooleanEquationVerdictExactness:
    """``boolean_equation_verdict`` must not certify from sampling either."""

    def test_true_identity_verifies(self) -> None:
        x = sp.Symbol("x")
        status, message, details = boolean_equation_verdict(
            "simplify", sp.Eq(sp.sin(x) ** 2 + sp.cos(x) ** 2, 1)
        )
        assert status == VerificationStatus.VERIFIED
        assert "is an identity" in message
        assert details == {}

    def test_asserted_false_identity_fails(self) -> None:
        x = sp.Symbol("x")
        status, message, details = boolean_equation_verdict(
            "simplify", sp.Eq(2 * x, 3 * x, evaluate=False)
        )
        assert status == VerificationStatus.FAILED
        assert details.get("suspect_identity") == "numeric"
        assert "FALSE" in message

    def test_numeric_contradiction_fails(self) -> None:
        status, _message, details = boolean_equation_verdict(
            "simplify", sp.Eq(1, 2, evaluate=False)
        )
        assert status == VerificationStatus.FAILED
        assert details.get("suspect_identity") == "numeric"


class TestRecordedEquationHonesty:
    """Recorded equations: exact zero verifies, sampling never promotes."""

    def test_true_recorded_identity_verifies(self) -> None:
        a, b = sp.symbols("a b")
        status, message = recorded_step_verdict(
            sp.Eq((a + b) ** 2, a**2 + 2 * a * b + b**2)
        )
        assert status == VerificationStatus.VERIFIED
        assert "Identity verified" in message

    def test_false_recorded_identity_fails(self) -> None:
        a, b = sp.symbols("a b")
        status, message = recorded_step_verdict(sp.Eq((a + b) ** 2, a**2 + b**2))
        assert status == VerificationStatus.FAILED
        assert "not an identity" in message

    def test_positive_real_identity_records_verified(self) -> None:
        a, b = sp.symbols("a b", positive=True)
        status, _message = recorded_step_verdict(
            sp.Eq(sp.sqrt(a * b), sp.sqrt(a) * sp.sqrt(b))
        )
        assert status == VerificationStatus.VERIFIED

    def test_undefined_function_stays_inconclusive(self) -> None:
        x = sp.Symbol("x")
        status, message = recorded_step_verdict(sp.Eq(sp.Function("f")(x), x))
        assert status == VerificationStatus.INCONCLUSIVE
        assert "unproven, not disproven" in message

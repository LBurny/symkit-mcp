"""Tests for Phase 3 StepVerifier — assumption-aware step verification."""

from __future__ import annotations

import pytest

from symkit.domain.assumption_engine import AssumptionEngine, AssumptionLevel
from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.math_domain import MathDomain
from symkit.domain.step_verifier import (
    StepVerifier,
    verification_result_from_json,
    verification_result_to_json,
)
from symkit.domain.value_objects import VerificationStatus


@pytest.fixture
def verifier():
    return StepVerifier()

def _make_step(
    operation: OperationType,
    input_expressions: dict[str, str],
    output_expression: str,
    sympy_command: str = "",
) -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="test step",
        input_expressions=input_expressions,
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command=sympy_command,
    )

class TestStepVerifierSimplify:
    def test_simplify_equality(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "(x + 1)**2"},
            "x**2 + 2*x + 1",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED

    def test_simplify_failure(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "x"},
            "x + 1",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.FAILED

    def test_simplify_with_assumption(self, verifier):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("x", "positive")
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "sqrt(x**2)"},
            "x",
        )
        result = verifier.verify_step(step, assumption_engine=engine)
        assert result.status == VerificationStatus.VERIFIED

class TestStepVerifierDifferentiate:
    def test_differentiate(self, verifier):
        step = _make_step(
            OperationType.DIFFERENTIATE,
            {"original": "x**2"},
            "2*x",
            sympy_command="diff(expr, x)",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED

    def test_differentiate_failure(self, verifier):
        step = _make_step(
            OperationType.DIFFERENTIATE,
            {"original": "x**2"},
            "3*x",
            sympy_command="diff(expr, x)",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.INCONCLUSIVE

class TestStepVerifierIntegrate:
    def test_integrate(self, verifier):
        step = _make_step(
            OperationType.INTEGRATE,
            {"original": "2*x"},
            "x**2",
            sympy_command="integrate(expr, x)",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED

class TestStepVerifierDefiniteIntegrate:
    """Regression (run-011): reverse differentiation is meaningless for a
    definite integral — the result no longer depends on the integration
    variable, so d/dv of the correct constant ``3*k_B*T/m`` is ``0`` and the
    old check false-FAILED a correct Maxwell-Boltzmann moment. Definite
    integrals are verified by numeric quadrature instead; disagreement yields
    INCONCLUSIVE (quadrature can mislead), never a false FAILED."""

    GAUSSIAN = "4*pi*v**4*(m/(2*pi*k_B*T))**(3/2)*exp(-m*v**2/(2*k_B*T))"

    def test_definite_integral_verified_by_quadrature(self, verifier):
        step = _make_step(
            OperationType.INTEGRATE,
            {"original": self.GAUSSIAN},
            "3*T*k_B/m",
            sympy_command="integrate(expr, (v, 0, oo))",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED

    def test_definite_integral_wrong_output_is_not_failed(self, verifier):
        step = _make_step(
            OperationType.INTEGRATE,
            {"original": self.GAUSSIAN},
            "2*T*k_B/m",
            sympy_command="integrate(expr, (v, 0, oo))",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert result.status != VerificationStatus.FAILED

    def test_definite_integral_without_valuatable_output_is_inconclusive(
        self, verifier
    ):
        # Output still depends on the integration variable: quadrature cannot
        # run, must degrade to INCONCLUSIVE rather than FAILED.
        step = _make_step(
            OperationType.INTEGRATE,
            {"original": self.GAUSSIAN},
            "3*T*k_B/m + v",
            sympy_command="integrate(expr, (v, 0, oo))",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.INCONCLUSIVE

class TestStepVerifierSubstitute:
    def test_substitute(self, verifier):
        step = _make_step(
            OperationType.SUBSTITUTE,
            {
                "original": "x + y",
                "replacement": "x = z",
            },
            "y + z",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.VERIFIED

    def test_substitute_failure(self, verifier):
        step = _make_step(
            OperationType.SUBSTITUTE,
            {
                "original": "x + y",
                "replacement": "x = z",
            },
            "x + y",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.FAILED

class TestStepVerifierSolve:
    def test_solve(self, verifier):
        step = _make_step(
            OperationType.SOLVE,
            {"equation": "x - 2"},
            "Eq(x, 2)",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.VERIFIED

class TestStepVerifierAssumptionConflicts:
    def test_conflict_marks_verified_as_failed(self, verifier):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("x", "positive")
        engine.assume("x", "negative", level=AssumptionLevel.STEP)
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "x + x"},
            "2*x",
        )
        result = verifier.verify_step(step, assumption_engine=engine)
        assert result.status == VerificationStatus.FAILED
        assert "contradictory" in result.message.lower()
        assert result.details.get("assumption_conflicts")

    def test_warning_for_division(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "1/x"},
            "1/x",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert any("division" in w.lower() for w in result.details.get("warnings", []))

class TestStepVerifierSerialization:
    def test_roundtrip(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "x + x"},
            "2*x",
        )
        result = verifier.verify_step(step)
        data = verification_result_to_json(result)
        restored = verification_result_from_json(data)
        assert restored.status == result.status
        assert restored.message == result.message
        assert restored.is_verified == result.is_verified

class TestStepVerifierRobustParsing:
    """The verifier should parse reserved names and equations via the unified parser."""

    def test_simplify_with_reserved_beta(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "beta * x + beta * x"},
            "2*beta*x",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.VERIFIED

    def test_verify_natural_equation(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "x**2 + 2*x + 1 = (x + 1)**2"},
            "x**2 + 2*x + 1 = x**2 + 2*x + 1",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.VERIFIED

    def test_multi_letter_identifier_not_split(self, verifier):
        step = _make_step(
            OperationType.SIMPLIFY,
            {"original": "nut + nut"},
            "2*nut",
        )
        result = verifier.verify_step(step)
        assert result.status == VerificationStatus.VERIFIED
        assert "n*u*t" not in str(result.message)

class TestSubstituteAssumptionAwareness:
    """Regression: substitution must use assumption-aware symbols, otherwise
    ``subs`` is a silent no-op and every substitute step is judged FAILED."""

    def test_substitute_with_assumptions_verifies(self, verifier):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("a", "positive")
        engine.assume("m", "positive")
        step = _make_step(
            OperationType.SUBSTITUTE,
            {"original": "a*m", "replacement": "a = 0"},
            "0",
        )
        result = verifier.verify_step(step, assumption_engine=engine)
        assert result.status == VerificationStatus.VERIFIED

    def test_substitute_non_identifier_key(self, verifier):
        step = _make_step(
            OperationType.SUBSTITUTE,
            {"original": "x**4", "replacement": "x**2 = w**2"},
            "w**4",
        )
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED

class TestFloatTolerance:
    """Purely numeric residuals within machine precision must not flip a
    correct step to FAILED."""

    def test_machine_epsilon_diff_passes(self, verifier):
        step = _make_step(OperationType.SIMPLIFY, {"original": "0.1 + 0.2"}, "0.3")
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED

    def test_real_mismatch_still_fails(self, verifier):
        step = _make_step(OperationType.SIMPLIFY, {"original": "x"}, "x + 1")
        result = verifier.verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.FAILED

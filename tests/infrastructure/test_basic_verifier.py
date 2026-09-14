"""
Tests for BasicVerifier.

`Verifier` is a public domain interface and `BasicVerifier` is its only concrete
implementation, consumed by `application/use_cases.py`. These tests pin its
observable behaviour.
"""

import pytest

pytest.importorskip("sympy")

from symkit.domain.entities import Derivation, DerivationStep
from symkit.domain.value_objects import VerificationStatus
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit.infrastructure.verifier import BasicVerifier


@pytest.fixture
def engine():
    return SymPyEngine()


@pytest.fixture
def verifier():
    return BasicVerifier()


def _step(engine, operation, input_str, output_str, number=1):
    return DerivationStep(
        step_number=number,
        operation=operation,
        input_expr=engine.parse(input_str),
        output_expr=engine.parse(output_str),
    )


class TestVerifyStep:
    """verify_step dispatch and outcomes."""

    def test_simplification_preserving_value_is_verified(self, engine, verifier):
        result = verifier.verify_step(
            engine.parse("x + x"), engine.parse("2*x"), "simplify"
        )

        assert result.status is VerificationStatus.VERIFIED

    def test_simplification_changing_value_fails(self, engine, verifier):
        result = verifier.verify_step(
            engine.parse("x + x"), engine.parse("3*x"), "simplify"
        )

        assert result.status is VerificationStatus.FAILED
        assert "difference" in result.details

    def test_differentiation_verified_by_reverse_integration(self, engine, verifier):
        result = verifier.verify_step(
            engine.parse("x**2"), engine.parse("2*x"), "differentiate"
        )

        assert result.status is VerificationStatus.VERIFIED
        assert result.reverse_check is True

    def test_integration_verified_by_differentiation(self, engine, verifier):
        result = verifier.verify_step(
            engine.parse("2*x"), engine.parse("x**2"), "integrate"
        )

        assert result.status is VerificationStatus.VERIFIED
        assert result.reverse_check is True

    def test_derivative_of_constant_is_zero(self, engine, verifier):
        result = verifier.verify_step(engine.parse("5"), engine.parse("0"), "differentiate")

        assert result.status is VerificationStatus.VERIFIED

    def test_substitution_is_accepted_for_valid_expressions(self, engine, verifier):
        result = verifier.verify_step(
            engine.parse("x**2"), engine.parse("4"), "substitute"
        )

        assert result.status is VerificationStatus.VERIFIED

    def test_unknown_operation_is_inconclusive(self, engine, verifier):
        result = verifier.verify_step(
            engine.parse("x**2"), engine.parse("x**2"), "meditate"
        )

        assert result.status is VerificationStatus.INCONCLUSIVE

    def test_invalid_input_expression_fails(self, engine, verifier):
        invalid = engine.parse("x +* 2")

        assert invalid.is_valid is False
        result = verifier.verify_step(invalid, engine.parse("2*x"), "simplify")

        assert result.status is VerificationStatus.FAILED
        assert result.details["input_valid"] is False


class TestVariableSelection:
    """Multi-symbol steps must be verified against the right variable,
    independent of set iteration order (PYTHONHASHSEED)."""

    def test_integration_over_x_of_several_symbols(self, engine, verifier):
        # ∫ x·t dx = x²t/2
        result = verifier.verify_step(
            engine.parse("x*t"), engine.parse("x**2*t/2"), "integrate"
        )

        assert result.status is VerificationStatus.VERIFIED

    def test_integration_over_t_of_several_symbols(self, engine, verifier):
        # ∫ x·t dt = xt²/2
        result = verifier.verify_step(
            engine.parse("x*t"), engine.parse("x*t**2/2"), "integrate"
        )

        assert result.status is VerificationStatus.VERIFIED

    def test_integration_with_variable_other_than_x(self, engine, verifier):
        # ∫ 5 dt = 5t — must not assume the variable is named x
        result = verifier.verify_step(engine.parse("5"), engine.parse("5*t"), "integrate")

        assert result.status is VerificationStatus.VERIFIED

    def test_wrong_antiderivative_fails(self, engine, verifier):
        # d/d?(x²t) is x² or 2xt — neither equals x·t
        result = verifier.verify_step(
            engine.parse("x*t"), engine.parse("x**2*t"), "integrate"
        )

        assert result.status is VerificationStatus.FAILED

    def test_differentiation_of_multivariable_expression(self, engine, verifier):
        # d/dt(x·t) = x — reverse integration must try the right symbol
        result = verifier.verify_step(
            engine.parse("x*t"), engine.parse("x"), "differentiate"
        )

        assert result.status is VerificationStatus.VERIFIED

    def test_differentiation_with_constant_result(self, engine, verifier):
        # d/dx(5x) = 5 — a nonzero constant can be a correct derivative
        result = verifier.verify_step(engine.parse("5*x"), engine.parse("5"), "differentiate")

        assert result.status is VerificationStatus.VERIFIED


class TestVerifyDerivation:
    """verify_derivation aggregates per-step outcomes."""

    def test_empty_derivation_fails(self, verifier):
        result = verifier.verify_derivation(Derivation(goal="empty"))

        assert result.status is VerificationStatus.FAILED

    def test_all_steps_verified(self, engine, verifier):
        derivation = Derivation(goal="ok")
        derivation.add_step(_step(engine, "differentiate", "x**2", "2*x", 1))
        derivation.add_step(_step(engine, "simplify", "x + x", "2*x", 2))

        result = verifier.verify_derivation(derivation)

        assert result.status is VerificationStatus.VERIFIED

    def test_failing_step_is_reported_by_number(self, engine, verifier):
        derivation = Derivation(goal="bad")
        derivation.add_step(_step(engine, "differentiate", "x**2", "2*x", 1))
        derivation.add_step(_step(engine, "simplify", "x + x", "3*x", 2))

        result = verifier.verify_derivation(derivation)

        assert result.status is VerificationStatus.FAILED
        assert result.details["failed_steps"] == [2]

    def test_inconclusive_steps_are_not_reported_as_failures(self, engine, verifier):
        derivation = Derivation(goal="mixed")
        derivation.add_step(_step(engine, "simplify", "x + x", "2*x", 1))
        derivation.add_step(_step(engine, "rearrange", "x + y", "y + x", 2))

        result = verifier.verify_derivation(derivation)

        assert result.status is VerificationStatus.INCONCLUSIVE
        assert result.details["inconclusive_steps"] == [2]

    def test_failed_and_inconclusive_steps_are_both_reported(self, engine, verifier):
        derivation = Derivation(goal="mixed")
        derivation.add_step(_step(engine, "simplify", "x + x", "3*x", 1))
        derivation.add_step(_step(engine, "meditate", "x", "x", 2))

        result = verifier.verify_derivation(derivation)

        assert result.status is VerificationStatus.FAILED
        assert result.details["failed_steps"] == [1]
        assert result.details["inconclusive_steps"] == [2]


class TestCheckDimensions:
    """Dimensional analysis without and with unit information."""

    def test_without_unit_info_is_inconclusive(self, engine, verifier):
        result = verifier.check_dimensions(engine.parse("x**2"))

        assert result.status is VerificationStatus.INCONCLUSIVE
        assert result.dimension_check is None

    def test_inconsistent_expression_with_unit_map_fails(self, engine, verifier):
        result = verifier.check_dimensions(
            engine.parse("rho + v"),
            unit_map={"rho": "kg/m^3", "v": "m/s"},
        )

        assert result.status is VerificationStatus.FAILED
        assert result.dimension_check is False
        assert result.details["dimension_issues"]

    def test_consistent_expression_with_unit_map_is_verified(self, engine, verifier):
        result = verifier.check_dimensions(
            engine.parse("rho*v"),
            unit_map={"rho": "kg/m^3", "v": "m/s"},
        )

        assert result.status is VerificationStatus.VERIFIED
        assert result.dimension_check is True

    def test_partial_unit_map_is_inconclusive(self, engine, verifier):
        result = verifier.check_dimensions(
            engine.parse("rho + v"),
            unit_map={"rho": "kg/m^3"},
        )

        assert result.status is VerificationStatus.INCONCLUSIVE
        assert result.dimension_check is None


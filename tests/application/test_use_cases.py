"""
Tests for the application-layer use cases.

These are the programmatic entry points re-exported from `symkit/__init__.py`.
The MCP layer does not route through them, so they are covered here rather than
by the MCP tool tests.
"""

import pytest

pytest.importorskip("sympy")

from symkit.application.use_cases import (
    CalculateUseCase,
    DeriveUseCase,
    SimplifyUseCase,
    VerifyUseCase,
)
from symkit.domain.value_objects import VerificationStatus
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit.infrastructure.verifier import BasicVerifier


@pytest.fixture
def engine():
    return SymPyEngine()


@pytest.fixture
def verifier():
    return BasicVerifier()


class TestCalculateUseCase:
    """Tests for CalculateUseCase."""

    def test_simplify_operation(self, engine):
        result = CalculateUseCase(engine).execute("x + x", "simplify")

        assert result.success is True
        assert result.result == "2*x"
        assert result.latex

    def test_evaluate_with_substitutions(self, engine):
        result = CalculateUseCase(engine).execute(
            "x**2 + 1", "evaluate", substitutions={"x": 3}
        )

        assert result.success is True
        assert result.result == "10"

    def test_unknown_operation_reports_error(self, engine):
        result = CalculateUseCase(engine).execute("x**2", "teleport")

        assert result.success is False
        assert "Unknown operation" in result.error

    def test_unparseable_expression_reports_error(self, engine):
        result = CalculateUseCase(engine).execute("x +* 2", "simplify")

        assert result.success is False
        assert result.error


class TestSimplifyUseCase:
    """Tests for SimplifyUseCase."""

    def test_simplifies_expression(self, engine):
        result = SimplifyUseCase(engine).execute("(x + 1)**2 - x**2 - 2*x")

        assert result.success is True
        assert result.result == "1"

    def test_unparseable_expression_reports_error(self, engine):
        result = SimplifyUseCase(engine).execute("x +* 2")

        assert result.success is False
        assert result.error


class TestDeriveUseCase:
    """Tests for DeriveUseCase."""

    def test_runs_steps_and_sets_conclusion(self, engine):
        derivation = DeriveUseCase(engine).execute(
            goal="differentiate x squared",
            premises=["x**2"],
            steps=[{"operation": "differentiate", "variable": "x"}],
            verify=False,
        )

        assert derivation.get_step_count() == 1
        assert derivation.conclusion is not None
        assert derivation.conclusion.raw == "2*x"
        assert derivation.is_verified is False

    def test_verifies_steps_when_verifier_given(self, engine, verifier):
        derivation = DeriveUseCase(engine, verifier).execute(
            goal="differentiate x squared",
            premises=["x**2"],
            steps=[{"operation": "differentiate", "variable": "x"}],
        )

        assert derivation.is_verified is True

    def test_substitute_step(self, engine):
        derivation = DeriveUseCase(engine).execute(
            goal="evaluate at x=2",
            premises=["x**2"],
            steps=[{"operation": "substitute", "substitutions": {"x": 2}}],
            verify=False,
        )

        assert derivation.conclusion is not None
        assert derivation.conclusion.raw == "4"

    def test_unknown_operation_passes_expression_through(self, engine):
        derivation = DeriveUseCase(engine).execute(
            goal="no-op",
            premises=["x**2"],
            steps=[{"operation": "meditate"}],
            verify=False,
        )

        assert derivation.conclusion is not None
        assert derivation.conclusion.raw == "x**2"

    def test_empty_premises_yields_no_steps(self, engine):
        derivation = DeriveUseCase(engine).execute(
            goal="nothing", premises=[], steps=[{"operation": "simplify"}], verify=False
        )

        assert derivation.get_step_count() == 0
        assert derivation.conclusion is None


class TestVerifyUseCase:
    """Tests for VerifyUseCase."""

    def test_execute_delegates_to_verifier(self, engine, verifier):
        result = VerifyUseCase(engine, verifier).execute("x**2", "2*x", "differentiate")

        assert result.status is VerificationStatus.VERIFIED

    def test_verify_equality_accepts_equivalent_forms(self, engine, verifier):
        result = VerifyUseCase(engine, verifier).verify_equality("x + x", "2*x")

        assert result.is_verified is True

    def test_verify_equality_rejects_different_forms(self, engine, verifier):
        result = VerifyUseCase(engine, verifier).verify_equality("x + x", "3*x")

        assert result.is_verified is False

    def test_verify_equality_reports_error_on_bad_input(self, engine, verifier):
        result = VerifyUseCase(engine, verifier).verify_equality("x +* 2", "2*x")

        assert result.is_verified is False

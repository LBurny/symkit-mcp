"""
Tests for SymKit Domain Layer
"""

from symkit.domain.entities import Derivation, DerivationStep, Expression
from symkit.domain.value_objects import (
    CalculationResult,
    MathContext,
    SimplificationLevel,
    VerificationResult,
    VerificationStatus,
)


class TestExpression:
    """Tests for Expression entity."""

    def test_expression_creation(self):
        """Test basic expression creation."""
        expr = Expression(raw="x**2", latex="x^{2}")
        assert expr.raw == "x**2"
        assert expr.latex == "x^{2}"
        assert expr.id is not None

    def test_expression_validity(self):
        """Test expression validity check."""
        valid_expr = Expression(raw="x", sympy_expr="dummy")
        invalid_expr = Expression(raw="x", sympy_expr=None)

        assert valid_expr.is_valid
        assert not invalid_expr.is_valid


class TestDerivation:
    """Tests for Derivation entity."""

    def test_empty_derivation(self):
        """Test empty derivation."""
        deriv = Derivation(goal="test")
        assert deriv.goal == "test"
        assert deriv.get_step_count() == 0
        assert not deriv.is_complete

    def test_add_step(self):
        """Test adding steps to derivation."""
        deriv = Derivation(goal="test")
        step = DerivationStep(
            step_number=1,
            operation="simplify",
            input_expr=Expression(raw="x"),
            output_expr=Expression(raw="x"),
        )
        deriv.add_step(step)
        assert deriv.get_step_count() == 1


class TestMathContext:
    """Tests for MathContext value object."""

    def test_default_context(self):
        """Test default context values."""
        ctx = MathContext()
        assert ctx.precision == 15
        assert ctx.domain == "complex"
        assert ctx.simplify_level == SimplificationLevel.BASIC

    def test_with_assumption(self):
        """Test adding assumptions creates new context."""
        ctx = MathContext()
        new_ctx = ctx.with_assumption("x", real=True, positive=True)

        # Original unchanged
        assert "x" not in ctx.assumptions

        # New has assumption
        assert "x" in new_ctx.assumptions
        assert new_ctx.assumptions["x"]["real"] is True
        assert new_ctx.assumptions["x"]["positive"] is True


class TestVerificationResult:
    """Tests for VerificationResult value object."""

    def test_success_result(self):
        """Test creating success result."""
        result = VerificationResult.success("All good")
        assert result.is_verified
        assert result.status == VerificationStatus.VERIFIED
        assert result.message == "All good"

    def test_failure_result(self):
        """Test creating failure result."""
        result = VerificationResult.failure("Something wrong", detail="info")
        assert not result.is_verified
        assert result.status == VerificationStatus.FAILED
        assert result.details["detail"] == "info"


class TestCalculationResult:
    """Tests for CalculationResult value object."""

    def test_from_error(self):
        """Test creating error result."""
        result = CalculationResult.from_error("Parse failed")
        assert not result.success
        assert result.error == "Parse failed"
        assert result.result == ""

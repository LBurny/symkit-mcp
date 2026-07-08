"""
Tests for SymPy Engine Implementation
"""

import pytest

# Skip all tests if sympy not installed
pytest.importorskip("sympy")

from symkit.domain.value_objects import MathContext, SimplificationLevel
from symkit.infrastructure.sympy_engine import SymPyEngine


@pytest.fixture
def engine():
    """Create a SymPyEngine instance."""
    return SymPyEngine()


class TestSymPyEngineParsing:
    """Tests for expression parsing."""

    def test_parse_simple(self, engine):
        """Test parsing simple expression."""
        expr = engine.parse("x**2 + 1")
        assert expr.is_valid
        assert "x**2" in expr.raw

    def test_parse_with_functions(self, engine):
        """Test parsing with mathematical functions."""
        expr = engine.parse("sin(x) + cos(x)")
        assert expr.is_valid

    def test_parse_invalid(self, engine):
        """Test parsing invalid expression."""
        expr = engine.parse("x +++ @#$ y")  # Clearly invalid
        assert not expr.is_valid

    def test_implicit_multiplication(self, engine):
        """Test implicit multiplication parsing."""
        expr = engine.parse("2x")  # Should parse as 2*x
        assert expr.is_valid


class TestSymPyEngineSimplification:
    """Tests for expression simplification."""

    def test_simplify_polynomial(self, engine):
        """Test simplifying polynomial."""
        expr = engine.parse("x**2 + 2*x + 1")
        result = engine.simplify(expr)
        # Should simplify to (x + 1)**2
        assert result.is_valid

    def test_simplify_trig(self, engine):
        """Test trigonometric simplification."""
        ctx = MathContext(simplify_level=SimplificationLevel.TRIGONOMETRIC)
        expr = engine.parse("sin(x)**2 + cos(x)**2")
        result = engine.simplify(expr, ctx)
        assert result.raw == "1"


class TestSymPyEngineCalculus:
    """Tests for calculus operations."""

    def test_differentiate_polynomial(self, engine):
        """Test differentiating polynomial."""
        expr = engine.parse("x**3")
        result = engine.differentiate(expr, "x")
        assert result.is_valid
        assert "3" in result.raw and "x**2" in result.raw

    def test_differentiate_trig(self, engine):
        """Test differentiating trig function."""
        expr = engine.parse("sin(x)")
        result = engine.differentiate(expr, "x")
        assert "cos" in result.raw

    def test_integrate_polynomial(self, engine):
        """Test integrating polynomial."""
        expr = engine.parse("2*x")
        result = engine.integrate(expr, "x")
        assert result.is_valid
        assert "x**2" in result.raw

    def test_definite_integral(self, engine):
        """Test definite integral."""
        expr = engine.parse("x")
        result = engine.integrate(expr, "x", lower="0", upper="1")
        assert result.is_valid
        assert result.raw == "1/2"


class TestSymPyEngineSolve:
    """Tests for equation solving."""

    def test_solve_linear(self, engine):
        """Test solving linear equation."""
        expr = engine.parse("x - 2")
        solutions = engine.solve(expr, "x")
        assert len(solutions) == 1
        assert solutions[0].raw == "2"

    def test_solve_quadratic(self, engine):
        """Test solving quadratic equation."""
        expr = engine.parse("x**2 - 4")
        solutions = engine.solve(expr, "x")
        assert len(solutions) == 2


class TestSymPyEngineSubstitution:
    """Tests for expression substitution."""

    def test_substitute_number(self, engine):
        """Test substituting a number."""
        expr = engine.parse("x + 1")
        result = engine.substitute(expr, {"x": 2})
        assert result.is_valid
        assert result.raw == "3"

    def test_substitute_expression(self, engine):
        """Test substituting an expression."""
        expr = engine.parse("f(x)")
        # Note: This tests symbolic substitution
        result = engine.substitute(expr, {"x": "a + b"})
        assert result.is_valid


class TestSymPyEngineEquality:
    """Tests for expression equality checking."""

    def test_equals_identical(self, engine):
        """Test identical expressions."""
        expr1 = engine.parse("x + 1")
        expr2 = engine.parse("x + 1")
        assert engine.equals(expr1, expr2)

    def test_equals_equivalent(self, engine):
        """Test equivalent expressions."""
        expr1 = engine.parse("(x + 1)**2")
        expr2 = engine.parse("x**2 + 2*x + 1")
        assert engine.equals(expr1, expr2)

    def test_not_equals(self, engine):
        """Test non-equal expressions."""
        expr1 = engine.parse("x")
        expr2 = engine.parse("x + 1")
        assert not engine.equals(expr1, expr2)


class TestSymPyEngineRobustParsing:
    """Tests that the engine uses the unified parser for reserved names and equations."""

    def test_parse_reserved_beta(self, engine):
        """beta should be parsed as a variable, not the Beta function."""
        expr = engine.parse("beta * x + beta**2")
        assert expr.is_valid
        assert "beta" in expr.raw

    def test_parse_multi_letter_identifier(self, engine):
        """Multi-letter identifiers like nut must not be split."""
        expr = engine.parse("nut * du/dy")
        assert expr.is_valid
        assert "nut" in expr.raw

    def test_parse_natural_equation(self, engine):
        """Natural ``A = B`` notation should parse to an Equality."""
        expr = engine.parse("x**2 + 1 = y")
        assert expr.is_valid
        assert expr.expr_type.name == "EQUATION"

    def test_parse_leibniz_derivative(self, engine):
        """Leibniz notation ``dX/dY`` should be converted to Derivative."""
        expr = engine.parse("dk/dt")
        assert expr.is_valid
        assert "Derivative" in expr.raw

    def test_parse_unicode_greek(self, engine):
        """Unicode Greek letters should be converted to ASCII identifiers."""
        expr = engine.parse("β * x")
        assert expr.is_valid
        assert "beta" in expr.raw

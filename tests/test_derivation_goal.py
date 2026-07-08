"""Tests for Phase 4 - DerivationGoal parsing and pattern selection."""

from __future__ import annotations

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.derivation_goal import DerivationGoal, parse_target_expression  # noqa: E402
from symkit.domain.derivation_pattern import DerivationPattern  # noqa: E402


class TestDerivationGoalParsing:
    def test_parse_simple_text(self):
        goal = DerivationGoal.from_text("derive Navier-Stokes equations from conservation laws")
        assert goal.text == "derive Navier-Stokes equations from conservation laws"
        assert goal.target_form == "derive_expression"
        assert goal.domain == "fluid_dynamics"

    def test_solve_for_target_form(self):
        goal = DerivationGoal.from_text("solve for k in first-order elimination")
        assert goal.target_form == "solve_for_k"
        assert "k" in goal.target_variables

    def test_reduce_symbols_target_form(self):
        goal = DerivationGoal.from_text("reduce the number of variables to x and t")
        assert goal.target_form == "reduce_symbols"

    def test_extract_variables(self):
        goal = DerivationGoal.from_text("derive F = m*a + b*v")
        variables = set(goal.target_variables)
        assert "F" in variables
        assert "m" in variables
        assert "a" in variables
        assert "b" in variables
        assert "v" in variables

    def test_natural_language_goal_does_not_capture_phrase(self):
        goal = DerivationGoal.from_text(
            "derive the escape velocity of a planet from conservation of kinetic energy and gravitational potential energy"
        )
        assert goal.target_expression is None

    def test_article_a_filtered_in_natural_language(self):
        goal = DerivationGoal.from_text(
            "derive the escape velocity of a planet from conservation of kinetic energy"
        )
        assert "a" not in goal.target_variables

    def test_single_letter_variable_kept_in_math_context(self):
        goal = DerivationGoal.from_text("derive F = m a")
        assert "a" in goal.target_variables

    def test_detect_quantum_domain(self):
        goal = DerivationGoal.from_text("derive schrodinger equation from operator correspondence")
        assert goal.domain == "quantum_mechanics"

    def test_extract_assumptions(self):
        goal = DerivationGoal.from_text("derive NS in incompressible steady state flow")
        assert "incompressible" in goal.assumptions
        assert "steady state" in goal.assumptions

    def test_parse_target_expression(self):
        expr = parse_target_expression("x**2 + 2*x + 1")
        assert expr is not None

    def test_parse_target_expression_with_reserved_name(self):
        expr = parse_target_expression("beta * omega + S")
        assert expr is not None
        assert "beta" in str(expr)

    def test_parse_target_expression_equation(self):
        expr = parse_target_expression("x**2 + 1 = y")
        assert expr is not None
        assert "Eq" in str(expr)


class TestDerivationPatternFromGoal:
    def test_conservation_pattern(self):
        goal = DerivationGoal.from_text("derive from conservation and constitutive")
        assert DerivationPattern.from_goal(goal) == DerivationPattern.CONSERVATION_CONSTITUTIVE

    def test_variational_pattern(self):
        goal = DerivationGoal.from_text("derive using energy minimization")
        assert DerivationPattern.from_goal(goal) == DerivationPattern.VARIATIONAL

    def test_operator_pattern(self):
        goal = DerivationGoal.from_text("use operator correspondence to quantize")
        assert DerivationPattern.from_goal(goal) == DerivationPattern.OPERATOR_CORRESPONDENCE

    def test_series_pattern(self):
        goal = DerivationGoal.from_text("approximate using taylor series")
        assert DerivationPattern.from_goal(goal) == DerivationPattern.SERIES_APPROXIMATION

    def test_eigenmode_pattern(self):
        goal = DerivationGoal.from_text("find normal modes of the system")
        assert DerivationPattern.from_goal(goal) == DerivationPattern.EIGENMODE_ANALYSIS

    def test_default_direct_manipulation(self):
        goal = DerivationGoal.from_text("simplify the expression")
        assert DerivationPattern.from_goal(goal) == DerivationPattern.DIRECT_MANIPULATION

"""Tests for Phase 4 - DerivationPlanner."""

from __future__ import annotations

import sys
from pathlib import Path

import sympy as sp

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.derivation_goal import DerivationGoal  # noqa: E402
from symkit.domain.derivation_session import (  # noqa: E402
    DerivationSession,
    DerivationStep,
    OperationType,
    StepStatus,
)


def _session_with_expression(
    expr: sp.Basic,
    goal: DerivationGoal | None = None,
    steps: list[DerivationStep] | None = None,
    extra_formulas: list[str] | None = None,
) -> DerivationSession:
    session = DerivationSession(
        session_id="test",
        name="test",
        domain="general",
        current_expression=expr,
        goal=goal,
        steps=steps or [],
    )
    if extra_formulas:
        for i, f in enumerate(extra_formulas, start=1):
            session.load_formula(f, formula_id=f"f{i}", set_as_current=False)
    return session


class TestDerivationPlanner:
    def test_no_expression_suggests_load_formula(self):
        session = DerivationSession(session_id="test", name="test")
        steps = session.plan_next_steps(max_steps=5)
        assert steps[0]["tool"] == "session_load_formula"

    def test_solve_for_x_suggests_solve(self):
        goal = DerivationGoal.from_text("solve for x in x**2 + b*x + c")
        session = _session_with_expression(sp.sympify("x**2 + b*x + c"), goal=goal)
        suggestions = session.plan_next_steps(max_steps=5)
        tools = [s["tool"] for s in suggestions]
        assert "math" in tools
        assert any(
            s.get("operation") == "solve" and s["tool"] == "math"
            for s in suggestions
        )

    def test_target_match_suggests_complete(self):
        goal = DerivationGoal.from_text("derive x**2 + 2*x + 1")
        session = _session_with_expression(sp.sympify("x**2 + 2*x + 1"), goal=goal)
        suggestions = session.plan_next_steps(max_steps=5)
        assert any(s["tool"] == "session_complete" for s in suggestions)

    def test_failed_step_suggests_rollback_and_assume(self):
        goal = DerivationGoal.from_text("derive x")
        failed_step = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="simplify",
            input_expressions={},
            output_expression="x + y",
            output_latex="x + y",
            sympy_command="simplify",
            status=StepStatus.FAILED,
        )
        session = _session_with_expression(
            sp.sympify("x + y"),
            goal=goal,
            steps=[failed_step],
        )
        suggestions = session.plan_next_steps(max_steps=5)
        tools = [s["tool"] for s in suggestions]
        assert "session_rollback" in tools
        assert "assume_for_step" in tools

    def test_failed_single_step_rollback_hint_is_valid(self):
        """The suggested rollback target must be a valid step number.

        With one failed step the only valid rollback target is 0 (reset all).
        The planner must not suggest ``to_step=1`` (no-op) or any out-of-range
        value.
        """
        goal = DerivationGoal.from_text("derive x")
        failed_step = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="simplify",
            input_expressions={},
            output_expression="x + y",
            output_latex="x + y",
            sympy_command="simplify",
            status=StepStatus.FAILED,
        )
        session = _session_with_expression(
            sp.sympify("x + y"),
            goal=goal,
            steps=[failed_step],
        )
        suggestions = session.plan_next_steps(max_steps=5)
        rollback = next(s for s in suggestions if s["tool"] == "session_rollback")
        # step_count == 1 -> max(0, 1 - 1) == 0 (reset), which is the only
        # valid target when there is a single step.
        assert "to_step=0" in rollback["example"]

    def test_reduce_symbols_suggests_substitution(self):
        goal = DerivationGoal.from_text("reduce variables x and y")
        session = _session_with_expression(
            sp.sympify("x + y"),
            goal=goal,
            extra_formulas=["x = 2*y"],
        )
        suggestions = session.plan_next_steps(max_steps=5)
        tools = [s["tool"] for s in suggestions]
        assert "session_suggest_formulas" in tools
        assert any(
            s["tool"] == "math" and s.get("operation") == "substitute"
            for s in suggestions
        )

    def test_unconstrained_symbols_suggests_assume(self):
        session = _session_with_expression(sp.sympify("x + y + z"))
        suggestions = session.plan_next_steps(max_steps=5)
        tools = [s["tool"] for s in suggestions]
        assert "assume_for_step" in tools

    def test_equation_suggests_simplify_and_expand(self):
        session = _session_with_expression(sp.Eq(sp.Symbol('x'), sp.Symbol('y') + 1))
        suggestions = session.plan_next_steps(max_steps=5)
        ops = [s.get('operation') for s in suggestions if s['tool'] == 'math']
        assert 'simplify' in ops
        assert 'expand' in ops

    def test_complexity_increasing_suggests_simplify(self):
        goal = DerivationGoal.from_text("derive x")
        simple = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="simplify",
            input_expressions={},
            output_expression="x + 1",
            output_latex="x + 1",
            sympy_command="simplify",
        )
        complex_step = DerivationStep(
            step_number=2,
            operation=OperationType.EXPAND,
            description="expand",
            input_expressions={},
            output_expression="x**3 + 3*x**2 + 3*x + 1",
            output_latex="x**3 + 3*x**2 + 3*x + 1",
            sympy_command="expand",
        )
        session = _session_with_expression(
            sp.sympify("x**3 + 3*x**2 + 3*x + 1"),
            goal=goal,
            steps=[simple, complex_step],
        )
        suggestions = session.plan_next_steps(max_steps=5)
        assert any(
            s["tool"] == "math" and s.get("operation") == "simplify"
            for s in suggestions
        )

    def test_max_steps_limits_output(self):
        goal = DerivationGoal.from_text("derive equation")
        session = _session_with_expression(sp.sympify("x + y + z"), goal=goal)
        suggestions = session.plan_next_steps(max_steps=2)
        assert len(suggestions) <= 2


class TestDerivationPlannerRobustParsing:
    """The planner should parse target expressions with reserved names and equations."""

    def test_target_expression_with_reserved_beta(self):
        goal = DerivationGoal.from_text('derive beta * x = y')
        session = _session_with_expression(
            sp.Eq(sp.Symbol('beta') * sp.Symbol('x'), sp.Symbol('y')),
            goal=goal,
        )
        suggestions = session.plan_next_steps(max_steps=5)
        assert any(s["tool"] == "session_complete" for s in suggestions)

    def test_target_expression_natural_equation(self):
        goal = DerivationGoal.from_text('derive x**2 + 1 = y')
        session = _session_with_expression(sp.Eq(sp.Symbol('x')**2 + 1, sp.Symbol('y')), goal=goal)
        suggestions = session.plan_next_steps(max_steps=5)
        assert any(s["tool"] == "session_complete" for s in suggestions)

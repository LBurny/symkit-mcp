"""DerivationPlanner — Goal-aware derivation step planner.

Provides next-step operation suggestions based on the current session state,
target expression, and derivation history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sympy as sp

from symkit.domain.expression_parser import parse_expression_string

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationSession


class DerivationPlanner:
    """Plan the next derivation operation based on the goal and session state."""

    def plan_next_steps(
        self,
        session: DerivationSession,
        max_steps: int = 5,
    ) -> list[dict[str, Any]]:
        """Return a list of suggested next-step operations."""
        suggestions: list[dict[str, Any]] = []
        if session.current_expression is None:
            suggestions.append({
                "tool": "session_load_formula",
                "reason": "No current expression. Load a base formula to begin.",
                "example": 'session_load_formula("x**2 + y**2")',
            })
            return suggestions[:max_steps]

        expr = session.current_expression
        goal = session.goal
        free_symbols = {str(s) for s in expr.free_symbols}

        # 1. Last step failed verification: suggest fixes
        if session.steps and session.steps[-1].status.value == "failed":
            suggestions.append({
                "tool": "session_verify_step",
                "reason": "Last step failed verification. Inspect the failure and consider rollback.",
                "example": "session_verify_step()",
            })
            suggestions.append({
                "tool": "session_rollback",
                "reason": "Rollback to before the failed step if the failure is not recoverable.",
                "example": f"session_rollback(to_step={max(0, session.step_count - 1)})",
            })
            suggestions.append({
                "tool": "assume_for_step",
                "reason": "Add missing assumptions that might make the step valid.",
                "example": 'assume_for_step("x", "positive")',
            })

        # 2. Goal is solve_for_x
        if goal and goal.target_form and goal.target_form.startswith("solve_for_"):
            target_var = goal.target_form.split("_", 2)[-1]
            if target_var in free_symbols and not self._is_solved_for(expr, target_var):
                suggestions.append({
                    "tool": "math",
                    "operation": "solve",
                    "reason": f"Goal is to solve for {target_var}. Apply solve operation.",
                    "example": f'math("solve", "{expr}", variable="{target_var}", session=True)',
                })

        # 3. Target expression exists: compare gap with target
        if goal and goal.target_expression:
            target_expr = self._parse(goal.target_expression)
            if target_expr is not None:
                if self._expressions_equal(expr, target_expr):
                    suggestions.append({
                        "tool": "session_complete",
                        "reason": "Current expression matches the target. Complete the derivation.",
                        "example": 'session_complete(description="Target reached")',
                    })
                else:
                    suggestions.append({
                        "tool": "math",
                        "operation": "simplify",
                        "reason": "Current expression does not yet match the target. Simplify to get closer.",
                        "example": 'math("simplify", session=True)',
                    })
                    if goal.target_variables:
                        missing = set(goal.target_variables) - free_symbols
                        extra = free_symbols - set(goal.target_variables)
                        if missing and extra:
                            suggestions.append({
                                "tool": "session_suggest_formulas",
                                "reason": f"Missing variables {sorted(missing)}; find a formula to substitute out {sorted(extra)}.",
                                "example": "session_suggest_formulas()",
                            })

        # 4. Goal reduce_symbols: suggest substitution
        if goal and goal.target_form == "reduce_symbols" and len(free_symbols) > 1 and session.formulas:
            suggestions.append({
                "tool": "session_suggest_formulas",
                "reason": "Goal is to reduce the number of variables. Look for a substitution formula.",
                "example": "session_suggest_formulas()",
            })
            suggestions.append({
                "tool": "math",
                "operation": "substitute",
                "reason": "Substitute a relationship to eliminate one variable.",
                "example": 'math("substitute", session=True)',
            })

        # 5. Symbols without assumptions
        unconstrained = self._unconstrained_symbols(session, free_symbols)
        if unconstrained:
            suggestions.append({
                "tool": "assume_for_step",
                "reason": f"Symbols without assumptions: {', '.join(unconstrained)}. Add assumptions to improve simplification and verification.",
                "example": f'assume_for_step("{unconstrained[0]}", "positive")',
            })

        # 6. Expression is increasingly complex: suggest simplification
        if self._is_complexity_increasing(session):
            suggestions.append({
                "tool": "math",
                "operation": "simplify",
                "reason": "Expression complexity increased. Simplify before continuing.",
                "example": 'math("simplify", session=True)',
            })

        # 7. Equation form: suggest handling both sides
        if isinstance(expr, sp.Equality):
            suggestions.append({
                "tool": "math",
                "operation": "simplify",
                "reason": "Current expression is an equation. Simplify both sides.",
                "example": 'math("simplify", session=True)',
            })
            suggestions.append({
                "tool": "math",
                "operation": "expand",
                "reason": "Expand the equation to compare terms.",
                "example": 'math("expand", session=True)',
            })

        # 8. Fallback suggestions
        if not suggestions:
            suggestions.append({
                "tool": "math",
                "operation": "simplify",
                "reason": "No specific goal heuristic matched. Simplify and reassess.",
                "example": 'math("simplify", session=True)',
            })
            suggestions.append({
                "tool": "session_explain",
                "reason": "Get a natural-language summary of the derivation so far.",
                "example": "session_explain()",
            })

        return suggestions[:max_steps]

    @staticmethod
    def _parse(expr_str: str) -> sp.Basic | None:
        expr, _ = parse_expression_string(expr_str.replace("^", "**"), convert_equation=True)
        return expr

    @staticmethod
    def _expressions_equal(left: sp.Basic, right: sp.Basic) -> bool:
        try:
            if isinstance(left, sp.Equality) and isinstance(right, sp.Equality):
                return bool(
                    sp.simplify((left.lhs - left.rhs) - (right.lhs - right.rhs)) == 0
                )
            return bool(sp.simplify(left - right) == 0)
        except Exception:
            return False

    @staticmethod
    def _is_solved_for(expr: sp.Basic, var: str) -> bool:
        """Check whether the expression is already in Eq(var, ...) form."""
        if not isinstance(expr, sp.Equality):
            return False
        return str(expr.lhs) == var and var not in {str(s) for s in expr.rhs.free_symbols}

    @staticmethod
    def _unconstrained_symbols(session: DerivationSession, free_symbols: set[str]) -> list[str]:
        """Return symbols in the current expression that have no assumptions set in the assumption engine."""
        assumptions = session.assumption_engine.get_assumptions()
        return sorted(
            s for s in free_symbols
            if s not in assumptions or not assumptions[s]
        )

    @staticmethod
    def _is_complexity_increasing(session: DerivationSession) -> bool:
        """Return True if the latest step is more complex than the previous one."""
        if len(session.steps) < 2:
            return False
        try:
            prev_expr = sp.sympify(session.steps[-2].output_expression)
            curr_expr = sp.sympify(session.steps[-1].output_expression)
            prev_ops = int(sp.count_ops(prev_expr))
            curr_ops = int(sp.count_ops(curr_expr))
            return curr_ops > prev_ops * 1.5
        except Exception:
            return False

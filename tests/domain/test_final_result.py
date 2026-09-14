"""D8: the headline result must not be hijacked by a known-failed step.

``complete()`` reported ``representative_expression()`` as ``final_expression``
even when that step had already been judged ``failed`` (task-06: a trailing
dimensionally wrong equation became the headline answer, with only a one-line
warning).  ``select_headline`` returns the last non-failed step output and
reports whether failed steps were skipped; ``complete()`` uses it to fall back
and surfaces ``final_expression_skipped_failed`` + a ``note`` naming the failed
step.  A session with no failed steps is byte-for-byte unchanged.
"""

from __future__ import annotations

import json

import sympy as sp

from symkit.domain.derivation_goal import DerivationGoal
from symkit.domain.derivation_session import (
    DerivationSession,
    DerivationStep,
    OperationType,
)
from symkit.domain.final_result import select_headline

# The exact response keys complete() produced before D8; a session without a
# failed step must not gain or lose any of them.
_LEGACY_COMPLETE_KEYS = {
    "final_expression",
    "final_latex",
    "formulas_used",
    "goal",
    "name",
    "progress",
    "provenance",
    "session_id",
    "status",
    "steps",
    "success",
    "target_reached",
    "total_steps",
    "verification_summary",
    "warnings",
}


def _step(number: int, output: str, status: str) -> DerivationStep:
    return DerivationStep(
        step_number=number,
        operation=OperationType.CUSTOM,
        description="probe",
        input_expressions={},
        output_expression=output,
        output_latex="",
        sympy_command="manual_record",
        verification_result=json.dumps({"status": status, "message": "", "details": {}}),
    )


class TestSelectHeadline:
    def test_skips_trailing_failed_step(self) -> None:
        steps = [
            _step(1, "a + b", "verified"),
            _step(2, "b - a", "verified"),
            _step(3, "wrong", "failed"),
        ]
        expression, skipped = select_headline(steps)
        assert expression == "b - a"
        assert skipped is True

    def test_no_failed_step_is_not_skipped(self) -> None:
        steps = [_step(1, "a + b", "verified"), _step(2, "a*b", "verified")]
        expression, skipped = select_headline(steps)
        assert expression == "a*b"
        assert skipped is False

    def test_all_failed_returns_no_headline(self) -> None:
        expression, skipped = select_headline([_step(1, "x", "failed")])
        assert expression is None
        assert skipped is True


class TestCompleteSkipsFailedStep:
    def _session_with_failed_tail(self) -> DerivationSession:
        session = DerivationSession(session_id="d8", name="d8")
        goal = DerivationGoal.from_text("derive z", domain="general")
        goal.target_variables = ["z"]
        session.set_goal(goal)
        session.load_formula("m*a", formula_id="f1")
        from symkit.domain.expression_parser import parse_user_expression

        eq, _ = parse_user_expression("z = m*a")
        assert isinstance(eq, sp.Equality)
        session._add_step(  # noqa: SLF001 - mirrors session_record_step
            operation=OperationType.CUSTOM,
            description="bad dimension equation",
            input_expressions={"original": "z = m*a"},
            output_expr=eq,
            sympy_command="manual_record",
            prior_expr=session.current_expression,
        )
        session.current_expression = eq
        # Force a FAILED verdict on the tail step (the task-06 shape).
        session.steps[-1].verification_result = json.dumps(
            {"status": "failed", "message": "dimension mismatch", "details": {}}
        )
        return session

    def test_final_expression_is_last_non_failed_step(self) -> None:
        session = self._session_with_failed_tail()
        # Sanity: the legacy outcome really did pick the failed step, so the
        # assertion below is a genuine regression guard.
        assert str(session.outcome_expression()) == "Eq(z, a*m)"

        result = session.complete()

        assert result["final_expression"] == "a*m"
        assert result["final_expression_skipped_failed"] is True
        assert "step 2" in result["note"]
        assert "2" in result["note"]

    def test_no_failed_step_keeps_legacy_response(self) -> None:
        session = DerivationSession(session_id="d8-clean", name="d8-clean")
        session.load_formula("m*a", formula_id="f1")
        result = session.complete()
        assert set(result.keys()) == _LEGACY_COMPLETE_KEYS
        assert result["final_expression"] == "a*m"


class TestZeroConvergenceIsTheHeadline:
    """A self-check step that converges exactly to 0 is the conclusion.

    r14 task-08: step 20's unevaluated integral was reported as the final
    expression while the true closing step (step 21, output ``0``) was skipped
    because it carries no free symbols.  ``outcome_expression`` and
    ``complete()`` must both land on the zero step so ``session_show``'s
    ``result_expression`` and ``session_complete``'s ``final_expression`` agree.
    """

    def test_constant_zero_self_check_beats_symbolic_intermediate(self) -> None:
        session = DerivationSession(session_id="zero-headline", name="zero-headline")
        goal = DerivationGoal.from_text("derive the wave residual", domain="general")
        goal.target_variables = ["c", "x", "t"]
        session.set_goal(goal)
        session.load_formula("c*x + t", formula_id="f1")
        session._add_step(  # noqa: SLF001 - mirrors math(simplify, session=True)
            operation=OperationType.SIMPLIFY,
            description="residual self-check",
            input_expressions={"original": "c*x + t - (c*x + t)"},
            output_expr=sp.Integer(0),
            sympy_command="math('simplify', ...)",
            prior_expr=session.current_expression,
        )
        session.current_expression = sp.Integer(0)
        # The residual check verifies cleanly; mark it so complete()'s
        # failed-step fallback does not kick in.
        session.steps[-1].verification_result = json.dumps(
            {"status": "verified", "message": "expressions are equal", "details": {}}
        )
        session.insert_note_after_step(after_step=2, note="residual is zero")

        assert str(session.outcome_expression()) == "0"
        result = session.complete(require_target_match=False)
        assert result["final_expression"] == "0"

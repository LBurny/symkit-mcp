"""Round-19 black-box regression suites (session deliverable / progress / notes).

Covers the verified defects fixed in this round:

* F2a — a closing exact-zero self-check must not stay the headline when later
  steps produce a nonzero (constant) output;
* F2b — ``session_complete(final_expression=...)`` lets the operator declare the
  deliverable explicitly, and the auto-save writes that expression;
* F4  — ``matches_target`` / ``target_reached`` become tri-state and only
  *explicit* target variables may confer a match (text-mined ones cannot);
* F5  — pure note steps are excluded from verification statistics;
* F10 — a failing ``math(session=True)`` call leaves a note-type trace;
* F19 — recorded steps carry the session's current assumptions;
* F20 — ``safe_load_expression`` must not turn a stored ``E``/``I`` display
  string into Euler's number / the imaginary unit.
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
from symkit.domain.expr_io import safe_load_expression
from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


class TestF2aZeroOutcomeSuperseded:
    def test_later_nonzero_constant_clears_zero_outcome(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f2a-superseded")
        tools["math"]("simplify", "x + x", session=True)
        tools["math"]("simplify", "(x + x) - (x + x)", session=True)
        tools["math"]("evalf", "sqrt(2)", session=True)

        show = tools["session_show"]()
        assert show["result_expression"] == "2*x", show
        assert show["result_latex"] == sp.latex(2 * sp.Symbol("x"))

    def test_trailing_zero_still_is_the_conclusion(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f2a-trailing-zero")
        tools["math"]("simplify", "x + x", session=True)
        tools["math"]("simplify", "(x + x) - (x + x)", session=True)

        show = tools["session_show"]()
        assert show["result_expression"] == "0", show


class TestF2bFinalExpressionOverride:
    def test_valid_override_wins_and_is_saved(
        self, fresh_session_manager, tmp_path, monkeypatch
    ):
        import yaml

        from symkit.infrastructure import derivation_repository as repo_mod

        _ = fresh_session_manager
        monkeypatch.chdir(tmp_path)
        repo_mod._repository = None
        tools = _tools()
        tools["session_start"]("f2b-override")
        tools["math"]("simplify", "x + x", session=True)

        result = tools["session_complete"](
            description="declared deliverable",
            final_expression="2*x",
            auto_save=True,
        )
        assert result["success"] is True, result
        assert result["final_expression"] == "2*x"
        assert result["final_latex"] == sp.latex(2 * sp.Symbol("x"))
        assert "saved_to" in result, result
        with open(result["saved_to"], encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["expression"] == "2*x"

    def test_unparseable_override_returns_error_without_completing(
        self, fresh_session_manager
    ):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f2b-bad")
        tools["math"]("simplify", "x + x", session=True)

        result = tools["session_complete"](final_expression="x +")
        assert result["success"] is False, result
        assert result.get("error")
        # The session must still be active and untouched (not completed).
        steps = tools["session_get_steps"]()
        assert steps["success"] is True
        assert steps["count"] == 1

    def test_override_completes_without_current_expression(
        self, fresh_session_manager, tmp_path, monkeypatch
    ):
        """r19x task-14: a dimension-only chain has no current expression, but an
        explicit ``final_expression`` is itself the deliverable — completion must
        not be blocked by the empty-current guard."""
        import yaml

        from symkit.infrastructure import derivation_repository as repo_mod

        _ = fresh_session_manager
        monkeypatch.chdir(tmp_path)
        repo_mod._repository = None
        tools = _tools()
        tools["session_start"]("f2b-dimension-only")
        tools["math"]("dimension", "m*v", session=True)
        session = _state.get_session()
        assert session is not None
        assert session.current_expression is None  # the guard's trigger

        result = tools["session_complete"](
            description="declared deliverable",
            final_expression="Eq(E, m*v**2)",
            auto_save=True,
        )
        assert result["success"] is True, result
        expected = sp.Eq(sp.Symbol("E"), sp.Symbol("m") * sp.Symbol("v") ** 2)
        assert result["final_expression"] == str(expected)
        assert result["final_latex"] == sp.latex(expected)
        assert "saved_to" in result, result
        with open(result["saved_to"], encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["expression"] == str(expected)

    def test_no_override_still_requires_current_expression(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f2b-no-override")
        tools["math"]("dimension", "m*v", session=True)
        session = _state.get_session()
        assert session is not None
        assert session.current_expression is None

        result = tools["session_complete"](auto_save=False)
        assert result["success"] is False, result
        assert "No result expression" in result["error"]

    def test_override_keeps_skipped_failed_flag_coherent(
        self, fresh_session_manager
    ):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f2b-failed-tail")
        tools["math"]("simplify", "x + x", session=True)
        tools["math"]("simplify", "x + x", session=True)
        session = _state.get_session()
        assert session is not None
        session.steps[-1].output_expression = "3*x"
        session.steps[-1].output_srepr = sp.srepr(3 * sp.Symbol("x"))
        session.steps[-1].verification_result = json.dumps(
            {"status": "failed", "message": "wrong", "details": {}}
        )

        result = tools["session_complete"](
            final_expression="5*y", auto_save=False
        )
        assert result["success"] is True, result
        assert result["final_expression"] == "5*y"
        assert result["final_expression_skipped_failed"] is True
        assert "override" in result["note"]


class TestF4TriStateTargets:
    def test_goal_without_target_is_null(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f4-null", goal="解释这个推导过程的物理含义")
        tools["math"]("simplify", "x + x", session=True)

        show = tools["session_show"]()
        progress = show["progress"]
        assert progress["matches_target"] is None
        assert progress["remaining_gaps"] == []
        assert progress["progress_score"] == 0.0

        done = tools["session_complete"](auto_save=False)
        assert done["target_reached"] is None

    def test_auto_extracted_targets_confer_nothing(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f4-auto", goal="derive the wall damping function f_w")
        tools["session_record_step"](expression="f_w", description="wall damping")
        tools["session_record_step"](expression="k = 1", description="constant")

        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is None
        assert progress["progress_score"] == 0.0
        assert progress["remaining_gaps"] == []
        done = tools["session_complete"](auto_save=False)
        assert done["target_reached"] is None

    def test_explicit_missing_targets_hint_at_target_expression(
        self, fresh_session_manager
    ):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](
            "f4-missing", goal="derive the thing", target_variables=["P0", "P1"]
        )
        tools["session_record_step"](expression="x", description="probe")

        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is False
        assert any(
            "pass target_expression instead" in gap
            for gap in progress["remaining_gaps"]
        ), progress["remaining_gaps"]

    def test_explicit_present_targets_match(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](
            "f4-present", goal="derive the thing", target_variables=["x"]
        )
        tools["session_load_formula"]("2*x", formula_id="f1")

        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is True

    def test_failed_overall_downgrades_target_reached(self):
        session = DerivationSession(session_id="f4-failed", name="f4-failed")
        goal = DerivationGoal.from_text("verify the wave equation")
        goal.target_variables = ["c", "x", "t"]
        session.set_goal(goal)
        goal_step = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="verified step covering every target",
            input_expressions={},
            output_expression="c*x + t",
            output_latex="",
            sympy_command="math('simplify', ...)",
            verification_result=json.dumps(
                {"status": "verified", "message": "", "details": {}}
            ),
        )
        failed_step = DerivationStep(
            step_number=2,
            operation=OperationType.SIMPLIFY,
            description="dimensionally impossible",
            input_expressions={},
            output_expression="m + s",
            output_latex="",
            sympy_command="math('simplify', ...)",
            verification_result=json.dumps(
                {"status": "failed", "message": "bad", "details": {}}
            ),
        )
        session.steps = [goal_step, failed_step]
        session.current_expression = sp.Symbol("c") * sp.Symbol("x") + sp.Symbol("t")

        progress = session.compute_progress()
        assert progress["matches_target"] is True
        result = session.complete(require_target_match=False)
        assert result["verification_summary"]["overall"] == "failed"
        assert result["target_reached"] is False


class TestF5NoteStepsExcludedFromVerification:
    def test_note_step_not_counted(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f5")
        tools["session_load_formula"]("x**2")
        tools["math"]("diff", "x**3", variable="x", session=True)
        tools["session_add_note"]("operator observation")

        verify = tools["session_verify_session"]()
        assert verify["total"] == 2, verify
        assert verify["inconclusive_steps"] == [], verify

        steps = tools["session_get_steps"]()
        assert steps["count"] == 3
        assert any("operator observation" in s["description"] for s in steps["steps"])

    def test_complete_summary_excludes_note(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f5-complete")
        tools["session_load_formula"]("x**2")
        tools["math"]("diff", "x**3", variable="x", session=True)
        tools["session_add_note"]("operator observation")

        result = tools["session_complete"](auto_save=False)
        summary = result["verification_summary"]
        assert summary["total"] == 2, summary
        assert summary["inconclusive_steps"] == [], summary


class TestF10FailedCallLeavesTrace:
    def test_failed_math_call_records_note_step(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f10")
        before = tools["session_get_steps"]()["count"]

        failed = tools["math"](
            "substitute", "1/x", substitution={"x": "0"}, session=True
        )
        assert failed["success"] is False, failed

        after = tools["session_get_steps"]()
        assert after["count"] == before + 1
        trace = after["steps"][-1]
        assert trace["description"].startswith("substitute failed:"), trace
        assert "note_type" in trace["input_expressions"]

        # The trace is a note: it must not inflate verification statistics.
        verify = tools["session_verify_session"]()
        assert verify["total"] == before, verify

    def test_successful_retry_records_its_own_step(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f10-retry")
        tools["math"]("substitute", "1/x", substitution={"x": "0"}, session=True)
        retry = tools["math"]("substitute", "1/x", substitution={"x": "2"}, session=True)
        assert retry["success"] is True, retry
        assert retry.get("step") == 2


class TestF19StepAssumptions:
    def test_recorded_step_carries_session_assumptions(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f19")
        tools["assume"]({"x": "positive", "t": "real"})
        tools["math"]("simplify", "sqrt(x**2)", session=True)

        steps = tools["session_get_steps"]()["steps"]
        assert steps[-1]["assumptions"], steps[-1]
        joined = " | ".join(steps[-1]["assumptions"])
        assert "x is positive" in joined, joined
        assert "t is real" in joined, joined


class TestF20EReservedName:
    def test_safe_load_expression_keeps_E_symbol(self):
        expr = safe_load_expression("-m*v**3 + E", "")
        assert expr is not None
        assert sp.Symbol("E") in expr.free_symbols
        assert sp.latex(expr) == sp.latex(
            sp.Symbol("E") - sp.Symbol("m") * sp.Symbol("v") ** 3
        )

    def test_safe_load_expression_keeps_I_symbol(self):
        expr = safe_load_expression("I + 1", "")
        assert expr is not None
        assert sp.Symbol("I") in expr.free_symbols

    def test_complete_headline_fallback_keeps_E(self):
        session = DerivationSession(session_id="f20", name="f20")
        session.load_formula("-m*v**3 + E", formula_id="f1")
        failed = DerivationStep(
            step_number=2,
            operation=OperationType.SIMPLIFY,
            description="wrong tail",
            input_expressions={},
            output_expression="3*x",
            output_latex="",
            sympy_command="math('simplify', ...)",
            verification_result=json.dumps(
                {"status": "failed", "message": "wrong", "details": {}}
            ),
        )
        session.steps.append(failed)

        result = session.complete(require_target_match=False)
        expected = sp.Symbol("E") - sp.Symbol("m") * sp.Symbol("v") ** 3
        assert result["final_expression"] == str(expected)
        assert result["final_latex"] == sp.latex(expected)


class TestF32StartTargetExpression:
    """F32 (wave 3): ``session_start`` must accept an explicit ``target_expression``.

    It had no such parameter, so an explicit target was swallowed by the tool
    schema and the goal recorded ``null`` (r19x-task-08).
    """

    def test_target_expression_is_recorded_verbatim(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        target = "Omega_res = sqrt(omega0**2 - 2*beta**2)"
        res = tools["session_start"](
            "wave3-target",
            goal="derive the resonance frequency of the driven oscillator",
            target_expression=target,
        )
        assert res["success"], res
        assert res["goal"]["target_expression"] == target, res["goal"]

    def test_target_expression_drives_progress_match(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](
            "wave3-target-progress",
            goal="derive the resonance frequency condition",
            target_expression="sqrt(omega0**2 - 2*beta**2)",
        )
        res = tools["math"]("simplify", "sqrt(omega0**2 - 2*beta**2)", session=True)
        assert res["success"], res
        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is True, progress

    def test_passing_neither_keeps_tri_state_null(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("wave3-target-null", goal="derive the terminal velocity")
        res = tools["math"]("simplify", "x + x", session=True)
        assert res["success"], res
        progress = tools["session_show"]()["progress"]
        assert progress["matches_target"] is None, progress

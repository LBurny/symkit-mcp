"""Round-23 F12: target matching over an equation target, one verdict, honest gaps.

Probe references: audit3[3] (``target_expression="Phi = ..."`` plus a bare RHS
deliverable reported ``target_reached: false``) and task-04
(``target_reached: false`` next to ``progress.matches_target: true``).
"""

from __future__ import annotations

import json
from typing import Any

import sympy as sp

from symkit_mcp.tools._state import set_session
from tests.conftest import MockMCP


def _tools() -> dict[str, Any]:
    from symkit_mcp.tools.math import register_math_tools
    from symkit_mcp.tools.session import register_session_tools

    mcp = MockMCP()
    register_session_tools(mcp)
    register_math_tools(mcp)
    return mcp.tools


def test_equation_target_is_reached_by_its_rhs(fresh_session_manager: Any) -> None:
    """audit3[3]: an Eq target matches the bare side the step delivered."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](
        name="f12-eq",
        target_expression="Phi = q*d*cos(theta)/(4*pi*epsilon0*r**2)",
    )
    tools["session_record_step"](
        expression="q*d*cos(theta)/(4*pi*epsilon0*r**2)", description="RHS"
    )

    done = tools["session_complete"](
        final_expression="q*d*cos(theta)/(4*pi*epsilon0*r**2)", auto_save=False
    )

    assert done["target_reached"] is True, done
    assert done["progress"]["matches_target"] is True, done["progress"]
    assert not any("does not match" in w for w in done.get("warnings") or []), done


def test_unrelated_deliverable_does_not_reach_equation_target(
    fresh_session_manager: Any,
) -> None:
    """Negative guard: an unrelated final must not be green-lit by a target."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](
        name="f12-miss", target_expression="Phi = q*d*cos(theta)/(4*pi*epsilon0*r**2)"
    )
    tools["session_record_step"](expression="x", description="probe")

    done = tools["session_complete"](final_expression="1 + x", auto_save=False)

    assert done["target_reached"] is False
    assert done["progress"]["matches_target"] is False
    assert any("does not match" in w for w in done.get("warnings") or []), done


def test_target_reached_agrees_with_progress_when_overall_failed() -> None:
    """task-04: the two fields come from one judgment, not two."""
    from symkit.domain.derivation_goal import DerivationGoal
    from symkit.domain.derivation_session import (
        DerivationSession,
        DerivationStep,
        OperationType,
    )

    session = DerivationSession(session_id="f12-task04", name="f12-task04")
    goal = DerivationGoal.from_text("verify the wave equation")
    goal.target_variables = ["c", "x", "t"]
    session.set_goal(goal)

    def _step(number: int, output: str, verdict: str) -> DerivationStep:
        return DerivationStep(
            step_number=number,
            operation=OperationType.SIMPLIFY,
            description="step",
            input_expressions={},
            output_expression=output,
            output_latex="",
            sympy_command="math('simplify', ...)",
            verification_result=json.dumps(
                {"status": verdict, "message": "", "details": {}}
            ),
        )

    session.steps = [
        _step(1, "c*x + t", "verified"),
        _step(2, "m + s", "failed"),
    ]
    session.current_expression = sp.Symbol("c") * sp.Symbol("x") + sp.Symbol("t")

    result = session.complete(require_target_match=False)

    assert result["verification_summary"]["overall"] == "failed"
    assert result["target_reached"] is False
    assert result["target_reached"] == result["progress"]["matches_target"]


def test_missing_target_hint_does_not_advise_a_passed_target_expression(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](
        name="f12-hint",
        goal="derive the thing",
        target_variables=["P0", "P1"],
        target_expression="Z_c = 3/8",
    )
    tools["session_record_step"](expression="x", description="probe")

    gaps = tools["session_show"]()["progress"]["remaining_gaps"]
    joined = " ".join(gaps)
    assert "Missing target variables" in joined, gaps
    assert "pass target_expression instead" not in joined, gaps


def teardown_function() -> None:
    set_session(None)

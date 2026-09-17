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


_AMPLITUDE = "A = F0/sqrt((k - m*omega**2)**2 + (c*omega)**2)"


def _start_damped(tools: dict[str, Any]) -> dict[str, Any]:
    """Verbatim r23 G4 probe: a comma-joined ``target_variables`` string."""
    return tools["session_start"](
        name="damped-forced-oscillator",
        goal="derive the amplitude A and phase phi of the damped forced oscillator",
        target_expression=_AMPLITUDE,
        target_variables="A, phi",
    )


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


def test_target_reached_diverges_from_progress_when_overall_failed() -> None:
    """task-04 / G9: the two fields MAY differ (intentional) on a dirty chain.

    ``matches_target`` is expression-level truth; ``target_reached`` stays
    conservative and requires a clean session.  F12b forced them equal, which
    erased that distinction; r23 G9 restores it and requires a disclosure.
    """
    from symkit.domain.derivation_goal import DerivationGoal
    from symkit.domain.derivation_session import (
        DerivationSession,
        DerivationStep,
        OperationType,
    )

    session = DerivationSession(session_id="g9-task04", name="g9-task04")
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
    # Intentional divergence: the expression does match, the chain is dirty.
    assert result["progress"]["matches_target"] is True
    assert result["target_reached"] is False
    assert any("failed steps" in w for w in result["warnings"]), result["warnings"]


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


def test_comma_separated_target_variables_are_split(fresh_session_manager: Any) -> None:
    """G4-1: ``target_variables="A, phi"`` is two targets, not one name."""
    _ = fresh_session_manager
    tools = _tools()
    _start_damped(tools)
    tools["session_record_step"](expression=_AMPLITUDE, description="amplitude")

    done = tools["session_complete"](final_expression=_AMPLITUDE, auto_save=False)

    progress = done["progress"]
    gaps = " ".join(progress["remaining_gaps"])
    assert "A, phi" not in gaps, progress
    assert "Missing target variables: phi" in gaps, progress
    # phi is genuinely absent: the honest verdict is false, and the score must
    # not read as a full one next to it (G4-2).
    assert progress["matches_target"] is False, progress
    assert done["target_reached"] is False, done
    assert progress["progress_score"] < 1.0, progress
    # Locked invariant: a full score is equivalent to an expression-level match.
    assert (progress["progress_score"] == 1.0) == (progress["matches_target"] is True), progress


def test_dirty_session_discloses_a_matching_deliverable(
    fresh_session_manager: Any,
) -> None:
    """G9: the expression matches, but a failed audit step blocks the verdict.

    ``matches_target`` is expression-level truth and must stay true; the
    conservative ``target_reached`` is false; the response must say why instead
    of leaving a silent "not reached".
    """
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](
        name="g9-dirty",
        goal="derive the harmonic oscillator energy levels",
        target_expression="E_n = hbar*omega*(n + 1/2)",
        target_variables=["E_n", "n"],
    )
    tools["math"]("simplify", "hbar*omega*(n + 1/2)", session=True)
    tools["session_record_step"](
        expression="hbar*omega*(n + 1/2) = hbar*omega",
        description="audit negative control",
    )

    done = tools["session_complete"](
        final_expression="hbar*omega*(n + 1/2)", auto_save=False
    )

    assert done["verification_summary"]["overall"] == "failed", done
    assert done["verification_summary"]["failed_steps"] == [2], done
    progress = done["progress"]
    assert progress["matches_target"] is True, progress
    assert progress["progress_score"] == 1.0, progress
    assert progress["remaining_gaps"] == [], progress
    assert done["target_reached"] is False, done
    warnings = " ".join(done["warnings"])
    assert "failed steps" in warnings, done["warnings"]
    assert "does not match" not in warnings, done["warnings"]


def test_clean_session_makes_the_three_fields_agree(
    fresh_session_manager: Any,
) -> None:
    """G9 control: drop the audit step and reached/matches/score all agree."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](
        name="g9-clean",
        goal="derive the harmonic oscillator energy levels",
        target_expression="E_n = hbar*omega*(n + 1/2)",
        target_variables=["E_n", "n"],
    )
    tools["math"]("simplify", "hbar*omega*(n + 1/2)", session=True)

    done = tools["session_complete"](
        final_expression="hbar*omega*(n + 1/2)", auto_save=False
    )

    assert done["verification_summary"]["overall"] == "verified", done
    progress = done["progress"]
    assert progress["matches_target"] is True, progress
    assert progress["progress_score"] == 1.0, progress
    assert progress["remaining_gaps"] == [], progress
    assert done["target_reached"] is True, done
    assert not any("failed steps" in w for w in done["warnings"]), done["warnings"]


def test_single_string_target_variable_is_still_one_target(
    fresh_session_manager: Any,
) -> None:
    """G4 red line 2: a comma-free string keeps its existing meaning."""
    _ = fresh_session_manager
    tools = _tools()
    started = tools["session_start"](
        name="g4-single", goal="deliver A", target_variables="A"
    )
    assert started["goal"]["target_variables"] == ["A"], started["goal"]
    tools["session_record_step"](expression="A", description="deliver A")

    progress = tools["session_show"]()["progress"]
    assert not any("Missing target variables" in g for g in progress["remaining_gaps"]), progress


def test_list_target_variables_are_unchanged(fresh_session_manager: Any) -> None:
    """G4 red line 2: the list form keeps working verbatim."""
    _ = fresh_session_manager
    tools = _tools()
    started = tools["session_start"](
        name="g4-list", goal="deliver A and phi", target_variables=["A", "phi"]
    )
    assert started["goal"]["target_variables"] == ["A", "phi"], started["goal"]
    tools["session_record_step"](expression="A + phi", description="both delivered")

    progress = tools["session_show"]()["progress"]
    assert not any("Missing target variables" in g for g in progress["remaining_gaps"]), progress


def test_absent_target_variables_keep_the_null_tri_state(
    fresh_session_manager: Any,
) -> None:
    """G4 red line 2: no / empty ``target_variables`` behavior is unchanged."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="g4-none", goal="derive the thing")
    tools["session_record_step"](expression="x", description="probe")

    progress = tools["session_show"]()["progress"]
    assert progress["matches_target"] is None, progress
    assert progress["progress_score"] == 0.0, progress
    assert progress["remaining_gaps"] == [], progress

    tools["session_start"](name="g4-empty", goal="derive the thing", target_variables=[])
    tools["session_record_step"](expression="x", description="probe")

    progress = tools["session_show"]()["progress"]
    assert progress["matches_target"] is None, progress
    assert progress["progress_score"] == 0.0, progress
    assert progress["remaining_gaps"] == [], progress

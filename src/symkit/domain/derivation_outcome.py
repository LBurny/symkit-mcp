"""Outcome selection and goal-progress evaluation for a derivation session.

Split out of :mod:`symkit.domain.derivation_session` (bylaw section 5.1) so the
frozen session module stays within its recorded size.  Everything here is pure
domain: it reads a session-like object (steps, goal, current expression) and
returns plain data.

Three concerns live here:

* :func:`select_representative_expression` — which step output is the outcome;
* :func:`compute_goal_progress` — the tri-state ``matches_target`` report
  (``None`` = no checkable target, ``True`` / ``False`` otherwise);
* :func:`is_note_step` — the note marker ``verify_derivation`` uses to keep
  pure-text notes out of the verification statistics (r19 F5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sympy as sp

from symkit.domain.derivation_goal import (
    DerivationGoal,
    narrow_target_variables,
    parse_target_expression,
    target_variables_reached,
)
from symkit.domain.expr_io import safe_load_expression
from symkit.domain.final_result import candidate_names, headline_fallback, symbol_names
from symkit.domain.step_verifier import verification_result_from_json

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationSession, DerivationStep


def _free_symbols(value: Any) -> set[sp.Symbol]:
    if isinstance(value, (list, tuple)):
        return {s for item in value for s in _free_symbols(item)}
    return value.free_symbols if isinstance(value, sp.Basic) else set()


def is_note_step(step: DerivationStep) -> bool:
    """Whether *step* is a pure-text note recorded outside the math chain.

    ``insert_note_after_step`` (and the failed-call trace added in r19 F10)
    mark notes with a ``note_type`` provenance key and no computed output.
    Notes are visible in ``session_get_steps`` but must not be counted as
    verification evidence — they carry no claim to verify.
    """
    inputs = step.input_expressions or {}
    if "note_type" not in inputs:
        return False
    return not (step.output_expression or "").strip() and not (
        step.output_srepr or ""
    ).strip()


def select_representative_expression(
    steps: list[DerivationStep],
    targets: list[str],
    current: sp.Basic | None,
) -> sp.Basic | None:
    """The step output that best represents the derivation's outcome.

    Selection order (see ``DerivationSession.representative_expression``):

    1. A closing exact-zero self-check; ANY later step output — symbolic or a
       nonzero constant — clears it, while note/empty-output steps leave the
       chain untouched (r19 F2a).
    2. The last symbolic output involving a goal target variable.
    3. The last lineage output, else the last symbolic output, else *current*.
    """
    candidates: list[tuple[sp.Basic, set[str], bool, bool]] = []
    previous_srepr = ""
    zero_outcome: sp.Basic | None = None
    for step in steps:
        is_custom = getattr(step.operation, "value", step.operation) == "custom"
        chained = bool(step.output_srepr) and step.input_srepr == previous_srepr
        previous_srepr = step.output_srepr or previous_srepr  # notes keep the chain
        out = safe_load_expression(step.output_expression, step.output_srepr)
        if out is None:
            continue
        if not out.free_symbols:
            # A later nonzero constant (a numeric probe, a delivered constant)
            # supersedes an earlier zero self-check (r19 F2a).
            zero_outcome = out if out == 0 else None
            continue
        candidates.append((out, symbol_names(out), is_custom, chained))
        zero_outcome = None

    if zero_outcome is not None:
        return zero_outcome
    if not candidates:
        return current

    if targets:
        for out, _names, _is_custom, _chained in reversed(candidates):
            if set(targets) & candidate_names(out, _names):
                return out

    lineage: set[str] = set()
    lineage_members: list[sp.Basic] = []
    for out, names, is_custom, chained in candidates:
        if is_custom:
            continue
        if not lineage or names & lineage or chained:
            lineage |= names
            lineage_members.append(out)
    if lineage_members:
        return lineage_members[-1]
    return candidates[-1][0]


def steps_summary(steps: list[DerivationStep]) -> list[dict[str, Any]]:
    """Compact per-step rows for the ``session_complete`` return.

    Embedding every step's full record in the completion payload overflowed
    the client's tool-output budget on long derivations and pushed the
    ``warnings`` / ``target_reached`` fields out of the visible preview
    (operator feedback, 2026-09-16).  The full records stay behind
    ``session_get_steps``; this summary only answers "which steps exist and
    how did each verify".
    """
    rows: list[dict[str, Any]] = []
    for step in steps:
        record = None
        if step.verification_result:
            try:
                record = verification_result_from_json(step.verification_result)
            except (TypeError, ValueError):
                record = None
        rows.append(
            {
                "step_number": step.step_number,
                "operation": step.operation.value,
                "status": record.status.value if record else None,
            }
        )
    return rows


def target_coverage(
    session: DerivationSession, current: sp.Basic
) -> tuple[list[str], set[str], bool]:
    """``(targets, missing, reached)`` for the goal's *explicit* targets."""
    symbols: list[set[str]] = []
    verified: list[set[str]] = []
    for step in session.steps:
        out = safe_load_expression(step.output_expression, step.output_srepr)
        if out is None or not out.free_symbols:
            continue
        names = {str(s) for s in out.free_symbols}
        symbols.append(names)
        try:
            if verification_result_from_json(step.verification_result).is_verified:
                verified.append(names)
        except (TypeError, ValueError):
            continue
    goal = session.goal
    raw_targets = goal.target_variables if goal is not None else []
    targets = narrow_target_variables(raw_targets, symbols)
    seen = {str(s) for s in _free_symbols(current)} | set().union(*symbols)
    return targets, set(targets) - seen, target_variables_reached(targets, verified)


_MISSING_HINT = (
    "targets not present in any step output; if these are labels for results "
    "rather than required symbols, pass target_expression instead"
)


def resolve_target_reached(
    matches: bool | None, overall: str | None
) -> bool | None:
    """``target_reached`` mirrors the tri-state and never green-lights a failure.

    A chain whose verification ``overall`` is ``"failed"`` cannot have reached
    its target, however well the current expression matches (r19 F4).
    """
    if matches is None:
        return None
    reached = bool(matches)
    if reached and overall == "failed":
        return False
    return reached


def completion_outcome(
    session: DerivationSession,
    failed_steps: list[int],
    override: sp.Basic | None,
) -> tuple[sp.Basic | None, dict[str, Any]]:
    """The headline for a completed session, plus the fallback response fields.

    A caller-declared ``override`` (explicit ``final_expression``) is the
    deliverable and always wins over the heuristic selection; the failed-step
    fallback fields are still returned so the caller can note the override
    (r19 F2b).
    """
    outcome, fields = headline_fallback(
        session.outcome_expression(), session.steps, failed_steps
    )
    return (override if override is not None else outcome), fields


def _has_checkable_target(goal: DerivationGoal, target: sp.Basic | None, form: str) -> bool:
    """Whether the goal defines anything progress can be checked against."""
    if target is not None:
        return True
    if goal.has_explicit_target_variables():
        return True
    return form not in ("", "derive_expression")


def _expression_progress(
    session: DerivationSession,
    form: str,
    target: sp.Basic | None,
    current: sp.Basic,
) -> tuple[list[str], float, bool]:
    """``(gaps, score, matches)`` from the target expression and target form."""
    gaps: list[str] = []
    score = 0.0
    matches = False

    if target is not None:
        if session._expressions_equivalent(
            current, target, session.assumption_engine.get_assumptions()
        ):
            matches = True
            score = 1.0
        else:
            gaps.append("Current expression does not match target expression")
            score = 0.5

    # solve for X counts as solved when ANY step output (or the current
    # expression) isolates X on the left — later steps may move the current
    # expression onward legitimately (run-005/006).
    if form.startswith("solve_for_"):
        var = form.split("_", 2)[-1]
        solved = isinstance(current, sp.Equality) and str(current.lhs) == var
        if not solved:
            for step in session.steps:
                out = safe_load_expression(step.output_expression, step.output_srepr)
                if isinstance(out, sp.Equality) and str(out.lhs) == var:
                    solved = True
                    break
        if solved:
            matches = True
            score = max(score, 1.0)
        else:
            gaps.append(f"Not yet solved for {var}")

    if form == "reduce_symbols":
        score, gap = _reduction_progress(session, current, score)
        if gap:
            gaps.append(gap)
    return gaps, score, matches


def _reduction_progress(
    session: DerivationSession, current: sp.Basic, score: float
) -> tuple[float, str | None]:
    """Score the ``reduce_symbols`` form against the first step's symbol count."""
    if not session.steps:
        return score, "No initial expression to compare"
    initial = safe_load_expression(
        session.steps[0].output_expression, session.steps[0].output_srepr
    )
    if initial is None:
        return score, "Could not load initial expression for comparison"
    try:
        initial_symbols = len(initial.free_symbols)
    except Exception:
        return score, "Could not compute symbol reduction"
    current_symbols = len(_free_symbols(current))
    if current_symbols < initial_symbols:
        return max(score, (initial_symbols - current_symbols) / initial_symbols), None
    return score, "Number of variables has not decreased"


def _coverage_progress(
    session: DerivationSession,
    goal: DerivationGoal,
    form: str,
    current: sp.Basic,
    gaps: list[str],
    score: float,
    matches: bool,
) -> tuple[float, bool]:
    """Fold explicit-target coverage into ``(score, matches)``."""
    targets, missing, reached = target_coverage(session, current)
    if not targets:
        return score, matches
    if missing:
        gaps.append(
            f"Missing target variables: {', '.join(sorted(missing))}; {_MISSING_HINT}"
        )
    else:
        matches = matches or reached
        score = max(score, 0.7)
    if not goal.target_expression and not form.startswith("solve_for_"):
        score = max(score, 0.7 * (1.0 - len(missing) / max(len(targets), 1)))
    return score, matches


def compute_goal_progress(session: DerivationSession) -> dict[str, Any]:
    """Progress of the current expression relative to the session goal.

    Tri-state contract (r19 F4): when a goal exists but defines NEITHER a
    ``target_expression`` NOR explicit ``target_variables`` (and the form is the
    default), nothing is checkable — ``matches_target`` is ``None``,
    ``remaining_gaps`` is empty and the score is 0.0.  Text-mined variables are
    a heuristic and never confer a match.
    """
    goal = session.goal
    if goal is None:
        return {
            "has_goal": False,
            "progress_score": 0.0,
            "matches_target": False,
            "remaining_gaps": ["No goal set"],
        }

    form = goal.target_form or ""
    target = parse_target_expression(goal.target_expression) if goal.target_expression else None
    if not _has_checkable_target(goal, target, form):
        return {
            "has_goal": True,
            "goal": goal.to_dict(),
            "progress_score": 0.0,
            "matches_target": None,
            "remaining_gaps": [],
        }

    current = session.current_expression
    if current is None:
        return {
            "has_goal": True,
            "goal": goal.to_dict(),
            "progress_score": 0.0,
            "matches_target": False,
            "remaining_gaps": ["No current expression"],
        }

    gaps, score, matches = _expression_progress(session, form, target, current)
    if goal.has_explicit_target_variables():
        score, matches = _coverage_progress(session, goal, form, current, gaps, score, matches)

    return {
        "has_goal": True,
        "goal": goal.to_dict(),
        "progress_score": score,
        "matches_target": matches,
        "remaining_gaps": gaps,
    }


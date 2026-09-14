"""Certify derivation-session steps with the Lean kernel (application layer).

This use case is strictly additive: it re-proves the algebraic-equality steps of
an existing session and records the kernel verdict under
``step.verification_result["details"]["lean"]``. It never rewrites ``step.status``,
``verification_result.status`` or the session's overall verdict — an ``unproven``
Lean result only means Lean automation could not close the goal, not that the
step is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import sympy as sp

from symkit.domain.derivation_session import OperationType, StepStatus
from symkit.domain.lean_translation import clear_denominators, translate_equality
from symkit.domain.lean_types import LeanOutcome, UntranslatableError
from symkit.domain.step_verifier import (
    verification_result_from_json,
    verification_result_to_json,
)
from symkit.domain.value_objects import VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationSession, DerivationStep
    from symkit.domain.lean_types import LeanChecker, LeanStatement

ELIGIBLE_OPERATIONS = frozenset(
    {
        OperationType.SIMPLIFY,
        OperationType.EXPAND,
        OperationType.FACTOR,
        OperationType.COMBINE,
        OperationType.CANCEL,
    }
)

_NOTE = (
    "unproven means Lean automation could not prove the equality; "
    "it does not imply the step is wrong. trivial means both sides were "
    "identical (e.g. x = x or 0 = 0), so nothing was verified."
)


@dataclass
class _StepRecord:
    """Mutable per-step bookkeeping while the batch is being certified."""

    step: DerivationStep
    certification: str
    lane: str | None = None
    statement: str | None = None
    statement_obj: LeanStatement | None = None
    reason: str | None = None
    detail: str | None = None
    record: VerificationResult | None = None
    outcome: LeanOutcome | None = None
    input_expr: sp.Basic | None = None
    output_expr: sp.Basic | None = None


def certify_session(
    session: DerivationSession,
    checker: LeanChecker,
    *,
    assumptions: dict[str, dict[str, bool]] | None = None,
) -> dict[str, Any]:
    """Re-prove eligible algebraic steps with Lean and attach the results.

    Args:
        session: The derivation session to certify (mutated in place).
        checker: A ``LeanChecker`` batch backend.
        assumptions: Extra per-symbol facts (``{"cp": {"nonzero": True}}``) to
            bind as Lean hypotheses. A step that records its own assumptions
            keeps them; every other step falls back to these merged over the
            session pool, so a missing denominator assumption can be supplied
            at certify time instead of re-running the whole derivation.

    Returns:
        The certification report; existing verification verdicts are preserved.
    """
    user_assumptions = assumptions or {}
    entries = _plan_steps(session, user_assumptions)
    statements: list[LeanStatement] = []
    for entry in entries:
        if entry.statement_obj is not None:
            statements.append(entry.statement_obj)
    outcomes = checker.check(statements)
    by_name = {outcome.name: outcome for outcome in outcomes}
    for entry in entries:
        statement = entry.statement_obj
        if statement is None:
            continue
        outcome = by_name.get(statement.name)
        if outcome is None:
            continue
        entry.outcome = outcome
        entry.certification = "proven" if outcome.proven else "unproven"
        entry.detail = outcome.detail
        _attach_lean(entry.step, outcome, statement.lane, entry.statement or "")
    _retry_unproven_field_lanes(entries, checker, session, user_assumptions)
    session._update_timestamp()
    if session._persist_path:
        session.save()
    return _build_report(entries)


def _retry_unproven_field_lanes(
    entries: list[_StepRecord],
    checker: LeanChecker,
    session: DerivationSession,
    user_assumptions: dict[str, dict[str, bool]],
) -> None:
    """Re-check unproven field statements as cleared polynomial (ring) goals.

    ``field_simp`` can leave an ``unsolved goals`` state even when the
    denominator-free polynomial identity is provable by ``ring``.  Multiplying
    both sides by the denominator factors and re-running the ring lane recovers
    those false negatives; a recovered step is reported with lane
    ``field+ring`` (r16 task-15).
    """
    retries = [
        entry
        for entry in entries
        if entry.statement_obj is not None
        and entry.statement_obj.lane == "field"
        and entry.outcome is not None
        and not entry.outcome.proven
        and entry.input_expr is not None
        and entry.output_expr is not None
    ]
    if not retries:
        return
    assumptions = _merge_assumptions(session.assumption_engine.get_assumptions(), user_assumptions)
    pending = [
        (entry, statement)
        for entry in retries
        if (statement := _retry_statement(entry, assumptions)) is not None
    ]
    if not pending:
        return
    outcomes = {o.name: o for o in checker.check([s for _, s in pending])}
    for entry, statement in pending:
        outcome = outcomes.get(statement.name)
        if outcome is None or not outcome.proven:
            continue
        entry.outcome = outcome
        entry.certification = "proven"
        entry.detail = outcome.detail
        entry.lane = "field+ring"
        entry.statement = _render_statement(statement)
        _attach_lean(entry.step, outcome, entry.lane, entry.statement)


def _retry_statement(
    entry: _StepRecord, assumptions: dict[str, dict[str, bool]]
) -> LeanStatement | None:
    """Build the cleared ring goal for one unproven field step, or ``None``."""
    assert entry.statement_obj is not None
    assert entry.input_expr is not None and entry.output_expr is not None
    try:
        lhs, rhs = clear_denominators(entry.input_expr, entry.output_expr)
        bases = _multiplier_bases(entry.input_expr, entry.output_expr)
        if not bases and not (lhs.free_symbols or rhs.free_symbols):
            # No denominator factors to bind and nothing left in the goal:
            # a ``0 = 0``-shaped theorem certifies nothing observable, so
            # keep the honest ``unproven`` verdict.
            return None
        # The cleared form is equivalent to the original only where the
        # multiplier is nonzero, so its factors must stay bound as
        # hypotheses even though the cleared goal itself has no division.
        retry_assumptions = dict(assumptions)
        for base in bases:
            retry_assumptions.setdefault(str(base), {})["nonzero"] = True
        return translate_equality(
            lhs,
            rhs,
            assumptions=retry_assumptions,
            name=entry.statement_obj.name,
        )
    except UntranslatableError:
        return None


def _multiplier_bases(lhs: sp.Basic, rhs: sp.Basic) -> list[sp.Basic]:
    """Denominator factors the field→ring clearing divided by, in order."""
    bases: list[sp.Basic] = []
    for expr in (lhs, rhs):
        for power in expr.atoms(sp.Pow):
            if (
                isinstance(power.exp, sp.Integer)
                and power.exp.is_negative
                and power.base not in bases
            ):
                bases.append(power.base)
    return bases


def _plan_steps(
    session: DerivationSession, user_assumptions: dict[str, dict[str, bool]]
) -> list[_StepRecord]:
    """Classify every step and translate the eligible ones (no checker call)."""
    fallback = _merge_assumptions(
        session.assumption_engine.get_assumptions(), user_assumptions
    )
    entries: list[_StepRecord] = []
    for step in session.steps:
        if step.operation not in ELIGIBLE_OPERATIONS:
            # Name the operation so a reader can tell *why* the step never
            # reached the kernel; a bare `skipped` with reason null read as an
            # unexplained gap (round-lean task-01).
            entries.append(
                _StepRecord(
                    step,
                    "skipped",
                    reason=(
                        f"{step.operation.value} steps are outside the certified "
                        "algebraic fragment (only simplify/expand/factor/combine/"
                        "cancel are kernel-checked)"
                    ),
                )
            )
            continue
        entries.append(_plan_eligible(session, step, _step_assumptions(step, fallback)))
    return entries


def _merge_assumptions(
    pool: dict[str, dict[str, bool]], extra: dict[str, dict[str, bool]]
) -> dict[str, dict[str, bool]]:
    """Overlay ``extra`` facts on ``pool``, returning a fresh mapping."""
    merged = {symbol: dict(facts) for symbol, facts in pool.items()}
    for symbol, facts in extra.items():
        merged.setdefault(symbol, {}).update(facts)
    return merged


def _step_assumptions(
    step: DerivationStep, fallback: dict[str, dict[str, bool]]
) -> dict[str, dict[str, bool]]:
    """Assumptions to bind for one step: its own record, else the fallback pool.

    Preferring the recorded step assumptions keeps a global/session assumption
    that was set for another step from leaking a binder into this one; the
    fallback (merged session pool + certify-time assumptions) covers steps that
    record none (r16 task-15).
    """
    if not step.assumptions:
        return fallback
    parsed: dict[str, dict[str, bool]] = {}
    for clause in step.assumptions:
        parts = clause.replace(" is ", " ").split()
        if len(parts) < 2:
            continue
        props = parsed.setdefault(parts[0], {})
        for prop in parts[1:]:
            props[prop] = True
    return parsed or fallback


def _goal_is_trivial(input_expr: sp.Basic, output_expr: sp.Basic) -> bool:
    """True when both sides are structurally identical (``x = x`` or ``0 = 0``).

    ``ring`` discharges such a goal instantly, but it validates no algebra: a
    derivation whose every "proven" step is ``x = x`` looks fully certified while
    nothing was checked (round-17 B1). Such steps are reported as ``trivial``
    and kept out of the ``proven`` count.
    """
    return bool(input_expr == output_expr)


def _plan_eligible(
    session: DerivationSession,
    step: DerivationStep,
    assumptions: dict[str, dict[str, bool]],
) -> _StepRecord:
    """Translate one eligible step, or record why it cannot be translated."""
    record = _load_record(step)
    input_expr, output_expr = _rebuild_expressions(session, step)
    if input_expr is None or output_expr is None:
        return _StepRecord(
            step,
            "untranslatable",
            reason="step expressions could not be reconstructed",
            record=record,
        )
    if _goal_is_trivial(input_expr, output_expr):
        return _StepRecord(
            step,
            "trivial",
            reason="input and output are identical; the goal certifies no algebra",
            record=record,
        )
    if isinstance(input_expr, sp.Equality) or isinstance(output_expr, sp.Equality):
        return _StepRecord(
            step,
            "untranslatable",
            reason="equality-to-equality rewrites need linear_combination (v2)",
            record=record,
        )
    try:
        statement = translate_equality(
            input_expr,
            output_expr,
            assumptions=assumptions,
            name=f"symkit_step_{step.step_number:03d}",
        )
    except UntranslatableError as exc:
        return _StepRecord(step, "untranslatable", reason=str(exc), record=record)
    rendered = _render_statement(statement)
    return _StepRecord(
        step,
        "unknown",
        lane=statement.lane,
        statement=rendered,
        statement_obj=statement,
        record=record,
        input_expr=input_expr,
        output_expr=output_expr,
    )


def _render_statement(statement: LeanStatement) -> str:
    """Render the theorem header so hypotheses are visible in the report.

    Dropping the binders here silently turned a conditional theorem into an
    unconditional-looking claim (round-15 C-02 / S1).
    """
    binders: list[str] = []
    if statement.variables:
        binders.append(f"({' '.join(statement.variables)} : {statement.target_type})")
    binders.extend(f"({hypothesis})" for hypothesis in statement.hypotheses)
    prefix = f"{' '.join(binders)} : " if binders else ""
    return f"{prefix}{statement.lhs} = {statement.rhs}"


def _rebuild_expressions(
    session: DerivationSession, step: DerivationStep
) -> tuple[sp.Basic | None, sp.Basic | None]:
    """Rebuild ``(input, output)`` exactly as the dimensional post-check does.

    Mirrors ``symkit_mcp.tools._unit_context.apply_dimension_to_step``: this
    reuses the verifier's private parse entry points, kept private by the
    modularity ratchet (promote them to public methods when
    ``derivation_session.py`` is next split). Display strings are never
    re-parsed here (invariant I2).
    """
    assumptions = session.assumption_engine.get_assumptions()
    if step.operation == OperationType.CUSTOM:
        input_expr: sp.Basic | None = None
    else:
        input_expr = session.verifier._parse_step_input(step, assumptions)
        if input_expr is None:
            input_expr = session._resolve_prior_expr(step.step_number)
    output_expr = session.verifier._parse_archived(
        step.output_expression, step.output_srepr, assumptions
    )
    return input_expr, output_expr


def _load_record(step: DerivationStep) -> VerificationResult:
    """Read the step's verification record, defaulting to inconclusive."""
    if step.verification_result:
        return verification_result_from_json(step.verification_result)
    return VerificationResult(status=VerificationStatus.INCONCLUSIVE)


def _attach_lean(
    step: DerivationStep, outcome: LeanOutcome, lane: str, statement: str
) -> None:
    """Merge a ``details.lean`` sub-record without touching the existing verdict."""
    record = _load_record(step)
    details = {
        **record.details,
        "lean": {
            "method": "lean_kernel",
            "status": "proven" if outcome.proven else "unproven",
            "lane": lane,
            "statement": statement,
            "detail": outcome.detail,
        },
    }
    step.verification_result = verification_result_to_json(
        replace(record, details=details)
    )


def _build_report(entries: list[_StepRecord]) -> dict[str, Any]:
    """Shape the per-step rows, summary counts and verifier discrepancies."""
    return {
        "success": True,
        "lean_available": True,
        "summary": {
            "eligible": sum(
                1 for e in entries if e.step.operation in ELIGIBLE_OPERATIONS
            ),
            "proven": _count(entries, "proven"),
            "unproven": _count(entries, "unproven"),
            "trivial": _count(entries, "trivial"),
            "untranslatable": _count(entries, "untranslatable"),
            "skipped": _count(entries, "skipped"),
        },
        "steps": [_row(e) for e in entries],
        "discrepancies": _discrepancies(entries),
        "note": _NOTE,
    }


def _count(entries: list[_StepRecord], certification: str) -> int:
    return sum(1 for e in entries if e.certification == certification)


def _row(entry: _StepRecord) -> dict[str, Any]:
    return {
        "step_number": entry.step.step_number,
        "operation": entry.step.operation.value,
        "certification": entry.certification,
        "lane": entry.lane,
        "statement": entry.statement,
        "reason": entry.reason,
        "detail": entry.detail,
    }


def _discrepancies(entries: list[_StepRecord]) -> list[dict[str, Any]]:
    """Report cases where Lean and the heuristic verifier disagree (no rejudge)."""
    found: list[dict[str, Any]] = []
    for entry in entries:
        outcome = entry.outcome
        if outcome is None:
            continue
        if outcome.proven and entry.step.status == StepStatus.FAILED:
            found.append(
                {
                    "step_number": entry.step.step_number,
                    "kind": "lean_proven_but_step_failed",
                }
            )
        elif (
            not outcome.proven
            and entry.record is not None
            and entry.record.status == VerificationStatus.VERIFIED
        ):
            found.append(
                {
                    "step_number": entry.step.step_number,
                    "kind": "lean_unproven_but_step_verified",
                }
            )
    return found

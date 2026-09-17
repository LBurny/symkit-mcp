"""Verifier-side heuristics kept out of the size-frozen ``step_verifier``.

The step record carries its own assumption clauses (``session_record_step``'s
``assumptions=[...]``, and the session snapshot the math recorder writes).  The
verifier must judge the step under them, because a clause like ``z is positive``
decides whether ``2a/z**2 = 2a z/(z**2)**(3/2)`` is an identity (r23 F5).  The
clause syntax is the same ``"<symbol> is <properties>"`` the MCP tools accept;
parsing it here keeps the domain free of a presentation-layer import.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sympy as sp

from symkit.domain.assumption_binding import ASSUMPTION_KEYWORDS
from symkit.domain.value_objects import VerificationStatus


def parse_assumption_clauses(
    clauses: Sequence[str] | None,
) -> dict[str, dict[str, bool]]:
    """Parse ``"z is positive real"`` / ``"z positive"`` clauses into symbol props.

    Unparseable or unsupported clauses are skipped, never raised: the recording
    already stored them, and a malformed clause must not turn verification into a
    crash.
    """
    parsed: dict[str, dict[str, bool]] = {}
    for clause in clauses or ():
        if not isinstance(clause, str):
            continue
        parts = clause.strip().split()
        properties = (
            parts[2:] if len(parts) >= 3 and parts[1] in ("is", "has") else parts[1:]
        )
        if not parts or not parts[0].isidentifier() or not properties:
            continue
        if not all(prop in ASSUMPTION_KEYWORDS for prop in properties):
            continue
        parsed.setdefault(parts[0], {}).update(dict.fromkeys(properties, True))
    return parsed


def merge_step_assumptions(
    base: Mapping[str, Mapping[str, bool]] | None,
    clauses: Sequence[str] | None,
) -> dict[str, dict[str, bool]]:
    """Engine/session assumptions plus the step record's own clauses.

    Step-level properties win over the merged engine view for the same symbol,
    matching the engine's own session-above-domain priority.
    """
    merged = {name: dict(props) for name, props in (base or {}).items()}
    for name, props in parse_assumption_clauses(clauses).items():
        merged.setdefault(name, {}).update(props)
    return merged


def step_assumptions(engine: Any, step: Any) -> dict[str, dict[str, bool]]:
    """The assumption mapping :class:`StepVerifier` should judge ``step`` under."""
    base = engine.get_assumptions() if engine is not None else {}
    return merge_step_assumptions(base, getattr(step, "assumptions", None))


_DEFINITION_RECORDED_MESSAGE = (
    "Recorded equation is not verified: the left side is the single free symbol"
    " {name}, and the right side does not contain it, so this reads as a"
    " definition or model constant — unproven, not disproven (the sides differ by"
    " {diff}). definition recorded; record the closed form as an equation for a"
    " definitive verdict."
)


def bare_symbol_definition(expr: sp.Equality, diff: sp.Basic) -> str | None:
    """Message when a recorded equation reads as a bare-symbol definition.

    ``tau_c = pi/2`` names a constant on a single free symbol, determined by a
    closed-form right side; a definition is true by fiat, so it must not be
    judged "disproven" (r13 F6).  A compound LHS keeps the full identity check,
    and an unevaluated right side (``f(0)``) is not a determined value.
    """
    from sympy.core.function import AppliedUndef

    lhs = expr.lhs
    if not isinstance(lhs, sp.Symbol):
        return None
    if str(lhs) in {str(s) for s in expr.rhs.free_symbols}:
        return None
    if expr.rhs.atoms(AppliedUndef, sp.Integral, sp.Derivative, sp.Sum):
        return None
    return _DEFINITION_RECORDED_MESSAGE.format(name=lhs, diff=diff)


def matrix_equality(
    lhs: sp.Basic, rhs: sp.Basic
) -> tuple[VerificationStatus, str] | None:
    """Direct verdict when both sides are concrete matrices (r23 F7).

    A recorded ``Q.T*A*Q = Lambda`` is decidable by elementwise comparison, but
    the scalar identity machinery called ``simplify`` on a matrix difference and
    reported "unproven" — a false matrix equation escaped as inconclusive and a
    true one got only the tautological "boolean value preserved".
    """
    if not isinstance(lhs, sp.MatrixBase) or not isinstance(rhs, sp.MatrixBase):
        return None
    if lhs.shape != rhs.shape:
        return VerificationStatus.FAILED, (
            f"Equation is false: the sides have different shapes {lhs.shape}"
            f" and {rhs.shape}"
        )
    difference = lhs - rhs
    if difference.is_zero_matrix:
        return VerificationStatus.VERIFIED, "Identity verified: both sides are equal"
    return VerificationStatus.FAILED, f"Equation is false: the sides differ by {difference}"

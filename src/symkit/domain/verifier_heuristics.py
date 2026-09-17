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
from symkit.domain.numeric_evidence import is_numerically_zero
from symkit.domain.value_objects import VerificationResult, VerificationStatus


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
    " definition or model constant — unproven, not disproven{diff_clause}."
    " definition recorded; record the closed form as an equation for a"
    " definitive verdict."
)

# A matrix right side cannot be disclosed through a scalar ``lhs - rhs``
# difference (that subtraction is what raised for ``M = Matrix(...)``, G6 r23).
_MATRIX_DEFINITION_DIFF_CLAUSE = (
    " (the right side is a matrix object, so the sides are not scalar-comparable)"
)

_MIXED_MATRIX_MESSAGE = (
    "Recorded equation is not verified: one side is a matrix and the other is"
    " not, so no elementwise identity check is possible — unproven, not"
    " disproven. Record both sides as matrices of the same shape for a"
    " definitive verdict."
)


def _is_matrix_like(expr: sp.Basic) -> bool:
    """Whether ``expr`` is a concrete matrix or a symbolic matrix expression."""
    return isinstance(expr, (sp.MatrixBase, sp.MatrixExpr))


def _definition_message(expr: sp.Equality, diff: sp.Basic | None) -> str | None:
    """F6 reading when ``expr`` names a constant on a single free symbol."""
    from sympy.core.function import AppliedUndef

    lhs = expr.lhs
    if not isinstance(lhs, sp.Symbol):
        return None
    if str(lhs) in {str(s) for s in expr.rhs.free_symbols}:
        return None
    if expr.rhs.atoms(AppliedUndef, sp.Integral, sp.Derivative, sp.Sum):
        return None
    clause = (
        f" (the sides differ by {diff})"
        if diff is not None
        else _MATRIX_DEFINITION_DIFF_CLAUSE
    )
    return _DEFINITION_RECORDED_MESSAGE.format(name=lhs, diff_clause=clause)


def bare_symbol_definition(expr: sp.Equality, diff: sp.Basic) -> str | None:
    """Message when a recorded equation reads as a bare-symbol definition.

    ``tau_c = pi/2`` names a constant on a single free symbol, determined by a
    closed-form right side; a definition is true by fiat, so it must not be
    judged "disproven" (r13 F6).  A compound LHS keeps the full identity check,
    and an unevaluated right side (``f(0)``) is not a determined value.
    """
    return _definition_message(expr, diff)


def mixed_matrix_verdict(
    expr: sp.Equality,
) -> tuple[VerificationStatus, str] | None:
    """Verdict for a recorded equation mixing a scalar side with a matrix side.

    ``M = Matrix([[1,1],[1,0]])`` is the same bare-symbol definition as the
    scalar F6 case, but the shared identity machinery computed ``Symbol - Matrix``
    and raised ``TypeError`` (G6 r23), leaking an internal message.  A bare
    symbol LHS keeps the F6 definition reading; any other scalar/matrix mix is
    honestly inconclusive instead of a crash.  Two matrix sides return ``None``
    so the concrete comparison in :func:`matrix_equality` still decides.
    """
    lhs_matrix = _is_matrix_like(expr.lhs)
    rhs_matrix = _is_matrix_like(expr.rhs)
    if lhs_matrix == rhs_matrix:
        return None
    if not lhs_matrix and isinstance(expr.lhs, sp.Symbol):
        definition = _definition_message(expr, None)
        if definition is not None:
            return VerificationStatus.INCONCLUSIVE, definition
    return VerificationStatus.INCONCLUSIVE, _MIXED_MATRIX_MESSAGE


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


def symbolic_value_preserved(raw_diff: sp.Basic) -> bool:
    """Exact-zero proof for an operator step's value-preservation residual.

    ``sqrt(F0**2*(...)/D**2)`` equals ``F0/sqrt(D)`` when ``F0`` is positive, but
    plain ``simplify`` cannot reduce the difference, so a correct simplify step
    was reported as changing the value (r23 G8).  The residual's symbols already
    carry the step's effective assumptions (F5), and ``sqrtdenest`` cancels the
    radicals exactly under them.  Only an *exact* zero counts: these transforms
    are identities, so a genuinely nonzero residual is never promoted.
    """
    if not isinstance(raw_diff, sp.Basic):
        return False
    if raw_diff == 0:
        return True
    try:
        return bool(sp.simplify(sp.sqrtdenest(raw_diff)) == 0)
    except Exception:
        return False


def value_preserved(diff: sp.Basic, raw_diff: sp.Basic) -> bool:
    """Whether a simplify/expand/factor step preserved the expression value.

    The exact symbolic reduction runs first (r23 G8); sampling, which can only
    refuse rather than prove, is the fallback and keeps its historical wording.
    """
    if symbolic_value_preserved(raw_diff):
        return True
    if is_numerically_zero(diff):
        return True
    return is_numerically_zero(sp.simplify(sp.expand(raw_diff)))


def has_branch_cut_power(expr: sp.Basic) -> bool:
    """Whether ``expr`` carries a non-integer power of a not-positive base.

    ``(x**4)**(3/4)`` is ``|x|**3``: it equals ``x**3`` only on the principal
    branch, so a numeric probe at a negative point "refutes" a correct
    antiderivative (G11 r23).  ``sqrt(2)`` (positive base) and integer powers are
    not hazards.
    """
    if not isinstance(expr, sp.Basic) or isinstance(expr, sp.MatrixBase):
        return False
    for node in sp.preorder_traversal(expr):
        if (
            isinstance(node, sp.Pow)
            and node.exp.is_Integer is not True
            and node.base.is_positive is not True
        ):
            return True
    return False


def branch_positive_zero(residual: sp.Basic) -> bool:
    """Exact-zero proof for a residual read on the principal branch (G11).

    ``integrate(exp(-x**4), x)`` returns a ``lowergamma(1/4, x**4)``
    antiderivative whose derivative differs from ``exp(-x**4)`` only by
    ``(x**4)**(3/4)`` versus ``x**3``.  Refining the residual under ``x > 0``
    collapses that difference to exactly zero, while a genuine mismatch
    (``2*exp(-x**4)`` against ``exp(-x**4)``) stays nonzero under the same
    reading, so only a true identity is ever promoted.  ``refine`` carries the
    reading as a predicate, so no assumption-bearing ``Symbol`` is built
    (invariant I1).
    """
    if not isinstance(residual, sp.Expr):
        return False
    if residual == 0:
        return True
    free = sorted(residual.free_symbols, key=str)
    if not free:
        return False
    refined = sp.refine(residual, sp.And(*[sp.Q.positive(s) for s in free]))
    for candidate in (
        sp.simplify(refined),
        sp.gammasimp(sp.powsimp(refined, force=True)),
        sp.simplify(sp.gammasimp(refined)),
    ):
        if candidate == 0:
            return True
    return False


def reverse_check_verdict(
    derivative: sp.Basic, expected: sp.Basic
) -> VerificationResult:
    """Verdict from comparing ``d(output)/dv`` with the expected integrand.

    Extracted from :class:`StepVerifier` (bylaw §5.1 ratchet).  A residual with a
    branch-cut power is decided under the principal-branch reading first; if that
    cannot prove it zero, the numeric disagreement stays INCONCLUSIVE — sampling
    a branch-ambiguous residual disproves nothing (r11/r21 doctrine).  A residual
    free of such powers keeps the numeric FAILED for a genuine mismatch.
    """
    from symkit.domain.final_result import evaluate_pending, residual_verdict
    from symkit.domain.verification_guardrails import (
        drop_piecewise_constant_derivatives,
    )

    diff = sp.simplify(drop_piecewise_constant_derivatives(derivative) - expected)
    if is_numerically_zero(diff) or branch_positive_zero(diff):
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            message="Integration verified by differentiation",
            reverse_check=True,
        )
    status = residual_verdict(evaluate_pending(diff))
    if status == VerificationStatus.VERIFIED:
        return VerificationResult(
            status=status,
            message="Integration verified by numeric substitution",
            reverse_check=True,
        )
    if status == VerificationStatus.INCONCLUSIVE:
        return VerificationResult(
            status=status,
            message=(
                "Reverse differentiation did not match; numeric substitution "
                "inconclusive"
            ),
            details={"derivative": str(derivative), "expected": str(expected)},
            reverse_check=False,
        )
    if has_branch_cut_power(diff):
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message=(
                "Could not decide the reverse check: the residual carries a "
                "branch-cut power, so numeric sampling cannot settle it"
            ),
            details={"derivative": str(derivative), "expected": str(expected)},
            reverse_check=False,
        )
    return VerificationResult.failure(
        "Differentiation of integral does not match original",
        derivative=str(derivative),
        expected=str(expected),
        reverse_check=False,
    )

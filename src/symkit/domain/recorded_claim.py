"""Recorded-claim text machinery: splitting ``A = B`` claims and judging folds.

Extracted from ``final_result`` (bylaw §5.1 file-size ratchet). A recorded
claim whose sides are both numeric folds to a Boolean at parse time; the
helpers here rebuild the unevaluated equality so a residual stays
disclosable (r22 task-04) and grade a zero-free-symbol difference.
"""

from __future__ import annotations

import re

import sympy as sp

from symkit.domain.numeric_evidence import is_numerically_zero
from symkit.domain.value_objects import VerificationStatus

_UNEVALUATED_DIFFERENCE_MESSAGE = (
    "Recorded equation is not verified: the difference contains an unevaluated function"
    " application or operation ({terms}) — boundary conditions and model data are not"
    " checkable as identities; record them as notes or leave the function undefined."
)


def _unevaluated_terms(diff: sp.Basic) -> str:
    """Unevaluated applications/operations in a zero-free-symbol difference; ``""`` is a constant."""
    from sympy.core.function import AppliedUndef

    terms = diff.atoms(AppliedUndef) | diff.atoms(sp.Integral, sp.Derivative, sp.Sum)
    return ", ".join(sorted(str(term) for term in terms))


def numeric_difference_verdict(diff: sp.Basic) -> tuple[VerificationStatus, str]:
    """Verdict for a zero-free-symbol identity difference.

    A truncated decimal standing in for a closed form is equal within
    tolerance — inconclusive, not disproven (r22 task-04).
    """
    terms = _unevaluated_terms(diff)
    if terms:
        return (
            VerificationStatus.INCONCLUSIVE,
            _UNEVALUATED_DIFFERENCE_MESSAGE.format(terms=terms),
        )
    if is_numerically_zero(diff):
        return (
            VerificationStatus.INCONCLUSIVE,
            f"Numerically equal within tolerance (the sides differ by {diff}); "
            "exact equality is unproven — record the closed form instead of a "
            "truncated decimal to make this step verifiable",
        )
    return VerificationStatus.FAILED, f"Equation is false: the sides differ by {diff}"


_CLAIM_EQ = re.compile(r"^\s*Eq\s*\((.*)\)\s*$", re.DOTALL)


def equation_claim_sides(text: str) -> tuple[str, str] | None:
    """Split a recorded ``Eq(lhs, rhs)`` / ``lhs = rhs`` claim into its sides.

    Returns ``None`` for an ordinary expression.  Sides are returned as written,
    never re-parsed, so the caller binds symbols with its assumption-aware parser.
    """
    stripped = text.strip()
    match = _CLAIM_EQ.match(stripped)
    if match is not None:
        return _split_claim(match.group(1), ",")
    if any(op in stripped for op in ("==", "<=", ">=", "!=")):
        return None
    return _split_claim(stripped, "=")


def _split_claim(inner: str, separators: str) -> tuple[str, str] | None:
    """Split ``inner`` at its first depth-0 separator, skipping quotes."""
    depth = 0
    quoted = False
    for index, char in enumerate(inner):
        if char == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0 and char in separators:
            left, right = inner[:index].strip(), inner[index + 1:].strip()
            return (left, right) if left and right else None
    return None


def unevaluated_equality(expression: str) -> sp.Equality | None:
    """Rebuild a recorded ``A = B`` claim as ``Eq(lhs, rhs, evaluate=False)``.

    ``Eq`` folds to a Boolean at construction when both sides are numeric, so a
    recorded claim like ``pi = 3.14`` archives as ``False`` and the verdict
    loses the sides — no residual can be disclosed (r22 task-04).  Returns
    ``None`` when the text is not an equality or a side does not parse.
    """
    sides = equation_claim_sides(expression)
    if sides is None and expression.count("==") == 1 and "=" not in expression.replace(
        "==", ""
    ):
        # Python-style ``A == B`` is the same recorded claim (r22v task-04); the
        # ``==`` rejection in equation_claim_sides guards the operator-claim path.
        left, _, right = expression.partition("==")
        sides = (left.strip(), right.strip()) if left.strip() and right.strip() else None
    if sides is None:
        return None
    from symkit.domain.expression_parser import parse_user_expression

    lhs, _ = parse_user_expression(sides[0])
    rhs, _ = parse_user_expression(sides[1])
    if not isinstance(lhs, sp.Basic) or not isinstance(rhs, sp.Basic):
        return None
    return sp.Eq(lhs, rhs, evaluate=False)

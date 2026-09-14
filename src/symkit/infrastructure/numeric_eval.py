"""High-precision numeric evaluation with finite-``Sum`` safety.

SymPy's default ``Sum.evalf`` substitutes the summation index as a ``Float``
and accumulates in double precision.  For a finite alternating sum such as
``Sum((-1)**n/n, (n, 1, 2000))`` that is a disaster: catastrophic cancellation
returns ``-0.7`` instead of ``-0.6929`` and ``(-1)**Float`` takes mpmath's
complex branch, adding a phantom imaginary part (r16 task-19).  ``doit`` on the
same finite sum is exact and fast, so this module evaluates finite ``Sum``
atoms exactly and only then rounds to a high working precision.

Only finite sums with integer, small-enough limits are rewritten; infinite
sums (already correct in SymPy) and everything else fall through to the normal
``evalf`` path unchanged.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

# Working precision for finite sums (spec: mp.dps >= 30).  Cancellation probes
# that suspect precision loss recompute at the doubled value.
_WORKING_DPS = 30
_DOUBLE_DPS = 60

# A result this much smaller than its largest term is treated as cancellation.
_CANCELLATION_RATIO = sp.Rational(1, 1000)

# Exact ``doit`` over more terms is not attempted (the exact rational can be
# arbitrarily large); such sums keep the previous ``evalf`` behaviour.
_MAX_EXACT_TERMS = 100_000


def _term_count(sum_expr: sp.Sum) -> int | None:
    """Number of terms in a finite ``Sum``, or ``None`` if not decidable."""
    total = 1
    for limit in sum_expr.limits:
        if len(limit) < 3:
            return None
        low, high = limit[1], limit[2]
        step = limit[3] if len(limit) >= 4 else sp.Integer(1)
        if not (low.is_Integer and high.is_Integer and step.is_Integer):
            return None
        if step.is_zero:
            return None
        count = (high - low) // step + 1
        total *= int(count) if count.is_Integer and count > 0 else 0
    return total


def _is_small_finite_sum(node: Any) -> bool:
    if not isinstance(node, sp.Sum):
        return False
    count = _term_count(node)
    return count is not None and 0 < count <= _MAX_EXACT_TERMS


def _max_term_magnitude(sum_expr: sp.Sum) -> sp.Expr:
    """Largest ``|term|`` at an integer endpoint (cheap cancellation probe)."""
    best: sp.Expr = sp.Integer(0)
    for limit in sum_expr.limits:
        var, low, high = limit[0], limit[1], limit[2]
        for point in (low, high):
            try:
                magnitude = sp.Abs(sum_expr.function.subs(var, point))
            except Exception:
                continue
            if magnitude.is_number:
                best = sp.Max(best, magnitude)
    return best


def _eval_finite_sum(sum_expr: sp.Sum) -> tuple[Any, bool]:
    """Return ``(value, cancellation_suspected)`` for one finite ``Sum``."""
    exact = sum_expr.doit()
    value = sp.N(exact, _WORKING_DPS)
    magnitude = sp.Abs(value)
    max_term = _max_term_magnitude(sum_expr)
    if not (magnitude.is_number and max_term.is_number):
        return value, False
    if magnitude.is_zero is True or max_term.is_zero is True:
        return value, False
    ratio = sp.N(magnitude / max_term, 20)
    if ratio.is_number and ratio < _CANCELLATION_RATIO:
        return sp.N(sum_expr.doit(), _DOUBLE_DPS), True
    return value, False


def numeric_evalf(expr: Any) -> tuple[Any, list[str]]:
    """Numerically evaluate ``expr``; finite ``Sum`` atoms at high precision.

    Returns ``(value, warnings)``.  Non-``Basic`` inputs (e.g. a matrix) are
    handled exactly as the plain ``evalf`` call did before.
    """
    if not isinstance(expr, sp.Basic):
        return expr.evalf(), []

    finite_sums = [node for node in expr.atoms(sp.Sum) if _is_small_finite_sum(node)]
    if not finite_sums:
        return expr.evalf(), []

    mapping: dict[Any, Any] = {}
    warnings: list[str] = []
    for sum_expr in finite_sums:
        value, suspected = _eval_finite_sum(sum_expr)
        mapping[sum_expr] = value
        if suspected:
            warnings.append(
                "catastrophic cancellation suspected; result computed at "
                f"{_DOUBLE_DPS}-digit working precision"
            )
    return expr.xreplace(mapping).evalf(), warnings

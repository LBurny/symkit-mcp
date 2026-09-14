"""Predicates about the *form* an expression or a recorded step was written in.

Distinguishing an asserted difference (``A - B``, which an identity warning can
apply to) from ordinary algebra (``-x**2 + x*(x + 1)``) needs more than the
parsed SymPy object: SymPy reorders a leading negated term to the front even
after a correct simplification. These helpers keep that judgement in one place
(round-lean task-02 W-1).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

import sympy as sp

_LEADING_NEGATIVE = re.compile(r"^\s*-\s*[A-Za-z]")


def is_difference_form(expr: sp.Basic | None) -> bool:
    """True when ``expr`` records a difference ``A - B`` worth an identity warning.

    The negated operand counts only when a non-negative, non-numeric term comes
    *before* it.  A *leading* negated compound (``-x**2 + x*(x + 1)``) is an
    ordinary expression — SymPy keeps the ``-x**2`` term first even after a
    successful simplification (``-> x``) — so reading it as an asserted
    ``A - B = 0`` produced a false "the difference did not reduce to zero ...
    numerically nonzero at tested points" warning on a correct step
    (round-lean task-02 W-1).

    A negated bare symbol (``-E``) or purely numeric term (``-1*(-3)**2``)
    remains ordinary arithmetic, not an asserted identity.
    """
    if not isinstance(expr, sp.Add):
        return False
    seen_operand = False
    for term in expr.args:
        if isinstance(term, sp.Mul):
            coeff, rest = term.as_coeff_Mul()
            if coeff == -1 and not isinstance(rest, sp.Atom) and rest.free_symbols:
                if seen_operand:
                    return True
            elif not isinstance(rest, sp.Number):
                seen_operand = True
        elif not isinstance(term, sp.Number):
            seen_operand = True
    return False


def recorded_leading_negative(input_expressions: Mapping[str, str]) -> bool:
    """True when the recorded input expression starts with "minus + identifier".

    ``-x**2 + x*(x + 1)`` is ordinary algebra, but SymPy keeps that negated term
    first even after a correct simplification, so a step's srepr cannot tell it
    apart from a genuine ``A - (B)`` identity claim.  The recorded display string
    still preserves the syntax, which is what this reads (task-02 W-1).  A
    parenthesised head (``-(1 - ...)``) is a negated *group* — a real difference
    — and is deliberately not matched.
    """
    for key in ("original", "equation"):
        text = input_expressions.get(key, "")
        if text:
            return bool(_LEADING_NEGATIVE.match(text))
    return False

"""Predicates about the *form* an expression or a recorded step was written in.

Distinguishing an asserted difference (``A - B``, which an identity warning can
apply to) from ordinary algebra (``-x**2 + x*(x + 1)``, or a three-term sum with
two subtracted compounds) needs more than the parsed SymPy object: SymPy
reorders a leading negated term to the front even after a correct
simplification. These helpers keep that judgement in one place (round-lean
task-02 W-1, r19 F1).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

import sympy as sp

_LEADING_NEGATIVE = re.compile(r"^\s*-\s*[A-Za-z]")

# The unevaluated parser wraps every subtraction in ``Mul(Integer(-1), ...)``.
_NEGATED_PREFIX = "Mul(Integer(-1),"


def is_difference_form(expr: sp.Basic | None) -> bool:
    """True when ``expr`` records a genuine two-sided difference ``A - B``.

    A difference claim has exactly one positive compound operand and exactly one
    negated compound operand.  Anything else is ordinary algebra:

    * a *leading* negated compound (``-x**2 + x*(x + 1)``) is an ordinary
      expression — SymPy keeps the ``-x**2`` term first even after a successful
      simplification (``-> x``) — so reading it as an asserted ``A - B = 0``
      produced a false "the difference did not reduce to zero ... numerically
      nonzero at tested points" warning on a correct step (round-lean task-02
      W-1).  The recorded display string gates this case upstream;
    * a sum with *two or more* subtracted compounds (a three-term expression
      such as ``p - q - r``) is a plain simplification, not an ``A - B`` claim,
      so it must not earn the advisory either (r19 F1);
    * a negated bare symbol (``-E``) or purely numeric term (``-1*(-3)**2``)
      remains ordinary arithmetic, not an asserted identity.
    """
    if not isinstance(expr, sp.Add):
        return False
    positives = 0
    negatives = 0
    seen_positive = False
    for term in expr.args:
        if _is_negated_compound(term):
            # A negated compound counts only *after* a positive operand: a
            # leading negated term (``-x**2 + x*(x + 1)``) is ordinary algebra.
            if seen_positive:
                negatives += 1
        elif not isinstance(term, sp.Number):
            positives += 1
            seen_positive = True
    return positives == 1 and negatives == 1


def _is_negated_compound(term: sp.Basic) -> bool:
    """True for ``-X`` where ``X`` is a compound, symbol-bearing operand."""
    if not isinstance(term, sp.Mul) or term.args[0] != sp.Integer(-1):
        return False
    rest = term.args[1:]
    if len(rest) == 1 and isinstance(rest[0], (sp.Atom, sp.Number)):
        return False
    return bool(term.free_symbols)


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


def recorded_difference_form(
    expr: sp.Basic | None,
    input_expressions: Mapping[str, str],
    input_srepr: str = "",
) -> bool:
    """Whether a recorded simplify/expand/factor input is an asserted ``A - B``.

    The live recorder archives ``input_srepr``, but ``safe_load_expression``
    flattens ``-(A - B)`` on reload, so the archive string is inspected as a
    fallback.  A leading negated compound (``-x**2 + x*(x + 1)``) is ordinary
    algebra: the parsed-object test already excludes it, and the archive
    fallback — which cannot see that ordering — is gated by the recorded display
    string (r19 F1).
    """
    if is_difference_form(expr):
        return True
    if recorded_leading_negative(input_expressions):
        return False
    return bool(input_srepr) and archived_difference_form(input_srepr)


def archived_difference_form(srepr_str: str) -> bool:
    """Inspect an archived srepr for a genuine top-level ``A - B`` difference.

    ``srepr`` is parsed structurally (never through ``sympify``, which flattens
    the unevaluated ``Mul(Integer(-1), ...)`` wrappers), so a three-term sum
    with two subtracted compounds is correctly read as ordinary algebra.
    """
    args = _top_level_add_args(srepr_str)
    if args is None:
        return False
    positives = 0
    negatives = 0
    for arg in args:
        if arg.startswith(_NEGATED_PREFIX):
            # The negated operand may itself be a product (``-2*x/3``), so rebuild
            # it as one ``Mul`` before classifying; a bare symbol/number is not a
            # compound and cannot assert a difference.
            rest = _sympify("Mul(" + arg[len(_NEGATED_PREFIX):-1] + ")")
            if rest is not None and not isinstance(rest, (sp.Atom, sp.Number)) and rest.free_symbols:
                negatives += 1
        else:
            loaded = _sympify(arg)
            if loaded is not None and not isinstance(loaded, sp.Number):
                positives += 1
    return positives == 1 and negatives == 1


def _sympify(text: str) -> sp.Basic | None:
    """Load one srepr fragment; ``None`` when it does not round-trip."""
    try:
        loaded = sp.sympify(text)
    except Exception:
        return None
    return loaded if isinstance(loaded, sp.Basic) else None


def _top_level_add_args(srepr_str: str) -> list[str] | None:
    """Top-level argument strings of ``Add(...)``; ``None`` when not an Add.

    Splits on depth-0 commas and skips quoted ``Symbol('a,b')`` content.
    """
    if not srepr_str.startswith("Add(") or not srepr_str.endswith(")"):
        return None
    body = srepr_str[len("Add("):-1]
    args: list[str] = []
    depth = 0
    start = 0
    quoted = False
    for index, char in enumerate(body):
        if char == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(body[start:index].strip())
            start = index + 1
    args.append(body[start:].strip())
    return args

"""Expression reconstruction from archived records.

Invariant I2: an expression that was already computed must be rebuilt from the
archived object, never re-parsed from its display string.  ``str(expr)`` is a
presentation format and does not always round-trip:

* ``str(E)`` / ``str(I)`` re-parse to ``Symbol('E')`` / ``Symbol('I')`` because
  the parser deliberately protects those names as user variables (run-020).
* ``str(Symbol('mu_{t}'))`` is not valid Python at all (LaTeX-derived symbols).

``srepr`` is the machine-readable counterpart and does round-trip, so it is
always tried first.  The display string and the unified user parser remain as
fallbacks for records written before ``srepr`` archiving existed.

This module is pure domain: it depends only on SymPy and the domain parser.
"""

from __future__ import annotations

from typing import Any

import sympy as sp


def _basic_or_none(candidate: Any) -> sp.Basic | None:
    """Return ``candidate`` when it is a SymPy Basic, else ``None``.

    ``sympify`` can return non-Basic containers (e.g. ``(1, 2)`` from legacy
    comma parses); callers must never receive an atom-less container.
    """
    return candidate if isinstance(candidate, sp.Basic) else None


def safe_load_expression(
    expr_str: str,
    srepr_str: str = "",
) -> sp.Basic | None:
    """Rebuild a stored expression, preferring the archived ``srepr``.

    Args:
        expr_str: The display string (``str(expr)``) as stored.
        srepr_str: The archived ``sp.srepr(expr)``, when available.

    Returns:
        The reconstructed SymPy object, or ``None`` when every strategy fails.
    """
    if srepr_str:
        try:
            loaded = _basic_or_none(sp.sympify(srepr_str))
            if loaded is not None:
                return loaded
        except Exception:
            pass

    try:
        loaded = _basic_or_none(sp.sympify(expr_str))
        if loaded is not None:
            return loaded
    except Exception:
        pass

    try:
        from symkit.domain.expression_parser import parse_user_expression

        expr, _ = parse_user_expression(expr_str)
        if expr is not None and isinstance(expr, sp.Basic):
            return expr
    except Exception:
        pass

    return None


def evaluated_form(expr: sp.Basic) -> sp.Basic:
    """Re-evaluate structurally-unevaluated nodes.

    The user parser leaves some arithmetic unevaluated, so ``/2`` arrives as
    ``Pow(2, -1)`` while an expression that has already been through the engine
    holds ``Rational(1, 2)``.  ``subs`` matches structurally, so a substitution
    key in the first form silently fails to apply to the second, and a correct
    step is reported FAILED (2026-09-12 black-box round).  Round-tripping
    through ``srepr`` forces evaluation without changing the value.
    """
    try:
        return sp.sympify(sp.srepr(expr))
    except Exception:
        return expr


def substitution_pairs(
    input_expressions: dict[str, str],
) -> list[tuple[str, str]] | None:
    """The ``key = value`` substitution pairs of a recorded step, losslessly.

    Prefers the archived JSON map.  The human-readable ``replacement`` string is
    comma-joined, so a value containing a comma — ``Rational(1,6)``,
    ``Eq(a, b)``, any multi-argument call — splits into fragments and the
    verifier reported a false "Could not parse replacement expression".  The
    string form is only a fallback for records written before the map was
    archived.
    """
    import json

    raw_map = input_expressions.get("replacement_map")
    if raw_map:
        try:
            mapping = json.loads(raw_map)
        except (TypeError, ValueError):
            mapping = None
        if isinstance(mapping, dict) and mapping:
            return [(str(k), str(v)) for k, v in mapping.items()]

    replacement_str = input_expressions.get("replacement", "")
    if not replacement_str:
        return None
    pairs: list[tuple[str, str]] = []
    for part in replacement_str.split(","):
        left, sep, right = part.strip().partition("=")
        if not sep or not left.strip() or not right.strip():
            return None
        pairs.append((left.strip(), right.strip()))
    return pairs or None

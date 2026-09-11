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

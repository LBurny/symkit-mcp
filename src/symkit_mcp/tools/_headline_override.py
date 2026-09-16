"""Explicit ``session_complete(final_expression=...)`` override (r19 F2b).

An operator-declared deliverable outranks the heuristic outcome selection: the
declared expression becomes the completion's ``final_expression`` /
``final_latex`` and the auto-save writes it.  Kept out of ``session.py`` (whose
size is frozen) and out of ``final_result.py`` (the headline heuristics stay
heuristics).
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.expression_parser import parse_user_expression

#: Attribute through which the override reaches ``pick_savable_expression``.
OVERRIDE_ATTR = "_headline_override"


def parse_final_expression_override(
    final_expression: str,
) -> tuple[sp.Basic | None, str | None]:
    """Parse a caller-declared deliverable with the unified user parser.

    Returns ``(expr, None)`` on success or ``(None, error)`` when the string
    cannot be understood.  The protected-name handling of the unified parser
    applies, so a declared ``E``/``I`` stays a symbol (r19 F20).
    """
    expr, error = parse_user_expression(final_expression, convert_equation=True)
    if expr is None or not isinstance(expr, sp.Basic):
        return None, error or f"Could not parse final_expression: {final_expression!r}"
    return expr, None


def apply_final_expression_override(
    session: Any, result: dict[str, Any], expr: sp.Basic
) -> None:
    """Write the declared deliverable into *result* (and the auto-save path).

    When a failed-step fallback also applied, ``final_expression_skipped_failed``
    is preserved but the note says the explicit declaration won.
    """
    result["final_expression"] = str(expr)
    result["final_latex"] = sp.latex(expr)
    if result.get("final_expression_skipped_failed"):
        result["note"] = (
            "explicit final_expression override used; the heuristic headline "
            "for the skipped failed step was ignored"
        )
    try:
        setattr(session, OVERRIDE_ATTR, expr)
    except Exception:
        # A session type that rejects the attribute must not block completion.
        return

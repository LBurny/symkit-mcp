"""Dimensional gate for the formula library write paths (r19 F6).

``formula_add`` and ``session_complete(auto_save=True)`` used to persist a
formula whose expression contradicts its own declared units (``E = m*v**3``
with ``E -> J``, ``m -> kg``, ``v -> m/s``) as if it were green.  The gate runs
the same dimensional checker the ``dimension`` tool uses, against the units the
caller actually declared, and blocks only a *decidable* inconsistency: an
incomplete unit map (``consistent is None``) still writes, because the staging
tier is the designed quarantine for unverified content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sympy as sp

from symkit.domain.dimensional_analysis import check_expression_dimensions
from symkit.domain.expression_parser import parse_user_expression

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationSession

#: ``parse_unit``/the checker treat this sentinel as "dimensionless or unknown".
UNKNOWN_UNIT = "-"


def _declared_unit_map(variables: Any) -> dict[str, str]:
    """``{symbol: unit}`` from a ``formula_add``-style variables mapping."""
    units: dict[str, str] = {}
    for name, meta in (variables or {}).items():
        raw = meta.get("unit") if isinstance(meta, dict) else getattr(meta, "unit", None)
        raw = str(raw or "").strip()
        if raw and raw != UNKNOWN_UNIT:
            units[name] = raw
    return units


def _inconsistency(expr: sp.Basic, unit_map: dict[str, str]) -> list[str]:
    """Checker issues when the declared units are decisively inconsistent."""
    if not unit_map:
        return []
    report = check_expression_dimensions(expr, unit_map)
    if report.consistent is not False:
        return []
    return list(report.issues) or ["the declared units do not balance"]


def _parse(expression_str: str) -> sp.Basic | None:
    expr, _error = parse_user_expression(expression_str, convert_equation=True)
    return expr if isinstance(expr, sp.Basic) else None


def formula_dimension_error(
    expression_str: str, variables: Any
) -> str | None:
    """Curated rejection for ``formula_add``, or ``None`` to proceed (F6)."""
    expr = _parse(expression_str)
    if expr is None:
        return None
    issues = _inconsistency(expr, _declared_unit_map(variables))
    if not issues:
        return None
    return (
        "Formula is dimensionally inconsistent with its declared units: "
        + "; ".join(issues)
        + ". Fix the expression or the declared units."
    )


def session_save_blocker(session: DerivationSession) -> str | None:
    """Reason ``session_complete(auto_save=True)`` must skip the library write.

    ``None`` means the write proceeds (consistent, or no decidable verdict).
    """
    from symkit_mcp.tools._session_views import pick_savable_expression
    from symkit_mcp.tools._unit_context import collect_unit_map

    expr, _note = pick_savable_expression(session)
    if expr is None:
        return None
    issues = _inconsistency(expr, collect_unit_map(session))
    if not issues:
        return None
    return "dimensionally inconsistent: " + "; ".join(issues)


def session_save_blocked(
    session: DerivationSession, result: dict[str, Any], warnings: list[str]
) -> bool:
    """Gate ``session_complete``'s library write; True means "skip it" (F6).

    The completion stays successful and the session JSON is still persisted;
    only the knowingly-false library write is skipped, with the reason attached
    to *result* and a warning appended to *warnings*.
    """
    reason = session_save_blocker(session)
    if reason is None:
        return False
    result["saved"] = {}
    result["not_saved_reason"] = reason
    warnings.append(f"auto_save skipped: {reason}")
    return True

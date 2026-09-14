"""Rendering helpers for the session view tools.

Split out of ``session.py`` (bylaw section 5.1) to keep that module within its
frozen size while the tools gained provenance warnings.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.derivation_session import DerivationSession, OperationType
from symkit.domain.expr_io import safe_load_expression
from symkit.infrastructure.derivation_repository import (
    DerivationResult,
    get_repository,
)
from symkit.infrastructure.formula_identity import staging_id
from symkit_mcp.tools._formula_governance import build_auto_variables
from symkit_mcp.tools._state import get_catalog


def render_session_header(
    session: DerivationSession,
    goal: dict[str, Any] | None,
    progress: dict[str, Any],
    latex_str: str,
) -> str:
    """The markdown header ``session_show`` renders above the current formula."""
    lines = [
        f"📊 **{session.name}** (Step {len(session.steps)}, {session.status.value})",
        f"🏷️ Domain: {session.domain or 'general'}",
    ]
    if goal:
        lines.append(f"🎯 Goal: {goal['text']}")
        lines.append(f"📈 Progress: {progress['progress_score']:.0%}")
        if goal.get("assumptions"):
            lines.append(f"📝 Assumptions: {', '.join(goal['assumptions'])}")
    lines.extend(["", "$$", f"{latex_str}", "$$"])
    return "\n".join(lines)


def render_empty_session(
    session: DerivationSession,
    goal: dict[str, Any] | None,
) -> str:
    """The display text for a session that has not loaded a formula yet."""
    text = f"📊 **{session.name}** (Step {len(session.steps)})\n\n_No formula loaded yet_"
    if goal:
        text += (
            f"\n\n🎯 **Goal:** {goal['text']}\n"
            f"**Target form:** {goal['target_form'] or 'derive_expression'}"
        )
        if goal.get("assumptions"):
            text += f"\n**Assumptions:** {', '.join(goal['assumptions'])}"
    return text


def unknown_pattern_warning(requested: str, used: str) -> str:
    """Report a derivation pattern that the server could not honor."""
    return f"Unknown derivation pattern '{requested}'; using '{used}'."


def pick_savable_expression(
    session: DerivationSession,
) -> tuple[sp.Basic | None, str | None]:
    """The library artifact must be symbolic content, not a bare constant.

    ``representative_expression`` reports a trailing zero self-check as the
    outcome (r14 task-08 display semantics), but a bare constant is not a
    reusable formula: prefer the last non-load derivation output carrying
    free symbols; when the derivation produced none, skip the library write.
    """
    saved = session.representative_expression()
    if saved is None:
        saved = session.current_expression
    if isinstance(saved, sp.Basic) and saved.free_symbols:
        return saved, None
    for step in reversed(session.steps):
        if step.operation == OperationType.LOAD_FORMULA:
            continue
        expr = safe_load_expression(step.output_expression, step.output_srepr)
        if expr is not None and expr.free_symbols:
            return expr, (
                f"auto_save: the outcome '{saved}' is a bare constant; saved "
                "the last symbolic derivation output instead"
            )
    if saved is not None:
        return None, (
            f"auto_save skipped: the derivation produced only the constant "
            f"'{saved}'; no formula saved (record one with formula_add)"
        )
    return None, None


def save_derivation_formula(
    session: DerivationSession,
    result: dict[str, Any],
    *,
    is_verified: bool,
    verification_method: str,
    verified_at: str | None,
    description: str,
    application_context: str,
    assumptions: list[str],
    limitations: list[str],
    references: list[str],
    tags: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Persist the derived formula (the auto-save half of ``session_complete``).

    Returns ``{"saved_path", "saved_id", "saved_expression"}``, empty when the
    derivation produced no savable symbolic expression. Notes land in
    ``warnings``.
    """
    saved_expr, save_note = pick_savable_expression(session)
    if save_note:
        warnings.append(save_note)
    if saved_expr is None:
        return {}
    repo = get_repository()
    saved_expression_str = str(saved_expr)
    # Deterministic staging id: identical content re-completed by any session
    # maps to the same id (idempotent re-save); different content yields a
    # different hash suffix, so no -vN minting is needed and random session
    # hex ids never enter the library.
    fallback_name = session.goal.text if session.goal is not None else ""
    result_id = staging_id(session.name or fallback_name, saved_expression_str)
    derivation_result = _build_staged_result(
        session,
        result,
        saved_expr,
        result_id,
        is_verified=is_verified,
        verification_method=verification_method,
        verified_at=verified_at,
        description=description,
        application_context=application_context,
        assumptions=assumptions,
        limitations=limitations,
        references=references,
        tags=tags,
    )
    repo.register(derivation_result)
    saved_path = repo.save(result_id)
    try:
        get_catalog().ensure_fresh()
    except Exception as e:
        warnings.append(f"Saved but index update failed: {e}")
    return {
        "saved_path": saved_path,
        "saved_id": result_id,
        "saved_expression": saved_expression_str,
    }


def _build_staged_result(
    session: DerivationSession,
    result: dict[str, Any],
    saved_expr: sp.Basic,
    result_id: str,
    *,
    is_verified: bool,
    verification_method: str,
    verified_at: str | None,
    description: str,
    application_context: str,
    assumptions: list[str],
    limitations: list[str],
    references: list[str],
    tags: list[str],
) -> DerivationResult:
    """The ``DerivationResult`` payload for a completed derivation."""
    repo = get_repository()
    existing = repo.get(result_id)
    session_ids = list(existing.session_ids) if existing is not None else []
    if session.session_id not in session_ids:
        session_ids.append(session.session_id)
    return DerivationResult(
        id=result_id,
        name=session.name,
        expression=str(saved_expr),
        latex=sp.latex(saved_expr),
        variables=build_auto_variables(saved_expr, session),
        derived_from=list(session.formulas.keys()),
        derivation_steps=[step["description"] for step in result["steps"]],
        assumptions=assumptions,
        session_ids=session_ids,
        verified=is_verified,
        verification_method=verification_method,
        verified_at=verified_at,
        description=description,
        domain=session.domain,
        application_context=application_context,
        limitations=limitations,
        references=references,
        tags=tags,
        author=session.author,
        category=session.domain or "derived",
    )

"""Rendering helpers for the session view tools.

Split out of ``session.py`` (bylaw section 5.1) to keep that module within its
frozen size while the tools gained provenance warnings.
"""

from __future__ import annotations

from typing import Any

from symkit.domain.derivation_session import DerivationSession


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

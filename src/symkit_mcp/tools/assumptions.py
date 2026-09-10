"""Assumption Management Tools — Multi-level assumption engine.

Tools for querying and managing assumptions across layers:
- global
- domain
- session
- step
"""

from __future__ import annotations

from typing import Any

from symkit.domain.assumption_engine import AssumptionLevel
from symkit.domain.value_objects import MathContext
from symkit_mcp.tools._state import get_context, get_session, set_context

# Assumption levels a user can have set (domain defaults are preserved by
# removal tools: they come from the domain profile, not from user calls).
_USER_LEVELS = (AssumptionLevel.GLOBAL, AssumptionLevel.SESSION, AssumptionLevel.STEP)


def register_assumption_tools(mcp: Any) -> None:
    """Register assumption management tools."""

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": 'assume_for_step("x", "positive", "y", "real")',
        }
    )
    def assume_for_step(
        *args: str,
    ) -> dict[str, Any]:
        """
        📋 Set assumptions for the current derivation step only.

        Args:
            *args: Alternating symbol and property strings
                   (e.g., "x", "positive", "y", "real")

        Returns:
            Updated step-level assumptions and any conflicts
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        if len(args) % 2 != 0:
            return {
                "success": False,
                "error": "Arguments must be alternating symbol and property strings.",
            }

        for i in range(0, len(args), 2):
            symbol = args[i]
            props = args[i + 1].split()
            session.assumption_engine.assume(symbol, *props, level=AssumptionLevel.STEP)

        conflicts = session.assumption_engine.detect_conflicts()
        return {
            "success": True,
            "step_assumptions": session.assumption_engine.get_assumptions(
                level=AssumptionLevel.STEP
            ),
            "merged_assumptions": session.assumption_engine.get_assumptions(),
            "conflicts": conflicts,
        }

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": "list_assumptions(level='session')",
        }
    )
    def list_assumptions(
        level: str | None = None,
    ) -> dict[str, Any]:
        """
        📐 List assumptions at a specific level or merged across all levels.

        Args:
            level: "global", "domain", "session", "step", or None for merged
                (the string "merged" is accepted as an alias for None)

        Returns:
            Assumptions at the requested level
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        if level is None or level == "merged":
            return {
                "success": True,
                "level": "merged",
                "assumptions": session.assumption_engine.get_assumptions(),
            }

        try:
            lvl = AssumptionLevel(level)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid level '{level}'. Use global/domain/session/step.",
            }

        return {
            "success": True,
            "level": level,
            "assumptions": session.assumption_engine.get_assumptions(level=lvl),
        }

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": "check_assumption_conflicts()",
        }
    )
    def check_assumption_conflicts() -> dict[str, Any]:
        """
        ⚠️ Detect conflicts across all assumption levels.

        A conflict occurs when a symbol is assigned contradictory properties
        (e.g., both positive and negative).

        Returns:
            Conflict report
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        conflicts = session.assumption_engine.detect_conflicts()
        return {
            "success": True,
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
            "warnings": [c["message"] for c in conflicts],
        }

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": "clear_step_assumptions()",
        }
    )
    def clear_step_assumptions() -> dict[str, Any]:
        """
        🧹 Clear step-level assumptions.

        Useful when moving to a new sub-derivation or branch.

        Returns:
            Operation result
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        session.assumption_engine.clear_level(AssumptionLevel.STEP)
        return {
            "success": True,
            "message": "Step-level assumptions cleared.",
            "remaining_assumptions": session.assumption_engine.get_assumptions(),
        }

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": 'unassume(["x", "y"])',
        }
    )
    def unassume(variables: list[str]) -> dict[str, Any]:
        """
        🧹 Remove symbolic assumptions for named symbols.

        Strips the symbols from the shared math context and from the active
        session's assumption engine (global/session/step layers; domain
        defaults are preserved).  Without a session only the shared context is
        touched.  Previously `assume({"x": "positive"})` was irreversible
        short of a server restart; assumptions could silently poison every
        later parse (run-013).

        Args:
            variables: Symbol names to strip, e.g. ["x", "y"]

        Returns:
            Remaining assumptions
        """
        if not variables:
            return {
                "success": True,
                "assumptions": get_context().assumptions,
                "message": "Nothing to remove (empty variable list).",
            }
        set_context(get_context().without_assumptions(variables))
        session = get_session()
        if session is not None:
            for name in variables:
                for lvl in _USER_LEVELS:
                    session.assumption_engine.unassume(name, level=lvl)
        remaining = get_context().assumptions
        return {
            "success": True,
            "removed": list(variables),
            "assumptions": remaining,
            "message": f"Assumptions removed for {len(variables)} symbol(s).",
        }

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": "clear_assumptions()",
        }
    )
    def clear_assumptions() -> dict[str, Any]:
        """
        🧹 Clear ALL symbolic assumptions in the current scope.

        Resets the shared math context and the active session's assumption
        engine (global/session/step layers).  Domain defaults (loaded from the
        domain profile when a session starts) are preserved.  Useful when a
        stray assumption is suspected of skewing results (run-013: per-call
        assumptions used to leak permanently and could not be removed).

        Returns:
            Remaining assumptions (normally empty)
        """
        set_context(MathContext())
        session = get_session()
        if session is not None:
            for lvl in _USER_LEVELS:
                session.assumption_engine.clear_level(lvl)
        return {
            "success": True,
            "assumptions": {},
            "message": "All assumptions cleared (domain defaults preserved).",
        }

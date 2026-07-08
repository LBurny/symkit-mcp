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
from symkit_mcp.tools._state import get_session


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

        Returns:
            Assumptions at the requested level
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        if level is None:
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

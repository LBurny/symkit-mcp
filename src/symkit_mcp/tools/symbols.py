"""Symbol Semantics Tools — Query and manage symbol meanings.

Provides MCP tools for:
- register_symbol: explicitly register what a symbol means in a domain
- lookup_symbol: query the meaning of a symbol
- list_domain_symbols: list default symbols for a domain
- check_symbol_conflicts: detect ambiguous symbol usage in current session
"""

from __future__ import annotations

from typing import Any

from symkit.domain.math_domain import MathDomain
from symkit.domain.symbol_registry import SymbolScope
from symkit_mcp.tools._state import get_session


def register_symbol_tools(mcp: Any) -> None:
    """Register symbol semantics tools."""

    @mcp.tool(
        meta={
            "category": "Symbol Semantics",
            "example": 'register_symbol("R", "Universal gas constant", domain="thermodynamics", unit="J/(mol*K)")',
        }
    )
    def register_symbol(
        name: str,
        meaning: str,
        domain: str = "general",
        unit: str | None = None,
        assumptions: list[str] | None = None,
        aliases: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        🏷️ Register the semantic meaning of a symbol in the current session.

        Args:
            name: Symbol name (e.g., "R", "hbar", "k")
            meaning: Human-readable meaning (e.g., "Universal gas constant")
            domain: Domain this meaning belongs to
            unit: Default physical unit
            assumptions: Common assumptions (e.g., ["positive"])
            aliases: Alternative names for this symbol

        Returns:
            Registration result
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        sem = session.symbol_registry.register(
            name=name,
            meaning=meaning,
            domain=MathDomain.from_string(domain),
            scope=SymbolScope.USER,
            default_unit=unit,
            common_assumptions=assumptions or [],
            aliases=aliases or [],
        )

        return {
            "success": True,
            "symbol": name,
            "meaning": meaning,
            "domain": domain,
            "registered": sem.to_dict(),
        }

    @mcp.tool(
        meta={
            "category": "Symbol Semantics",
            "example": 'lookup_symbol("R", domain="thermodynamics")',
        }
    )
    def lookup_symbol(
        name: str,
        domain: str | None = None,
    ) -> dict[str, Any]:
        """
        🔍 Look up the semantic meaning of a symbol.

        Args:
            name: Symbol name
            domain: Optional domain to prefer

        Returns:
            Symbol meaning and all known definitions
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        sem = session.symbol_registry.lookup(name, domain)
        all_entries = session.symbol_registry.lookup_all(name)

        return {
            "success": True,
            "symbol": name,
            "preferred": sem.to_dict() if sem else None,
            "all_definitions": [e.to_dict() for e in all_entries],
            "count": len(all_entries),
        }

    @mcp.tool(
        meta={
            "category": "Symbol Semantics",
            "example": 'list_domain_symbols(domain="fluid_dynamics")',
        }
    )
    def list_domain_symbols(
        domain: str = "general",
    ) -> dict[str, Any]:
        """
        📋 List default symbols for a given domain.

        Args:
            domain: Domain name

        Returns:
            List of symbols with meanings and units
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        symbols = session.symbol_registry.list_symbols(
            domain=MathDomain.from_string(domain),
        )

        return {
            "success": True,
            "domain": domain,
            "symbols": [s.to_dict() for s in symbols],
            "count": len(symbols),
        }

    @mcp.tool(
        meta={
            "category": "Symbol Semantics",
            "example": 'check_symbol_conflicts()',
        }
    )
    def check_symbol_conflicts() -> dict[str, Any]:
        """
        ⚠️ Check for ambiguous symbols in the current session.

        A conflict occurs when the same symbol name has multiple meanings
        or appears in multiple domains.

        Returns:
            Conflict report with suggested disambiguation
        """
        session = get_session()
        if session is None:
            return {
                "success": False,
                "error": "No active session. Use session_start() or derive() first.",
            }

        # Collect symbols from loaded formulas and current expression
        names: set[str] = set()
        for formula in session.formulas.values():
            names.update(str(s) for s in formula.expression.free_symbols)
        if session.current_expression is not None:
            names.update(str(s) for s in session.current_expression.free_symbols)

        conflicts = session.symbol_registry.detect_conflicts(list(names))

        return {
            "success": True,
            "symbols_checked": len(names),
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
            "warnings": [
                f"'{c['symbol']}' is ambiguous: {c['meanings']}"
                for c in conflicts
            ],
        }

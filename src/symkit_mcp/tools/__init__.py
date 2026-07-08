"""SymKit MCP Tools — Unified Symbolic Math Derivation Engine

Unified tool surface:
- math.py:    ⭐ Unified math() tool — ~25 operations in one call
- session.py: Session management + derivation workflow
- formula.py: 🌐 Formula search (Wikidata, SciPy, BioModels)
- codegen.py: Generate Python code and reports from derivations
- symbols.py: Symbol registry and semantic checks
- assumptions.py: Multi-level assumption management
- orchestration.py: High-level derive() / intent routing

Design Principles:
1. math() is the primary tool — LLMs only need to know ONE tool name for math.
2. session_* is the primary workflow — one entry point for derivation sessions.
3. Every derivation step is recorded with full provenance.
4. Sessions persist to prevent mid-derivation data loss.
5. Leverage SymPy for all symbolic computation.
6. Domain-agnostic — works for fluid dynamics, QM, structures, etc.
"""

from typing import Any

from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.codegen import register_codegen_tools
from symkit_mcp.tools.formula import register_formula_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.orchestration import register_orchestration_tools
from symkit_mcp.tools.session import register_session_tools
from symkit_mcp.tools.symbols import register_symbol_tools


def register_all_tools(mcp: Any) -> None:
    """Register all SymKit tools with the MCP server."""

    # ⭐ Core: Unified math tool + global assumptions
    register_math_tools(mcp)

    # 🗂️ Session management + unified derivation workflow
    register_session_tools(mcp)

    # 🌐 External formula sources
    register_formula_tools(mcp)

    # 🏷️ Symbol semantics
    register_symbol_tools(mcp)

    # 📝 Code / report generation
    register_codegen_tools(mcp)

    # 🚀 High-level orchestration
    register_orchestration_tools(mcp)

    # 📐 Multi-level assumption tools
    register_assumption_tools(mcp)

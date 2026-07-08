"""
SymKit MCP Server — General-Purpose Mathematical Derivation Engine

FastMCP-based server providing symbolic reasoning tools to AI agents.
Supports derivation across fluid dynamics, quantum mechanics, solid mechanics,
electromagnetism, and any mathematical domain.

Core tool: math() — a unified Mathematica-style interface for ~25 operations.
"""

from concurrent.futures import ThreadPoolExecutor

from mcp.server.fastmcp import FastMCP

from symkit_mcp.tools import register_all_tools

# Create the FastMCP server instance
mcp = FastMCP(
    name="symkit",
    instructions=(
        "SymKit — LLM-assisted mathematical derivation engine. "
        "Use math() for calculations (diff, integrate, solve, dsolve, "
        "gradient, laplace, matrix ops, etc.). "
        "Use session_start()/session_show()/session_complete() for "
        "step-by-step derivations with full provenance tracking."
    ),
)

# Register all tools
register_all_tools(mcp)


def main() -> None:
    """Entry point for the MCP server."""
    # Eagerly initialize the shared SessionManager in a worker thread so
    # that the first session_start() call does not block FastMCP's asyncio
    # event loop (which runs synchronous tool handlers directly on the loop).
    from symkit_mcp.tools._state import get_manager

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(get_manager).result()

    mcp.run()


if __name__ == "__main__":
    main()

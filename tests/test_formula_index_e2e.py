"""End-to-end MCP test for the persistent formula index tools.

Spawns the real server over stdio and exercises formula_stats,
formula_search with a tier filter, and formula_reindex. Marked ``e2e``
because it spawns a subprocess.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent


async def _call(session: ClientSession, name: str, arguments: dict) -> dict:
    """Call a tool and decode its JSON TextContent payload."""
    result = await session.call_tool(name, arguments=arguments)
    assert not result.isError, f"tool {name!r} returned error: {result.content}"
    for block in result.content:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except Exception:
                return {"raw": block.text}
    return {"raw": str(result.content)}


@pytest.mark.e2e
async def test_formula_index_tools_e2e() -> None:
    """formula_stats / tier-filtered search / formula_reindex over real stdio."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "symkit_mcp.server"],
        env=os.environ.copy(),
        cwd=str(PROJECT_ROOT),
    )

    async with (
        stdio_client(server_params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        stats = await _call(session, "formula_stats", {})
        assert stats["success"], stats
        assert stats["tiers"]["seed"] >= 6  # bundled seeds always load
        assert stats["index_path"].endswith("index.sqlite3")

        seeds = await _call(session, "formula_search", {
            "query": "Reynolds number", "tier": "seed",
        })
        assert seeds["success"], seeds
        assert any(r["id"] == "reynolds_number" for r in seeds["results"])
        assert all(r["tier"] == "seed" for r in seeds["results"])

        staging = await _call(session, "formula_search", {
            "query": "Reynolds number", "tier": "staging",
        })
        assert staging["success"], staging
        assert all(r["tier"] == "staging" for r in staging["results"])

        reindex = await _call(session, "formula_reindex", {})
        assert reindex["success"], reindex
        assert reindex["stats"]["total"] >= 6

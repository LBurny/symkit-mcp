"""End-to-end MCP test for the escape-velocity derivation.

Spawns ``python -m symkit_mcp.server`` in stdio mode via the MCP client SDK
and exercises the real tool surface that the LLM host uses. Marked ``e2e``
because it spawns a subprocess and is slower than unit tests.
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


async def call(session: ClientSession, name: str, arguments: dict) -> dict:
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
async def test_escape_velocity_derivation_e2e() -> None:
    """Derive v = sqrt(2GM/R) through the real MCP stdio surface."""
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
        assert session._server_capabilities is not None

        # 1. session_start
        r = await call(session, "session_start", {
            "name": "escape_velocity_e2e",
            "description": "Derive escape velocity via MCP stdio transport",
            "domain": "mechanics",
            "pattern": "direct-manipulation",
            "goal": "derive escape velocity formula v = sqrt(2GM/R)",
            "author": "mcp_e2e_test",
        })
        assert r["success"], r
        assert r["session_id"]

        # 2. session_set_goal with explicit target
        r = await call(session, "session_set_goal", {
            "goal": "derive escape velocity formula v = sqrt(2GM/R)",
            "target_expression": "v = sqrt(2*G*M/R)",
        })
        assert r["success"], r

        # 3. assume positive variables
        r = await call(session, "assume", {
            "variables": {
                "G": "positive", "M": "positive", "R": "positive",
                "v": "positive", "m": "positive",
            },
        })
        assert r["success"], r

        # 4. record conservation-of-energy step
        r = await call(session, "session_record_step", {
            "expression": "1/2*m*v**2 - G*M*m/R = 0",
            "description": "Conservation of energy: kinetic + potential = 0 at infinity",
        })
        assert r["success"], r

        # 5. math solve for v
        r = await call(session, "math", {
            "operation": "solve",
            "expression": "1/2*m*v**2 - G*M*m/R = 0",
            "variable": "v",
            "session": True,
            "description": "Solve energy equation for escape velocity",
        })
        assert r["success"], r

        # 6. session_status
        r = await call(session, "session_status", {})
        assert r["success"], r

        # 7. session_complete requiring target match
        r = await call(session, "session_complete", {
            "description": "Escape velocity formula",
            "application_context": "Escape velocity from a spherical mass M of radius R",
            "assumptions": ["G, M, R are positive"],
            "require_target_match": True,
        })
        assert r["success"], r
        assert r["target_reached"], r

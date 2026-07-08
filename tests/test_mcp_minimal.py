"""Minimal MCP client smoke test — only calls session_start.

Spawns the real server over stdio and confirms one round-trip tool call works.
Marked ``e2e`` because it spawns a subprocess.
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


@pytest.mark.e2e
async def test_mcp_minimal_session_start() -> None:
    """A single session_start call must succeed against the real server."""
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

        result = await session.call_tool("session_start", arguments={
            "name": "minimal_test",
            "description": "Minimal test",
            "domain": "mechanics",
            "goal": "derive escape velocity formula v = sqrt(2GM/R)",
        })
        assert not result.isError, f"session_start errored: {result.content}"

        payload = None
        for block in result.content:
            if getattr(block, "type", None) == "text" and hasattr(block, "text"):
                try:
                    payload = json.loads(block.text)
                    break
                except Exception:
                    payload = {"raw": block.text}
        assert payload is not None, "no text content returned"
        assert payload["success"], payload
        assert payload["session_id"]
        assert payload["name"] == "minimal_test"

"""End-to-end test for python_exec over real MCP stdio transport."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
async def test_python_exec_over_stdio() -> None:
    """Run a sympy snippet through the real server and read the result back."""
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
        payload = await call(
            session,
            "python_exec",
            {"code": "x = symbols('x')\nresult = integrate(x**2, x)"},
        )
        assert payload["status"] == "success"
        assert payload["result"]["repr"] == "x**3/3"
        assert payload["result"]["srepr"]

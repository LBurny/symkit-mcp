#!/usr/bin/env python
"""Stdio smoke probe: prove the lab server answers before spending on full tasks.

Usage: python probe/smoke.py [DATA_DIR]
Check the printed tool count against the version under test (1.7.0 = 45 tools)
and that session_certify is present, before running any card.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LAB = Path(__file__).resolve().parent.parent
EXE = str(LAB / ".venv" / "Scripts" / "symkit-mcp.exe")
DATA = sys.argv[1] if len(sys.argv) > 1 else str(LAB / "data" / "smoke")


async def main() -> int:
    params = StdioServerParameters(
        command=EXE,
        args=[],
        env={"SYMKIT_DATA_DIR": DATA},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools: {len(names)}")
            print(f"session_certify present: {'session_certify' in names}")
            for call in (
                ("session_start", {"name": "probe", "goal": "1+1"}),
                ("math", {"operation": "simplify", "expression": "x + x"}),
                ("math", {"operation": "dimension", "expression": "v*t",
                          "units": {"v": "m/s", "t": "s"}}),
                ("session_certify", {}),
            ):
                result = await session.call_tool(call[0], call[1])
                blob = " ".join(
                    getattr(c, "text", "") for c in result.content
                )
                print(f"{call[0]}: isError={result.isError} | {blob[:180]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
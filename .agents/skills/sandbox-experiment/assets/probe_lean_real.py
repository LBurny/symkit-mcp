#!/usr/bin/env python
"""Real-kernel certification probe against a persistent Lean install.

Template: point LEAN_ROOT at the install root containing data/ (with a
lean-workspace/.symkit-lean-ready readiness stamp) and elan/. The probe
starts a session, runs three algebraic steps, certifies, and asserts:
- session_certify success
- proven >= 1
- heuristic verification_summary unchanged by certification (Lean never
  rewrites existing verdicts; disagreements go to `discrepancies`).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LAB = Path(__file__).resolve().parent.parent
EXE = str(LAB / ".venv" / "Scripts" / "symkit-mcp.exe")
ROOT = Path(os.environ.get("LEAN_ROOT", "D:/Code/Mathlib"))
DATA = str(ROOT / "data")
ELAN_HOME = str(ROOT / "elan")


async def call(session: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(tool, args)
    blob = " ".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(blob)
    except ValueError:
        return {"_unparsed": blob, "_isError": result.isError}


async def main() -> int:
    env = dict(os.environ)
    env["SYMKIT_DATA_DIR"] = DATA
    env["ELAN_HOME"] = ELAN_HOME
    env["PATH"] = str(ROOT / "elan" / "bin") + os.pathsep + env.get("PATH", "")
    params = StdioServerParameters(command=EXE, args=[], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await call(session, "session_start",
                       {"name": "lean-real-d", "goal": "certify algebraic steps"})
            await call(session, "math",
                       {"operation": "expand", "expression": "(x+1)^3"})
            await call(session, "math",
                       {"operation": "factor", "expression": "x^3 + 3*x^2 + 3*x + 1"})
            await call(session, "math",
                       {"operation": "cancel", "expression": "(x**2 - 1)/(x - 1)"})
            before = await call(session, "session_verify_session", {})
            report = await call(session, "session_certify", {})
            after = await call(session, "session_verify_session", {})

    print(json.dumps(report, ensure_ascii=False, indent=2)[:3000])
    ok = report.get("success") is True
    summary = report.get("summary") or {}
    proven = summary.get("proven", 0)
    same = before.get("verification_summary") == after.get("verification_summary")
    print(f"\nsuccess={ok} proven={proven} summary={summary}")
    print(f"verification_summary unchanged: {same}")
    if ok and proven >= 1 and same:
        print("REAL-CERTIFY(D): PASS")
        return 0
    print("REAL-CERTIFY(D): FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
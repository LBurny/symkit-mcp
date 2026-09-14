#!/usr/bin/env python
"""Deterministic regress probe for the four round-17 Lean certification fixes.

Expected values are authored by the orchestrator (not delegated). Each check
runs independently; a raised exception is recorded as FAIL rather than silently
skipping the rest (hard rule 5).

Covers:
  B1  identical input/output steps -> `trivial`, excluded from `proven`, no lean record
  C1  session_certify(assumptions=...) resolves a missing denominator nonzero
  A3  toolchain guard: selected lake lacking the pinned toolchain -> clear unavailable
  --  healthy install still certifies real algebraic steps

Environment (defaults target the maintainer install):
  LEAN_ROOT   install root holding data/ (with lean-workspace stamp) and elan/
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LAB = Path(__file__).resolve().parent.parent
EXE = os.environ.get("SYMKIT_MCP_EXE", str(LAB / ".venv" / "Scripts" / "symkit-mcp.exe"))
ROOT = Path(os.environ.get("LEAN_ROOT", "D:/Code/Mathlib"))
DATA = str(ROOT / "data")
ELAN_HOME = str(ROOT / "elan")

RESULTS: list[tuple[str, bool, str]] = []


async def call(session: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(tool, args)
    blob = " ".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(blob)
    except ValueError:
        return {"_unparsed": blob, "_isError": result.isError}


def _env(**over: str) -> dict[str, str]:
    env = dict(os.environ)
    env["SYMKIT_DATA_DIR"] = over.get("data", DATA)
    env["ELAN_HOME"] = over.get("elan", ELAN_HOME)
    if "path_prefix" in over:
        env["PATH"] = over["path_prefix"] + os.pathsep + env.get("PATH", "")
    if "timeout" in over:
        env["SYMKIT_LEAN_TIMEOUT"] = over["timeout"]
    env.pop("_CHECK_EXCLUDE", None)
    return env


async def _with_server(env: dict[str, str], body: Any) -> Any:
    params = StdioServerParameters(command=EXE, args=[], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await body(session)


def _record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


async def check_trivial(tmp: Path) -> None:
    async def body(session: Any) -> None:
        await call(session, "session_start", {"name": "regress-trivial"})
        await call(session, "math",
                   {"operation": "simplify", "expression": "x*(x + 1)", "session": True})
        await call(session, "math",
                   {"operation": "simplify", "expression": "x*(x + 1) - x**2", "session": True})
        report = await call(session, "session_certify", {})
        summary = report.get("summary") or {}
        rows = {r["step_number"]: r for r in report.get("steps", [])}
        trivial_rows = [r for r in rows.values() if r["certification"] == "trivial"]
        trivial_ok = (
            summary.get("trivial") == 1
            and summary.get("proven") == 1
            and len(trivial_rows) == 1
            and "identical" in (trivial_rows[0].get("reason") or "")
        )
        _record(
            "B1 trivial step is classified and excluded from proven",
            trivial_ok,
            f"summary={summary} trivial_reason={trivial_rows[0].get('reason') if trivial_rows else None}",
        )

    await _with_server(_env(), body)


async def check_assumptions(tmp: Path) -> None:
    async def body(session: Any) -> None:
        await call(session, "session_start", {"name": "regress-assume"})
        await call(session, "math",
                   {"operation": "simplify", "expression": "1/x + 1/x**3", "session": True})
        without = await call(session, "session_certify", {})
        row_without = next(
            (r for r in without.get("steps", []) if r["operation"] == "simplify"), {}
        )
        with_assume = await call(session, "session_certify", {"assumptions": "x nonzero"})
        row_with = next(
            (r for r in with_assume.get("steps", []) if r["operation"] == "simplify"), {}
        )
        ok = (
            row_without.get("certification") == "untranslatable"
            and "nonzero" in (row_without.get("reason") or "")
            and row_with.get("certification") == "proven"
            and "h_x : x \u2260 0" in (row_with.get("statement") or "")
        )
        _record(
            "C1 certify-time assumptions turn untranslatable into proven",
            ok,
            f"without={row_without.get('certification')} with={row_with.get('certification')}",
        )

    await _with_server(_env(), body)


async def check_toolchain_guard(tmp: Path) -> None:
    """A lake whose elan home lacks the pinned toolchain must not start a download."""
    wrong_elan = tmp / "wrong-elan"
    (wrong_elan / "bin").mkdir(parents=True, exist_ok=True)
    (wrong_elan / "toolchains").mkdir(exist_ok=True)
    (wrong_elan / "bin" / "lake.exe").write_text("", encoding="utf-8")
    workspace = tmp / "lean-workspace"
    workspace.mkdir(exist_ok=True)
    (workspace / "lakefile.toml").write_text('name = "ws"\n', encoding="utf-8")
    (workspace / "lean-toolchain").write_text(
        "leanprover/lean4:v4.33.0", encoding="utf-8"
    )
    (workspace / ".symkit-lean-ready").write_text(
        json.dumps({"toolchain": "4.33.0", "mathlib_rev": "v4.33.0"}), encoding="utf-8"
    )

    async def body(session: Any) -> None:
        await call(session, "session_start", {"name": "regress-guard"})
        report = await call(session, "session_certify", {})
        reason = report.get("reason") or ""
        ok = report.get("lean_available") is False and "ELAN_HOME" in reason
        _record("A3 guard: wrong-elan lake refuses instead of downloading", ok,
                f"lean_available={report.get('lean_available')} reason={reason}")

    await _with_server(_env(data=str(tmp), elan=str(wrong_elan)), body)


async def check_healthy_certify(tmp: Path) -> None:
    async def body(session: Any) -> None:
        await call(session, "session_start", {"name": "regress-healthy"})
        await call(session, "math",
                   {"operation": "simplify", "expression": "x*(x + 1) - x**2", "session": True})
        report = await call(session, "session_certify", {})
        ok = report.get("success") is True and (report.get("summary") or {}).get("proven") == 1
        _record("Healthy install still certifies a real step",
                ok, f"toolchain={report.get('toolchain')} summary={report.get('summary')}")

    await _with_server(_env(), body)


async def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="symkit-regress-") as tmp:
        tmp_path = Path(tmp)
        for name, fn in (
            ("trivial", check_trivial),
            ("assumptions", check_assumptions),
            ("toolchain_guard", check_toolchain_guard),
            ("healthy", check_healthy_certify),
        ):
            try:
                await fn(tmp_path)
            except Exception as exc:  # noqa: BLE001 - a check must never skip the rest
                _record(name, False, f"raised {type(exc).__name__}: {exc}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("LEAN-REGRESS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

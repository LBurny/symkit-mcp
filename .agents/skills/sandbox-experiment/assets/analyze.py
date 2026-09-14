#!/usr/bin/env python
"""Summarize a symkit-mcp black-box suite run.

Usage: python analyze.py [RUN-PREFIX]      (default r16; must match the
run-id prefix used by run_suite.sh, e.g. r17 -> r17-task-01, r17-task-02, ...)

Reads runs/<prefix>-task-*/stream.jsonl and emits a markdown table plus JSON.
Read-only: never touches run artifacts. Known noise to strip by hand before
writing reports: client-side Read/Edit errors inflate mcp_errors, and Read
echoes containing the substring '"success": false' inflate success_false.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

# <lab>/analyze.py -> parents[0] is the lab root
LAB = Path(__file__).resolve().parent
RUNS = LAB / "runs"
FORBIDDEN = ("symkit-mcp-master", "nsforge-mcp-sigma")


def blocks(ev: dict, key: str) -> list:
    msg = ev.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict) and b.get("type") == key]
    return []


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b.get("text") or b.get("content") or "")
            else:
                out.append(str(b))
        return " ".join(out)
    return str(content)


def analyze(run_dir: Path) -> dict:
    stream = run_dir / "stream.jsonl"
    info: dict = {
        "run": run_dir.name,
        "stream_bytes": stream.stat().st_size if stream.exists() else 0,
        "events": collections.Counter(),
        "tool_use": collections.Counter(),
        "mcp_calls": 0,
        "nonmcp_calls": 0,
        "mcp_errors": 0,
        "success_false": 0,
        "discipline": [],
        "result": {},
    }
    if not stream.exists():
        info["result"] = {"subtype": "NO-STREAM"}
        return info

    with stream.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                info["events"]["<unparsed>"] += 1
                continue
            t = ev.get("type", "?")
            info["events"][t] += 1

            if t == "assistant":
                for b in blocks(ev, "tool_use"):
                    name = b.get("name", "?")
                    info["tool_use"][name] += 1
                    if name.startswith("mcp__"):
                        info["mcp_calls"] += 1
                    else:
                        info["nonmcp_calls"] += 1
                    payload = json.dumps(b.get("input", {}), ensure_ascii=False)
                    for bad in FORBIDDEN:
                        if bad in payload:
                            info["discipline"].append(f"{name}: {payload[:200]}")
            elif t == "user":
                for b in blocks(ev, "tool_result"):
                    blob = text_of(b.get("content", ""))
                    if b.get("is_error"):
                        info["mcp_errors"] += 1
                    if '"success": false' in blob or '"success":false' in blob:
                        info["success_false"] += 1
            elif t == "result":
                info["result"] = {
                    k: ev.get(k)
                    for k in (
                        "subtype", "is_error", "num_turns", "total_cost_usd",
                        "duration_ms", "terminal_reason", "stop_reason",
                        "permission_denials", "result",
                    )
                }
    return info


def verdict(info: dict) -> str:
    r = info.get("result") or {}
    if r.get("subtype") == "NO-STREAM":
        return "NO-STREAM"
    if r.get("is_error"):
        return "ERROR"
    if r.get("subtype") != "success":
        return f"INCOMPLETE({r.get('subtype')})"
    return "SUCCESS"


def main() -> int:
    prefix = sys.argv[1] if len(sys.argv) > 1 else "r16"
    dirs = sorted(p for p in RUNS.glob(f"{prefix}-task-*") if p.is_dir())
    if not dirs:
        print(f"no {prefix}-task-* run directories found", file=sys.stderr)
        return 1
    rows = [analyze(d) for d in dirs]

    print("| run | verdict | turns | MCP | non-MCP | err | success:false | discipline | cost |")
    print("|---|---|---|---|---|---|---|---|---|")
    for i in rows:
        r = i["result"] or {}
        cost = r.get("total_cost_usd")
        cost = f"${cost:.2f}" if isinstance(cost, (int, float)) else "-"
        disc = "CLEAN" if not i["discipline"] else f"VIOLATION({len(i['discipline'])})"
        print(
            f"| {i['run']} | {verdict(i)} | {r.get('num_turns','-')} | "
            f"{i['mcp_calls']} | {i['nonmcp_calls']} | {i['mcp_errors']} | "
            f"{i['success_false']} | {disc} | {cost} |"
        )

    print("\n### tool_use detail\n")
    for i in rows:
        print(f"- **{i['run']}**: " + ", ".join(
            f"{k}={v}" for k, v in i["tool_use"].most_common()
        ))

    print("\n### result tails\n")
    for i in rows:
        r = i["result"] or {}
        tail = r.get("result") or ""
        tail = re.sub(r"\s+", " ", str(tail))[:400]
        print(f"- **{i['run']}** [{verdict(i)}]: {tail}")

    out = LAB / "runs" / "_analysis" / "suite-summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nJSON -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
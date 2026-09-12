#!/usr/bin/env python
"""Modularity ratchet checker for bylaw §5.1.

Existing oversized files and functions are frozen at their current size in
``modularity-baseline.json``. They may shrink but never grow; anything not in
the baseline must respect the hard limits. This turns §5.1 from an unenforced
aspiration into a CI gate.

Usage:
    uv run python scripts/check_modularity.py            # check, exit 1 on violation
    uv run python scripts/check_modularity.py --report   # check plus advisory metrics
    uv run python scripts/check_modularity.py --update   # lower the baseline (never raise)
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "modularity-baseline.json"
SCAN_ROOTS = ("src", "tests")

FILE_HARD = 600
FILE_SOFT = 300
FUNC_HARD = 60
FUNC_SOFT = 40
CLASS_HARD = 400
CLASS_SOFT = 200
CC_HARD = 15
CC_SOFT = 10
DIR_HARD = 20
DIR_SOFT = 12


@dataclass
class FileMetrics:
    """Metrics for one source file."""

    lines: int
    functions: dict[str, tuple[int, int]] = field(default_factory=dict)  # name -> (lines, cc)
    classes: dict[str, int] = field(default_factory=dict)  # name -> lines


def _length(node: ast.stmt) -> int:
    """Line span of a statement node; `end_lineno` is optional in the AST types."""
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return end - node.lineno + 1


def _cyclomatic(node: ast.AST) -> int:
    branches = (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With,
                ast.BoolOp, ast.IfExp, ast.Assert, ast.comprehension)
    return 1 + sum(1 for child in ast.walk(node) if isinstance(child, branches))


def _walk_body(body: list[ast.stmt], prefix: str, metrics: FileMetrics) -> None:
    """Collect leaf functions and all classes, using dotted names for nesting."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = prefix + node.name
            nested = any(isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)) for c in node.body)
            if not nested:
                metrics.functions[name] = (_length(node), _cyclomatic(node))
            _walk_body(node.body, name + ".", metrics)
        elif isinstance(node, ast.ClassDef):
            name = prefix + node.name
            metrics.classes[name] = _length(node)
            _walk_body(node.body, name + ".", metrics)


def measure_file(path: Path) -> FileMetrics | None:
    """Parse one file; return None when it cannot be read or parsed."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None
    metrics = FileMetrics(lines=source.count("\n") + 1)
    _walk_body(tree.body, "", metrics)
    return metrics


def collect() -> dict[str, FileMetrics]:
    """Measure every Python file under the scanned roots, keyed by POSIX relpath."""
    metrics: dict[str, FileMetrics] = {}
    for root_name in SCAN_ROOTS:
        for path in sorted((REPO_ROOT / root_name).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            result = measure_file(path)
            if result is not None:
                metrics[path.relative_to(REPO_ROOT).as_posix()] = result
    return metrics


def _load_baseline() -> dict[str, dict[str, int]]:
    if not BASELINE_PATH.exists():
        return {"files": {}, "functions": {}}
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {"files": data.get("files", {}), "functions": data.get("functions", {})}


def check(metrics: dict[str, FileMetrics], baseline: dict[str, dict[str, int]]) -> list[str]:
    """Return violation messages: baselined growth, or new items over the hard limit."""
    problems: list[str] = []
    frozen_files = baseline["files"]
    frozen_funcs = baseline["functions"]

    for rel, m in sorted(metrics.items()):
        if rel in frozen_files:
            if m.lines > frozen_files[rel]:
                problems.append(
                    f"{rel}: {m.lines} lines, baseline {frozen_files[rel]} "
                    f"(+{m.lines - frozen_files[rel]}) — frozen file grew"
                )
        elif m.lines > FILE_HARD:
            problems.append(f"{rel}: {m.lines} lines exceeds hard limit {FILE_HARD} (new file)")

        for name, (lines, _cc) in sorted(m.functions.items()):
            key = f"{rel}::{name}"
            if key in frozen_funcs:
                if lines > frozen_funcs[key]:
                    problems.append(
                        f"{key}: {lines} lines, baseline {frozen_funcs[key]} "
                        f"(+{lines - frozen_funcs[key]}) — frozen function grew"
                    )
            elif lines > FUNC_HARD:
                problems.append(f"{key}: {lines} lines exceeds hard limit {FUNC_HARD} (new function)")

    for key in sorted(set(frozen_files) | set(frozen_funcs)):
        rel = key.split("::", 1)[0]
        if rel not in metrics:
            problems.append(f"{key}: baselined entry no longer exists — run --update")
    return problems


def desired_baseline(metrics: dict[str, FileMetrics]) -> dict[str, dict[str, int]]:
    """Current sizes of everything still over a hard limit (digested items drop out)."""
    files = {rel: m.lines for rel, m in metrics.items() if m.lines > FILE_HARD}
    functions = {
        f"{rel}::{name}": lines
        for rel, m in metrics.items()
        for name, (lines, _cc) in m.functions.items()
        if lines > FUNC_HARD
    }
    return {"files": dict(sorted(files.items())), "functions": dict(sorted(functions.items()))}


def apply_update(new: dict[str, dict[str, int]], old: dict[str, dict[str, int]]) -> int:
    """Write the baseline, refusing to raise any recorded limit."""
    raised = [
        f"{key}: {old[section][key]} -> {value}"
        for section, values in new.items()
        for key, value in values.items()
        if key in old[section] and value > old[section][key]
    ]
    if raised:
        print("Refusing to raise baselined limits (bylaw §5.1.1 — ratchet only lowers):")
        for item in raised:
            print(f"  {item}")
        print("Split the file/function first, or pass --force with reviewer approval.")
        return 1
    BASELINE_PATH.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Baseline written to {BASELINE_PATH.relative_to(REPO_ROOT)}")
    print(f"  frozen files: {len(new['files'])}  frozen functions: {len(new['functions'])}")
    return 0


def _top(items: list[tuple[int, str]], limit: int, label: str) -> None:
    if not items:
        return
    print(f"\n  {label}:")
    for value, name in sorted(items, reverse=True)[:8]:
        mark = "hard" if value > limit * 1.5 else "soft"
        print(f"    {name}: {value} ({mark} band)")


def report(metrics: dict[str, FileMetrics]) -> None:
    """Print advisory metrics that are review triggers, not failures."""
    print("Advisory review triggers (reported, never fatal):")
    _top([(m.lines, rel) for rel, m in metrics.items() if m.lines > FILE_SOFT],
         FILE_SOFT, f"files over {FILE_SOFT} lines")
    _top([(m.functions[n][0], f"{rel}::{n}") for rel, m in metrics.items()
          for n in m.functions if m.functions[n][0] > FUNC_SOFT],
         FUNC_SOFT, f"functions over {FUNC_SOFT} lines")
    _top([(m.classes[c], f"{rel}::{c}") for rel, m in metrics.items()
          for c in m.classes if m.classes[c] > CLASS_SOFT],
         CLASS_SOFT, f"classes over {CLASS_SOFT} lines (hard cap {CLASS_HARD})")
    _top([(m.functions[n][1], f"{rel}::{n}") for rel, m in metrics.items()
          for n in m.functions if m.functions[n][1] > CC_SOFT],
         CC_SOFT, f"cyclomatic complexity over {CC_SOFT} (hard cap {CC_HARD})")
    _top([(count, f"{d.as_posix()}/") for d in _dirs()
          if (count := sum(1 for _ in d.glob("*.py"))) > DIR_SOFT],
         DIR_SOFT, f"modules with over {DIR_SOFT} files (hard cap {DIR_HARD})")


def _dirs() -> list[Path]:
    dirs: list[Path] = []
    for root_name in SCAN_ROOTS:
        for path in sorted((REPO_ROOT / root_name).rglob("*")):
            if path.is_dir() and "__pycache__" not in path.parts:
                dirs.append(path)
    return dirs


def main() -> int:
    parser = argparse.ArgumentParser(description="Modularity ratchet checker (bylaw §5.1)")
    parser.add_argument("--update", action="store_true", help="rewrite the baseline downward")
    parser.add_argument("--force", action="store_true", help="allow --update to raise a limit")
    parser.add_argument("--report", action="store_true", help="also print advisory metrics")
    args = parser.parse_args()

    metrics = collect()
    if args.report:
        report(metrics)
    if args.update:
        if args.force:
            BASELINE_PATH.write_text(
                json.dumps(desired_baseline(metrics), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print("Baseline force-written (limits raised).")
            return 0
        return apply_update(desired_baseline(metrics), _load_baseline())

    problems = check(metrics, _load_baseline())
    if problems:
        print(f"Modularity violations: {len(problems)}\n")
        for item in problems:
            print(f"  {item}")
        print("\nSee .github/bylaws/ddd-architecture.md §5.1 for the ratchet rules.")
        return 1
    frozen = len(_load_baseline()["files"]) + len(_load_baseline()["functions"])
    print(f"Modularity OK — no frozen item grew; {frozen} baselined item(s) still frozen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

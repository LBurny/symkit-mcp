"""One-shot Python/sympy code execution in an isolated subprocess.

Escape hatch for derivations the curated tool surface cannot express. Every
call spawns a fresh interpreter (no state survives between calls) and the
whole process tree is killed on timeout via ``run_with_tree_timeout``, so a
wedged SymPy call cannot take the MCP server down with it. The AST screen
is a speed bump against obvious filesystem/network/process escapes, NOT a
security boundary — the trust model is a trusted local client, and the MCP
layer can disable the tool outright via ``SYMKIT_DISABLE_CODE_EXEC``.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from symkit.infrastructure.lean_process import run_with_tree_timeout

STDOUT_LIMIT = 8192
STDERR_LIMIT = 4096
RESULT_LIMIT = 8192

_BANNED_NAMES = frozenset(
    {"__import__", "open", "eval", "exec", "compile", "input", "breakpoint"}
)
_BANNED_MODULES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "importlib",
        "ctypes",
        "builtins",
        "urllib",
        "http",
        "requests",
    }
)

# The runner reads the user script and a result-file path from argv, executes
# the script in a namespace pre-seeded with ``from sympy import *``, and on
# success writes {"repr", "srepr", "type"} of a top-level ``result`` variable
# (if defined) to the result file. stdout/stderr stay purely the user's.
_RUNNER = """\
import json
import sys
import traceback

import sympy


def emit(value, result_path):
    try:
        srepr = sympy.srepr(value)
    except Exception:
        srepr = None
    payload = {"repr": repr(value), "srepr": srepr, "type": type(value).__name__}
    with open(result_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, default=str)


def main():
    code_path, result_path = sys.argv[1], sys.argv[2]
    with open(code_path, encoding="utf-8") as handle:
        source = handle.read()
    namespace = {"__name__": "__main__"}
    try:
        exec(compile("from sympy import *", "<prelude>", "exec"), namespace)
        exec(compile(source, code_path, "exec"), namespace)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    if "result" in namespace:
        emit(namespace["result"], result_path)


main()
"""


@dataclass(frozen=True)
class ExecResult:
    """Structured outcome of a one-shot code execution."""

    status: str  # "success" | "error" | "timeout" | "rejected"
    stdout: str = ""
    stderr: str = ""
    result_repr: str | None = None
    result_srepr: str | None = None
    result_type: str | None = None
    # ``None`` when no process ever ran (screen failures): a numeric code there
    # would fabricate a success signal for exit-code-driven callers (r22).
    exit_code: int | None = None
    duration_ms: int = 0
    truncated: tuple[str, ...] = ()
    reason: str | None = None


_GUIDANCE = (
    "filesystem/network/process access is not available in python_exec; "
    "compute in memory and hand results back via a top-level 'result' variable"
)


def _banned_construct(node: ast.AST) -> str | None:
    """Return a reason string if ``node`` is a banned construct, else None."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] in _BANNED_MODULES:
                return f"import of banned module {alias.name!r}: {_GUIDANCE}"
    elif isinstance(node, ast.ImportFrom):
        if (node.module or "").split(".")[0] in _BANNED_MODULES:
            return f"import from banned module {node.module!r}: {_GUIDANCE}"
    elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
        return f"use of banned name {node.id!r}: {_GUIDANCE}"
    return None


def screen_code(source: str) -> ExecResult | None:
    """Return a failure ``ExecResult`` for unusable source, else None."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ExecResult(status="error", stderr=f"SyntaxError: {exc}")
    for node in ast.walk(tree):
        reason = _banned_construct(node)
        if reason is not None:
            return ExecResult(status="rejected", reason=reason)
    return None


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = f"\n... [truncated, {len(text)} chars total]"
    return text[:limit] + marker, True


def _read_payload(path: Path) -> dict[str, str | None] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _result_fields(
    payload: dict[str, str | None] | None, truncated: list[str]
) -> tuple[str | None, str | None, str | None]:
    """Truncated (repr, srepr, type) triple from the runner's result payload."""
    if payload is None:
        return None, None, None
    result_repr, hit = _truncate(str(payload.get("repr") or ""), RESULT_LIMIT)
    if hit:
        truncated.append("result.repr")
    result_srepr = None
    srepr = payload.get("srepr")
    if srepr:
        result_srepr, hit = _truncate(str(srepr), RESULT_LIMIT)
        if hit:
            truncated.append("result.srepr")
    return result_repr, result_srepr, str(payload.get("type") or "") or None


def run_python(code: str, timeout_seconds: float) -> ExecResult:
    """Screen ``code``, run it one-shot in a subprocess, return the outcome."""
    failure = screen_code(code)
    if failure is not None:
        return failure
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="symkit-exec-") as tmp:
        tmpdir = Path(tmp)
        runner = tmpdir / "runner.py"
        script = tmpdir / "user_code.py"
        result_file = tmpdir / "result.json"
        runner.write_text(_RUNNER, encoding="utf-8")
        script.write_text(code, encoding="utf-8")
        exit_code, raw_out, raw_err, timed_out = run_with_tree_timeout(
            [sys.executable, "-u", str(runner), str(script), str(result_file)],
            cwd=tmpdir,
            timeout=timeout_seconds,
        )
        payload = _read_payload(result_file)
    duration_ms = int((time.monotonic() - started) * 1000)
    truncated: list[str] = []
    stdout, hit = _truncate(raw_out, STDOUT_LIMIT)
    if hit:
        truncated.append("stdout")
    stderr, hit = _truncate(raw_err, STDERR_LIMIT)
    if hit:
        truncated.append("stderr")
    if timed_out:
        return ExecResult(
            status="timeout",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            truncated=tuple(truncated),
            reason=(
                f"timed out after {timeout_seconds:g}s; the process tree was "
                "killed and any captured output is partial"
            ),
        )
    result_repr, result_srepr, result_type = _result_fields(payload, truncated)
    status = "success" if exit_code == 0 else "error"
    return ExecResult(
        status=status,
        stdout=stdout,
        stderr=stderr,
        result_repr=result_repr,
        result_srepr=result_srepr,
        result_type=result_type,
        exit_code=exit_code,
        duration_ms=duration_ms,
        truncated=tuple(truncated),
    )

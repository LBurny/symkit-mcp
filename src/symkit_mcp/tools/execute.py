"""python_exec: one-shot Python/sympy execution escape hatch."""

from __future__ import annotations

import os
from typing import Any

from symkit.infrastructure.code_exec import ExecResult, run_python

_DEFAULT_TIMEOUT = 10
_MAX_TIMEOUT = 60
_DISABLE_ENV = "SYMKIT_DISABLE_CODE_EXEC"


def _clamp_timeout(value: int) -> int:
    """Clamp ``timeout_seconds`` into [1, 60] seconds."""
    return max(1, min(_MAX_TIMEOUT, int(value)))


def _to_response(outcome: ExecResult) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": outcome.status,
        "stdout": outcome.stdout,
        "stderr": outcome.stderr,
        "exit_code": outcome.exit_code,
        "duration_ms": outcome.duration_ms,
    }
    if outcome.result_repr is not None:
        response["result"] = {
            "repr": outcome.result_repr,
            "srepr": outcome.result_srepr,
            "type": outcome.result_type,
        }
    if outcome.truncated:
        response["truncated"] = list(outcome.truncated)
    if outcome.reason is not None:
        response["reason"] = outcome.reason
    return response


def python_exec_impl(code: str, timeout_seconds: int = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Validate inputs, honor the disable switch, run the engine, shape the reply."""
    if os.environ.get(_DISABLE_ENV) == "1":
        return {
            "status": "disabled",
            "message": f"code execution is disabled via {_DISABLE_ENV}=1",
        }
    effective = _clamp_timeout(timeout_seconds)
    outcome = run_python(code, timeout_seconds=float(effective))
    response = _to_response(outcome)
    # Echo the effective limit so a clamped request is visible (r22 task-14).
    response["timeout_seconds"] = effective
    return response


def register_execute_tools(mcp: Any) -> None:
    """Register the code-execution escape hatch."""

    @mcp.tool(
        meta={
            "category": "Execution",
            "example": "python_exec(code=\"x = symbols('x'); result = integrate(x**2, x)\")",
        }
    )
    def python_exec(code: str, timeout_seconds: int = _DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Run a one-shot Python snippet in an isolated subprocess with SymPy preloaded.

        Escape hatch for derivations the curated tools cannot express. The code
        runs in a fresh interpreter on every call (no state persists); the whole
        process tree is killed when the timeout expires. Define a top-level
        variable named ``result`` to get its repr and srepr back — the srepr
        pastes directly into any tool's ``expression`` field (constructor
        forms like ``Mul(...)``/``Symbol('c', positive=True)`` load with
        assumptions intact). stdout and
        stderr are captured and returned. Prefer the curated tools (math,
        session_*, assume) first; use this only when they cannot express the
        computation, and record outcomes worth keeping via session_record_step.
        Obvious filesystem/network/process escapes (open, os, subprocess,
        socket, ...) are rejected; this is a courtesy screen, not a sandbox.
        Set SYMKIT_DISABLE_CODE_EXEC=1 to disable the tool (status "disabled").

        Args:
            code: Python source to execute. ``from sympy import *`` is already
                applied. The child shares the server's Python environment, so
                packages installed there (sympy always; numpy/scipy only if
                present) are importable.
            timeout_seconds: Wall-clock limit in whole seconds, clamped to
                [1, 60]. Default 10. The effective value is echoed back in the
                response, so a clamped request is visible.

        Returns:
            Dict with status ("success" | "error" | "timeout" | "rejected" |
            "disabled"), stdout, stderr, exit_code (null when no process ran),
            duration_ms, timeout_seconds, and on success an optional result
            {repr, srepr, type}. Truncated channels are listed by name under
            "truncated" ("stdout", "stderr", "result.repr", "result.srepr");
            rejections and timeouts carry "reason". A timeout keeps whatever
            stdout/stderr the code flushed before the kill.
        """
        return python_exec_impl(code, timeout_seconds)

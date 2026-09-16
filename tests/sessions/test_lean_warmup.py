"""``lean_status(warmup=true)`` primes the Lean workspace before a first certify.

A fresh workspace compiles its Mathlib imports on the first
``session_certify``; that single synchronous call can exceed the client's
request timeout and surfaced as a raw ``MCP error -32001`` (operator feedback,
2026-09-16: the same call passed on the second attempt, once the caches were
warm).  The warmup entry runs the same batch checker on a trivial ring
theorem, so the compile cost lands in an explicit, retryable, honestly
reported call instead of the middle of a certification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from symkit.domain.lean_types import LeanOutcome
from symkit.infrastructure.lean_toolchain import LeanStatus
from symkit_mcp.tools import certification as certification_tools
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _mcp() -> Any:
    mcp = MockMCP()
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    certification_tools.register_certification_tools(mcp)
    return mcp


_READY = {
    "lake_path": "D:/fake/lake",
    "workspace": "D:/fake/ws",
    "mathlib_found": True,
    "mathlib_ready": True,
    "workspace_ready": True,
    "stamp_present": True,
}


class _WarmChecker:
    """Stand-in recording how the warmup drove the real batch-checker seam."""

    instances: list[tuple[str, str]] = []
    statements: list[str] = []

    def __init__(self, lake: Any, workspace: Any, **_kwargs: Any) -> None:
        _WarmChecker.instances.append((str(lake), str(workspace)))

    def check(self, statements: Any) -> list[LeanOutcome]:
        _WarmChecker.statements = [s.name for s in statements]
        return [LeanOutcome(s.name, True) for s in statements]


def test_warmup_runs_the_workspace_smoke(fresh_session_manager, monkeypatch) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(certification_tools, "detect_status", lambda: LeanStatus(True, None, **_READY))
    monkeypatch.setattr(certification_tools, "LeanBatchChecker", _WarmChecker)
    _WarmChecker.instances = []
    _WarmChecker.statements = []

    res = _mcp().tools["lean_status"](warmup=True)

    warm = res["warmup"]
    assert warm["smoke_passed"] is True, warm
    assert warm["elapsed_s"] >= 0.0
    assert _WarmChecker.instances[0][1] == str(Path("D:/fake/ws"))
    assert _WarmChecker.statements == ["symkit_warmup"]


def test_warmup_is_skipped_without_a_toolchain(fresh_session_manager, monkeypatch) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(
        certification_tools, "detect_status", lambda: LeanStatus(False, "no lake")
    )

    res = _mcp().tools["lean_status"](warmup=True)

    assert res["warmup"] == {"skipped": "no lake"}, res


def test_warmup_reports_a_timeout_with_retry_guidance(fresh_session_manager, monkeypatch) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(certification_tools, "detect_status", lambda: LeanStatus(True, None, **_READY))

    class _TimeoutChecker:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def check(self, statements: Any) -> list[LeanOutcome]:
            return [LeanOutcome(s.name, False, "timeout") for s in statements]

    monkeypatch.setattr(certification_tools, "LeanBatchChecker", _TimeoutChecker)

    res = _mcp().tools["lean_status"](warmup=True)

    warm = res["warmup"]
    assert warm["smoke_passed"] is False
    assert warm["detail"] == "timeout"
    assert "again" in warm["next_step"], warm


def test_default_lean_status_stays_read_only(fresh_session_manager, monkeypatch) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(certification_tools, "detect_status", lambda: LeanStatus(True, None, **_READY))

    res = _mcp().tools["lean_status"]()

    assert "warmup" not in res, sorted(res)

"""Lean kernel certification MCP tool (``session_certify``) and ``lean_status``."""

from __future__ import annotations

import json
from typing import Any

import pytest

from symkit.domain.lean_types import LeanOutcome
from symkit.infrastructure import lean_toolchain
from symkit.infrastructure.lean_toolchain import LeanStatus
from symkit_mcp.tools import certification as certification_tools
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# MockMCP is provided by conftest.py


def _mcp() -> Any:
    mcp = MockMCP()  # noqa: F821
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    certification_tools.register_certification_tools(mcp)
    return mcp


class _FakeBatchChecker:
    """Stand-in for LeanBatchChecker returning every goal as proven."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def check(self, statements: Any) -> list[LeanOutcome]:
        return [LeanOutcome(s.name, True) for s in statements]


def test_certify_reports_unavailable_without_toolchain(
    fresh_session_manager: Any, monkeypatch: Any
) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(
        certification_tools, "detect_status", lambda: LeanStatus(False, "no lake")
    )
    mcp = _mcp()
    mcp.tools["session_start"]("certify-unavailable")

    result = mcp.tools["session_certify"]()

    assert result["success"] is False
    assert result["lean_available"] is False
    assert "symkit-lean-setup" in result["setup"]
    assert "lean_status()" in result["diagnose"]


def test_lean_status_reports_environment(fresh_session_manager: Any, monkeypatch: Any) -> None:
    _ = fresh_session_manager
    status = LeanStatus(
        False,
        "lake not found",
        lake_path=None,
        workspace=None,
        mathlib_found=False,
        mathlib_ready=False,
        workspace_ready=False,
        stamp_present=False,
    )
    monkeypatch.setattr(certification_tools, "describe_environment", lambda: _report(status))
    mcp = _mcp()

    result = mcp.tools["lean_status"]()

    assert result["available"] is False
    assert result["missing"] == ["lake", "workspace"]
    assert result["next_step"] and "--yes" in result["next_step"]


def _report(status: LeanStatus) -> dict[str, Any]:
    return lean_toolchain.describe_environment(status)


@pytest.mark.parametrize("name", ["lean_status", "session_certify"])
def test_lean_tools_are_registered(fresh_session_manager: Any, name: str) -> None:
    _ = fresh_session_manager
    assert name in _mcp().tools


def test_lean_status_is_read_only(fresh_session_manager: Any, monkeypatch: Any) -> None:
    """It must never run `lake` or download: describe_environment is pure."""
    _ = fresh_session_manager
    calls: list[str] = []

    def _guard(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("subprocess")
        raise AssertionError("lean_status must not run subprocesses")

    monkeypatch.setattr(lean_toolchain.subprocess, "run", _guard)
    monkeypatch.setattr(lean_toolchain.subprocess, "Popen", _guard)

    mcp = _mcp()
    mcp.tools["lean_status"]()

    assert calls == []


def test_lean_status_available_and_no_next_step(
    fresh_session_manager: Any, monkeypatch: Any
) -> None:
    _ = fresh_session_manager
    status = LeanStatus(
        True,
        "",
        lake_path="/l/lake",
        workspace="/ws",
        toolchain="4.33.0",
        mathlib_rev="v4.33.0",
        mathlib_found=True,
        mathlib_ready=True,
        workspace_ready=True,
        stamp_present=True,
    )
    monkeypatch.setattr(certification_tools, "describe_environment", lambda: _report(status))
    mcp = _mcp()

    result = mcp.tools["lean_status"]()

    assert result["available"] is True
    assert result["missing"] == [] and result["next_step"] is None
    assert json.dumps(result).count("mathlib") >= 1


def test_certify_runs_with_fake_checker(
    fresh_session_manager: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(
        certification_tools,
        "detect_status",
        lambda: LeanStatus(
            True, "", "/fake/lake", str(tmp_path), "4.24.0",
            mathlib_found=True, mathlib_ready=True, workspace_ready=True, stamp_present=True,
        ),
    )
    monkeypatch.setattr(certification_tools, "LeanBatchChecker", _FakeBatchChecker)
    mcp = _mcp()
    mcp.tools["session_start"]("certify-fake")
    # Non-trivial on purpose: `x + 2*x` parses straight to `3*x`, so the simplify
    # step would be a tautology and certify as `trivial` (B1).
    mcp.tools["math"]("simplify", "x*(x + 1) - x**2", session=True)

    result = mcp.tools["session_certify"]()

    assert result["success"] is True
    assert result["toolchain"] == "4.24.0"
    assert result["summary"]["proven"] >= 1


def test_certify_rejects_malformed_assumptions(
    fresh_session_manager: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(
        certification_tools,
        "detect_status",
        lambda: LeanStatus(True, "", "/fake/lake", str(tmp_path), "4.24.0"),
    )
    monkeypatch.setattr(certification_tools, "LeanBatchChecker", _FakeBatchChecker)
    mcp = _mcp()
    mcp.tools["session_start"]("certify-bad-assume")

    result = mcp.tools["session_certify"](assumptions="cp")

    assert result["success"] is False
    assert "symbol/property" in result["error"]


def test_certify_accepts_string_assumptions(
    fresh_session_manager: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    _ = fresh_session_manager
    monkeypatch.setattr(
        certification_tools,
        "detect_status",
        lambda: LeanStatus(True, "", "/fake/lake", str(tmp_path), "4.24.0"),
    )
    monkeypatch.setattr(certification_tools, "LeanBatchChecker", _FakeBatchChecker)
    mcp = _mcp()
    mcp.tools["session_start"]("certify-assume-str")
    mcp.tools["math"]("simplify", "1/x + 1/x**3", session=True)

    result = mcp.tools["session_certify"](assumptions="x nonzero")

    assert result["success"] is True
    row = next(r for r in result["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "proven"
    assert "h_x : x ≠ 0" in row["statement"]

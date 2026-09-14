"""Lean kernel certification MCP tool (``session_certify``)."""

from __future__ import annotations

from typing import Any

from symkit.domain.lean_types import LeanOutcome
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


def test_certify_runs_with_fake_checker(
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

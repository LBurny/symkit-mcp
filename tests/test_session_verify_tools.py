"""Tests for unified session verification and completion tools."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.infrastructure import derivation_repository as repo_mod  # noqa: E402
from symkit_mcp.tools import math as math_tools  # noqa: E402
from symkit_mcp.tools import session as session_tools  # noqa: E402

# MockMCP is provided by conftest.py


def _register_all_tools(mcp: Any) -> None:
    """Register session and math tools."""
# ruff: noqa: F821  # MockMCP from conftest.py
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)


class TestSessionVerifyTools:
    def test_verify_step_without_session(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["session_verify_step"]()
        assert result["success"] is False
        assert "No active session" in result["error"]

    def test_verify_step_last_step(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("test")
        mcp.tools["session_load_formula"]("(x + 1)**2")
        mcp.tools["math"]("simplify", "(x + 1)**2", session=True)

        result = mcp.tools["session_verify_step"](1)
        assert result["success"] is True
        assert result["verification_status"] == "verified"
        assert "verified" in result["step"]["verification_result"]

    def test_verify_session_summary(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("test")
        mcp.tools["session_load_formula"]("x**3")
        mcp.tools["math"]("diff", "x**3", variable="x", session=True)

        result = mcp.tools["session_verify_session"]()
        assert result["success"] is True
        assert result["total"] == 2
        assert result["verified"] == 2
        assert result["overall"] == "verified"
        assert "Verified:" in result["display_text"]


class TestSessionCompleteVerification:
    def test_complete_saves_verified_status(
        self, fresh_session_manager: Any, tmp_path: Path, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        monkeypatch.chdir(tmp_path)
        repo_mod._repository = None  # reset global repo singleton

        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("verified_test")
        mcp.tools["session_load_formula"]("x**2")
        mcp.tools["math"]("diff", "x**2", variable="x", session=True)

        result = mcp.tools["session_complete"](
            description="test derivation",
            assumptions=["x is real"],
        )
        assert result["success"] is True
        assert "verification_summary" in result
        assert result["verification_summary"]["overall"] == "verified"
        assert "saved_to" in result

        saved_path = Path(result["saved_to"])
        assert saved_path.exists()
        with open(saved_path, encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["verified"] is True
        assert saved["verification_method"] == "step_verifier"
        assert saved["verified_at"] is not None

    def test_complete_with_custom_step_not_verified(
        self, fresh_session_manager: Any, tmp_path: Path, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        monkeypatch.chdir(tmp_path)
        repo_mod._repository = None

        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("inconclusive_test")
        mcp.tools["session_load_formula"]("x**2")
        mcp.tools["session_add_note"]("observation note", note_type="observation")

        result = mcp.tools["session_complete"](description="test")
        assert result["success"] is True
        assert result["verification_summary"]["overall"] == "inconclusive"
        saved_path = Path(result["saved_to"])
        with open(saved_path, encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["verified"] is False
        assert saved["verification_method"] == ""

"""Tests for Phase 5 - External source integration in orchestration tools."""
# ruff: noqa: F821  # MockMCP from conftest.py

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.formula_recommender import FormulaInfoAdapter  # noqa: E402
from symkit.infrastructure.adapters.base import BaseAdapter, FormulaInfo  # noqa: E402
from symkit_mcp.tools import (  # noqa: E402
    math as math_tools,
)
from symkit_mcp.tools import (
    orchestration as orchestration_tools,
)
from symkit_mcp.tools import (
    session as session_tools,
)

# MockMCP is provided by conftest.py


class FakeExternalAdapter(BaseAdapter):
    """Returns a single canned external formula."""

    @property
    def source_name(self) -> str:
        return "fake_external"

    def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
        return [
            FormulaInfo(
                id="ext_e=mc2",
                name="Mass-energy equivalence",
                expression="E - m*c**2",
                sympy_str="E - m*c**2",
                source="fake_external",
                category="physics",
                description="Einstein's mass-energy relation",
                variables={"E": {}, "m": {}, "c": {}},
            ),
        ]

    def get_formula(self, _formula_id: str) -> FormulaInfo | None:
        return None


def _register_all_tools(mcp: Any) -> None:
    """Register all tools needed for orchestration tests."""
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    orchestration_tools.register_orchestration_tools(mcp)


class TestDeriveExternalSources:
    def test_derive_includes_external_recommendations(self, fresh_session_manager: Any, monkeypatch: Any) -> None:
        _ = fresh_session_manager
        monkeypatch.setattr(
            orchestration_tools,
            "_build_external_adapters",
            lambda _sources: [FormulaInfoAdapter(FakeExternalAdapter())],
        )

        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["derive"](
            "derive mass-energy relation",
            external_sources=["fake_external"],
        )
        assert result["success"] is True
        recommended = result["recommended_formulas"]
        sources = {r["source"] for r in recommended}
        assert "fake_external" in sources

    def test_derive_external_sources_disabled(self, fresh_session_manager: Any, monkeypatch: Any) -> None:
        _ = fresh_session_manager
        monkeypatch.setattr(
            orchestration_tools,
            "_build_external_adapters",
            lambda _sources: [],
        )

        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["derive"](
            "derive mass-energy relation",
            external_sources=[],
        )
        assert result["success"] is True
        recommended = result["recommended_formulas"]
        assert all(r["source"] == "local" for r in recommended)

    def test_derive_graceful_when_external_fails(self, fresh_session_manager: Any, monkeypatch: Any) -> None:
        class FailingAdapter(BaseAdapter):
            @property
            def source_name(self) -> str:
                return "failing"

            def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
                raise RuntimeError("network down")

            def get_formula(self, _formula_id: str) -> FormulaInfo | None:
                return None

        _ = fresh_session_manager
        monkeypatch.setattr(
            orchestration_tools,
            "_build_external_adapters",
            lambda _sources: [FormulaInfoAdapter(FailingAdapter())],
        )

        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["derive"](
            "derive mass-energy relation",
            external_sources=["failing"],
        )
        assert result["success"] is True
        recommended = result["recommended_formulas"]
        assert all(r["source"] == "local" for r in recommended)


class TestDeriveExternalSourcesDefault:
    """derive without external_sources should request all sources per the docstring."""

    def test_derive_default_external_sources_is_all(self, fresh_session_manager: Any, monkeypatch: Any) -> None:
        received_sources: list[str] | None = "not-called"

        def _capture(sources: list[str] | None) -> list[Any]:
            nonlocal received_sources
            received_sources = sources
            return [FormulaInfoAdapter(FakeExternalAdapter())]

        _ = fresh_session_manager
        monkeypatch.setattr(orchestration_tools, "_build_external_adapters", _capture)

        mcp = MockMCP()
        _register_all_tools(mcp)
        result = mcp.tools["derive"]("derive mass-energy relation")
        assert result["success"] is True
        assert received_sources is None


class TestSessionExternalAdapters:
    def test_session_suggest_formulas_uses_session_external_adapters(
        self, fresh_session_manager: Any, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        # Patch the helper so derive creates a session with our fake external adapter.
        monkeypatch.setattr(
            orchestration_tools,
            "_build_external_adapters",
            lambda _sources: [FormulaInfoAdapter(FakeExternalAdapter())],
        )
        result = mcp.tools["derive"](
            "derive energy relation",
            external_sources=["fake_external"],
        )
        assert result["success"] is True

        # Now use session_suggest_formulas on the current session
        suggestion = mcp.tools["session_suggest_formulas"]()
        assert suggestion["success"] is True
        sources = {s["source"] for s in suggestion["recommendations"]}
        assert "fake_external" in sources

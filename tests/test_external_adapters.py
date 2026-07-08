"""Tests for Phase 5 - External formula adapter integration."""

from __future__ import annotations

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.formula_recommender import (  # noqa: E402
    FormulaInfoAdapter,
    create_default_external_adapters,
)
from symkit.infrastructure.adapters.base import BaseAdapter, FormulaInfo  # noqa: E402


class FakeAdapter(BaseAdapter):
    """A minimal BaseAdapter for testing the bridge."""

    @property
    def source_name(self) -> str:
        return "fake_source"

    def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
        return [
            FormulaInfo(
                id="f1",
                name="Fake Formula",
                expression="x + y",
                sympy_str="x + y",
                source="fake_source",
                category="test_domain",
                description="A fake formula for testing",
                tags=["test"],
            ),
        ]

    def get_formula(self, _formula_id: str) -> FormulaInfo | None:
        return None


class BrokenAdapter(BaseAdapter):
    """Adapter that always raises to test graceful degradation."""

    @property
    def source_name(self) -> str:
        return "broken"

    def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
        raise RuntimeError("network down")

    def get_formula(self, _formula_id: str) -> FormulaInfo | None:
        return None


class TestFormulaInfoAdapter:
    def test_converts_formula_info_to_dict(self):
        adapter = FormulaInfoAdapter(FakeAdapter())
        results = adapter.search("test", limit=5)
        assert len(results) == 1
        item = results[0]
        assert item["id"] == "f1"
        assert item["formula_id"] == "f1"
        assert item["name"] == "Fake Formula"
        assert item["expression"] == "x + y"
        assert item["domain"] == "test_domain"
        assert item["source"] == "fake_source"
        assert item["verified"] is False

    def test_uses_source_name_when_info_source_missing(self):
        class NoSourceAdapter(BaseAdapter):
            @property
            def source_name(self) -> str:
                return "no_source"

            def search(self, _query: str, _limit: int = 10) -> list[FormulaInfo]:
                return [FormulaInfo(id="ns1", name="No Source", expression="a")]

            def get_formula(self, _formula_id: str) -> FormulaInfo | None:
                return None

        adapter = FormulaInfoAdapter(NoSourceAdapter())
        results = adapter.search("x", limit=5)
        assert results[0]["source"] == "no_source"

    def test_exception_returns_empty_list(self):
        adapter = FormulaInfoAdapter(BrokenAdapter())
        results = adapter.search("test", limit=5)
        assert results == []


class TestDefaultExternalAdapters:
    def test_create_default_external_adapters_includes_scipy(self):
        adapters = create_default_external_adapters()
        assert adapters
        # SciPy constants adapter is offline and should always be present
        sources = {a.adapter.source_name for a in adapters if hasattr(a, "adapter")}
        assert any(src.startswith("scipy") for src in sources)

    def test_default_adapters_implement_protocol(self):
        adapters = create_default_external_adapters()
        assert adapters
        # Pick the offline SciPy adapter for a real search; avoid network calls.
        scipy_adapter = next(
            (a for a in adapters
             if getattr(getattr(a, "adapter", None), "source_name", "").startswith("scipy")),
            None,
        )
        assert scipy_adapter is not None
        assert callable(getattr(scipy_adapter, "search", None))
        results = scipy_adapter.search("speed of light", limit=2)
        assert isinstance(results, list)
        assert results

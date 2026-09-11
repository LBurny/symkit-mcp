"""Tests for MCP formula tools backed by the persistent index catalog."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore
from symkit_mcp.tools import _state
from symkit_mcp.tools import formula as formula_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821


def _write_yaml(root: Path, category: str, fid: str, **data) -> Path:
    d = root / category
    d.mkdir(parents=True, exist_ok=True)
    payload = {"id": fid, "name": fid, "sympy_str": "x + 1", "category": category, **data}
    path = d / f"{fid}.yaml"
    path.write_text(yaml.dump(payload, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def catalog_env(tmp_path, monkeypatch):
    seed, staging, curated = (tmp_path / t for t in ("seed", "staging", "curated"))
    for d in (seed, staging, curated):
        d.mkdir()
    store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    store.open()
    catalog = FormulaCatalog(
        store, YamlFormulaFileSource(),
        seed_dir=seed, staging_dir=staging, curated_dir=curated,
    )
    monkeypatch.setattr(_state, "_catalog", catalog)
    mcp = MockMCP()
    formula_tools.register_formula_tools(mcp)
    yield SimpleNamespace(
        catalog=catalog, mcp=mcp, seed=seed, staging=staging, curated=curated
    )
    store.close()


class TestFreshness:
    def test_add_then_search_immediately_visible(self, catalog_env):
        mcp = catalog_env.mcp
        added = mcp.tools["formula_add"](
            id="test_drag_force",
            name="Drag force",
            sympy_str="F_d == 1/2 * rho * v**2 * C_d * A",
            latex="F_d = \\frac{1}{2} \\rho v^2 C_d A",
            variables={"F_d": {"description": "drag force"}},
            category="fluid_dynamics",
        )
        assert added["success"], added
        results = mcp.tools["formula_search"]("drag force")
        ids = [r["id"] for r in results["results"]]
        assert "test_drag_force" in ids

    def test_remove_then_search_gone(self, catalog_env):
        mcp = catalog_env.mcp
        mcp.tools["formula_add"](
            id="temp_f", name="Temp formula", sympy_str="a+b", latex="a+b",
            variables={"a": {}}, category="general",
        )
        removed = mcp.tools["formula_remove"]("temp_f")
        assert removed["success"], removed
        results = mcp.tools["formula_search"]("temp formula")
        assert all(r["id"] != "temp_f" for r in results["results"])


class TestCurationSurface:
    def test_results_include_tier_verified_duplicates(self, catalog_env):
        _write_yaml(catalog_env.staging, "derived", "stg-1", name="Pendulum")
        mcp = catalog_env.mcp
        results = mcp.tools["formula_search"]("pendulum")
        top = results["results"][0]
        assert top["tier"] == "staging"
        assert top["verified"] is False
        assert top["duplicates"] == 0

    def test_tier_filter(self, catalog_env):
        _write_yaml(catalog_env.staging, "derived", "stg-1", name="Pendulum")
        _write_yaml(catalog_env.curated, "mechanics", "cur-1", name="Pendulum curated")
        mcp = catalog_env.mcp
        staging_only = mcp.tools["formula_search"]("pendulum", tier="staging")
        assert [r["id"] for r in staging_only["results"]] == ["stg-1"]

    def test_remove_seed_refused(self, catalog_env):
        _write_yaml(catalog_env.seed, "fluid", "ro_seed")
        catalog_env.catalog.ensure_fresh()
        mcp = catalog_env.mcp
        result = mcp.tools["formula_remove"]("ro_seed")
        assert result["success"] is False
        assert "seed" in result["error"]


class TestGenericTokenPrecision:
    """Through the MCP tool (index path), not just the legacy library scorer.

    The pre-redesign tool path suppressed generic words via
    ``FormulaLibrary._STOPWORDS``; the existing test of that contract exercises
    ``FormulaLibrary.search`` directly, so it cannot catch a regression on the
    path ``formula_search`` actually uses. These tests close that gap.
    """

    def test_generic_query_returns_no_unrelated_formulas(self, catalog_env):
        _write_yaml(catalog_env.seed, "fluid", "euler_equations_inviscid",
                    name="Euler equations inviscid")
        _write_yaml(catalog_env.seed, "fluid", "ns_incompressible",
                    name="Navier-Stokes equations")
        catalog_env.catalog.ensure_fresh()
        res = catalog_env.mcp.tools["formula_search"]("Einstein field equations")
        assert res["results"] == [], res["results"]

    def test_discriminative_token_keeps_only_relevant(self, catalog_env):
        _write_yaml(catalog_env.seed, "fluid", "euler_equations_inviscid",
                    name="Euler equations inviscid")
        _write_yaml(catalog_env.seed, "fluid", "ns_incompressible",
                    name="Navier-Stokes equations")
        catalog_env.catalog.ensure_fresh()
        res = catalog_env.mcp.tools["formula_search"]("Navier Stokes equations")
        assert [r["id"] for r in res["results"]] == ["ns_incompressible"]

    def test_generic_noun_query_still_finds_containing_formulas(self, catalog_env):
        _write_yaml(catalog_env.seed, "mechanics", "newtons_second_law",
                    name="Newton's second law")
        catalog_env.catalog.ensure_fresh()
        res = catalog_env.mcp.tools["formula_search"]("law")
        assert "newtons_second_law" in [r["id"] for r in res["results"]]


class TestUnsafeIdRejected:
    """The MCP tools must refuse ids that would escape the library root."""

    @pytest.mark.parametrize("bad_id", ["../../escaped", "sub/dir", "..", "C:/abs"])
    def test_add_rejects_traversal_id(self, catalog_env, bad_id):
        res = catalog_env.mcp.tools["formula_add"](
            id=bad_id, name="Evil", sympy_str="x = 1", latex="x = 1",
            variables={"x": {}}, category="lab",
        )
        assert res["success"] is False, res
        assert "escape" in res["error"].lower() or "unsafe" in res["error"].lower()
        # No file may be left outside the curated root.
        assert not (catalog_env.curated.parent / "escaped.yaml").exists()
        assert not list(catalog_env.curated.rglob("escaped.yaml"))

    def test_add_rejects_traversal_category(self, catalog_env):
        res = catalog_env.mcp.tools["formula_add"](
            id="ok_id", name="Evil cat", sympy_str="x = 1", latex="x = 1",
            variables={"x": {}}, category="../../outside",
        )
        assert res["success"] is False, res
        assert not (catalog_env.curated.parent / "outside").exists()

    def test_promote_rejects_traversal_new_id(self, catalog_env):
        _write_yaml(catalog_env.staging, "lab", "stg_trav",
                    name="Staging", sympy_str="z = 1")
        catalog_env.catalog.ensure_fresh()
        res = catalog_env.mcp.tools["formula_promote"](
            "stg_trav", new_id="../../promo_escaped",
        )
        assert res["success"] is False, res
        assert not (catalog_env.curated.parent / "promo_escaped.yaml").exists()


class TestAdapterDelegation:
    def test_adapter_uses_injected_catalog(self, catalog_env):
        from symkit.infrastructure.adapters.local_formula import LocalFormulaAdapter

        _write_yaml(catalog_env.curated, "mechanics", "cur-1", name="Pendulum")
        adapter = LocalFormulaAdapter(catalog=catalog_env.catalog)
        results = adapter.search("pendulum")
        assert [r.id for r in results] == ["cur-1"]
        assert results[0].extra["tier"] == "curated"
        assert "score" in results[0].extra

    def test_adapter_default_mode_reads_default_dirs(self):
        from symkit.infrastructure.adapters.local_formula import LocalFormulaAdapter

        adapter = LocalFormulaAdapter()
        results = adapter.search("Reynolds number", limit=3)
        assert results and results[0].id == "reynolds_number"


class TestCurationTools:
    def test_promote_staging_to_curated(self, catalog_env):
        _write_yaml(
            catalog_env.staging, "derived", "pendulum-abc123",
            name="Pendulum period", sympy_str="T = 2*pi*sqrt(l/g)",
        )
        catalog_env.catalog.ensure_fresh()
        mcp = catalog_env.mcp
        result = mcp.tools["formula_promote"](
            "pendulum-abc123", new_id="pendulum_period", aliases=["单摆周期"],
        )
        assert result["success"], result
        assert result["formula_id"] == "pendulum_period"
        assert result["tier"] == "curated"
        assert mcp.tools["formula_search"]("单摆周期")["results"][0]["id"] == (
            "pendulum_period"
        )
        gone = mcp.tools["formula_get"]("pendulum-abc123")
        assert gone["success"] is False

    def test_promote_refuses_seed(self, catalog_env):
        _write_yaml(catalog_env.seed, "fluid", "ro_seed")
        catalog_env.catalog.ensure_fresh()
        result = catalog_env.mcp.tools["formula_promote"]("ro_seed")
        assert result["success"] is False
        assert "staging" in result["error"]

    def test_promote_id_collision(self, catalog_env):
        _write_yaml(catalog_env.staging, "derived", "stg-1")
        _write_yaml(catalog_env.curated, "mechanics", "taken")
        catalog_env.catalog.ensure_fresh()
        result = catalog_env.mcp.tools["formula_promote"]("stg-1", new_id="taken")
        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_reindex_picks_up_hand_edits(self, catalog_env):
        p = _write_yaml(catalog_env.curated, "mechanics", "hand", name="before")
        mcp = catalog_env.mcp
        mcp.tools["formula_stats"]()
        p.write_text(
            yaml.dump({"id": "hand", "name": "after hand edit",
                       "sympy_str": "y", "category": "mechanics"}),
            encoding="utf-8",
        )
        result = mcp.tools["formula_reindex"]()
        assert result["success"], result
        assert mcp.tools["formula_get"]("hand")["formula"]["name"] == "after hand edit"

    def test_stats_reports_tiers_and_duplicates(self, catalog_env):
        _write_yaml(catalog_env.seed, "fluid", "s1")
        _write_yaml(catalog_env.staging, "derived", "d1", sympy_str="dup expr")
        _write_yaml(catalog_env.staging, "derived", "d2", sympy_str="dup expr")
        result = catalog_env.mcp.tools["formula_stats"]()
        assert result["success"], result
        assert result["tiers"]["seed"] == 1
        assert result["tiers"]["staging"] == 2
        assert result["duplicate_groups"] == 1
        assert result["last_sync"] is not None

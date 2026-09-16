"""Tests for the formula file loader and the FormulaCatalog orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.domain.formula_library import FormulaEntry
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore


def write_yaml(root: Path, category: str, fid: str, **data) -> Path:
    d = root / category
    d.mkdir(parents=True, exist_ok=True)
    payload = {"id": fid, "name": fid, "sympy_str": "x + 1", "category": category, **data}
    path = d / f"{fid}.yaml"
    path.write_text(yaml.dump(payload, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def env(tmp_path):
    seed, staging, curated = (tmp_path / t for t in ("seed", "staging", "curated"))
    for d in (seed, staging, curated):
        d.mkdir()
    store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    store.open()
    catalog = FormulaCatalog(
        store,
        YamlFormulaFileSource(),
        seed_dir=seed,
        staging_dir=staging,
        curated_dir=curated,
    )
    yield catalog, seed, staging, curated
    store.close()


class TestEnsureFresh:
    def test_full_then_incremental(self, env):
        catalog, seed, staging, _ = env
        write_yaml(seed, "fluid", "seed_a")
        p = write_yaml(staging, "fluid", "stg_a")
        report = catalog.ensure_fresh()
        assert report.added == 2 and report.updated == 0

        p.write_text(
            yaml.dump({"id": "stg_a", "name": "changed name", "sympy_str": "x + 2"}),
            encoding="utf-8",
        )
        report = catalog.ensure_fresh()
        assert report.updated == 1 and report.added == 0
        assert catalog.get("stg_a").name == "changed name"

        p.unlink()
        report = catalog.ensure_fresh()
        assert report.removed == 1
        assert catalog.get("stg_a") is None

    def test_bad_yaml_counted_as_failed(self, env):
        catalog, seed, _, _ = env
        (seed / "bad.yaml").write_text("{{{ not yaml", encoding="utf-8")
        report = catalog.ensure_fresh()
        assert report.failed == 1 and report.failed_paths

    def test_quarantine_dir_skipped(self, env):
        catalog, _, staging, _ = env
        q = staging / "_quarantine"
        q.mkdir()
        (q / "junk.yaml").write_text(
            yaml.dump({"id": "junk", "name": "junk", "sympy_str": "x"}), encoding="utf-8"
        )
        catalog.ensure_fresh()
        assert catalog.get("junk") is None


class TestSearchThroughCatalog:
    def test_three_tiers_and_duplicate_collapse(self, env):
        catalog, seed, staging, curated = env
        write_yaml(seed, "fluid", "reynolds_number", name="Reynolds number")
        write_yaml(staging, "fluid", "re-copy", name="Reynolds number")
        write_yaml(curated, "mech", "other", name="Other", sympy_str="F = m*a")
        results = catalog.search("reynolds")
        assert len(results) == 1
        assert results[0].formula.tier == "seed"  # seed outranks staging as representative
        assert results[0].duplicates == 1

    def test_curated_overrides_seed_with_same_id(self, env):
        catalog, seed, _, curated = env
        write_yaml(seed, "fluid", "x", name="seed version")
        write_yaml(curated, "fluid", "x", name="curated version")
        catalog.ensure_fresh()
        got = catalog.get("x")
        assert got.name == "curated version"
        assert got.tier == "curated"

    def test_tier_filter(self, env):
        catalog, seed, staging, _ = env
        write_yaml(seed, "fluid", "s")
        write_yaml(staging, "fluid", "t")
        results = catalog.search("", tier="staging")
        assert [r.formula.id for r in results] == ["t"]


class TestWritePaths:
    def test_add_entry_immediately_searchable(self, env):
        catalog, _, _, _ = env
        catalog.add_entry(FormulaEntry(id="new_f", name="Fresh formula", sympy_str="a+b"))
        results = catalog.search("fresh")
        assert [r.formula.id for r in results] == ["new_f"]

    def test_staging_resave_is_idempotent(self, env):
        catalog, _, staging, _ = env
        write_yaml(staging, "derived", "det-abc123", sympy_str="T = 2*pi*sqrt(l/g)")
        catalog.ensure_fresh()
        # Identical re-save (session_complete re-completing the same content):
        # the index must still hold exactly one row with no duplicate group.
        write_yaml(staging, "derived", "det-abc123", sympy_str="T = 2*pi*sqrt(l/g)")
        catalog.ensure_fresh()
        results = catalog.search("sqrt")
        assert len(results) == 1 and results[0].duplicates == 0

    def test_remove_entry_deletes_file_and_row(self, env):
        catalog, _, staging, _ = env
        p = write_yaml(staging, "derived", "gone")
        catalog.ensure_fresh()
        removed = catalog.remove_entry("gone")
        assert removed == ["staging"]
        assert not p.exists()
        assert catalog.get("gone") is None

    def test_remove_seed_refused(self, env):
        catalog, seed, _, _ = env
        p = write_yaml(seed, "fluid", "ro_seed")
        catalog.ensure_fresh()
        assert catalog.remove_entry("ro_seed") == []
        assert p.exists()
        assert catalog.get("ro_seed") is not None


class TestExternallyWrittenEntries:
    """Curation operations must reconcile the index themselves.

    ``search``/``get`` call ``ensure_fresh``; ``promote``/``remove_entry`` read
    the store directly, so a file written by hand (or by another process) was
    invisible to them and they reported "not found" until some other call
    happened to refresh the index.
    """

    def test_promote_sees_externally_written_staging_entry(self, env):
        catalog, _, staging, _ = env
        write_yaml(staging, "derived", "external-1", name="Externally written")
        promoted = catalog.promote("external-1", new_id="promoted_external")
        assert promoted.id == "promoted_external"
        assert promoted.tier == "curated"

    def test_remove_entry_sees_externally_written_entry(self, env):
        catalog, _, staging, _ = env
        path = write_yaml(staging, "derived", "external-2")
        assert catalog.remove_entry("external-2") == ["staging"]
        assert not path.exists()


class TestPromote:
    def test_promote_staging_to_curated(self, env):
        catalog, _, staging, curated = env
        write_yaml(staging, "derived", "stg-1", name="My derivation")
        catalog.ensure_fresh()
        promoted = catalog.promote("stg-1", new_id="my_formula", aliases=["我的公式"])
        assert promoted.id == "my_formula"
        assert promoted.tier == "curated"
        assert promoted.aliases == ["我的公式"]
        assert catalog.get("stg-1") is None
        assert not (staging / "derived" / "stg-1.yaml").exists()
        assert (curated / "derived" / "my_formula.yaml").exists()

    def test_promote_refuses_seed(self, env):
        catalog, seed, _, _ = env
        write_yaml(seed, "fluid", "ro_seed")
        catalog.ensure_fresh()
        with pytest.raises(ValueError, match="staging"):
            catalog.promote("ro_seed")

    def test_promote_refuses_id_collision(self, env):
        catalog, _, staging, curated = env
        write_yaml(staging, "derived", "stg-1")
        write_yaml(curated, "derived", "taken")
        catalog.ensure_fresh()
        with pytest.raises(ValueError, match="already exists"):
            catalog.promote("stg-1", new_id="taken")

    def test_promote_unknown_id(self, env):
        catalog, *_ = env
        with pytest.raises(ValueError, match="not found"):
            catalog.promote("nope")


class TestReindex:
    def test_reindex_picks_up_hand_edits(self, env):
        catalog, seed, _, _ = env
        p = write_yaml(seed, "fluid", "hand", name="before")
        catalog.ensure_fresh()
        p.write_text(
            yaml.dump({"id": "hand", "name": "after", "sympy_str": "y"}),
            encoding="utf-8",
        )
        catalog.reindex()
        assert catalog.get("hand").name == "after"


class TestLoaderFields:
    def test_verified_and_provenance_fields_loaded(self, env):
        catalog, _, staging, _ = env
        write_yaml(
            staging, "derived", "v1",
            verified=True, application_context="pipe flow",
            derivation_steps=["step one"], created_at="2026-09-11T00:00:00",
        )
        catalog.ensure_fresh()
        got = catalog.get("v1")
        assert got.verified is True
        assert got.application_context == "pipe flow"
        assert got.derivation_steps == ["step one"]
        assert got.created_at == "2026-09-11T00:00:00"

    def test_load_returns_none_without_id(self, tmp_path):
        from symkit.infrastructure.formula_files import load_indexed

        p = tmp_path / "noid.yaml"
        p.write_text(yaml.dump({"name": "no id"}), encoding="utf-8")
        assert load_indexed(p, "staging") is None


# Lifecycle of the shared catalog in `symkit_mcp.tools._state`.
@pytest.fixture
def injected_catalog(tmp_path):
    store = SqliteFormulaIndexStore(tmp_path / "index.db")
    store.open()
    catalog = FormulaCatalog(
        store=store,
        file_source=YamlFormulaFileSource(),
        seed_dir=tmp_path / "seed",
        staging_dir=tmp_path / "staging",
        curated_dir=tmp_path / "curated",
    )
    from symkit_mcp.tools import _state

    previous = _state._catalog
    _state.set_catalog(catalog)
    yield store
    _state.set_catalog(previous)


def test_reset_catalog_closes_the_store(injected_catalog):
    """An open SQLite connection holds file locks on Windows; dropping the
    catalog without closing it leaks them."""
    from symkit_mcp.tools import _state

    store = injected_catalog

    _state.reset_catalog()

    with pytest.raises(RuntimeError, match="store is not open"):
        store.all()

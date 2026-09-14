"""Tests for FormulaCatalog.find_similar, curated metadata, schema migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.domain.formula_index import IndexedFormula
from symkit.domain.formula_library import FormulaEntry
from symkit.infrastructure.formula_files import (
    YamlFormulaFileSource,
    load_indexed,
    write_entry_yaml,
)
from symkit.infrastructure.formula_index_store import (
    _SCHEMA_VERSION,
    SqliteFormulaIndexStore,
)


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
        store, YamlFormulaFileSource(),
        seed_dir=seed, staging_dir=staging, curated_dir=curated,
    )
    yield catalog, seed, staging, curated
    store.close()


def mk(fid: str, **kw) -> IndexedFormula:
    defaults = {"tier": "curated", "content_hash": "h-" + fid, "name": fid}
    defaults.update(kw)
    return IndexedFormula(id=fid, **defaults)


class TestFindSimilar:
    def test_bernoulli_pair_hits_via_text_channel(self, env):
        # Both forms are physically identical, but structural_hash differs:
        # ``Eq(lhs, C)`` unifies to ``lhs - C``, introducing a free symbol. The
        # hit must therefore come from the FTS text channel on the shared
        # identifier token ``rho``.
        catalog, seed, _, _ = env
        write_yaml(seed, "fluid", "bern_v", name="Bernoulli v",
                   sympy_str="g*z+p/rho+v**2/2")
        write_yaml(seed, "fluid", "bern_c", name="Bernoulli C",
                   sympy_str="Eq(g*z+p/rho+u**2/2, C)")
        results = catalog.find_similar("g*z+p/rho+v**2/2", limit=3)
        ids = [r["id"] for r in results]
        assert "bern_c" in ids
        hit = next(r for r in results if r["id"] == "bern_c")
        assert hit["match"] in ("structural", "text")
        assert hit["score"] >= 0.5
        assert set(hit) == {"id", "name", "tier", "score", "match"}

    def test_self_is_excluded(self, env):
        catalog, seed, _, _ = env
        write_yaml(seed, "fluid", "bern_v", name="Bernoulli v",
                   sympy_str="g*z+p/rho+v**2/2")
        write_yaml(seed, "fluid", "bern_c", name="Bernoulli C",
                   sympy_str="Eq(g*z+p/rho+u**2/2, C)")
        by_content = catalog.find_similar("g*z+p/rho+v**2/2")
        by_id = catalog.find_similar("g*z+p/rho+v**2/2", exclude_id="bern_v")
        assert all(r["id"] != "bern_v" for r in by_content)
        assert all(r["id"] != "bern_v" for r in by_id)

    def test_structural_exact_match_preferred(self, env):
        # Same structure, different symbol names and different content hashes:
        # the structural channel must fire and rank first.
        catalog, seed, _, _ = env
        write_yaml(seed, "fluid", "ren_v", name="v form",
                   sympy_str="g*z+p/rho+v**2/2")
        write_yaml(seed, "fluid", "ren_u", name="u form",
                   sympy_str="g*z+p/rho+u**2/2")
        results = catalog.find_similar("g*z+p/rho+v**2/2", exclude_id="ren_v")
        assert results
        assert results[0]["id"] == "ren_u"
        assert results[0]["match"] == "structural"

    def test_limit_is_respected(self, env):
        catalog, seed, _, _ = env
        for i, sym in enumerate(("v", "u", "w", "s")):
            write_yaml(seed, "fluid", f"f{i}", name=f"form {sym}",
                       sympy_str=f"g*z+p/rho+{sym}**2/2")
        results = catalog.find_similar("g*z+p/rho+v**2/2", limit=2)
        assert len(results) == 2

    def test_no_match_returns_empty(self, env):
        catalog, seed, _, _ = env
        write_yaml(seed, "fluid", "other", name="Other", sympy_str="F = m*a")
        assert catalog.find_similar("zeta**7 + omega", limit=3) == []


class TestCuratedField:
    def test_indexed_formula_defaults_to_false(self):
        assert mk("a").curated is False

    def test_yaml_roundtrip_true(self, tmp_path):
        entry = FormulaEntry(id="c1", name="n", sympy_str="a+b", category="cat")
        path = write_entry_yaml(tmp_path, entry, curated=True)
        indexed = load_indexed(path, "curated")
        assert indexed is not None and indexed.curated is True

    def test_yaml_missing_key_defaults_false(self, tmp_path):
        entry = FormulaEntry(id="c2", name="n", sympy_str="a+b", category="cat")
        path = write_entry_yaml(tmp_path, entry)
        indexed = load_indexed(path, "curated")
        assert indexed is not None and indexed.curated is False

    def test_promote_marks_curated(self, env):
        catalog, _, staging, _ = env
        write_yaml(staging, "derived", "stg-1", name="My derivation",
                   sympy_str="a = b")
        promoted = catalog.promote("stg-1", new_id="my_formula")
        assert promoted.curated is True
        assert catalog.get("my_formula").curated is True


class TestStatsAndMigration:
    def test_structural_duplicate_groups_in_stats(self, tmp_path):
        s = SqliteFormulaIndexStore(tmp_path / "i.sqlite3")
        s.open()
        s.upsert_many([
            mk("a", tier="staging", sympy_str="x + y", content_hash="c1"),
            mk("b", tier="staging", sympy_str="p + q", content_hash="c2"),
            mk("c", tier="seed", sympy_str="x*y", content_hash="c3"),
        ])
        stats = s.stats()
        assert stats["structural_duplicate_groups"] == 1
        assert stats["duplicate_groups"] == 0
        s.close()

    def test_old_schema_rebuilt_on_open(self, tmp_path):
        path = tmp_path / "index.sqlite3"
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE formulas (id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
        )
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
        conn.close()

        s = SqliteFormulaIndexStore(path)
        s.open()  # must not raise: schema version mismatch triggers a rebuild
        s.upsert_many([mk("a", sympy_str="x + y")])
        assert s.stats()["total"] == 1
        assert s.find_by_structural_hash(_digest("x + y"))
        s.close()

    def test_missing_column_with_matching_version_rebuilt(self, tmp_path):
        # A DB stamped with the current user_version but lacking the new
        # structural_hash column must still be rebuilt, not crash on upsert.
        path = tmp_path / "index.sqlite3"
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE formulas (id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
        )
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        conn.commit()
        conn.close()

        s = SqliteFormulaIndexStore(path)
        s.open()
        s.upsert_many([mk("a", sympy_str="x + y")])
        assert s.stats()["total"] == 1
        s.close()


def _digest(expr: str) -> str:
    from symkit.infrastructure.formula_identity import structural_hash

    return structural_hash(expr)

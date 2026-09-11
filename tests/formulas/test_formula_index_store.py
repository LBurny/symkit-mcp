"""Tests for the SQLite FTS5 formula index store."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.domain.formula_index import IndexedFormula, ManifestEntry
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore


def mk(fid: str, **kw) -> IndexedFormula:
    defaults = {"tier": "curated", "content_hash": "h-" + fid, "name": fid}
    defaults.update(kw)
    return IndexedFormula(id=fid, **defaults)


@pytest.fixture
def store(tmp_path):
    s = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    s.open()
    yield s
    s.close()


class TestRoundTrip:
    def test_upsert_get_all_remove(self, store):
        store.upsert_many([
            mk("a", aliases=["雷诺数"], verified=True, application_context="ctx",
               sympy_str="Re = rho*v*L/mu"),
            mk("b", tier="staging"),
        ])
        got = store.get("a")
        assert got is not None
        assert got.aliases == ["雷诺数"]
        assert got.verified is True
        assert got.application_context == "ctx"
        assert got.sympy_str == "Re = rho*v*L/mu"
        assert len(store.all()) == 2
        store.remove_ids(["a"])
        assert store.get("a") is None
        assert len(store.all()) == 1

    def test_upsert_overwrites_same_id(self, store):
        store.upsert_many([mk("a", name="old")])
        store.upsert_many([mk("a", name="new")])
        assert store.get("a").name == "new"
        assert len(store.all()) == 1


class TestSearch:
    def test_exact_id(self, store):
        store.upsert_many([mk("reynolds_number", name="Reynolds number")])
        hits = store.search("reynolds_number")
        assert hits[0].match_kind == "exact_id"
        assert hits[0].base_score == 1.0

    def test_exact_name_normalized(self, store):
        store.upsert_many([mk("x", name="Navier-Stokes equations")])
        hits = store.search("navier stokes equations")
        assert hits[0].match_kind == "exact_name"

    def test_exact_alias_chinese(self, store):
        store.upsert_many([mk("x", name="Reynolds number", aliases=["雷诺数"])])
        hits = store.search("雷诺数")
        assert hits[0].match_kind == "exact_alias"

    def test_fts_latin_substring(self, store):
        store.upsert_many([mk("x", name="Reynolds number")])
        hits = store.search("reyn")
        assert hits and hits[0].match_kind == "fts"
        assert 0.5 <= hits[0].base_score <= 0.7

    def test_fts_cjk_three_chars(self, store):
        store.upsert_many([mk("x", name="dimensionless ratio", tags=["雷诺数"])])
        hits = store.search("雷诺数")
        assert hits and hits[0].match_kind == "fts"

    def test_like_fallback_two_char_cjk(self, store):
        store.upsert_many([mk("x", name="dimensionless ratio", aliases=["雷诺数"])])
        hits = store.search("雷诺")
        assert hits and hits[0].match_kind == "like"
        assert hits[0].base_score == pytest.approx(0.35)

    def test_single_letter_tokens_no_crash(self, store):
        store.upsert_many([mk("x", name="a b coefficient")])
        hits = store.search("a b")
        assert hits and hits[0].formula.id == "x"

    def test_tier_domain_category_filters(self, store):
        store.upsert_many([
            mk("s1", tier="seed", domain="fluid_dynamics", category="fluid_dynamics"),
            mk("c1", tier="curated", domain="mechanics", category="mechanics"),
        ])
        hits = store.search("", tier="seed")
        assert [h.formula.id for h in hits] == ["s1"]
        hits = store.search("", domain="mechanics")
        assert [h.formula.id for h in hits] == ["c1"]
        hits = store.search("", category="fluid_dynamics")
        assert [h.formula.id for h in hits] == ["s1"]

    def test_browse_empty_query(self, store):
        store.upsert_many([mk("s1", tier="seed"), mk("s2", tier="seed"), mk("c1")])
        hits = store.search("", tier="seed")
        assert len(hits) == 2
        assert all(h.match_kind == "browse" for h in hits)

    def test_empty_query_no_filters_returns_nothing(self, store):
        store.upsert_many([mk("x")])
        assert store.search("") == []

    def test_fts_scores_within_bounds_for_multiple_hits(self, store):
        store.upsert_many([
            mk("a", name="reynolds reynolds reynolds"),
            mk("b", name="reynolds number for fluids"),
        ])
        hits = store.search("reynolds")
        assert len(hits) == 2
        for h in hits:
            assert 0.5 <= h.base_score <= 0.7


class TestManifestAndStats:
    def test_manifest_round_trip(self, store):
        store.set_manifest([ManifestEntry("/p/a.yaml", 1.0, 10, "a")])
        m = store.manifest()
        assert m["/p/a.yaml"].entry_id == "a"
        assert m["/p/a.yaml"].mtime == 1.0

    def test_stats_duplicate_groups(self, store):
        store.upsert_many([
            mk("a", tier="staging", content_hash="same"),
            mk("b", tier="staging", content_hash="same"),
            mk("c", tier="seed", content_hash="unique"),
        ])
        stats = store.stats()
        assert stats["total"] == 3
        assert stats["tiers"] == {"staging": 2, "seed": 1}
        assert stats["duplicate_groups"] == 1
        assert stats["duplicate_entries"] == 1

    def test_last_sync_updated_by_set_manifest(self, store):
        assert store.stats()["last_sync"] is None
        store.set_manifest([])
        assert store.stats()["last_sync"] is not None

    def test_clear(self, store):
        store.upsert_many([mk("a")])
        store.set_manifest([ManifestEntry("/p/a.yaml", 1.0, 10, "a")])
        store.clear()
        assert store.all() == []
        assert store.manifest() == {}


class TestGenericTokenPrecision:
    """A hit must be justified by a discriminative token.

    Mirrors the legacy ``FormulaLibrary._STOPWORDS`` contract: generic domain
    nouns cannot alone justify a match when the query also carries a
    discriminative word, and function words never justify a match at all.
    """

    def test_generic_words_alone_do_not_match(self, store):
        store.upsert_many([
            mk("euler", name="Euler equations inviscid"),
            mk("ns", name="Navier-Stokes equations"),
        ])
        assert store.search("Einstein field equations") == []

    def test_meaningful_token_excludes_stopword_only_matches(self, store):
        store.upsert_many([
            mk("euler", name="Euler equations inviscid"),
            mk("ns", name="Navier-Stokes equations"),
        ])
        ids = [h.formula.id for h in store.search("Navier Stokes equations")]
        assert ids == ["ns"]

    def test_all_generic_noun_query_keeps_low_relevance_matches(self, store):
        store.upsert_many([mk("ns", name="Navier-Stokes equations")])
        ids = [h.formula.id for h in store.search("equations")]
        assert ids == ["ns"]

    def test_function_word_alone_never_matches(self, store):
        store.upsert_many([mk("x", name="Reynolds number",
                             description="the ratio of inertial to viscous forces")])
        assert store.search("the") == []

    def test_exact_name_still_wins_over_stopword_rule(self, store):
        store.upsert_many([mk("newtons_second_law", name="law")])
        hits = store.search("law")
        assert hits and hits[0].match_kind == "exact_name"


class TestCorruptionRecovery:
    def test_garbage_file_rebuilt(self, tmp_path):
        path = tmp_path / "index.sqlite3"
        path.write_bytes(b"this is not a sqlite database at all")
        s = SqliteFormulaIndexStore(path)
        s.open()  # must not raise
        s.upsert_many([mk("a")])
        assert store_search_ids(s, "a") == ["a"]
        s.close()


def store_search_ids(store, query):
    return [h.formula.id for h in store.search(query)]


def test_user_index_path_location():
    from symkit.domain.paths import user_index_path

    p = user_index_path()
    assert p.name == "index.sqlite3"
    assert p.parent.name == "formulas"


def test_in_memory_store():
    s = SqliteFormulaIndexStore(Path(":memory:"))
    s.open()
    s.upsert_many([mk("m1", name="memory entry")])
    assert [f.id for f in s.all()] == ["m1"]
    s.close()


class TestPerformanceBudgets:
    """Guardrails against accidental quadratic behavior (not microbenchmarks)."""

    N = 500

    @pytest.fixture
    def perf_catalog(self, tmp_path):
        seed, staging, curated = (tmp_path / t for t in ("seed", "staging", "curated"))
        for d in (seed, staging, curated):
            d.mkdir()
        for i in range(self.N):
            d = curated / "synthetic"
            d.mkdir(exist_ok=True)
            (d / f"formula_{i:04d}.yaml").write_text(
                yaml.dump({
                    "id": f"formula_{i:04d}",
                    "name": f"Synthetic formula number {i}",
                    "sympy_str": f"y_{i} = x_{i}**2 + {i}",
                    "category": "synthetic",
                    "tags": ["synthetic", f"group_{i % 10}"],
                }),
                encoding="utf-8",
            )
        store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
        store.open()
        c = FormulaCatalog(
            store, YamlFormulaFileSource(),
            seed_dir=seed, staging_dir=staging, curated_dir=curated,
        )
        yield c
        store.close()

    def test_cold_build_and_search_budgets(self, perf_catalog):
        start = time.perf_counter()
        report = perf_catalog.reindex()
        build_s = time.perf_counter() - start
        assert report.added == self.N
        assert build_s < 5.0, f"cold build of {self.N} entries took {build_s:.2f}s"

        start = time.perf_counter()
        results = perf_catalog.search("synthetic formula", limit=5)
        search_ms = (time.perf_counter() - start) * 1000
        assert results
        assert search_ms < 100, f"search took {search_ms:.1f}ms"

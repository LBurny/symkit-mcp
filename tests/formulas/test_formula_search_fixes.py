"""Regression tests for three confirmed formula-retrieval bugs.

B1 — glued expression queries (``v*L*rho/mu``) must tokenize on non-word
characters so the FTS/LIKE channels can recall an entry that stores the
spaced form.
B2 — a query that parses as an expression must reach entries with the same
alpha-invariant structure through a dedicated ``structural`` match channel,
ranked above text hits.
B3 — ``structural_hash`` must alpha-rename reserved SymPy names used as
variables (``E``, ``I``, ...) so rename-invariant fingerprints are equal;
``content_hash`` stays byte-for-byte frozen, and the index schema bumps so
old libraries rebuild automatically.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.domain.formula_index import MATCH_KINDS, IndexedFormula
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_identity import content_hash, structural_hash
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


def _write_yaml(root: Path, category: str, fid: str, **data) -> Path:
    d = root / category
    d.mkdir(parents=True, exist_ok=True)
    payload = {"id": fid, "name": fid, "sympy_str": "x + 1", "category": category, **data}
    path = d / f"{fid}.yaml"
    path.write_text(yaml.dump(payload, allow_unicode=True), encoding="utf-8")
    return path


class TestB1Tokenization:
    """Glued expression queries must reach the FTS/LIKE recall channels."""

    def test_glued_expression_recalls_reynolds(self, store):
        store.upsert_many([
            mk("reynolds_number", name="Reynolds number",
               sympy_str="Re = rho*v*L/mu", verified=True),
        ])
        hits = store.search("v*L*rho/mu")
        assert [h.formula.id for h in hits] == ["reynolds_number"]

    def test_glued_and_spaced_queries_agree(self, store):
        store.upsert_many([
            mk("reynolds_number", name="Reynolds number",
               sympy_str="Re = rho*v*L/mu", verified=True),
        ])
        glued = [h.formula.id for h in store.search("v*L*rho/mu")]
        spaced = [h.formula.id for h in store.search("rho * v * L / mu")]
        assert glued == spaced == ["reynolds_number"]

    def test_cjk_query_stays_a_single_token(self, store):
        store.upsert_many([mk("x", name="dimensionless ratio", aliases=["伯努利"])])
        hits = store.search("伯努利")
        assert hits and hits[0].match_kind == "exact_alias"


class TestB2StructuralChannel:
    """An expression query reaches structurally identical entries first."""

    def test_match_kinds_declares_structural(self):
        assert "structural" in MATCH_KINDS

    def test_expression_query_marked_structural_and_first(self, store):
        store.upsert_many([
            mk("struct_dup", tier="staging", name="v form",
               sympy_str="g*z+p/rho+v**2/2"),
            mk("text_only", tier="curated", verified=True,
               name="g z p rho formula", sympy_str="a + b"),
        ])
        hits = store.search("g*z+p/rho+u**2/2")
        assert hits[0].formula.id == "struct_dup"
        assert hits[0].match_kind == "structural"

    def test_text_query_does_not_trigger_structural(self, store):
        store.upsert_many([
            mk("reynolds_number", name="Reynolds number",
               sympy_str="Re = rho*v*L/mu", tags=["伯努利"]),
        ])
        for query in ("reynolds", "伯努利"):
            hits = store.search(query)
            assert hits, query
            assert all(h.match_kind != "structural" for h in hits), query

    def test_rename_clone_with_reordered_denominator_matches(self, store):
        # Black-box regression: the stored denominator ``mu`` and the query
        # denominator ``q4`` sort at opposite ends of the name order. The
        # structural channel must still recall the rename clone.
        store.upsert_many([
            mk("reynolds_number", tier="staging", name="viscous form",
               sympy_str="rho*v*L/mu"),
        ])
        hits = store.search("q1*q2*q3/q4")
        assert hits and hits[0].formula.id == "reynolds_number"
        assert hits[0].match_kind == "structural"

    def test_strict_variant_never_returns_a_fallback_hash(self):
        # The textual fallback of structural_hash must not leak into the
        # structural channel: an unparseable query simply has no digest.
        from symkit.infrastructure.formula_identity import (
            structural_hash,
            try_structural_hash,
        )

        assert structural_hash("not an (expr") == structural_hash("not an (expr")
        assert try_structural_hash("not an (expr") is None

    def test_strict_variant_rejects_unparseable_and_blank(self):
        from symkit.infrastructure.formula_identity import try_structural_hash

        assert try_structural_hash("not an (expr") is None
        assert try_structural_hash("") is None
        assert try_structural_hash("   ") is None
        assert try_structural_hash("E = m*c**2") is not None


class TestB3ReservedNameFingerprint:
    """Reserved names used as variables must be alpha-renamed, not constants."""

    def test_energy_mass_rename_invariant(self):
        assert structural_hash("E = m*c**2") == structural_hash("F = m*c**2")

    def test_ohm_rename_invariant(self):
        assert structural_hash("V = I*R") == structural_hash("V = J*R")

    def test_content_hash_baseline_frozen(self):
        # 1.6.x published behaviour (staging id stability): one byte frozen.
        assert content_hash("rho * v * L / mu") == "e1b0e985e519"

    def test_unparseable_still_falls_back_without_raising(self):
        h1 = structural_hash("not an (expr")
        assert h1 == structural_hash("not an (expr")
        assert len(h1) == 12


class TestSchemaBumpRebuild:
    """A version bump makes an old index rebuild from the YAML layers."""

    def test_old_version_db_is_dropped_and_restamped(self, tmp_path):
        path = tmp_path / "index.sqlite3"
        s = SqliteFormulaIndexStore(path)
        s.open()
        s.upsert_many([mk("old", sympy_str="x + y")])
        s.close()

        conn = sqlite3.connect(path)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        s = SqliteFormulaIndexStore(path)
        s.open()  # version mismatch must drop the stale tables
        assert s.all() == []
        stamp = sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0]
        assert stamp == 5
        s.close()

    def test_catalog_repopulates_and_recalls_structurally(self, tmp_path):
        seed, staging, curated = (tmp_path / t for t in ("seed", "staging", "curated"))
        for d in (seed, staging, curated):
            d.mkdir()
        _write_yaml(seed, "relativity", "einstein_mass_energy",
                    name="Mass-energy equivalence", sympy_str="E = m*c**2")

        path = tmp_path / "index.sqlite3"
        s = SqliteFormulaIndexStore(path)
        s.open()
        s.close()
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        s = SqliteFormulaIndexStore(path)
        s.open()
        catalog = FormulaCatalog(
            s, YamlFormulaFileSource(),
            seed_dir=seed, staging_dir=staging, curated_dir=curated,
        )
        results = catalog.search("F = m*c**2")
        assert [r.formula.id for r in results][:1] == ["einstein_mass_energy"]
        s.close()

"""Tests for the pure-domain formula ranker (boosts + duplicate collapse)."""

from __future__ import annotations

from symkit.domain.formula_index import IndexedFormula, SearchHit
from symkit.domain.formula_ranker import rank_hits


def _f(fid: str, tier: str, h: str, verified: bool = False, name: str = "") -> IndexedFormula:
    return IndexedFormula(id=fid, tier=tier, content_hash=h, verified=verified, name=name)


class TestRankHits:
    def test_tier_boost_curated_beats_staging(self):
        hits = [
            SearchHit(_f("s1", "staging", "h1"), "fts", 0.6),
            SearchHit(_f("c1", "curated", "h2"), "fts", 0.6),
        ]
        ranked = rank_hits(hits)
        assert ranked[0].formula.id == "c1"
        assert ranked[0].score > ranked[1].score

    def test_verified_boost(self):
        hits = [
            SearchHit(_f("a", "staging", "h1", verified=True), "fts", 0.5),
            SearchHit(_f("b", "staging", "h2"), "fts", 0.5),
        ]
        assert rank_hits(hits)[0].formula.id == "a"

    def test_duplicates_collapsed_best_tier_representative(self):
        hits = [
            SearchHit(_f("s1", "staging", "same"), "fts", 0.6),
            SearchHit(_f("s2", "staging", "same", verified=True), "fts", 0.5),
            SearchHit(_f("c1", "curated", "same"), "fts", 0.4),
        ]
        ranked = rank_hits(hits)
        assert len(ranked) == 1
        assert ranked[0].formula.id == "c1"
        assert ranked[0].duplicates == 2
        assert set(ranked[0].duplicate_ids) == {"s1", "s2"}

    def test_exact_id_beats_fts(self):
        hits = [
            SearchHit(_f("x", "staging", "h1"), "fts", 0.7),
            SearchHit(_f("y", "staging", "h2"), "exact_id", 1.0),
        ]
        assert rank_hits(hits)[0].formula.id == "y"

    def test_limit(self):
        hits = [SearchHit(_f(f"f{i}", "seed", f"h{i}"), "browse", 0.5) for i in range(5)]
        assert len(rank_hits(hits, limit=3)) == 3

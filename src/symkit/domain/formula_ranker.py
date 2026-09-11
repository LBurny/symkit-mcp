"""Pure ranking for index search hits: match base + curation boosts + dedup."""

from __future__ import annotations

from symkit.domain.formula_index import TIER_ORDER, RankedResult, SearchHit

_MATCH_BASE = {
    "exact_id": 1.0,
    "exact_name": 0.95,
    "exact_alias": 0.90,
    "like": 0.35,
    "browse": 0.5,
    "fts": 0.0,  # fts base_score arrives pre-scaled to [0.5, 0.7] by the store
}
_TIER_BOOST = {"curated": 0.15, "seed": 0.10, "staging": 0.0}
_VERIFIED_BOOST = 0.10


def _score(hit: SearchHit) -> float:
    base = hit.base_score if hit.match_kind == "fts" else _MATCH_BASE[hit.match_kind]
    score = base + _TIER_BOOST.get(hit.formula.tier, 0.0)
    if hit.formula.verified:
        score += _VERIFIED_BOOST
    return score


def _representative(group: list[tuple[float, SearchHit]]) -> tuple[float, SearchHit]:
    return max(
        group,
        key=lambda item: (
            -TIER_ORDER.get(item[1].formula.tier, 9),
            item[1].formula.verified,
            item[0],
        ),
    )


def rank_hits(hits: list[SearchHit], *, limit: int = 10) -> list[RankedResult]:
    """Score, collapse duplicate content_hash groups, sort, and limit."""
    groups: dict[str, list[tuple[float, SearchHit]]] = {}
    for hit in hits:
        key = hit.formula.content_hash or hit.formula.id
        groups.setdefault(key, []).append((_score(hit), hit))
    results: list[RankedResult] = []
    for group in groups.values():
        best_score, best_hit = _representative(group)
        others = [h.formula.id for _, h in group if h.formula.id != best_hit.formula.id]
        results.append(RankedResult(best_hit.formula, best_score, len(others), sorted(others)))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]

"""FormulaRecommender — Goal-aware formula recommendation engine.

Based on the local derivation repository (DerivationRepository) and external
formula adapter interfaces, recommends formulas that can serve as derivation
starting points for a given goal.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

from symkit.infrastructure.adapters.base import BaseAdapter

if TYPE_CHECKING:
    from symkit.domain.derivation_goal import DerivationGoal
    from symkit.infrastructure.derivation_repository import (
        DerivationRepository,
        DerivationResult,
    )


# Tokens that carry little discriminative power and should not be counted as
# keyword overlap between a goal and a formula.
_RELEVANCE_STOPWORDS: set[str] = {
    "derive", "from", "for", "using", "where", "when", "what", "how", "why",
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "as", "by",
    "is", "are", "be", "was", "were", "been", "being", "am", "it", "its",
    "this", "that", "these", "those", "with", "into", "onto", "through",
    "during", "before", "after", "above", "below", "between", "among",
    "within", "without", "against", "under", "over", "again", "further",
    "once", "here", "there", "then", "than", "so", "no", "not", "only",
    "just", "also", "very", "more", "most", "some", "such", "same", "other",
    "all", "any", "both", "each", "few", "own", "can", "could", "will",
    "would", "should", "shall", "may", "might", "must", "have", "has", "had",
    "do", "does", "did", "we", "you", "he", "she", "they", "them", "their",
    "there", "i", "me", "my", "our", "us", "him", "his", "her", "she",
    "equation", "equations", "formula", "formulas", "expression", "expressions",
}


class FormulaSourceAdapter(Protocol):
    """External formula adapter interface (Wikidata / SciPy / BioModels, etc.)."""

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return a list of candidate formulas; each item must contain at least name, expression, and id."""
        ...


class FormulaInfoAdapter:
    """Bridge a BaseAdapter returning FormulaInfo to the FormulaSourceAdapter protocol."""

    def __init__(self, adapter: BaseAdapter) -> None:
        self.adapter = adapter

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search and convert to a list of dictionaries usable by FormulaRecommender."""
        results: list[dict[str, Any]] = []
        try:
            for info in self.adapter.search(query, limit):
                item = info.to_dict()
                # Keep the formula_id field consistent with local candidates
                item["formula_id"] = item.get("id", "external")
                # Bridge field: BaseAdapter's category maps to the domain used by the recommender
                item.setdefault("domain", item.get("category", ""))
                item.setdefault("verified", False)
                # Fall back to adapter source_name if FormulaInfo has no source
                if not item.get("source"):
                    item["source"] = self.adapter.source_name
                results.append(item)
        except Exception:
            # External adapter failure should not block the whole recommendation flow
            return []
        return results


def create_default_external_adapters() -> list[FormulaSourceAdapter]:
    """Create the default list of external formula adapters (offline sources only, avoiding network dependencies by default)."""
    adapters: list[FormulaSourceAdapter] = []

    # SciPy physics/math constants (fully offline, safe default)
    try:
        from symkit.infrastructure.adapters import ScipyConstantsAdapter

        adapters.append(FormulaInfoAdapter(ScipyConstantsAdapter()))
    except Exception:
        pass

    return adapters


def create_all_external_adapters() -> list[FormulaSourceAdapter]:
    """Create the full list of external formula adapters (including network sources)."""
    adapters = create_default_external_adapters()

    # Wikidata formulas (network)
    try:
        from symkit.infrastructure.adapters import get_wikidata_adapter

        adapters.append(FormulaInfoAdapter(get_wikidata_adapter()))
    except Exception:
        pass

    # BioModels pharmacokinetic/enzyme-kinetics models (network)
    try:
        from symkit.infrastructure.adapters import get_biomodels_adapter

        adapters.append(FormulaInfoAdapter(get_biomodels_adapter()))
    except Exception:
        pass

    return adapters


class FormulaRecommender:
    """Recommend relevant formulas based on DerivationGoal."""

    def __init__(
        self,
        repository: DerivationRepository | None = None,
        external_adapters: list[FormulaSourceAdapter] | None = None,
    ) -> None:
        self.repository = repository
        self.external_adapters = external_adapters or []

    def recommend(
        self,
        goal: DerivationGoal,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return a sorted list of formula recommendations."""
        candidates: list[dict[str, Any]] = []

        if self.repository is not None:
            for result in self.repository._results.values():  # noqa: SLF001
                score, reason = self._score_local(result, goal)
                if score > 0:
                    candidates.append({
                        "formula_id": result.id,
                        "name": result.name,
                        "expression": result.expression,
                        "domain": result.domain,
                        "verified": result.verified,
                        "score": score,
                        "reason": reason,
                        "source": "local",
                    })

        # External adapters (optional)
        for adapter in self.external_adapters:
            try:
                for item in adapter.search(goal.text, limit=top_k):
                    candidates.append({
                        "formula_id": item.get("id", "external"),
                        "name": item.get("name", "External formula"),
                        "expression": item.get("expression", ""),
                        "domain": item.get("domain", ""),
                        "verified": item.get("verified", False),
                        "score": 0.5,  # External formulas get a default medium score
                        "reason": "External formula search result",
                        "source": item.get("source") or adapter.__class__.__name__,
                    })
            except Exception:
                # External adapter failure should not affect local recommendations
                continue

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    def _score_local(
        self,
        result: DerivationResult,
        goal: DerivationGoal,
    ) -> tuple[float, str]:
        """Score a local formula and return the reason."""
        score = 0.0
        reasons: list[str] = []
        goal_text = goal.text.lower()
        goal_tokens = set(self._tokenize(goal_text))

        # Keyword overlap: name, description, tags, application context
        fields = [
            result.name,
            result.description,
            result.application_context,
            " ".join(result.tags),
            " ".join(result.derivation_steps),
        ]
        text = " ".join(f for f in fields if f).lower()
        field_tokens = set(self._tokenize(text))
        overlap = len(goal_tokens & field_tokens)
        if overlap:
            score += overlap * 0.3
            reasons.append(f"keyword overlap: {overlap}")

        # Domain match
        domain_match = False
        if result.domain and goal.domain and result.domain == goal.domain:
            score += 1.0
            reasons.append("domain match")
            domain_match = True
        elif result.domain and goal.domain and result.domain in goal.domain:
            score += 0.5
            reasons.append("domain sub-match")
            domain_match = True

        # Target variable overlap with formula variables.
        # Single-letter overlaps are heavily discounted because they are generic
        # (e.g. "a") and frequently produce false positives across unrelated domains.
        variable_score = 0.0
        if goal.target_variables and result.variables:
            common = set(goal.target_variables) & set(result.variables.keys())
            for var in common:
                weight = 0.2 if len(var) == 1 else 0.5
                variable_score += weight
                reasons.append(f"variable overlap: {var}")
        score += variable_score

        # Target expression similarity with formula expression (simple string containment)
        expression_similarity = False
        if goal.target_expression and result.expression:
            norm_target = goal.target_expression.lower().replace(" ", "")
            norm_expr = result.expression.lower().replace(" ", "")
            if norm_target in norm_expr or norm_expr in norm_target:
                score += 0.8
                reasons.append("expression similarity")
                expression_similarity = True

        # Relevance derived from the goal itself (verification excluded)
        relevance_score = score
        has_semantic_signal = overlap > 0 or domain_match or expression_similarity

        # Verification status bonus
        verified = False
        if result.verified:
            score += 0.5
            reasons.append("verified")
            verified = True

        # Guardrails: a verified but otherwise unrelated result should not be
        # recommended.  Likewise, a single generic variable overlap should not
        # bring in formulas from a completely different domain.
        if verified and relevance_score < 0.5:
            return 0.0, "verified but no relevance signal"
        if not has_semantic_signal and score < 0.6:
            return 0.0, "score below relevance threshold"

        reason = "; ".join(reasons) if reasons else "low relevance"
        return score, reason

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple alphanumeric tokenization with generic stopwords removed."""
        tokens = re.findall(r"[a-z0-9]+", text)
        return [t for t in tokens if t not in _RELEVANCE_STOPWORDS]

"""Formula index domain types and storage port (zero external deps).

The domain owns the *shape* of indexed formulas and the storage protocol;
the SQLite implementation lives in ``symkit.infrastructure.formula_index_store``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Protocol

from symkit.domain.formula_library import FormulaEntry

TIER_SEED = "seed"
TIER_STAGING = "staging"
TIER_CURATED = "curated"
# Representative precedence inside a duplicate group (lower wins).
TIER_ORDER = {TIER_CURATED: 0, TIER_SEED: 1, TIER_STAGING: 2}

MATCH_KINDS = (
    "exact_id", "exact_name", "exact_alias", "structural", "fts", "like", "browse",
)

# Generic domain nouns carried over from the legacy library scorer
# (``FormulaLibrary._STOPWORDS``): they appear in many formula names, so they
# cannot by themselves justify a hit when the query also carries a
# discriminative word. A query made *entirely* of these keeps the legacy
# low-relevance behaviour (e.g. "law" still finds Newton's second law).
GENERIC_TERMS: frozenset[str] = frozenset({
    "equation", "equations", "formula", "formulas", "law", "number",
    "constant", "model", "derivation", "derive", "function", "relation",
})

# Function words carry no retrieval signal: a query consisting only of these
# must match nothing rather than every entry whose text happens to contain them.
FUNCTION_WORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "among", "an", "and", "any", "are", "as", "at", "be", "been", "before",
    "being", "below", "between", "both", "by", "can", "could", "did", "do",
    "does", "during", "each", "few", "for", "from", "further", "had", "has",
    "have", "he", "her", "here", "him", "his", "how", "i", "in", "into", "is",
    "it", "its", "just", "may", "me", "might", "more", "most", "must", "my",
    "no", "not", "of", "on", "once", "only", "onto", "or", "other", "our",
    "over", "own", "same", "shall", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "to", "under", "us", "using", "very", "was",
    "we", "were", "what", "when", "where", "why", "will", "with", "within",
    "without", "would", "you", "expression", "expressions",
})

# Every token that cannot justify a hit on its own.
SEARCH_STOPWORDS: frozenset[str] = GENERIC_TERMS | FUNCTION_WORDS


@dataclass
class IndexedFormula:
    """A formula as stored in the index: entry fields plus curation metadata."""

    id: str
    tier: str
    content_hash: str
    name: str = ""
    sympy_str: str = ""
    latex: str = ""
    domain: str = ""
    category: str = ""
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)
    references: list[str] = field(default_factory=list)
    verified: bool = False
    curated: bool = False
    application_context: str = ""
    derivation_steps: list[str] = field(default_factory=list)
    source_path: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_entry(
        cls,
        entry: FormulaEntry,
        *,
        tier: str,
        content_hash: str,
        verified: bool = False,
        curated: bool = False,
        application_context: str = "",
        derivation_steps: list[str] | None = None,
    ) -> IndexedFormula:
        """Build an IndexedFormula from a YAML-backed FormulaEntry."""
        return cls(
            id=entry.id,
            tier=tier,
            content_hash=content_hash,
            name=entry.name,
            sympy_str=entry.sympy_str,
            latex=entry.latex,
            domain=entry.domain,
            category=entry.category,
            description=entry.description,
            aliases=list(entry.aliases),
            tags=list(entry.tags),
            variables=dict(entry.variables),
            references=list(entry.references),
            verified=verified,
            curated=curated,
            application_context=application_context,
            derivation_steps=list(derivation_steps or []),
            source_path=str(entry.source_path or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the index payload column."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexedFormula:
        """Deserialize from a payload dict; unknown keys are ignored."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class SearchHit:
    """One raw index match before domain ranking."""

    formula: IndexedFormula
    match_kind: str  # one of MATCH_KINDS
    base_score: float


@dataclass
class RankedResult:
    """A ranked, deduplicated search result."""

    formula: IndexedFormula
    score: float
    duplicates: int = 0
    duplicate_ids: list[str] = field(default_factory=list)


@dataclass
class ManifestEntry:
    """Freshness record for one source YAML file."""

    path: str
    mtime: float
    size: int
    entry_id: str


@dataclass
class SyncReport:
    """Outcome of an incremental or full index sync."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    failed: int = 0
    failed_paths: list[str] = field(default_factory=list)


class FormulaIndexStore(Protocol):
    """Storage port for the persistent formula index."""

    def open(self) -> None: ...
    def close(self) -> None: ...
    def clear(self) -> None: ...
    def upsert_many(self, entries: list[IndexedFormula]) -> None: ...
    def remove_ids(self, ids: list[str]) -> None: ...
    def get(self, formula_id: str) -> IndexedFormula | None: ...
    def all(self) -> list[IndexedFormula]: ...
    def find_by_structural_hash(self, digest: str) -> list[IndexedFormula]: ...
    def search(
        self,
        query: str,
        *,
        tier: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        prelimit: int = 200,
    ) -> list[SearchHit]: ...
    def manifest(self) -> dict[str, ManifestEntry]: ...
    def set_manifest(self, entries: list[ManifestEntry]) -> None: ...
    def stats(self) -> dict[str, Any]: ...

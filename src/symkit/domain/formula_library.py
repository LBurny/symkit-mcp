"""Local formula library for SymKit.

The local library stores formula entries as YAML files. It is user-editable:
you can add, remove, or edit files directly, or use the ``formula_add`` MCP tool.

Entries are sourced from two layers:

1. **Bundled seed formulas** — read-only YAML files shipped inside the wheel
   under ``symkit/resources/seed_formulas/``. These always load and provide the
   baseline library (Reynolds number, Navier-Stokes, ideal gas law, …) so the
   package works immediately after ``pip install`` from any working directory.
2. **User overlay** — a writable directory (``user_library_dir()`` by default,
   or an explicit ``library_path``) where the ``formula_add`` / ``delete`` MCP
   tools persist entries. A user entry with the same id as a seed overrides the
   seed; deleting a seed-id removes only the user override, leaving the seed
   intact.

Each entry is indexed by id, name, aliases, tags, and keywords so that
``formula_search`` returns ranked results deterministically and without network
latency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from symkit.domain.paths import bundled_seed_library_dir, user_library_dir


@dataclass
class FormulaEntry:
    """A single formula in the local library."""

    id: str
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
    source_path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_path: Path | None = None) -> FormulaEntry:
        """Create a FormulaEntry from a dictionary."""
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            sympy_str=str(data.get("sympy_str", "")),
            latex=str(data.get("latex", "")),
            domain=str(data.get("domain", "")),
            category=str(data.get("category", "")),
            description=str(data.get("description", "")),
            aliases=list(data.get("aliases", []) or []),
            tags=list(data.get("tags", []) or []),
            variables=dict(data.get("variables", {}) or {}),
            references=list(data.get("references", []) or []),
            source_path=source_path,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary suitable for YAML output."""
        return {
            "id": self.id,
            "name": self.name,
            "aliases": self.aliases,
            "domain": self.domain,
            "category": self.category,
            "description": self.description,
            "sympy_str": self.sympy_str,
            "latex": self.latex,
            "tags": self.tags,
            "variables": self.variables,
            "references": self.references,
        }

    @property
    def search_text(self) -> str:
        """Return a normalized search string combining all text fields."""
        parts = [
            self.id,
            self.name,
            self.domain,
            self.category,
            self.description,
            " ".join(self.aliases),
            " ".join(self.tags),
        ]
        return " ".join(p for p in parts if p).lower()


class FormulaLibrary:
    """Loads and indexes YAML formula entries from a local directory.

    The default configuration reads bundled seed formulas (read-only, shipped
    in the wheel) merged with a writable user overlay directory. An explicit
    ``library_path`` overrides only the *writable* overlay location; seeds are
    always loaded underneath it.
    """

    def __init__(self, library_path: str | Path | None = None):
        self._writable_path: Path = (
            Path(library_path) if library_path else user_library_dir()
        )
        self._seed_path: Path = bundled_seed_library_dir()
        self._entries: dict[str, FormulaEntry] = {}
        self._load_entries()

    @property
    def library_path(self) -> Path:
        """Writable overlay directory where ``add_or_update`` persists entries."""
        return self._writable_path

    def _load_entries(self) -> None:
        """Load all YAML files from the bundled seeds and the writable overlay.

        Seeds are loaded first; user entries with the same id override them.
        """
        self._entries.clear()
        # Read-only bundled seeds (always loaded).
        self._load_from(self._seed_path, read_only=True)
        # Writable user overlay (may override seeds by id).
        self._load_from(self._writable_path, read_only=False)

    def _load_from(self, root: Path, read_only: bool) -> None:
        """Load YAML entries from ``root`` (no-op if it does not exist)."""
        if not root.exists():
            return
        for path in root.rglob("*.yaml"):
            if path.name == "README.md":
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                entry = FormulaEntry.from_dict(data, source_path=path)
                if not entry.id:
                    continue
                # Writable entries override seed entries with the same id.
                if read_only and entry.id in self._entries:
                    continue
                self._entries[entry.id] = entry
            except Exception as e:
                print(f"Failed to load formula {path}: {e}")

    def reload(self) -> None:
        """Reload entries from disk."""
        self._load_entries()

    def get(self, formula_id: str) -> FormulaEntry | None:
        """Get a formula by id."""
        return self._entries.get(formula_id)

    def list_categories(self) -> list[str]:
        """List all distinct categories in the library."""
        categories = {e.category for e in self._entries.values() if e.category}
        return sorted(categories)

    def list_domains(self) -> list[str]:
        """List all distinct domains in the library."""
        domains = {e.domain for e in self._entries.values() if e.domain}
        return sorted(domains)

    def list_formula_ids(self, category: str | None = None) -> list[str]:
        """List formula ids, optionally filtered by category."""
        entries = self._entries.values()
        if category:
            entries = [e for e in entries if e.category == category]
        return sorted(e.id for e in entries)

    def search(
        self,
        query: str,
        category: str | None = None,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[tuple[float, FormulaEntry]]:
        """Search the library and return ranked (score, entry) tuples.

        Ranking:
        - id exact match: 1.0
        - name exact match: 0.95
        - alias exact match: 0.90
        - tag match: 0.75
        - keyword in search text: 0.50
        - category/domain match: +0.10 bonus

        If ``query`` is empty but ``category`` or ``domain`` is provided, all
        matching entries are returned with a neutral score of 0.5.
        """
        normalized_query = self._normalize(query)
        if not normalized_query and not category and not domain:
            return []

        results: list[tuple[float, FormulaEntry]] = []
        for entry in self._entries.values():
            if category and entry.category != category:
                continue
            if domain and entry.domain != domain:
                continue

            score = 0.5 if not normalized_query else self._score(entry, normalized_query)
            if score > 0:
                results.append((score, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return results[:limit]

    def _normalize(self, text: str) -> str:
        """Normalize text for matching: lowercase, collapse whitespace, trim."""
        text = text.lower().strip()
        text = re.sub(r"[\s\-_]+", " ", text)
        return text.strip()

    # Generic words that appear in many formula names/descriptions and should not
    # alone trigger a high partial-match score.
    _STOPWORDS: frozenset[str] = frozenset({
        "equation", "equations", "formula", "formulas", "law", "number",
        "constant", "model", "derivation", "derive", "function", "relation",
    })

    def _score(self, entry: FormulaEntry, query: str) -> float:
        """Compute a relevance score for the entry against the query."""
        # Exact id match
        if self._normalize(entry.id) == query:
            return 1.0

        # Exact name match
        if self._normalize(entry.name) == query:
            return 0.95

        # Alias exact match
        for alias in entry.aliases:
            if self._normalize(alias) == query:
                return 0.90

        score = 0.0
        query_words = query.split()
        if not query_words:
            return score

        # Tag match
        tags_lower = [t.lower() for t in entry.tags]
        if any(q in tags_lower for q in query_words):
            score = max(score, 0.75)

        # Keyword match in combined search text. Stopwords are ignored for the
        # "all words match" bonus, and a single stopword match does not produce
        # a score by itself.
        meaningful_words = [q for q in query_words if q not in self._STOPWORDS]
        search_text = entry.search_text

        if meaningful_words and all(q in search_text for q in meaningful_words):
            # All non-stop words match: high relevance
            score = max(score, 0.55)
        elif meaningful_words and any(q in search_text for q in meaningful_words):
            # Some non-stop words match: moderate relevance
            score = max(score, 0.35)
        elif all(q in search_text for q in query_words):
            # Only stopwords (or all words including stopwords) match: low relevance
            score = max(score, 0.15)

        # Category/domain bonus only if the query contains a meaningful term
        # that also appears in the category/domain. Stopwords alone do not earn
        # this bonus.
        category_domain_text = self._normalize(entry.category) + " " + self._normalize(entry.domain)
        for q in meaningful_words:
            if q in category_domain_text:
                score += 0.10
                break

        return score

    def add_or_update(self, entry: FormulaEntry) -> None:
        """Persist an entry to the writable user overlay.

        Writing targets the writable overlay directory only; the read-only
        bundled seed tree is never modified. A user entry with the same id as
        a seed overrides the seed in the in-memory index.
        """
        self._entries[entry.id] = entry
        category = entry.category or "uncategorized"
        target_dir = self._writable_path / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{entry.id}.yaml"
        entry.source_path = target_path

        with target_path.open("w", encoding="utf-8") as f:
            yaml.dump(entry.to_dict(), f, allow_unicode=True, sort_keys=False)

    def delete(self, formula_id: str) -> bool:
        """Delete a formula by id. Returns True if a writable copy existed.

        Only the user-overlay YAML is removed. If the id also exists as a
        bundled seed, the seed remains read-only and the entry stays in the
        in-memory index (reloaded from the seed on next ``reload``).
        """
        entry = self._entries.get(formula_id)
        if not entry or not entry.source_path:
            return False
        # Only unlink files that live under the writable overlay; never touch
        # the bundled seed tree.
        try:
            entry.source_path.relative_to(self._writable_path)
        except ValueError:
            return False
        if not entry.source_path.exists():
            return False
        entry.source_path.unlink()
        # Remove from the in-memory index only if there is no seed backing it.
        seed_entry = None
        if self._seed_path.exists():
            for path in self._seed_path.rglob(f"{formula_id}.yaml"):
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and data.get("id") == formula_id:
                    seed_entry = FormulaEntry.from_dict(data, source_path=path)
                    break
        if seed_entry is not None:
            self._entries[formula_id] = seed_entry
        else:
            self._entries.pop(formula_id, None)
        return True

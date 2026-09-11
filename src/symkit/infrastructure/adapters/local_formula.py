"""Local Formula Adapter - Formula lookup via the persistent formula index.

The adapter delegates to a ``FormulaCatalog`` (SQLite FTS5 index over the
YAML layers) and returns ``FormulaInfo`` objects so the rest of the toolchain
(e.g. ``formula_get(..., load_into_session=True)``) keeps working unchanged.

Construction modes:
- ``LocalFormulaAdapter(catalog=...)`` — delegate to a shared catalog (the MCP
  tools inject the process-wide one from ``tools._state.get_catalog``).
- ``LocalFormulaAdapter(library_path=..., derived_path=...)`` — private
  in-memory catalog over those directories (tests, ad-hoc use).
- ``LocalFormulaAdapter()`` — private in-memory catalog over the default
  per-user directories and the bundled seeds.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from symkit.domain.formula_index import RankedResult

from .base import BaseAdapter, FormulaInfo

if TYPE_CHECKING:
    from symkit.application.formula_catalog import FormulaCatalog


def _build_catalog(
    library_path: str | Path | None,
    derived_path: str | Path | None,
) -> FormulaCatalog:
    """Build a private in-memory catalog over the given (or default) dirs."""
    from symkit.application.formula_catalog import FormulaCatalog
    from symkit.domain.paths import (
        bundled_seed_library_dir,
        user_derived_dir,
        user_library_dir,
    )
    from symkit.infrastructure.formula_files import YamlFormulaFileSource
    from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore

    store = SqliteFormulaIndexStore(Path(":memory:"))
    store.open()
    catalog = FormulaCatalog(
        store,
        YamlFormulaFileSource(),
        seed_dir=bundled_seed_library_dir(),
        staging_dir=Path(derived_path) if derived_path else user_derived_dir(),
        curated_dir=Path(library_path) if library_path else user_library_dir(),
    )
    catalog.ensure_fresh()
    return catalog


class LocalFormulaAdapter(BaseAdapter):
    """Adapter over the persistent formula index (BaseAdapter interface).

    Example:
        adapter = LocalFormulaAdapter()
        results = adapter.search("Navier-Stokes")
        formula = adapter.get_formula("ns_incompressible")
    """

    def __init__(
        self,
        catalog: FormulaCatalog | None = None,
        library_path: str | Path | None = None,
        derived_path: str | Path | None = None,
    ):
        self._catalog = catalog if catalog is not None else _build_catalog(
            library_path, derived_path
        )

    @property
    def source_name(self) -> str:
        return "local"

    def search(
        self, query: str, limit: int = 10, tier: str | None = None
    ) -> list[FormulaInfo]:
        """Search the formula index by query string."""
        return [
            self._to_formula_info(r)
            for r in self._catalog.search(query, tier=tier, limit=limit)
        ]

    def search_by_category(
        self, category: str, query: str = "", limit: int = 20, tier: str | None = None
    ) -> list[FormulaInfo]:
        """Search within a specific category."""
        return [
            self._to_formula_info(r)
            for r in self._catalog.search(query, tier=tier, category=category, limit=limit)
        ]

    def get_formula(self, formula_id: str) -> FormulaInfo | None:
        """Get a formula by id from the index."""
        indexed = self._catalog.get(formula_id)
        if indexed is None:
            return None
        return self._to_formula_info(RankedResult(indexed, 1.0))

    def list_categories(self) -> list[str]:
        """List available formula categories."""
        return sorted({f.category for f in self._catalog.all() if f.category})

    def list_formulas(self, category: str | None = None) -> list[str]:
        """List formula ids, optionally filtered by category."""
        formulas = self._catalog.all()
        if category:
            formulas = [f for f in formulas if f.category == category]
        return sorted(f.id for f in formulas)

    def _to_formula_info(self, result: RankedResult) -> FormulaInfo:
        """Convert a ranked index result to the shared ``FormulaInfo`` format."""
        entry = result.formula
        return FormulaInfo(
            id=entry.id,
            name=entry.name,
            expression=entry.sympy_str,
            sympy_str=entry.sympy_str,
            latex=entry.latex,
            variables=entry.variables,
            source=self.source_name,
            category=entry.category,
            description=entry.description,
            tags=entry.tags,
            references=entry.references,
            extra={
                "score": result.score,
                "tier": entry.tier,
                "verified": entry.verified,
                "duplicates": result.duplicates,
                "duplicate_ids": result.duplicate_ids,
                "aliases": entry.aliases,
                "domain": entry.domain,
                "load_hint": f'formula_get("{entry.id}", source="local")',
            },
        )

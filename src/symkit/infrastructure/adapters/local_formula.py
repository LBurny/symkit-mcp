"""Local Formula Adapter - Formula lookup from a local YAML library.

This adapter replaces the external Wikidata/BioModels adapters in the default
MCP tool path. It reads user-editable YAML entries from ``formulas/library/``
and returns them as ``FormulaInfo`` objects so that the rest of the toolchain
(e.g. ``formula_get(..., load_into_session=True)``) continues to work unchanged.
"""

from __future__ import annotations

from pathlib import Path

from symkit.domain.formula_library import FormulaEntry, FormulaLibrary

from .base import BaseAdapter, FormulaInfo


class LocalFormulaAdapter(BaseAdapter):
    """
    Adapter for the local formula library.

    Example:
        adapter = LocalFormulaAdapter()
        results = adapter.search("Navier-Stokes")
        formula = adapter.get_formula("ns_incompressible")
    """

    def __init__(self, library_path: str | Path | None = None):
        self._library = FormulaLibrary(library_path)

    @property
    def source_name(self) -> str:
        return "local"

    def search(self, query: str, limit: int = 10) -> list[FormulaInfo]:
        """Search the local formula library by query string."""
        ranked = self._library.search(query, limit=limit)
        return [self._to_formula_info(entry, score=score) for score, entry in ranked]

    def search_by_category(self, category: str, query: str = "", limit: int = 20) -> list[FormulaInfo]:
        """Search within a specific category."""
        ranked = self._library.search(query, category=category, limit=limit)
        return [self._to_formula_info(entry, score=score) for score, entry in ranked]

    def get_formula(self, formula_id: str) -> FormulaInfo | None:
        """Get a formula by id from the local library."""
        entry = self._library.get(formula_id)
        if entry is None:
            return None
        return self._to_formula_info(entry, score=1.0)

    def list_categories(self) -> list[str]:
        """List available formula categories."""
        return self._library.list_categories()

    def list_formulas(self, category: str | None = None) -> list[str]:
        """List formula ids, optionally filtered by category."""
        return self._library.list_formula_ids(category)

    def _to_formula_info(self, entry: FormulaEntry, score: float = 1.0) -> FormulaInfo:
        """Convert a local ``FormulaEntry`` to the shared ``FormulaInfo`` format."""
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
                "score": score,
                "aliases": entry.aliases,
                "domain": entry.domain,
                "load_hint": f'formula_get("{entry.id}", source="local")',
            },
        )

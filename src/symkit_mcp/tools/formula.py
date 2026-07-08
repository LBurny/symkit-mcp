"""Formula Tools — Local formula library MCP tools

Provides lookup and editing for the local SymKit formula library. The library is
stored as YAML files under ``formulas/library/`` and can be edited directly or
through the ``formula_add`` tool. This removes network dependencies and ensures
deterministic, high-accuracy search.

Legacy adapters (Wikidata, BioModels, SciPy) are still available on request, but
the default workflow is local-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from symkit.domain.formula import FormulaSource
from symkit.domain.formula_library import FormulaEntry, FormulaLibrary
from symkit.domain.formula_search_query import (
    normalize_formula_search_inputs,
)
from symkit.infrastructure.adapters.local_formula import LocalFormulaAdapter
from symkit_mcp.tools._state import get_session

if TYPE_CHECKING:
    from symkit.infrastructure.adapters.base import BaseAdapter


# Singleton local adapter instance used by all tools. The adapter is lazily
# initialized from the default ``formulas/library`` directory.
_local_adapter: BaseAdapter | None = None


def _get_local_adapter() -> BaseAdapter:
    """Return the shared local adapter instance."""
    global _local_adapter  # noqa: PLW0603
    if _local_adapter is None:
        _local_adapter = LocalFormulaAdapter()
    return _local_adapter


def _reset_local_adapter() -> None:
    """Reset the shared adapter (useful after formula_add writes new files)."""
    global _local_adapter  # noqa: PLW0603
    _local_adapter = None


# Legacy sources that still work on request. They are not searched by default.
_LEGACY_SOURCES = ("wikidata", "biomodels", "scipy")


def _get_legacy_adapter(source: str) -> BaseAdapter:
    """Return a legacy adapter for the requested source."""
    if source == "wikidata":
        from symkit.infrastructure.adapters.wikidata_formulas import (
            WikidataFormulaAdapter,
        )

        return WikidataFormulaAdapter()
    if source == "biomodels":
        from symkit.infrastructure.adapters.biomodels import BioModelsAdapter

        return BioModelsAdapter()
    if source == "scipy":
        from symkit.infrastructure.adapters.scipy_constants import (
            ScipyConstantsAdapter,
        )

        return ScipyConstantsAdapter()
    raise ValueError(f"Unknown legacy source: {source}")


def register_formula_tools(mcp: Any) -> None:
    """Register formula search tools."""

    # ═══════════════════════════════════════════════════════════════════════
    # Local formula search
    # ═══════════════════════════════════════════════════════════════════════

    @mcp.tool()
    def formula_search(
        query: str,
        source: str = "local",
        domain: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search the local formula library.

        Retrieve accurate mathematical/physical formulas from the local, editable
        YAML library. This is deterministic, fast, and does not require network
        access.

        The query and domain are normalized automatically, so you can pass
        free-form text such as "Navier–Stokes equations" or "fluid_dynamics".

        Args:
            query: Search keyword
                   - English name: "Reynolds number", "Arrhenius equation"
                   - Domain terms: "fluid dynamics", "quantum", "thermodynamics"
            source: Data source
                   - "local": Local YAML library (default, recommended)
                   - "scipy": Physical constants only (no local search)
                   - "legacy": Search local, then Wikidata, BioModels, SciPy
                   - "all": Alias for "legacy" (kept for compatibility)
                   - "wikidata", "biomodels", "scipy": Legacy source only
            domain: Restrict domain (optional)
                   - "mechanics", "thermodynamics", "electromagnetism"
                   - "fluid_dynamics", "fluid_mechanics", "quantum_mechanics"
            limit: Maximum number of results to return

        Returns:
            {
                "success": true,
                "results": [...],
                "total": 1,
                "query": "navier-stokes equations",
                "domain": "fluid",
                "sources_searched": ["local"],
                "next_steps": [...]
            }

        Example:
            # Search the local library
            formula_search("Reynolds number")

            # Search by domain
            formula_search("diffusion", domain="thermodynamics")

        Correct workflow for derivation:
            1. formula_search("<concept>", domain="<domain>")
            2. formula_get(result["id"])
            3. session_load_formula(formula["sympy_str"] or formula["latex"], ...)
            4. math(..., session=True) to derive or transform
        """
        normalized = normalize_formula_search_inputs(query, domain)
        normalized_query = normalized["query"]
        normalized_domain = normalized["domain"]

        results: list[dict[str, Any]] = []
        sources_searched: list[str] = []
        source_errors: list[str] = []

        search_local = source in ("local", "legacy", "all")
        search_legacy = source in _LEGACY_SOURCES
        search_legacy = search_legacy or source in ("legacy", "all")

        # ── Local library (default) ──────────────────────────────────────────
        if search_local:
            try:
                adapter = _get_local_adapter()
                if normalized_domain:
                    local_results = adapter.search_by_category(
                        normalized_domain, normalized_query, limit
                    )
                else:
                    local_results = adapter.search(normalized_query, limit)

                for r in local_results:
                    info = r.to_dict()
                    info["source"] = "local"
                    results.append(info)
                sources_searched.append("local")
            except Exception as e:
                source_errors.append(f"Local library search failed: {e}")

        # ── Legacy sources (optional) ───────────────────────────────────────
        if search_legacy and source not in ("local",):
            # If the user explicitly asked for "scipy" or "wikidata" etc.,
            # search only that source. Otherwise search all legacy sources.
            explicit_sources = [s for s in _LEGACY_SOURCES if s == source]
            legacy_sources = explicit_sources if explicit_sources else list(_LEGACY_SOURCES)

            for legacy in legacy_sources:
                try:
                    adapter = _get_legacy_adapter(legacy)
                    try:
                        if normalized_domain and hasattr(adapter, "search_by_category"):
                            legacy_results = adapter.search_by_category(
                                normalized_domain, normalized_query, limit
                            )
                        else:
                            legacy_results = adapter.search(normalized_query, limit)

                        for r in legacy_results:
                            info = r.to_dict()
                            info["source"] = legacy
                            results.append(info)
                        sources_searched.append(legacy)
                    finally:
                        if hasattr(adapter, "close"):
                            adapter.close()
                except Exception as e:
                    source_errors.append(f"{legacy.capitalize()} search failed: {e}")

        # Add metadata and workflow hints
        # Sort results by their real relevance score across all sources so the
        # highest-scoring item is promoted regardless of where it came from.
        results.sort(key=lambda r: r.get("extra", {}).get("score", 0.0), reverse=True)
        results = results[:limit]

        top_result = results[0] if results else None
        next_steps: list[dict[str, Any]] = []
        if top_result:
            # Preserve the real score; do not override it to 1.0. Ensure a
            # top-level load_hint is present for convenience.
            top_result.setdefault("load_hint", f'formula_get("{top_result["id"]}")')
            next_steps.append({
                "tool": "formula_get",
                "reason": "Get full details of the best match",
                "example": f'formula_get("{top_result["id"]}")',
            })
            next_steps.append({
                "tool": "formula_add",
                "reason": "Add a missing formula to the local library",
                "example": 'formula_add(id="my_formula", name="My formula", ...)',
            })

        response: dict[str, Any] = {
            "success": True,
            "results": results[:limit],
            "total": len(results),
            "query": normalized_query,
            "domain": normalized_domain,
            "sources_searched": sources_searched,
            "next_steps": next_steps,
        }
        if source_errors:
            response["warnings"] = source_errors
        return response

    @mcp.tool()
    def formula_get(
        formula_id: str,
        source: str = "local",
        load_into_session: bool = False,
    ) -> dict[str, Any]:
        """Get detailed formula information from the local library.

        Args:
            formula_id: Formula identifier (e.g., "reynolds_number")
            source: Data source
                   - "local": Local YAML library (default, recommended)
                   - "wikidata", "biomodels", "scipy": Legacy sources
            load_into_session: If True, load the formula into the current derivation session.
                              Requires an active session started with session_start().

        Returns:
            {
                "success": true,
                "formula": {
                    "id": "reynolds_number",
                    "name": "Reynolds number",
                    "latex": "Re = \\frac{\\rho v L}{\\mu}",
                    "sympy_str": "rho * v * L / mu",
                    "variables": {...},
                    "source": "local"
                },
                "session_loaded": true
            }

        Example:
            # Get a local formula
            formula_get("reynolds_number")

            # Get and immediately load into a derivation session
            formula_get("reynolds_number", load_into_session=True)
        """
        from symkit.infrastructure.adapters.base import FormulaInfo

        result: FormulaInfo | None = None
        formula_source = source

        if source == "local":
            try:
                adapter = _get_local_adapter()
                result = adapter.get_formula(formula_id)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Local library error: {e}",
                    "formula_id": formula_id,
                }
        elif source in _LEGACY_SOURCES:
            try:
                adapter = _get_legacy_adapter(source)
                try:
                    result = adapter.get_formula(formula_id)
                finally:
                    if hasattr(adapter, "close"):
                        adapter.close()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"{source.capitalize()} error: {e}",
                    "formula_id": formula_id,
                }
        else:
            return {
                "success": False,
                "error": f"Unknown source: {source}",
                "available_sources": ["local", "wikidata", "biomodels", "scipy"],
            }

        if result is None:
            return {
                "success": False,
                "error": f"Formula not found: {formula_id}",
                "source": source,
            }

        response: dict[str, Any] = {
            "success": True,
            "formula": result.to_dict(),
        }

        if load_into_session:
            session = get_session()
            if session is None:
                response["session_loaded"] = False
                response["session_error"] = "No active session. Use session_start() first."
            else:
                try:
                    formula_source_enum = FormulaSource(formula_source)
                except ValueError:
                    formula_source_enum = FormulaSource.LOCAL
                # Prefer sympy_str; fall back to latex for formulas that cannot be parsed yet.
                expression_to_load = result.sympy_str or result.latex or str(result.expression)
                load_result = session.load_formula(
                    expression_to_load,
                    formula_id=result.id,
                    source=formula_source_enum,
                    source_detail=formula_source,
                )
                response["session_loaded"] = load_result.get("success", False)
                response["session_load_result"] = load_result

        return response

    @mcp.tool()
    def formula_add(
        id: str,  # noqa: A002
        name: str,
        sympy_str: str,
        latex: str,
        variables: dict[str, dict[str, Any]],
        domain: str = "",
        category: str = "",
        description: str = "",
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        references: list[str] | None = None,
        library_path: str | None = None,
    ) -> dict[str, Any]:
        """Add or update a formula in the local library.

        This lets you (and the LLM) extend the local formula collection manually.
        Formulas are persisted as YAML files under ``formulas/library/<category>/``.

        Args:
            id: Unique identifier for the formula (e.g., "custom_drag_force").
               Used as the file name and lookup key.
            name: Human-readable formula name.
            sympy_str: SymPy-compatible expression, e.g. "F_d == 1/2 * rho * v**2 * C_d * A".
            latex: LaTeX representation, e.g. "F_d = \\frac{1}{2} \\rho v^2 C_d A".
            variables: Mapping of symbol names to metadata, e.g.
                       {"rho": {"description": "density", "unit": "kg/m^3"}}.
            domain: Optional domain tag (e.g., "fluid_dynamics").
            category: Optional category folder name (e.g., "fluid_dynamics").
            description: Optional longer description of the formula.
            aliases: Optional list of alternative names.
            tags: Optional list of tags.
            references: Optional list of references / URLs.
            library_path: Optional custom library directory. Defaults to ``formulas/library``.

        Returns:
            {
                "success": true,
                "formula_id": "custom_drag_force",
                "file_path": "formulas/library/fluid_dynamics/custom_drag_force.yaml",
                "message": "Formula added to local library."
            }

        Example:
            formula_add(
                id="custom_drag_force",
                name="Drag force",
                sympy_str="F_d == 1/2 * rho * v**2 * C_d * A",
                latex="F_d = \\frac{1}{2} \\rho v^2 C_d A",
                domain="fluid_dynamics",
                category="fluid_dynamics",
                description="Drag force on a body in a fluid.",
                variables={
                    "F_d": {"description": "drag force", "unit": "N"},
                    "rho": {"description": "density", "unit": "kg/m^3"},
                    "v": {"description": "velocity", "unit": "m/s"},
                    "C_d": {"description": "drag coefficient"},
                    "A": {"description": "reference area", "unit": "m^2"}
                },
                aliases=["drag force", "fluid drag"],
                tags=["drag", "force"],
            )
        """
        if not id:
            return {
                "success": False,
                "error": "Formula id is required.",
            }
        if not sympy_str:
            return {
                "success": False,
                "error": "sympy_str is required.",
            }
        if not variables:
            return {
                "success": False,
                "error": "variables must be provided (can be empty {}).",
            }

        try:
            library = FormulaLibrary(library_path) if library_path else FormulaLibrary()
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to open local library: {e}",
            }

        entry = FormulaEntry(
            id=id,
            name=name,
            sympy_str=sympy_str,
            latex=latex,
            domain=domain,
            category=category or "uncategorized",
            description=description,
            aliases=list(aliases or []),
            tags=list(tags or []),
            variables=variables,
            references=list(references or []),
        )

        try:
            library.add_or_update(entry)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save formula: {e}",
            }

        # Reset the shared adapter so the new entry is picked up immediately.
        _reset_local_adapter()

        return {
            "success": True,
            "formula_id": id,
            "file_path": str(entry.source_path) if entry.source_path else None,
            "message": "Formula added to local library.",
        }

    @mcp.tool()
    def formula_categories(
        source: str = "local",
    ) -> dict[str, Any]:
        """List available formula categories.

        Get the categories currently present in the local formula library.

        Args:
            source: Data source
                   - "local": Local YAML library (default)
                   - "all": Local + legacy sources
                   - "wikidata", "biomodels", "scipy": Legacy source only

        Returns:
            {
                "success": true,
                "categories": {
                    "local": ["fluid_dynamics", "mechanics", "thermodynamics"],
                    "wikidata": [...]
                }
            }
        """
        categories: dict[str, list[str]] = {}

        if source in ("local", "all"):
            try:
                adapter = _get_local_adapter()
                categories["local"] = adapter.list_categories()
            except Exception:
                categories["local"] = []

        if source in ("all",) or source in _LEGACY_SOURCES:
            explicit = [source] if source in _LEGACY_SOURCES else list(_LEGACY_SOURCES)
            for legacy in explicit:
                try:
                    adapter = _get_legacy_adapter(legacy)
                    categories[legacy] = adapter.list_categories()
                    if hasattr(adapter, "close"):
                        adapter.close()
                except Exception:
                    categories[legacy] = []

        return {
            "success": True,
            "categories": categories,
        }

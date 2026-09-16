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
from symkit.domain.formula_library import FormulaEntry
from symkit.domain.formula_search_query import (
    normalize_formula_search_inputs,
)
from symkit.infrastructure.adapters.local_formula import LocalFormulaAdapter
from symkit.infrastructure.derivation_repository import get_repository
from symkit_mcp.tools import _formula_governance as gov
from symkit_mcp.tools._state import get_catalog, get_session

if TYPE_CHECKING:
    from symkit.infrastructure.adapters.base import BaseAdapter


def _get_local_adapter() -> LocalFormulaAdapter:
    """Return a local adapter bound to the shared formula catalog."""
    return LocalFormulaAdapter(catalog=get_catalog())


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

    @mcp.tool(meta={"category": "Formula Library"})
    def formula_search(
        query: str,
        source: str = "local",
        domain: str | None = None,
        tier: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search the formula library.

        The default ``source="local"`` searches the persistent index over the
        local YAML layers: deterministic, fast, no network. Other sources query
        external services (Wikidata, SciPy constants, BioModels) and degrade
        gracefully when offline.

        Query and domain are normalized automatically, so free-form text such as
        "Navier-Stokes equations", "fluid_dynamics", or Chinese aliases works.

        Args:
            query: Search keyword
                   - English name: "Reynolds number", "Arrhenius equation"
                   - Chinese alias: "雷诺数" (when stored as an alias)
                   - Domain terms: "fluid dynamics", "quantum", "thermodynamics"
                   - Expression content: "sqrt(2*G*M/R)"
            source: Data source
                   - "local": Local YAML library (default, recommended)
                   - "legacy": Search local, then Wikidata, BioModels, SciPy
                   - "all": Alias for "legacy" (kept for compatibility)
                   - "wikidata", "biomodels", "scipy": Query that legacy
                     source only (no local search)
            domain: Restrict domain (optional)
                   - "mechanics", "thermodynamics", "electromagnetism"
                   - "fluid_dynamics", "fluid_mechanics", "quantum_mechanics"
            tier: Restrict curation tier (optional, local source only)
                   - "curated": user-added / promoted formulas
                   - "seed": bundled read-only formulas
                   - "staging": session-derived formulas not yet curated
            limit: Maximum number of results to return

        Returns:
            {
                "success": true,
                "results": [{"id", "name", ..., "tier", "verified",
                             "duplicates"}],
                "total": 1,
                "query": "navier-stokes equations",
                "domain": "fluid",
                "sources_searched": ["local"],
                "next_steps": [...]
            }

        Example:
            # Search the local library
            formula_search("Reynolds number")

            # Search only curated formulas
            formula_search("drag", tier="curated")

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
                        normalized_domain, normalized_query, limit, tier=tier
                    )
                else:
                    local_results = adapter.search(normalized_query, limit, tier=tier)

                for r in local_results:
                    info = r.to_dict()
                    info["source"] = "local"
                    extra = info.get("extra", {})
                    for key in ("tier", "verified", "duplicates", "duplicate_ids"):
                        info[key] = extra.get(key)
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
                    legacy_adapter = _get_legacy_adapter(legacy)
                    try:
                        if normalized_domain and hasattr(legacy_adapter, "search_by_category"):
                            legacy_results = legacy_adapter.search_by_category(
                                normalized_domain, normalized_query, limit
                            )
                        else:
                            legacy_results = legacy_adapter.search(normalized_query, limit)

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

    @mcp.tool(meta={"category": "Formula Library"})
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
                legacy_adapter = _get_legacy_adapter(source)
                try:
                    result = legacy_adapter.get_formula(formula_id)
                finally:
                    if hasattr(legacy_adapter, "close"):
                        legacy_adapter.close()
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
                    gov.with_variable_units(expression_to_load, result),
                    formula_id=result.id,
                    source=formula_source_enum,
                    source_detail=formula_source,
                )
                response["session_loaded"] = load_result.get("success", False)
                response["session_load_result"] = load_result

        return gov.attach_curated(response, formula_id)

    @mcp.tool(meta={"category": "Formula Library"})
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
                       Every variable requires a non-empty ``unit``; use "-" for
                       a dimensionless or unknown quantity. Unit strings that
                       cannot be parsed are kept verbatim with a warning.
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
                "message": "Formula added to local library.",
                "similar_to": [{"id", "name", "tier", "score", "match"}]
            }

            ``similar_to`` appears only when a similar formula already exists.

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
                    "C_d": {"description": "drag coefficient", "unit": "-"},
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
        if variables is None:
            return {
                "success": False,
                "error": "variables must be provided ({} is allowed with no free symbols).",
            }
        unit_error, unit_warnings = gov.validate_add_variables(variables, sympy_str)
        if unit_error:
            return unit_error

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
            gov.persist_entry(entry, library_path)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save formula: {e}",
            }
        return gov.add_response(entry, warnings=unit_warnings, library_path=library_path)

    @mcp.tool(
        meta={
            "category": "Formula Library",
            "example": 'formula_remove("my_formula_id")',
        }
    )
    def formula_remove(formula_id: str) -> dict[str, Any]:
        """Remove a formula from the local library and/or derived store.

        Deletes the user-overlay YAML (written by ``formula_add``) and/or the
        session-derived record (written by ``session_complete`` auto_save).
        Bundled seed entries are read-only and cannot be removed.  Use this to
        clean up unwanted entries — e.g. formulas saved by mistake — which
        otherwise keep surfacing in search and ``derive()`` recommendations.

        Args:
            formula_id: Id of the formula to remove.

        Returns:
            Which stores the entry was removed from.
        """
        if not formula_id:
            return {"success": False, "error": "formula_id is required."}

        removed_from: list[str] = []

        try:
            # Catalog removes the YAML file and the index row; map index tiers
            # back to the store names this tool has always reported.
            tier_names = {"curated": "library", "staging": "derived"}
            removed_from.extend(
                tier_names[t] for t in get_catalog().remove_entry(formula_id)
            )
        except Exception as e:
            return {"success": False, "error": f"Failed to open local library: {e}"}

        try:
            repo = get_repository()
            if repo.get(formula_id) is not None:
                repo.delete(formula_id, delete_file=True)
                if "derived" not in removed_from:
                    removed_from.append("derived")
        except Exception as e:
            return {"success": False, "error": f"Failed to remove derived entry: {e}"}

        if not removed_from:
            return {
                "success": False,
                "error": f"Formula '{formula_id}' not found (or is a read-only seed).",
            }

        return {
            "success": True,
            "formula_id": formula_id,
            "removed_from": removed_from,
            "message": f"Formula removed from: {', '.join(removed_from)}.",
        }

    @mcp.tool(meta={"category": "Formula Library"})
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
                    legacy_adapter = _get_legacy_adapter(legacy)
                    categories[legacy] = legacy_adapter.list_categories()
                    if hasattr(legacy_adapter, "close"):
                        legacy_adapter.close()
                except Exception:
                    categories[legacy] = []

        return {
            "success": True,
            "categories": categories,
        }

    @mcp.tool(meta={"category": "Formula Library"})
    def formula_promote(
        formula_id: str,
        new_id: str | None = None,
        name: str | None = None,
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        domain: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Promote a staging (session-derived) formula into the curated tier.

        Moves the YAML record from the derived store into the curated library,
        applying any metadata overrides, so the entry ranks above staging copies
        in search results. Seed entries are read-only and cannot be promoted.
        ``verified`` means the step verifier ran; ``curated`` means a human
        explicitly promoted the entry into the curated tier.

        Args:
            formula_id: Id of the staging formula to promote.
            new_id: Optional clean identifier (default: slug from the name).
            name: Optional new display name.
            aliases: Optional alias list (add Chinese aliases here).
            tags: Optional tag list.
            description: Optional description override.
            domain: Optional domain override.
            category: Optional category override.

        Returns:
            {"success": true, "formula_id": ..., "tier": "curated",
             "curated": true, "file_path": ...}

        Example:
            formula_promote("pendulum-9f3a2c", new_id="pendulum_period",
                            aliases=["单摆周期"])
        """
        try:
            promoted = get_catalog().promote(
                formula_id,
                new_id=new_id,
                name=name,
                aliases=aliases,
                tags=tags,
                description=description,
                domain=domain,
                category=category,
            )
        except ValueError as e:
            return {"success": False, "error": str(e), "formula_id": formula_id}
        except Exception as e:
            return {"success": False, "error": f"Promote failed: {e}"}

        return {
            "success": True,
            "formula_id": promoted.id,
            "tier": promoted.tier,
            "curated": promoted.curated,
            "file_path": promoted.source_path,
            "message": f"Formula promoted to curated tier as '{promoted.id}'.",
        }

    @mcp.tool(meta={"category": "Formula Library"})
    def formula_reindex() -> dict[str, Any]:
        """Rebuild the formula index from the YAML layers.

        The index normally stays in sync automatically (writes update it
        immediately; startup reconciles changed files). Use this after editing
        formula YAML files by hand to force a full rebuild without restarting
        the server.

        Returns:
            {"success": true, "added": n, "updated": n, "removed": n,
             "failed": n, "stats": {...}}
        """
        try:
            report = get_catalog().reindex()
        except Exception as e:
            return {"success": False, "error": f"Reindex failed: {e}"}
        return {
            "success": True,
            "added": report.added,
            "updated": report.updated,
            "removed": report.removed,
            "failed": report.failed,
            "failed_paths": report.failed_paths,
            "stats": get_catalog().stats(),
        }

    @mcp.tool(meta={"category": "Formula Library"})
    def formula_stats() -> dict[str, Any]:
        """Report formula library statistics.

        Returns per-tier entry counts (seed / staging / curated), duplicate
        groups collapsed by content hash, alpha-invariant structural duplicate
        groups, the index file location, and the last sync time.

        Returns:
            {"success": true, "total": n, "tiers": {"seed": n, ...},
             "duplicate_groups": n, "duplicate_entries": n,
             "structural_duplicate_groups": n,
             "index_path": "...", "last_sync": "..."}
        """
        try:
            stats = get_catalog().stats()
        except Exception as e:
            return {"success": False, "error": f"Stats failed: {e}"}
        return {
            "success": True,
            "total": stats["total"],
            "tiers": stats["tiers"],
            "duplicate_groups": stats["duplicate_groups"],
            "duplicate_entries": stats["duplicate_entries"],
            "structural_duplicate_groups": stats["structural_duplicate_groups"],
            "index_path": stats["path"],
            "last_sync": stats["last_sync"],
        }

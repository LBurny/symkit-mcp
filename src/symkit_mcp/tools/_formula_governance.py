"""Write-path governance helpers for the formula tools (Wave C2).

The MCP write paths (``formula_add``, ``session_complete(auto_save=True)``)
must enforce unit metadata and surface near-duplicate formulas. That logic
lives here rather than in ``formula.py``/``session.py`` because those modules
are frozen by the modularity ratchet (they may only shrink); this private
module is the MCP-side glue over ``FormulaCatalog`` and ``parse_unit``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from symkit.domain.formula_library import FormulaLibrary
from symkit.domain.units import parse_unit
from symkit_mcp.tools import _library_gate
from symkit_mcp.tools._state import get_catalog

if TYPE_CHECKING:
    from symkit.domain.formula_library import FormulaEntry

# Explicit sentinel meaning "no unit / unknown"; accepted by formula_add.
UNKNOWN_UNIT = "-"


def validate_add_variables(
    variables: dict[str, dict[str, Any]],
    sympy_str: str = "",
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate per-variable units for ``formula_add``.

    Returns ``(error_response, warnings)``. ``error_response`` is ``None`` when
    every variable carries a non-empty unit; the explicit ``"-"`` sentinel is
    accepted, while a missing or empty ``unit`` is rejected. Unit strings that
    ``parse_unit`` cannot interpret produce a warning but do not block the
    write (unit strings are display-oriented).

    When ``sympy_str`` is given, the declared units are also run through the
    dimensional gate (r19 F6): an expression that decisively contradicts its own
    units is rejected instead of being written as if curated.
    """
    missing = sorted(
        name
        for name, meta in variables.items()
        if not str((meta or {}).get("unit", "") or "").strip()
    )
    if missing:
        return (
            {
                "success": False,
                "error": (
                    'Every variable needs a unit; use "-" for a dimensionless or '
                    "unknown quantity. Missing unit for: " + ", ".join(missing)
                ),
            },
            [],
        )
    if sympy_str:
        dimension_error = _library_gate.formula_dimension_error(sympy_str, variables)
        if dimension_error is not None:
            return {"success": False, "error": dimension_error}, []
    return None, _unit_warnings(variables)


def backfill_loaded_formula_units(session: Any, formula_id: str | None) -> None:
    """Restore a library formula's declared units on a loaded session record.

    ``session_load_formula`` only receives the expression string, so
    ``FormulaParser`` rebuilt the variables with ``unit=None`` even though the
    library YAML carries units: the completion response's ``formulas_used``
    then showed ``"unit": null`` for a formula that plainly declares them
    (r19 F7).  Existing units (the ``formula_get`` path) are never overwritten.
    """
    if not formula_id:
        return
    formula = session.formulas.get(formula_id)
    if formula is None:
        return
    try:
        entry = get_catalog().get(formula_id)
    except Exception:
        return
    declared = getattr(entry, "variables", None) or {}
    for name, variable in formula.variables.items():
        if getattr(variable, "unit", None):
            continue
        unit = str((declared.get(name) or {}).get("unit") or "").strip()
        if unit and unit != UNKNOWN_UNIT:
            variable.unit = unit


def _unit_warnings(variables: dict[str, dict[str, Any]]) -> list[str]:
    """Warn about unit strings that are neither ``"-"`` nor parseable."""
    unparsed = sorted(
        name
        for name, meta in variables.items()
        if (unit := str((meta or {}).get("unit", "") or "").strip())
        and unit != UNKNOWN_UNIT
        and parse_unit(unit) is None
    )
    if not unparsed:
        return []
    return [
        "Could not interpret unit(s) for: "
        + ", ".join(unparsed)
        + ". They are kept verbatim and treated as unknown."
    ]


def persist_entry(entry: FormulaEntry, library_path: str | None) -> None:
    """Write ``entry`` to a custom library path or the shared catalog."""
    if library_path:
        # Custom directory: write the YAML only; it is not part of the default
        # indexed library.
        FormulaLibrary(library_path).add_or_update(entry)
    else:
        get_catalog().add_entry(entry)


def with_variable_units(expression: str, formula: Any) -> str | dict[str, Any]:
    """Pair a loaded expression with the variable units the library declares.

    ``formula_get(load_into_session=True)`` used to hand only the expression
    string to ``session.load_formula``, so a curated formula's per-variable
    ``unit`` metadata — which ``formula_get`` itself displays — never reached
    the dimension checker: the documented unit source "the unit declared on
    each loaded formula's variables" was unreachable from the MCP surface.
    ``session.load_formula`` accepts a dict, which is how the domain API has
    always carried them.
    """
    variables = getattr(formula, "variables", None) or {}
    if not variables:
        return expression
    return {"expression": expression, "variables": variables}


def add_response(
    entry: FormulaEntry,
    *,
    warnings: list[str],
    library_path: str | None,
) -> dict[str, Any]:
    """Build a ``formula_add`` success payload.

    Adds ``warnings`` for unparseable units, the custom-``library_path``
    advisory, and ``similar_to`` when the catalog knows near-duplicates.
    """
    response: dict[str, Any] = {
        "success": True,
        "formula_id": entry.id,
        "file_path": str(entry.source_path) if entry.source_path else None,
        "message": "Formula added to local library.",
    }
    if warnings:
        response["warnings"] = warnings
    if library_path:
        response["warning"] = (
            "Saved to a custom library_path; not visible in the default "
            "indexed library."
        )
    similar = similar_to(entry.sympy_str, entry.id)
    if similar:
        response["similar_to"] = similar
    return response


def similar_to(
    expression_str: str, exclude_id: str | None
) -> list[dict[str, Any]]:
    """Return similar indexed formulas, or ``[]`` when the lookup fails."""
    try:
        return get_catalog().find_similar(expression_str, exclude_id=exclude_id)
    except Exception:
        return []


def attach_curated(
    response: dict[str, Any], formula_id: str
) -> dict[str, Any]:
    """Expose the ``curated`` flag on a local ``formula_get`` payload."""
    formula = response.get("formula")
    if not isinstance(formula, dict) or formula.get("source") != "local":
        return response
    try:
        indexed = get_catalog().get(formula_id)
    except Exception:
        return response
    if indexed is not None:
        formula["curated"] = indexed.curated
    return response


def build_auto_variables(
    expression: Any, session: Any
) -> dict[str, dict[str, str]]:
    """Auto-save variables with units backfilled from the session context.

    Priority: the session's aggregated unit map (registry + loaded-formula
    variables) first, falling back to the ``"-"`` unknown sentinel -- never an
    empty string.
    """
    from symkit_mcp.tools._unit_context import collect_unit_map

    unit_map = collect_unit_map(session)
    return {
        str(symbol): {
            "description": "",
            "unit": unit_map.get(str(symbol), UNKNOWN_UNIT),
        }
        for symbol in expression.free_symbols
    }

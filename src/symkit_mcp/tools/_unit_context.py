"""Unit-context aggregation and dimension-check wiring for the MCP layer.

The domain owns dimensional analysis (``symkit.domain.dimensional_analysis``);
this private module is the MCP-side glue: it collects the unit information a
session already knows about (``SymbolRegistry`` default units and the units
declared on loaded-formula variables), runs the ``dimension`` math operation,
and post-processes step/session verification with ``apply_dimension_check``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from symkit.domain.derivation_session import OperationType, StepStatus
from symkit.domain.dimensional_analysis import (
    apply_dimension_check,
    check_expression_dimensions,
    describe_dimension,
    expression_dimension,
)
from symkit.domain.expression_parser import parse_user_expression
from symkit.domain.step_verifier import (
    verification_result_from_json,
    verification_result_to_json,
)
from symkit.domain.symbol_registry import SymbolScope
from symkit.domain.units import parse_unit
from symkit.domain.value_objects import VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from symkit.domain.derivation_session import DerivationSession


def collect_unit_map(session: DerivationSession | None) -> dict[str, str]:
    """Merge the session's *explicit* unit declarations, weakest source first.

    Unit information comes from exactly three explicit sources:

    1. the ``units=`` argument of a ``math("dimension", ...)`` call (applied on
       top of this map by :func:`dimension_operation`);
    2. ``register_symbol(name, unit=...)`` — ``USER`` scope;
    3. the ``unit`` declared on each loaded formula's variables.

    Built-in ``GLOBAL``/``DOMAIN`` registry entries are semantic catalogue hints
    (``k`` → rate constant ``1/h``, ``p`` → pressure ``Pa``, ``rho`` → density),
    not declarations about this derivation.  Consuming them assigned units to
    ordinary unregistered symbols by name collision and failed physically
    correct steps (task-09: ``k = pi/L`` judged inconsistent because ``k``
    inherited the pharmacokinetics default).  A symbol without an explicit
    declaration is unknown, never dimensioned by default.
    """
    units: dict[str, str] = {}
    if session is None:
        return units
    registry = getattr(session, "symbol_registry", None)
    if registry is not None:
        for semantics in registry.list_symbols():
            if not semantics.default_unit:
                continue
            if semantics.scope in (SymbolScope.USER, SymbolScope.SESSION):
                # Later registrations supersede earlier ones for the same name.
                units[semantics.name] = semantics.default_unit
    for formula in session.formulas.values():
        for name, variable in formula.variables.items():
            if variable.unit:
                units[name] = variable.unit
    return units


def dimension_operation(
    expr_str: str,
    explicit_units: dict[str, str] | None,
    session: DerivationSession | None,
) -> dict[str, Any]:
    """Run the ``dimension`` math operation and shape its result dict."""
    expr, error = parse_user_expression(expr_str, convert_equation=True)
    if expr is None:
        return {"success": False, "error": f"Cannot parse expression: {error}"}
    unit_map = collect_unit_map(session)
    if explicit_units:
        unit_map.update({name: unit for name, unit in explicit_units.items() if unit})
    report = check_expression_dimensions(expr, unit_map)
    result_dim = expression_dimension(expr, unit_map)
    message = _dimension_message(report, bool(unit_map))
    if unit_map and result_dim is not None:
        message = (
            f"{message} {expr_str} has net dimension: "
            f"{describe_dimension(result_dim)}."
        )
    return {
        "success": True,
        "operation": "dimension",
        "consistent": report.consistent,
        "dimensionless": report.consistent is True and result_dim == {},
        "result_dimension": result_dim,
        "dimensions": report.dimensions,
        "issues": report.issues,
        "unknown_symbols": report.unknown_symbols,
        "units": unit_map,
        "message": message,
    }


def _dimension_message(report: Any, has_units: bool) -> str:
    if not has_units:
        return (
            "No unit information available (pass units=..., load a formula "
            "with units, or register_symbol(unit=...)); nothing to check."
        )
    if report.consistent is False:
        return "Dimensional analysis found inconsistencies."
    if report.consistent is None:
        reasons = getattr(report, "indeterminate_reasons", []) or []
        if "derivative" in reasons:
            declared = (
                f" for {', '.join(report.unknown_symbols)}"
                if report.unknown_symbols
                else ""
            )
            return (
                "Dimensional analysis inconclusive: the expression contains a "
                f"derivative; declare units{declared} via register_symbol so "
                "dim(dF/dt) can be reduced."
            )
        if report.unknown_symbols:
            return (
                "Dimensional analysis incomplete: some symbols have unknown units "
                f"({', '.join(report.unknown_symbols)})."
            )
        return (
            "Dimensional analysis inconclusive: this expression uses a form the "
            "checker cannot reduce (for example a dimensioned base with a "
            "non-integer exponent)."
        )
    return "Expression is dimensionally consistent."


def with_unit_warnings(
    session: DerivationSession, result: dict[str, Any]
) -> dict[str, Any]:
    """Append warnings for loaded-formula units that ``parse_unit`` rejects."""
    formula_id = result.get("formula_id")
    formula = session.formulas.get(formula_id) if formula_id else None
    if formula is None:
        return result
    unparsed = sorted(
        name
        for name, variable in formula.variables.items()
        if variable.unit and parse_unit(variable.unit) is None
    )
    if unparsed:
        result.setdefault("warnings", []).append(
            "Could not interpret unit(s) for: "
            + ", ".join(unparsed)
            + ". They are kept verbatim and treated as unknown."
        )
    return result


def verify_step_with_dimensions(
    session: DerivationSession, step_number: int
) -> dict[str, Any]:
    """``session.verify_step`` plus a dimensional post-check when units exist."""
    payload = session.verify_step(step_number)
    if not payload.get("success"):
        return payload
    unit_map = collect_unit_map(session)
    if not unit_map:
        return payload
    record = apply_dimension_to_step(session, step_number, unit_map)
    if record is None:
        return payload
    step = session.steps[step_number - 1]
    payload.update(
        {
            "status": step.status.value,
            "verification_status": record.status.value,
            "verification_message": record.message,
            "verification": record.details,
            "step": step.to_dict(),
        }
    )
    return payload


def apply_dimension_checks(session: DerivationSession) -> None:
    """Apply the dimensional post-check to every archived step, in place."""
    unit_map = collect_unit_map(session)
    if unit_map:
        for step in session.steps:
            apply_dimension_to_step(session, step.step_number, unit_map)


def apply_dimension_to_step(
    session: DerivationSession, step_number: int, unit_map: dict[str, str]
) -> VerificationResult | None:
    """Re-run the dimensional post-check on one archived step, in place.

    Mirrors :meth:`StepVerifier.verify_step`'s input/output reconstruction so
    the post-check sees exactly the expressions the algebraic check saw. Returns
    the updated result, or ``None`` when the step has no verification record or
    its expressions cannot be rebuilt.
    """
    step = session.steps[step_number - 1]
    if not step.verification_result:
        return None
    # Ratchet constraint: derivation_session.py/step_verifier.py are frozen
    # (may only shrink), so the parse entry points stay private; promote them
    # to public methods when those files are next split.
    assumptions = session.assumption_engine.get_assumptions()
    if step.operation == OperationType.CUSTOM:
        # A manually recorded step asserts one result. Its archived
        # input_srepr holds the *previous* step's expression (that is how
        # _add_step defaults it), so reading it here judged the wrong
        # formula and failed correct steps.
        input_expr = None
    else:
        input_expr = session.verifier._parse_step_input(step, assumptions)
        if input_expr is None:
            input_expr = session._resolve_prior_expr(step_number)
    output_expr = session.verifier._parse_archived(
        step.output_expression, step.output_srepr, assumptions
    )
    if output_expr is None or (input_expr is None and step.operation != OperationType.CUSTOM):
        return None
    record = verification_result_from_json(step.verification_result)
    updated = apply_dimension_check(record, input_expr, output_expr, unit_map)
    step.verification_result = verification_result_to_json(updated)
    if updated.status == VerificationStatus.VERIFIED:
        step.status = StepStatus.SUCCESS
    elif updated.status == VerificationStatus.INCONCLUSIVE:
        step.status = StepStatus.PENDING_VERIFICATION
    else:
        step.status = StepStatus.FAILED
    session._update_timestamp()
    if session._persist_path:
        session.save()
    return updated

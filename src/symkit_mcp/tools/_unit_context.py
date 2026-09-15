"""Unit-context aggregation and dimension-check wiring for the MCP layer.

The domain owns dimensional analysis (``symkit.domain.dimensional_analysis``);
this private module is the MCP-side glue: it collects the unit information a
session already knows about (``SymbolRegistry`` default units and the units
declared on loaded-formula variables), runs the ``dimension`` math operation,
and post-processes step/session verification with ``apply_dimension_check``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from symkit.domain.derivation_session import OperationType, StepStatus
from symkit.domain.dimensional_analysis import (
    apply_dimension_check,
    check_expression_dimensions,
    describe_dimension,
    expression_dimension,
)
from symkit.domain.expression_parser import parse_user_expression
from symkit.domain.math_domain import MathDomain
from symkit.domain.step_verifier import (
    verification_result_from_json,
    verification_result_to_json,
)
from symkit.domain.symbol_registry import SymbolScope
from symkit.domain.units import is_dimensionless_marker, parse_unit
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
    # Weakest source first, so later writes win: a library formula's bundled
    # unit (3) is catalogue metadata, while a ``register_symbol`` declaration
    # (2) is a deliberate statement about *this* derivation and must outrank it.
    for formula in session.formulas.values():
        for name, variable in formula.variables.items():
            if variable.unit:
                units[name] = variable.unit
    registry = getattr(session, "symbol_registry", None)
    if registry is not None:
        for semantics in registry.list_symbols():
            if not semantics.default_unit:
                continue
            if semantics.scope in (SymbolScope.USER, SymbolScope.SESSION):
                # Later registrations supersede earlier ones for the same name.
                units[semantics.name] = semantics.default_unit
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
    # Only claim a net dimension for an expression the checker did not already
    # call inconsistent: "found inconsistencies ... has net dimension:
    # dimensionless" reads as one sentence contradicting itself.
    if unit_map and result_dim is not None and report.consistent is True:
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
    # ``-1`` means "the last step"; use the number the verifier resolved so the
    # post-check judges the same step the payload describes.
    resolved = payload.get("step_number") or step_number
    is_dimension_step = _recorded_dimension_step(session.steps[resolved - 1])[0]
    unit_map = collect_unit_map(session)
    if not unit_map and not is_dimension_step:
        return payload
    record = apply_dimension_to_step(session, resolved, unit_map)
    if record is None:
        return payload
    step = session.steps[resolved - 1]
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


def _has_recorded_dimension_step(session: DerivationSession) -> bool:
    return any(_recorded_dimension_step(step)[0] for step in session.steps)


def apply_dimension_checks(session: DerivationSession) -> list[int]:
    """Apply the dimensional post-check to every archived step, in place.

    Returns the step numbers whose dimensional verdict came back ``None``: the
    check ran (units are declared) but reached no conclusion. A recorded
    ``dimension`` step is reported from its own record, so it is processed even
    when the session declares no units — the call may have passed them directly.
    """
    inconclusive: list[int] = []
    unit_map = collect_unit_map(session)
    if not unit_map and not _has_recorded_dimension_step(session):
        return inconclusive
    for step in session.steps:
        record = apply_dimension_to_step(session, step.step_number, unit_map)
        if record is not None and record.dimension_check is None:
            inconclusive.append(step.step_number)
    return inconclusive


def declaration_warning(domain: str, unit: str | None) -> str | None:
    """Advisory for a ``register_symbol`` declaration that will not behave as
    written: an unknown domain, or a unit string the parser cannot read.

    ``formula_add`` already warned about unreadable units; the registry took
    them silently, so ``register_symbol(unit="dB")`` succeeded with no warning
    and the symbol quietly counted as unknown in every later check.
    """
    try:
        MathDomain(domain.lower().replace(" ", "_"))
    except ValueError:
        return (
            f"'{domain}' is not a built-in domain; stored verbatim as a "
            "custom domain."
        )
    if unit and not is_dimensionless_marker(unit) and parse_unit(unit) is None:
        return (
            f"Unit {unit!r} could not be interpreted; it is kept verbatim and "
            "this symbol counts as unknown in dimensional checks."
        )
    return None


def persist_declaration(session: DerivationSession) -> None:
    """Write a session out after a symbol/unit declaration.

    A declaration is session state. Relying on some later step to save the
    session meant a restart right after declaring units resumed a session that
    knew none of them (30 declarations, no steps, fresh process).
    """
    if session._persist_path:  # noqa: SLF001 - mirrors apply_dimension_to_step
        session.save()


def summary_with_dimension_disclosure(session: DerivationSession) -> dict[str, Any]:
    """``session.verify_derivation()`` with the dimensional post-check folded in.

    The post-check runs over the archived steps first, the summary is built from
    the resulting verdicts, and any step whose dimensional check reached no
    conclusion is disclosed. ``overall`` only ever reflects the *algebraic*
    checks, so without this disclosure a chain whose units were half declared
    reported a bare ``overall: verified`` and the caller had no way to tell that
    dimensional checking never concluded — the very thing the server advertises.
    """
    inconclusive = apply_dimension_checks(session)
    summary = session.verify_derivation()
    if inconclusive:
        summary["dimension_inconclusive_steps"] = inconclusive
        summary.setdefault("warnings", []).append(
            "Dimensional analysis reached no conclusion for steps "
            f"{inconclusive} (symbol units missing or unreadable); "
            "'overall' reflects the algebraic checks only."
        )
    return summary


def _recorded_dimensions(step: Any) -> dict[str, Any]:
    """Per-symbol dimensions from the step's own provenance record."""
    raw = (step.input_expressions or {}).get("dimensions")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _recorded_dimension_step(step: Any) -> tuple[bool, bool | None]:
    """``(is_a_recorded_dimension_step, the verdict it already carries)``."""
    inputs = step.input_expressions or {}
    if inputs.get("operation") != "dimension":
        return False, None
    return True, {"True": True, "False": False}.get(str(inputs.get("consistent")), None)


# A recorded ``dimension`` step is itself a verdict, so it gets its own message
# rather than the generic "no automatic verification available".
_DIMENSION_STEP_MESSAGES: dict[bool | None, str] = {
    True: "Recorded dimension check: the expression is dimensionally consistent",
    False: "Recorded dimension check: the expression is dimensionally inconsistent",
    None: "Recorded dimension check: consistency could not be determined",
}


def _apply_recorded_dimension_step(
    session: DerivationSession, step: Any, recorded: bool | None
) -> VerificationResult:
    """Report a recorded ``dimension`` step from its own verdict.

    Such a step *is* a dimensional verdict, so re-judging it against the session
    unit map produced two defects: it contradicted the step whenever the call
    passed ``units=`` explicitly (the details claimed "x unknown" for a step
    that had resolved temperature), and an expression the tool had just called
    inconsistent sat in the chain looking unexamined.
    """
    record = verification_result_from_json(step.verification_result)
    dimensions = _recorded_dimensions(step)
    return _commit(
        session,
        step,
        VerificationResult(
            status={
                True: VerificationStatus.VERIFIED,
                False: VerificationStatus.FAILED,
                None: VerificationStatus.INCONCLUSIVE,
            }[recorded],
            message=_DIMENSION_STEP_MESSAGES[recorded],
            details={"dimensions": dimensions} if dimensions else {},
            dimension_check=recorded,
            reverse_check=record.reverse_check,
            boundary_check=record.boundary_check,
        ),
    )


def _commit(session: DerivationSession, step: Any, updated: VerificationResult) -> VerificationResult:
    """Store an updated verdict on the step, sync its status and persist."""
    step.verification_result = verification_result_to_json(updated)
    if updated.status == VerificationStatus.VERIFIED:
        step.status = StepStatus.SUCCESS
    elif updated.status == VerificationStatus.INCONCLUSIVE:
        step.status = StepStatus.PENDING_VERIFICATION
    else:
        step.status = StepStatus.FAILED
    session._update_timestamp()  # noqa: SLF001 - mirrors the pre-existing tail
    if session._persist_path:  # noqa: SLF001
        session.save()
    return updated


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
    is_dimension_step, recorded = _recorded_dimension_step(step)
    if is_dimension_step:
        return _apply_recorded_dimension_step(session, step, recorded)
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
    return _commit(session, step, updated)

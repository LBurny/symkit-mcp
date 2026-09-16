"""Recording helpers for the unified ``math()`` tool (bylaw section 5.1 split).

Split out of ``math.py`` so that module stays within the 600-line hard limit
while the recorder gained assumption snapshots and failure traces.  Everything
here is presentation-layer plumbing for the session archive: the operation
semantics live in ``_math_dispatch.py``.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.assumption_engine import AssumptionLevel
from symkit.domain.derivation_session import DerivationStep, OperationType

#: Marker stored in ``input_expressions`` of every note-type step.  The domain's
#: ``is_note_step`` uses it to keep notes out of verification statistics.
NOTE_MARKER = "note_type"


def matrix_input_srepr(input_obj: Any) -> str:
    """Archive a matrix input object's srepr (r19 F26).

    ``DerivationSession._add_step`` only defaults ``input_srepr`` from a
    ``prior_expr`` that is an ``sp.Basic``; a SymPy ``Matrix`` is *not* a Basic,
    so ``inv``/``eigenvals``/matrix-``simplify`` steps archived
    ``input_srepr: ""`` and their reverse verification had no input to check.
    """
    if isinstance(input_obj, sp.MatrixBase):
        return str(sp.srepr(input_obj))
    return ""


def _render_dimension_display(result: dict[str, Any]) -> str:
    """Render the ``dimension`` operation's verdict as display text."""
    status = result.get("consistent")
    if status is True:
        label = "✅ dimensionally consistent"
    elif status is False:
        label = "❌ dimensionally inconsistent"
    else:
        label = "⚠️ dimensionally inconclusive"
    lines = [f"🔹 **DIMENSION** result: {label}"]
    issues = result.get("issues") or []
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    elif result.get("message"):
        lines.append(f"- {result['message']}")
    return "\n".join(lines)


def _sympy_command(
    operation: str,
    variable: str | None,
    order: int,
    lower: str | None,
    upper: str | None,
    point: str | None,
) -> str:
    """A sympy_command string the step verifier can parse."""
    if operation == "diff":
        if order == 1:
            return f"diff(expr, {variable})"
        return f"diff(expr, {variable}, {order})"
    if operation == "integrate":
        if lower is not None and upper is not None:
            return f"integrate(expr, ({variable}, {lower}, {upper}))"
        return f"integrate(expr, {variable})"
    if operation == "limit":
        return f"limit(expr, {variable}, {point or '0'})"
    return f"math('{operation}', ...)"


def session_assumption_strings(sess: Any) -> list[str]:
    """Snapshot the session's own assumptions as human strings (r19 F19).

    Only the ``SESSION`` layer is read: domain defaults are noise in a step
    record and ``assume_for_step`` is scoped to a single step by definition.
    The string convention matches ``assume_for_step`` / step assumptions,
    e.g. ``["t is real", "x is positive"]``.
    """
    try:
        assumptions = sess.assumption_engine.get_assumptions(
            level=AssumptionLevel.SESSION
        )
    except Exception:
        return []
    rendered: list[str] = []
    for name in sorted(assumptions):
        active = [prop for prop, value in assumptions[name].items() if value]
        if active:
            rendered.append(f"{name} is {' '.join(active)}")
    return rendered


def record_failed_operation_note(
    sess: Any, operation: str, error: str
) -> None:
    """Record a failing ``math(session=True)`` call as a note-type step (r19 F10).

    The failed call used to leave no trace, so the chain showed a gap where the
    operator had actually tried something.  The step is marked as a note (the
    ``note_type`` provenance key) and therefore stays out of the verification
    statistics while remaining visible in ``session_get_steps``.
    """
    if sess is None:
        return
    try:
        message = (error or "unknown error").strip()
        step = DerivationStep(
            step_number=len(sess.steps) + 1,
            operation=OperationType.CUSTOM,
            description=f"{operation} failed: {message[:120]}",
            input_expressions={NOTE_MARKER: "failure", "operation": operation},
            output_expression="",
            output_latex="",
            output_srepr="",
            input_srepr="",
            sympy_command="# failed operation (no computation)",
        )
        sess.steps.append(step)
        sess._update_timestamp()
        if sess._persist_path:
            sess.save()
    except Exception:
        # The trace must never turn a reported failure into a crash.
        return

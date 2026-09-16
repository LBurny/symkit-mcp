"""Unified Math Tool — SymKit's core computation tool.

``math()`` is the primary tool LLMs use (33 operations); ``session=True``
records a traceable derivation step while ``session=False`` is stateless. The
dispatcher lives in ``_math_dispatch.py``; this module is the thin wrapper
(parameter plumbing, per-call assumptions, display, session recording).
"""

from __future__ import annotations

import json
from typing import Any

from symkit.domain.assumption_binding import ASSUMPTION_KEYWORDS
from symkit.domain.assumption_engine import AssumptionLevel
from symkit.domain.derivation_session import OperationType
from symkit.domain.value_objects import MathContext
from symkit_mcp.tools._assumption_text import expression_valued_assumption, invalid_clause_message
from symkit_mcp.tools._math_dispatch import (
    _OP_TYPE_MAP,
    _effective_context,
    _execute_operation,
    _preprocess,
    lambda_symbol_warning,
)
from symkit_mcp.tools._math_recording import (
    _render_dimension_display,
    _sympy_command,
    attach_dimension_verdict,
    matrix_input_srepr,
    record_failed_operation_note,
    session_assumption_strings,
)
from symkit_mcp.tools._state import get_context, get_session, set_context


def _parse_assumption_clause(a: str) -> tuple[str, dict[str, bool]] | None:
    """Parse an assumption clause into ``(variable, {prop: True, ...})``.

    Accepts ``"x is positive real"`` and ``"x positive real"``; returns
    ``None`` when the clause is not a symbol-plus-properties clause (caller
    warns) — an expression-valued entry must not be split on whitespace and
    applied as garbage properties (r19 F23).
    """
    parts = a.strip().split()
    properties = (
        parts[2:] if len(parts) >= 3 and parts[1] in ("is", "has") else parts[1:]
    )
    if not parts[0:1] or not parts[0].isidentifier() or not properties:
        return None
    if not all(prop in ASSUMPTION_KEYWORDS for prop in properties):
        return None
    return parts[0], dict.fromkeys(properties, True)


def _normalize_assume_input(
    variables: dict[str, str] | list[str],
) -> dict[str, str]:
    """Accept ``{"x": "positive"}`` and ``["x is positive"]`` clause lists.

    The list form normalizes through the same clause parser ``math`` uses.
    """
    if isinstance(variables, dict):
        return variables
    normalized: dict[str, str] = {}
    for clause in variables:
        match = _parse_assumption_clause(clause)
        if match is None:
            raise ValueError(
                f"Could not parse assumption '{clause}'. Use 'x is positive'."
            )
        var_name, props_dict = match
        normalized[var_name] = " ".join(props_dict)
    return normalized


def _apply_call_assumptions(
    assumptions: list[str] | None, session: bool
) -> tuple[MathContext | None, dict[str, dict[str, bool]], list[str]]:
    """Scope per-call assumptions; ``session=True`` persists them (run-013).

    Session scope reaches the step verifier; session=false is call-local only.
    """
    warnings: list[str] = []
    applied: dict[str, dict[str, bool]] = {}
    if not assumptions:
        return None, applied, warnings
    ctx = get_context()
    for clause_text in assumptions:
        rejected = expression_valued_assumption(clause_text)
        if rejected is not None:
            warnings.append(rejected)
            continue
        clause = _parse_assumption_clause(clause_text)
        if clause is None:
            warnings.append(
                f"Could not parse assumption '{clause_text}'. "
                "Use 'x is positive' or 'x positive'."
            )
            continue
        var_name, props_dict = clause
        ctx = ctx.with_assumption(var_name, **props_dict)
        applied[var_name] = props_dict
    if session:
        set_context(ctx)
        sess = get_session()
        if sess is not None:
            for var_name, props_dict in applied.items():
                sess.assumption_engine.assume(
                    var_name, *props_dict, level=AssumptionLevel.SESSION
                )
    return ctx, applied, warnings


def _step_input_expressions(
    operation: str,
    preprocessed: Any,
    input_obj: Any,
    variable: str | None,
    substitution: dict[str, Any] | None,
    direction: str,
) -> dict[str, str]:
    """Provenance for a recorded step: operation, input, and operation params."""
    input_expressions: dict[str, str] = {
        # A coarse bucket records matrix ops as matrix_op.
        "operation": operation,
        # The submitted string: sympy folds eagerly (``hermite(3, 0.7)`` -> ``-5.656``), so
        # ``str(input_obj)`` loses the provenance (r17 audit6); explicit None check: sympy's 0/false are falsy.
        "original": (preprocessed if isinstance(preprocessed, str)
                     else str(input_obj) if input_obj is not None else ""),
    }
    if operation == "substitute" and substitution:
        input_expressions["replacement"] = ", ".join(
            f"{k} = {v}" for k, v in substitution.items()
        )
        # Machine-readable copy: the human-readable join splits a value with a
        # comma (``Rational(1,6)``, ``Eq(a, b)``) into fragments (task-02 step 23).
        input_expressions["replacement_map"] = json.dumps(
            substitution, ensure_ascii=False
        )
    elif operation == "solve" and variable:
        input_expressions["target_variable"] = variable
    elif operation == "limit":
        # The verifier must probe the side the user actually asked for (P5).
        input_expressions["limit_direction"] = direction
    elif operation == "evalf" and substitution:
        # Without this the numeric anchor is unreplayable: the archived input is
        # the pure symbolic expression and the substituted point is lost
        # (r16 task-01/03/14).
        input_expressions["input_substitution"] = json.dumps(
            substitution, ensure_ascii=False
        )
    return input_expressions


def _record_math_step(
    sess: Any,
    operation: str,
    expression: str,
    preprocessed: Any,
    result: dict[str, Any],
    input_obj: Any,
    result_obj: Any,
    *,
    variable: str | None,
    order: int,
    lower: str | None,
    upper: str | None,
    point: str | None,
    direction: str,
    substitution: dict[str, Any] | None,
    description: str,
    notes: str,
) -> None:
    """Record one successful math() call as a derivation step."""
    try:
        # parse/cancel have exact labels; other operations keep their coarse
        # verification bucket (r16 task-03/15).
        op_type = (
            OperationType(operation)
            if operation in ("parse", "cancel")
            else _OP_TYPE_MAP.get(operation, OperationType.CUSTOM)
        )
        desc = description or f"{operation}: {expression}"
        sess._add_step(
            operation=op_type,
            description=desc,
            input_expressions=_step_input_expressions(
                operation, preprocessed, input_obj, variable, substitution, direction
            ),
            output_expr=result_obj,
            sympy_command=_sympy_command(
                operation, variable, order, lower, upper, point
            ),
            notes=notes,
            # Snapshot the session's assumptions onto the step record (r19 F19):
            # a step archived assumptions=[] although assume(...) was in effect.
            assumptions=session_assumption_strings(sess),
            # The live input object so the step archives an input_srepr and
            # verification never re-parses a display string (invariant I2).
            prior_expr=input_obj,
            input_srepr=matrix_input_srepr(input_obj),
        )
        sess.current_expression = result_obj
        result["step"] = sess.step_count
        result["session_id"] = sess.session_id
    except Exception as exc:
        # Fail loud: recording problems are surfaced to the caller.
        result.setdefault("warnings", []).append(
            f"Step recording failed: {type(exc).__name__}: {exc}"
        )


def _record_dimension_step(
    sess: Any,
    expression: str,
    result: dict[str, Any],
    description: str,
    notes: str,
) -> None:
    """Record a ``dimension`` check: output is the checked expression, and the
    verdict plus per-symbol dimensions go into provenance metadata (r16)."""
    from symkit.domain.expression_parser import parse_user_expression

    expr, _error = parse_user_expression(expression, convert_equation=True)
    if expr is None:
        return
    step = sess._add_step(
        operation=OperationType.CUSTOM,
        description=description or f"dimension: {expression}",
        input_expressions={
            "operation": "dimension",
            "original": expression,
            "consistent": str(result.get("consistent")),
            "dimensions": json.dumps(result.get("dimensions") or {}, ensure_ascii=False),
            # tri-state: "null" (undetermined) must stay distinct from "{}"
            "result_dimension": json.dumps(result.get("result_dimension"), ensure_ascii=False),
        },
        output_expr=expr,
        sympy_command="dimension(expr)",
        notes=notes or str(result.get("message") or ""),
        prior_expr=expr,
    )
    # The verdict the tool just returned belongs on the step now, not after the
    # next verify pass (r20 W2).
    attach_dimension_verdict(sess, step, result)
    result["step"] = sess.step_count
    result["session_id"] = sess.session_id


def _record_step_if_possible(
    operation: str,
    expression: str,
    preprocessed: Any,
    result: dict[str, Any],
    input_obj: Any,
    result_obj: Any,
    *,
    variable: str | None,
    order: int,
    lower: str | None,
    upper: str | None,
    point: str | None,
    direction: str,
    substitution: dict[str, Any] | None,
    description: str,
    notes: str,
) -> None:
    """Record a successful math() call to the current session when possible."""
    sess = get_session()
    if sess is None:
        from symkit_mcp.tools.session import _flag_unrecorded_math_step
        return _flag_unrecorded_math_step(result)
    if operation == "dimension":
        _record_dimension_step(sess, expression, result, description, notes)
    elif result_obj is not None:
        _record_math_step(
            sess, operation, expression, preprocessed, result, input_obj, result_obj,
            variable=variable, order=order, lower=lower, upper=upper, point=point,
            direction=direction, substitution=substitution,
            description=description, notes=notes,
        )


def register_math_tools(mcp: Any) -> None:
    """Register the unified math() tool and supporting tools."""

    @mcp.tool(
        meta={
            "category": "Unified Math",
            "example": "math('diff', 'x**3', variable='x')",
        }
    )
    def math(
        operation: str,
        expression: str,
        variable: str | None = None,
        with_respect_to: str | None = None,
        substitution: dict[str, Any] | None = None,
        point: str | None = None,
        direction: str = "+-",
        order: int = 1,
        lower: str | None = None,
        upper: str | None = None,
        assumptions: list[str] | None = None,
        method: str = "auto",
        ics: dict[str, str] | None = None,
        units: dict[str, str] | None = None,
        session: bool = True,
        description: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """
        Run mathematical operations (unified Mathematica-style tool).

        SymKit's core tool: one entry point for the 33 operations below,
        covering derivation, calculation, solving, and transformation.

        **Supported operations (operation):**

        | Category | Operation | Description |
        |------|------|------|
        | Parse | `parse` | Parse expression and extract symbols |
        | Numeric | `evalf` | Numeric floating-point evaluation |
        | Dimension | `dimension` | Check dimensional consistency (units optional) |
        | Simplify | `simplify` | General simplification |
        | | `expand` | Expand polynomial |
        | | `factor` | Factorization |
        | | `collect` | Collect like terms (requires variable) |
        | | `cancel` | Cancel rational function |
        | | `apart` | Partial fraction expansion (requires variable) |
        | | `together` | Combine over common denominator |
        | | `trigsimp` | Trigonometric simplification |
        | | `powsimp` | Power simplification |
        | | `radsimp` | Radical simplification |
        | | `combsimp` | Combinatorial simplification |
        | Solve | `solve` | Solve for variable (requires variable) |
        | Substitute | `substitute` | Substitute variables (requires substitution dict) |
        | Calculus | `diff` | Differentiate (requires variable; order optional) |
        | | `integrate` | Integrate (variable, lower/upper optional) |
        | | `limit` | Limit (variable, point, direction) |
        | | `series` | Series expansion (variable, point, order) |
        | ODE | `dsolve` | Solve ODE (variable=function name, with_respect_to=independent variable; ics optional) |
        | Vector | `gradient` | Gradient (variable="x,y,z" comma-separated coordinates) |
        | | `divergence` | Divergence |
        | | `curl` | Curl |
        | | `laplacian` | Laplacian |
        | Matrix | `det` | Determinant |
        | | `inv` | Inverse matrix |
        | | `eigenvals` | Eigenvalues |
        | | `eigenvects` | Eigenvectors |
        | Transform | `laplace` | Laplace transform (variable=time, with_respect_to=s) |
        | | `ilaplace` | Inverse Laplace transform (variable=s, with_respect_to=t) |
        | | `fourier` | Fourier transform |
        | | `ifourier` | Inverse Fourier transform |

        Args:
            operation: Operation name (see table above)
            expression: Mathematical expression (SymPy or LaTeX format)
            variable: Differentiation/integration/solving variable (for vector operations can be comma-separated like "x,y,z")
            with_respect_to: Second variable (independent variable for ODE, target variable for transforms)
            substitution: Substitution mapping {"var": "replacement", ...}
            point: Limit point / series expansion point (default "0")
            direction: Limit direction "+-", "+", "-"
            order: Differentiation order / number of series terms (default 1)
            lower: Definite integral lower bound
            upper: Definite integral upper bound
            assumptions: Symbolic assumptions ["x is positive", "t is real"].
                With session=true they persist for the session (visible to the
                step verifier); with session=false they apply to this call only.
                Use assume() for cross-session globals, unassume() to remove.
            method: Simplification method "auto", "trig", "radical", "expand_then_simplify"
            ics: Initial conditions for dsolve {"V(0)": "V_0"} — keys are the
                dependent function applied to a point, values are expressions
            units: Unit mapping for the `dimension` operation {"rho": "kg/m^3"}.
                Explicit units take priority over session formula units and
                registered symbol default units.
            session: True=record to derivation session, False=stateless computation
            description: Description of this step (used when recording to session)
            notes: Human insight (used when recording to session)

        Returns:
            Result dict containing expression, latex, operation

        Examples:
            # Stateless quick calculation
            math("diff", "x**3", variable="x")
            → {"expression": "3*x**2", "latex": "3 x^{2}"}

            # Substitute
            math("substitute", "m*a", substitution={"m": "2", "a": "9.8"})
            → {"expression": "19.6", ...}

            # Laplace transform
            math("laplace", "exp(-k*t)", variable="t", with_respect_to="s")
            → {"expression": "1/(k + s)", ...}

            # Solve ODE
            math("dsolve", "diff(y,t) - k*y", variable="y", with_respect_to="t")
            math("dsolve", "dy/dt - k*y", variable="y", with_respect_to="t",
                 ics={"y(0)": "y_0"})
        """
        preprocessed = _preprocess(expression)
        lambda_warning = lambda_symbol_warning(expression)

        # Per-call assumption scoping (see _apply_call_assumptions).
        (
            call_context,
            applied_assumptions,
            assumption_warnings,
        ) = _apply_call_assumptions(assumptions, session)

        # Execute the operation
        try:
            result = _execute_operation(
                operation, expression,
                variable=variable,
                with_respect_to=with_respect_to,
                substitution=substitution,
                point=point,
                direction=direction,
                order=order,
                lower=lower,
                upper=upper,
                method=method,
                ics=ics,
                units=units,
                assumption_context=call_context,
            )
        except Exception as exc:  # an internal failure is still a tool result
            result = {
                "success": False,
                "error": f"Operation '{operation}' failed: {type(exc).__name__}: {exc}",
            }

        if applied_assumptions:
            result["assumptions_applied"] = {
                var: [p for p, v in props.items() if v]
                for var, props in applied_assumptions.items()
            }

        # Internal live SymPy objects: consumed for session recording below,
        # never leaked to the MCP client.
        input_obj = result.pop("_input_obj", None)
        result_obj = result.pop("_result_obj", None)

        if assumption_warnings:
            result["assumption_warnings"] = list(assumption_warnings)
            result.setdefault("warnings", []).extend(assumption_warnings)
        # G10: disclose the assumption set the call actually ran under. Session
        # assumptions persist and silently shape later results, so the merged
        # view is reported and names not passed this call are marked.
        effective = _effective_context(call_context).assumptions
        if effective:
            result["assumptions_effective"] = {
                name: sorted(p for p, on in props.items() if on)
                for name, props in effective.items()
            }
            if (names := sorted(set(effective) - set(applied_assumptions))):
                result["assumptions_from_session"] = names
        if lambda_warning:
            result.setdefault("warnings", []).append(lambda_warning)

        # Build display text
        if result["success"]:
            if operation == "dimension":
                display = _render_dimension_display(result)
            else:
                display = (
                    f"🔹 **{operation.upper()}** result:\n\n"
                    f"$${result.get('latex', '')}$$"
                )
            result["display_text"] = display

            # Record to derivation session if requested
            if session:
                _record_step_if_possible(
                    operation, expression, preprocessed, result,
                    input_obj, result_obj,
                    variable=variable, order=order, lower=lower, upper=upper,
                    point=point, direction=direction, substitution=substitution,
                    description=description, notes=notes,
                )
        else:
            result["display_text"] = f"❌ **{operation}** failed: {result.get('error', 'unknown')}"
            # A failed attempt must not vanish from the chain (r19 F10): record
            # a note-type trace so the gap is visible and attributable.
            if session:
                record_failed_operation_note(
                    get_session(), operation, str(result.get("error", ""))
                )

        return result

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": 'assume({"x": "positive", "t": "real"})',
        }
    )
    def assume(variables: dict[str, str] | list[str]) -> dict[str, Any]:
        """
        Set symbolic assumptions (affecting subsequent math() calculations)

        Assumptions are recorded in MathContext and passed to SymPy, and also written
        to the current session's multi-level assumption engine (session level).

        Args:
            variables: Mapping from variable to properties
                       e.g., {"x": "positive real", "n": "integer"} — or the
                       clause-list form math()/assume_for_step() use:
                       ["x is positive real", "n is integer"]

        Returns:
            All current assumptions

        Example:
            assume({"x": "positive", "t": "real"})
            assume(["x is positive"])
            # Afterwards, math("simplify", "sqrt(x**2)") returns x instead of Abs(x)
        """
        try:
            variables = _normalize_assume_input(variables)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        # An assumption that can never take effect (a pseudo-property, or a key
        # that is an expression rather than a symbol) must not be applied (r20 W2).
        if (invalid := invalid_clause_message(variables)) is not None:
            return {"success": False, "error": invalid}
        ctx = get_context()
        for var, props_str in variables.items():
            props = {}
            for p in props_str.strip().split():
                props[p] = True
            ctx = ctx.with_assumption(var, **props)
        set_context(ctx)

        # Also record in session-level assumption engine if a session exists
        sess = get_session()
        if sess is not None:
            for var, props_str in variables.items():
                sess.assumption_engine.assume(
                    var, *props_str.strip().split(), level=AssumptionLevel.SESSION
                )

        return {
            "success": True,
            "assumptions": {
                var: {k: v for k, v in props.items() if v}
                for var, props in ctx.assumptions.items()
            },
            # Echo what this call actually set — math()'s per-call mode has
            # this echo; assume() used to omit it (run-021).
            "assumptions_applied": {
                var: props_str.strip().split()
                for var, props_str in variables.items()
            },
            "message": f"Assumptions set for {len(variables)} variable(s)",
        }

    @mcp.tool(
        meta={
            "category": "Assumptions",
            "example": "show_assumptions()",
        }
    )
    def show_assumptions() -> dict[str, Any]:
        """
        Show the symbolic assumptions in the shared math context.

        Covers assume() and math(..., assumptions=[...]); session-level
        assumptions are not included (use list_assumptions()).

        Returns:
            Assumptions in the current MathContext
        """
        assumptions = get_context().assumptions
        if not assumptions:
            return {
                "success": True,
                "assumptions": {},
                "message": "No assumptions set. Use assume() to set variable properties.",
            }

        lines = []
        for var, props in assumptions.items():
            active = ", ".join(k for k, v in props.items() if v)
            lines.append(f"  {var}: {active}")

        return {
            "success": True,
            "assumptions": {
                var: {k: v for k, v in props.items() if v}
                for var, props in assumptions.items()
            },
            "display_text": "📐 **Current Assumptions:**\n" + "\n".join(lines),
        }

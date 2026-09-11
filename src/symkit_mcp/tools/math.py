"""Unified Math Tool — SymKit's core computation tool

A single `math()` tool supports ~25 mathematical operations,
similar to Mathematica's function-call style.

Design:
- math() is the primary tool that LLMs use
- session=True → record to derivation session, preserving full step traceability
- session=False → stateless quick calculation

The operation dispatcher lives in ``_math_dispatch.py``; this module is the
thin MCP wrapper: parameter plumbing, per-call assumptions, display text, and
session recording from the live SymPy objects the dispatcher returns.
"""

from __future__ import annotations

from typing import Any

from symkit.domain.assumption_engine import AssumptionLevel
from symkit.domain.derivation_session import OperationType
from symkit.domain.value_objects import MathContext
from symkit_mcp.tools._math_dispatch import (
    _OP_TYPE_MAP,
    _execute_operation,
    _preprocess,
)
from symkit_mcp.tools._state import get_context, get_session, set_context


def _parse_assumption_clause(a: str) -> tuple[str, dict[str, bool]] | None:
    """Parse an assumption clause into ``(variable, {prop: True, ...})``.

    Accepts both ``"x is positive real"`` and ``"x positive real"`` forms.
    Returns ``None`` when the clause cannot be understood (caller warns).
    """
    parts = a.strip().split()
    if len(parts) >= 3 and parts[1] == "is":
        return parts[0], dict.fromkeys(parts[2:], True)
    if len(parts) >= 2:
        return parts[0], dict.fromkeys(parts[1:], True)
    return None


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
        session: bool = True,
        description: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """
        Run mathematical operations (unified Mathematica-style tool)

        ═══════════════════════════════════════════════════════════════════════
        SymKit's core tool — supports ~25 mathematical operations.
        One tool handles derivation, calculation, solving, and transformation.
        ═══════════════════════════════════════════════════════════════════════

        **Supported operations (operation):**

        | Category | Operation | Description |
        |------|------|------|
        | Parse | `parse` | Parse expression and extract symbols |
        | Numeric | `evalf` | Numeric floating-point evaluation |
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
                With session=true they persist for the session (and become
                visible to the step verifier); with session=false they apply
                to this call only. Use assume() for cross-session globals and
                unassume()/clear_assumptions() to remove them.
            method: Simplification method "auto", "trig", "radical", "expand_then_simplify"
            ics: Initial conditions for dsolve {"V(0)": "V_0"} — keys are the
                dependent function applied to a point, values are expressions
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

            # Vector calculus
            math("gradient", "x**2 + y**2 + z**2", variable="x,y,z")
            → gradient in vector form

            # Solve ODE
            math("dsolve", "diff(y,t) - k*y", variable="y", with_respect_to="t")
            math("dsolve", "dy/dt - k*y", variable="y", with_respect_to="t",
                 ics={"y(0)": "y_0"})
        """
        preprocessed = _preprocess(expression)

        # Per-call assumption scoping: with session=true the assumptions
        # persist into the shared context AND the session's assumption engine
        # (so the step verifier can see them); with session=false they apply
        # to THIS call only — the shared context is left untouched, keeping
        # stateless calls side-effect free (run-013).  Cross-session globals
        # are set explicitly via assume().
        assumption_warnings: list[str] = []
        applied_assumptions: dict[str, dict[str, bool]] = {}
        call_context: MathContext | None = None
        if assumptions:
            ctx = get_context()
            for a in assumptions:
                clause = _parse_assumption_clause(a)
                if clause is None:
                    assumption_warnings.append(
                        f"Could not parse assumption '{a}'. "
                        "Use 'x is positive' or 'x positive'."
                    )
                    continue
                var_name, props_dict = clause
                ctx = ctx.with_assumption(var_name, **props_dict)
                applied_assumptions[var_name] = props_dict
            call_context = ctx
            if session:
                set_context(ctx)
                sess = get_session()
                if sess is not None:
                    for var_name, props_dict in applied_assumptions.items():
                        sess.assumption_engine.assume(
                            var_name, *props_dict, level=AssumptionLevel.SESSION
                        )

        # Execute the operation
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
            assumption_context=call_context,
        )

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
            result.setdefault("warnings", []).extend(assumption_warnings)

        # Build display text
        if result["success"]:
            latex_str = result.get("latex", "")
            op_tag = operation.upper()
            display = f"🔹 **{op_tag}** result:\n\n$${latex_str}$$"
            result["display_text"] = display

            # Record to derivation session if requested
            if session:
                sess = get_session()
                if sess is not None and result_obj is not None:
                    try:
                        op_type = _OP_TYPE_MAP.get(operation, OperationType.CUSTOM)
                        desc = description or f"{operation}: {expression[:50]}"
                        # Build a sympy_command that the step verifier can parse
                        # (e.g. diff(expr, x), integrate(expr, x)).
                        if operation == "diff":
                            if order == 1:
                                sympy_cmd = f"diff(expr, {variable})"
                            else:
                                sympy_cmd = f"diff(expr, {variable}, {order})"
                        elif operation == "integrate":
                            if lower is not None and upper is not None:
                                sympy_cmd = f"integrate(expr, ({variable}, {lower}, {upper}))"
                            else:
                                sympy_cmd = f"integrate(expr, {variable})"
                        elif operation == "limit":
                            sympy_cmd = f"limit(expr, {variable}, {point or '0'})"
                        else:
                            sympy_cmd = f"math('{operation}', ...)"

                        # Provide extra input metadata so the verifier can check
                        # substitution and solve steps too. The recorded input is
                        # str() of the same live object the operation consumed, so
                        # the archive cannot diverge from the response.
                        input_expressions: dict[str, str] = {
                            "original": (
                                str(input_obj) if input_obj is not None else preprocessed
                            ),
                        }
                        if operation == "substitute" and substitution:
                            input_expressions["replacement"] = ", ".join(
                                f"{k} = {v}" for k, v in substitution.items()
                            )
                        elif operation == "solve" and variable:
                            input_expressions["target_variable"] = variable
                        elif operation == "limit":
                            # The verifier must probe the side the user actually
                            # asked for; without this a correct one-sided limit
                            # was reported INCONCLUSIVE because the other side
                            # disagrees (P5).
                            input_expressions["limit_direction"] = direction

                        sess._add_step(
                            operation=op_type,
                            description=desc,
                            input_expressions=input_expressions,
                            output_expr=result_obj,
                            sympy_command=sympy_cmd,
                            notes=notes,
                            # The live input object, so the step archives an
                            # input_srepr and verification never has to
                            # re-parse a display string (invariant I2).  A
                            # non-Basic input (comma-parsed tuple) is ignored
                            # by _add_step.
                            prior_expr=input_obj,
                        )
                        sess.current_expression = result_obj
                        result["step"] = sess.step_count
                        result["session_id"] = sess.session_id
                    except Exception as exc:
                        # Fail loud: recording problems are surfaced to the
                        # caller instead of silently dropping the step.
                        result.setdefault("warnings", []).append(
                            f"Step recording failed: {type(exc).__name__}: {exc}"
                        )
        else:
            result["display_text"] = f"❌ **{operation}** failed: {result.get('error', 'unknown')}"

        return result

    @mcp.tool(
        meta={
            "category": "Unified Math",
            "example": 'assume({"x": "positive", "t": "real"})',
        }
    )
    def assume(variables: dict[str, str]) -> dict[str, Any]:
        """
        Set symbolic assumptions (affecting subsequent math() calculations)

        Assumptions are recorded in MathContext and passed to SymPy, and also written
        to the current session's multi-level assumption engine (session level).

        Args:
            variables: Mapping from variable to properties
                       e.g., {"x": "positive real", "n": "integer"}

        Returns:
            All current assumptions

        Example:
            assume({"x": "positive", "t": "real"})
            # Afterwards, math("simplify", "sqrt(x**2)") returns x instead of Abs(x)
        """
        from symkit.domain.assumption_engine import AssumptionLevel

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
            "category": "Unified Math",
            "example": "show_assumptions()",
        }
    )
    def show_assumptions() -> dict[str, Any]:
        """
        Show all symbolic assumptions in the current scope

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

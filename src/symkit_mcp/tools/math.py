"""Unified Math Tool — SymKit's core computation tool

A single `math()` tool supports ~25 mathematical operations,
similar to Mathematica's function-call style.

Design:
- math() is the primary tool that LLMs use
- session=True → record to derivation session, preserving full step traceability
- session=False → stateless quick calculation
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_application,
    implicit_multiplication,
    parse_expr,
    standard_transformations,
)

from symkit.domain.derivation_session import OperationType
from symkit.domain.expression_parser import (
    _convert_equals_to_eq,
    _split_eq_args,
    build_reserved_local_dict,
    parse_user_expression,
    preprocess_unicode,
)
from symkit.domain.value_objects import MathContext
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools._state import get_context, get_session, set_context

_engine = SymPyEngine()


def _preprocess(expr_str: str) -> str:
    """Convert Unicode math chars to SymPy-compatible ASCII."""
    return preprocess_unicode(expr_str)


def _apply_context_assumptions(
    expr: sp.Basic, context: MathContext | None
) -> sp.Basic:
    """Replace bare symbols with assumption-bearing versions from context.

    This lets ``assume({"x": "positive"})`` followed by ``math("simplify", ...)``
    produce assumption-aware results such as ``sqrt(x**2) -> x``.
    """
    if context is None or not context.assumptions:
        return expr
    subs: dict[sp.Basic, sp.Symbol] = {}
    for name, props in context.assumptions.items():
        sym = sp.Symbol(name)
        if expr.has(sym):
            subs[sym] = sp.Symbol(name, **props)
    return expr.xreplace(subs)


def _resolve_variable_symbol(
    expr: sp.Basic,
    variable: str,
    context: MathContext | None,
) -> sp.Symbol:
    """Return the symbol object for *variable* as it appears in *expr*.

    After applying context assumptions, the symbols in *expr* may carry those
    assumptions.  A newly created bare symbol will not match them, so SymPy
    operations such as ``solve`` and ``diff`` would silently return no results.
    This helper prefers the symbol already present in the expression and falls
    back to creating a symbol with the assumptions recorded in *context*.
    """
    for sym in expr.free_symbols:
        if sym.name == variable:
            return sym
    props = context.assumptions.get(variable, {}) if context else {}
    return sp.Symbol(variable, **props)


def _parse_math_expression(expr_str: str) -> tuple[sp.Expr | None, str | None]:
    """Parse a math expression using the unified parser.

    Supports SymPy strings, natural equations, Leibniz derivatives, Unicode/Greek
    math, and LaTeX. Returns (sympy_expr, error_message).
    """
    return parse_user_expression(expr_str, convert_equation=True)


def _parse_ode(expr_str: str, func: str, var: str) -> sp.Basic | sp.Equality | None:
    """Parse an ODE expression such as ``diff(C, t) + k*C`` into SymPy form.

    Supports both ``diff(C, t)`` and ``diff(C(t), t)`` notations, plus an
    optional derivative order (``diff(C, t, 2)``). The dependent variable is
    treated as a SymPy ``Function`` so that ``C(t)`` is not rewritten as an
    implicit multiplication ``C*t`` by the parser.
    """
    _TRANSFORMATIONS = standard_transformations + (
        implicit_multiplication,
        implicit_application,
        convert_xor,
    )

    # Pattern: diff(C, t), diff(C(t), t), diff(C, t, 2), diff(C(t), t, 2)
    pattern = rf"diff\({func}\s*(?:\(\s*{var}\s*\))?\s*,\s*{var}(?:\s*,\s*(\d+))?\)"
    result_str = expr_str

    def _make_deriv(m: re.Match[str]) -> str:
        order_str = m.group(1)
        order = int(order_str) if order_str else 1
        if order == 1:
            return f"Derivative({func}({var}), {var})"
        return f"Derivative({func}({var}), ({var}, {order}))"

    result_str = re.sub(pattern, _make_deriv, result_str)

    # Replace any remaining bare dependent variable with the function call form.
    result_str = re.sub(rf"\b{func}\b(?!\s*\()", f"{func}({var})", result_str)

    # Use a local dict that forces ``func`` to be a SymPy Function and protects
    # reserved names (e.g. beta) from being interpreted as SymPy functions.
    processed = _convert_equals_to_eq(preprocess_unicode(result_str))
    local_dict: dict[str, Any] = {func: sp.Function(func)}
    local_dict.update(build_reserved_local_dict(processed))

    eq_args = _split_eq_args(processed)
    try:
        if eq_args is not None:
            lhs_str, rhs_str = eq_args
            lhs = parse_expr(
                lhs_str,
                local_dict=local_dict,
                transformations=_TRANSFORMATIONS,
            )
            rhs = parse_expr(
                rhs_str,
                local_dict=local_dict,
                transformations=_TRANSFORMATIONS,
            )
            expr = sp.Eq(lhs, rhs)
        else:
            expr = parse_expr(
                processed,
                local_dict=local_dict,
                transformations=_TRANSFORMATIONS,
                evaluate=False,
            )
    except Exception:  # pragma: no cover - parser raises many types
        return None

    # If the user gave an expression, turn it into an equation equal to 0.
    if not isinstance(expr, sp.Equality):
        expr = sp.Eq(expr, 0)
    return expr


# ── Operation dispatcher ──────────────────────────────────────────────

# Operations that are purely syntactical (only need parse + apply)
_SYNTACTIC_OPS = {
    "expand", "factor", "collect", "cancel", "apart", "together",
    "trigsimp", "powsimp", "radsimp", "combsimp",
}

# Operations that need the engine
_ENGINE_OPS = {
    "diff", "integrate", "limit", "series", "dsolve",
    "gradient", "divergence", "curl", "laplacian",
    "det", "inv", "eigenvals", "eigenvects",
    "laplace", "ilaplace", "fourier", "ifourier",
}

ALL_OPS = sorted(_SYNTACTIC_OPS | _ENGINE_OPS |
                 {"simplify", "solve", "substitute", "parse"})


def _execute_operation(
    operation: str,
    expr_str: str,
    *,
    variable: str | None = None,
    with_respect_to: str | None = None,
    substitution: dict[str, Any] | None = None,
    point: str | None = None,
    direction: str = "+-",
    order: int = 1,
    lower: str | None = None,
    upper: str | None = None,
    method: str = "auto",
) -> dict[str, Any]:
    """Execute a single math operation and return result dict."""
    preprocessed = _preprocess(expr_str)
    context = get_context()

    # Helper to parse with consistent error handling
    def _parse(expr: str) -> tuple[sp.Expr | None, str | None]:
        return _parse_math_expression(expr)

    # Helper to require a successful parse
    def _require_parse(expr: str) -> sp.Expr | dict[str, Any]:
        parsed, error = _parse(expr)
        if parsed is None:
            return {"success": False, "error": f"Cannot parse: {error}"}
        return parsed

    # Helper to require a successful parse and apply context assumptions
    def _require_parse_with_assumptions(expr: str) -> sp.Expr | dict[str, Any]:
        parsed = _require_parse(expr)
        if isinstance(parsed, dict):
            return parsed
        return _apply_context_assumptions(parsed, context)

    # ── SYNTACTIC OPERATIONS ──
    if operation == "expand":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.expand(parsed)
    elif operation == "factor":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.factor(parsed)
    elif operation == "collect":
        if not variable:
            return {"success": False, "error": "collect requires variable parameter"}
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        var = _resolve_variable_symbol(parsed, variable, context)
        result = sp.collect(parsed, var)
    elif operation == "cancel":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.cancel(parsed)
    elif operation == "apart":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        var = _resolve_variable_symbol(parsed, variable or "x", context)
        result = sp.apart(parsed, var)
    elif operation == "together":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.together(parsed)
    elif operation == "trigsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.trigsimp(parsed)
    elif operation == "powsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.powsimp(parsed)
    elif operation == "radsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.radsimp(parsed)
    elif operation == "combsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = sp.combsimp(parsed)

    # ── PARSE ONLY ──
    elif operation == "parse":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        result = parsed

    # ── SOLVE ──
    elif operation == "solve":
        if not variable:
            return {"success": False, "error": "solve requires variable parameter"}
        try:
            # The shared parser already converts a single '=' to Eq(...).
            parsed = _require_parse_with_assumptions(preprocessed)
            if isinstance(parsed, dict):
                return parsed
            v = _resolve_variable_symbol(parsed, variable, context)
            eq = parsed if isinstance(parsed, sp.Equality) else parsed
            solutions = sp.solve(eq, v)
            if not solutions:
                return {"success": False, "error": f"No solution found for {variable}"}
            sol = solutions[0]
            result = sp.Eq(v, sol)
            return {
                "success": True,
                "expression": str(result),
                "latex": sp.latex(result),
                "all_solutions": [str(s) for s in solutions],
                "operation": operation,
            }
        except Exception as e:
            return {"success": False, "error": f"Solve failed: {e}"}

    # ── SIMPLIFY ──
    elif operation == "simplify":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        if method == "trig":
            result = sp.trigsimp(parsed)
        elif method == "radical":
            result = sp.radsimp(parsed)
        elif method == "expand_then_simplify":
            result = sp.simplify(sp.expand(parsed))
        else:
            result = sp.simplify(parsed)

    # ── SUBSTITUTE ──
    elif operation == "substitute":
        if not substitution:
            return {"success": False, "error": "substitute requires substitution dict"}
        expr, expr_error = _parse(preprocessed)
        if expr is None:
            return {"success": False, "error": f"Cannot parse expression: {expr_error}"}
        subs: dict[sp.Basic, sp.Expr] = {}
        for k, v in substitution.items():
            key, key_error = _parse(str(k))
            if key is None:
                return {"success": False, "error": f"Cannot parse substitution key '{k}': {key_error}"}
            val, val_error = _parse(str(v))
            if val is None:
                return {"success": False, "error": f"Cannot parse substitution value '{v}': {val_error}"}
            subs[key] = val
        result = expr.subs(subs)

    # ── ENGINE-BASED OPERATIONS ──
    elif operation in _ENGINE_OPS:
        expr_obj = _engine.parse(preprocessed, context)
        if not expr_obj.is_valid:
            return {"success": False, "error": f"Cannot parse: {expr_str}"}
        v = variable or "x"

        if operation == "diff":
            out = _engine.differentiate(expr_obj, v, order, context)
        elif operation == "integrate":
            out = _engine.integrate(expr_obj, v, lower, upper, context)
        elif operation == "limit":
            pt = point or "0"
            out = _engine.limit(expr_obj, v, pt, direction, context)
        elif operation == "series":
            pt = point or "0"
            out = _engine.series(expr_obj, v, pt, order, context)
        elif operation == "dsolve":
            func_var = with_respect_to or "t"
            # Parse as ODE: convert "diff(y,t) - k*y" to SymPy form
            ode_expr = _parse_ode(preprocessed, v, func_var)
            if ode_expr is None:
                return {"success": False,
                        "error": f"Cannot parse ODE. Use format: 'diff({v},{func_var}) - k*{v}'"}
            # Wrap the parsed ODE directly as an Expression
            from symkit.domain.entities import Expression as ExprEntity
            from symkit.domain.entities import ExpressionType
            ode_obj = ExprEntity(
                raw=str(ode_expr),
                latex=sp.latex(ode_expr),
                sympy_expr=ode_expr,
                expr_type=ExpressionType.EQUATION,
            )
            out = _engine.dsolve(ode_obj, v, func_var, context)
        elif operation in ("gradient", "divergence", "curl", "laplacian"):
            coords = [c.strip() for c in (v or "x,y,z").split(",")]
            if operation == "gradient":
                out = _engine.gradient(expr_obj, coords, context)
            elif operation == "divergence":
                out = _engine.divergence(expr_obj, coords, context)
            elif operation == "curl":
                out = _engine.curl(expr_obj, coords, context)
            else:
                out = _engine.laplacian(expr_obj, coords, context)
        elif operation in ("det", "inv", "eigenvals", "eigenvects"):
            if operation == "det":
                out = _engine.matrix_det(expr_obj, context)
            elif operation == "inv":
                out = _engine.matrix_inv(expr_obj, context)
            elif operation == "eigenvals":
                vals = _engine.matrix_eigenvals(expr_obj, context)
                return {
                    "success": True,
                    "eigenvalues": [e.raw for e in vals],
                    "eigenvalues_latex": [e.latex for e in vals],
                    "operation": operation,
                }
            else:  # eigenvects
                vects = _engine.matrix_eigenvects(expr_obj, context)
                return {
                    "success": True,
                    "eigenvectors": vects,
                    "operation": operation,
                }
        elif operation in ("laplace", "ilaplace"):
            freq = with_respect_to or ("s" if operation == "laplace" else "t")
            if operation == "laplace":
                out = _engine.laplace_transform(expr_obj, v, freq, context)
            else:
                out = _engine.inverse_laplace_transform(expr_obj, v, freq, context)
        elif operation in ("fourier", "ifourier"):
            freq = with_respect_to or "k"
            if operation == "fourier":
                out = _engine.fourier_transform(expr_obj, v, freq, context)
            else:
                # inverse_fourier_transform(expr, freq_var, space_var)
                out = _engine.inverse_fourier_transform(expr_obj, v, freq, context)
        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

        if not out.is_valid:
            return {"success": False, "error": f"Operation '{operation}' failed"}
        result = out.sympy_expr

    else:
        return {
            "success": False,
            "error": f"Unknown operation '{operation}'. Supported: {', '.join(ALL_OPS)}",
        }

    return {
        "success": True,
        "expression": str(result),
        "latex": sp.latex(result),
        "operation": operation,
    }


# ── MCP Tool Registration ─────────────────────────────────────────────

# Map operation names to OperationType
_OP_TYPE_MAP = {
    "parse": OperationType.LOAD_FORMULA,
    "simplify": OperationType.SIMPLIFY,
    "expand": OperationType.EXPAND,
    "factor": OperationType.FACTOR,
    "solve": OperationType.SOLVE,
    "substitute": OperationType.SUBSTITUTE,
    "diff": OperationType.DIFFERENTIATE,
    "integrate": OperationType.INTEGRATE,
    "limit": OperationType.LIMIT,
    "series": OperationType.SERIES,
    "dsolve": OperationType.DSOLVE,
    "gradient": OperationType.VECTOR_OP,
    "divergence": OperationType.VECTOR_OP,
    "curl": OperationType.VECTOR_OP,
    "laplacian": OperationType.VECTOR_OP,
    "det": OperationType.MATRIX_OP,
    "inv": OperationType.MATRIX_OP,
    "eigenvals": OperationType.MATRIX_OP,
    "eigenvects": OperationType.MATRIX_OP,
    "laplace": OperationType.TRANSFORM,
    "ilaplace": OperationType.TRANSFORM,
    "fourier": OperationType.TRANSFORM,
    "ifourier": OperationType.TRANSFORM,
    "collect": OperationType.EXPAND,  # Approximation
    "cancel": OperationType.SIMPLIFY,
    "apart": OperationType.EXPAND,
    "together": OperationType.SIMPLIFY,
    "trigsimp": OperationType.SIMPLIFY,
    "powsimp": OperationType.SIMPLIFY,
    "radsimp": OperationType.SIMPLIFY,
    "combsimp": OperationType.SIMPLIFY,
}


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
        | ODE | `dsolve` | Solve ODE (variable=function name, with_respect_to=independent variable) |
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
            assumptions: Symbolic assumptions ["x is positive", "t is real"]
            method: Simplification method "auto", "trig", "radical", "expand_then_simplify"
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
        """
        preprocessed = _preprocess(expression)

        # Apply symbolic assumptions if provided
        if assumptions:
            ctx = get_context()
            for a in assumptions:
                parts = a.strip().split()
                if len(parts) >= 3 and parts[1] == "is":
                    var_name = parts[0]
                    props = parts[2:]
                    props_dict: dict[str, bool] = {}
                    for p in props:
                        props_dict[p] = True
                    ctx = ctx.with_assumption(var_name, **props_dict)
            set_context(ctx)

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
        )

        # Build display text
        if result["success"]:
            latex_str = result.get("latex", "")
            op_tag = operation.upper()
            display = f"🔹 **{op_tag}** result:\n\n$${latex_str}$$"
            result["display_text"] = display

            # Record to derivation session if requested
            if session:
                sess = get_session()
                if sess is not None:
                    try:
                        sympy_expr, _ = _parse_math_expression(preprocessed)
                        output_expr, _ = _parse_math_expression(result["expression"])
                        if sympy_expr is not None and output_expr is not None:
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
                            else:
                                sympy_cmd = f"math('{operation}', ...)"

                            # Provide extra input metadata so the verifier can check
                            # substitution and solve steps too.
                            # Use str(sympy_expr) as the canonical input so equations
                            # are stored as Eq(...) rather than raw '=', which the
                            # step verifier can parse.
                            input_expressions: dict[str, str] = {
                                "original": str(sympy_expr),
                            }
                            if operation == "substitute" and substitution:
                                input_expressions["replacement"] = ", ".join(
                                    f"{k} = {v}" for k, v in substitution.items()
                                )
                            elif operation == "solve" and variable:
                                input_expressions["target_variable"] = variable

                            sess._add_step(
                                operation=op_type,
                                description=desc,
                                input_expressions=input_expressions,
                                output_expr=output_expr,
                                sympy_command=sympy_cmd,
                                notes=notes,
                            )
                            sess.current_expression = output_expr
                            result["step"] = sess.step_count
                            result["session_id"] = sess.session_id
                    except Exception:
                        pass  # Don't fail if recording fails
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

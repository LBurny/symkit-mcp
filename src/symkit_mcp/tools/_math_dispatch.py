"""Unified math operation dispatcher.

Internal machinery behind the ``math()`` MCP tool (see ``math.py``). Kept
separate so the thin MCP wrapper only handles parameter plumbing, display
text, and session recording, while this module owns operation semantics.

Contract: successful result dicts carry two internal keys — ``_input_obj``
and ``_result_obj`` — holding the *live* SymPy objects for the operation's
input and output. The wrapper pops them before responding to the client and
uses them for session recording, so the session archive is built from the
same object the client received (never re-parsed from its string form).
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
    _rationalize_unevaluated_divisions,
    _split_eq_args,
    build_reserved_local_dict,
    parse_user_expression,
    preprocess_unicode,
)
from symkit.domain.value_objects import MathContext
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools._state import get_context

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


def _build_subs_dict(
    substitution: dict[str, Any],
) -> tuple[dict[sp.Basic, Any] | None, dict[str, Any] | None]:
    """Parse a substitution mapping into SymPy objects.

    Shared by the ``substitute`` and ``evalf`` operations. Returns
    ``(subs, None)`` on success and ``(None, error_dict)`` on failure.
    """
    subs: dict[sp.Basic, Any] = {}
    for k, v in substitution.items():
        key, key_error = _parse_math_expression(str(k))
        if key is None:
            return None, {
                "success": False,
                "error": f"Cannot parse substitution key '{k}': {key_error}",
            }
        val, val_error = _parse_math_expression(str(v))
        if val is None:
            return None, {
                "success": False,
                "error": f"Cannot parse substitution value '{v}': {val_error}",
            }
        subs[key] = val
    return subs, None


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
            expr = _rationalize_unevaluated_divisions(expr)
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
                 {"simplify", "solve", "substitute", "parse", "evalf"})


# ── Parameter-consumption audit ─────────────────────────────────────────
#
# Fail-loud discipline: a caller-supplied parameter must either be consumed
# by the requested operation or produce an explicit warning. Defaults that
# the caller did not deviate from never warn.

_KNOB_DEFAULTS: dict[str, Any] = {
    "variable": None,
    "with_respect_to": None,
    "substitution": None,
    "point": None,
    "direction": "+-",
    "order": 1,
    "lower": None,
    "upper": None,
    "method": "auto",
}

_PARAM_USE: dict[str, frozenset[str]] = {
    "parse": frozenset(),
    "evalf": frozenset({"substitution"}),
    "simplify": frozenset({"method"}),
    "expand": frozenset(),
    "factor": frozenset(),
    "cancel": frozenset(),
    "together": frozenset(),
    "trigsimp": frozenset(),
    "powsimp": frozenset(),
    "radsimp": frozenset(),
    "combsimp": frozenset(),
    "collect": frozenset({"variable"}),
    "apart": frozenset({"variable"}),
    "solve": frozenset({"variable"}),
    "substitute": frozenset({"substitution"}),
    "diff": frozenset({"variable", "order"}),
    "integrate": frozenset({"variable", "lower", "upper"}),
    "limit": frozenset({"variable", "point", "direction"}),
    "series": frozenset({"variable", "point", "order"}),
    "dsolve": frozenset({"variable", "with_respect_to"}),
    "gradient": frozenset({"variable"}),
    "divergence": frozenset({"variable"}),
    "curl": frozenset({"variable"}),
    "laplacian": frozenset({"variable"}),
    "det": frozenset(),
    "inv": frozenset(),
    "eigenvals": frozenset(),
    "eigenvects": frozenset(),
    "laplace": frozenset({"variable", "with_respect_to"}),
    "ilaplace": frozenset({"variable", "with_respect_to"}),
    "fourier": frozenset({"variable", "with_respect_to"}),
    "ifourier": frozenset({"variable", "with_respect_to"}),
}


def _ignored_param_warnings(operation: str, provided: dict[str, Any]) -> list[str]:
    """Warn about parameters the caller set that the operation does not consume."""
    allowed = _PARAM_USE.get(operation, frozenset())
    warnings: list[str] = []
    for name, default in _KNOB_DEFAULTS.items():
        if name in allowed:
            continue
        if provided.get(name, default) != default:
            warnings.append(
                f"Parameter '{name}' is not used by operation "
                f"'{operation}' and was ignored."
            )
    return warnings


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
    """Execute a single math operation and return result dict.

    Success dicts include the internal keys ``_input_obj``/``_result_obj``
    with the live SymPy objects; callers must pop them before responding.
    Parameters that do not apply to the requested operation produce explicit
    entries in ``warnings`` (fail-loud; nothing is silently ignored).
    """
    provided = {
        "variable": variable,
        "with_respect_to": with_respect_to,
        "substitution": substitution,
        "point": point,
        "direction": direction,
        "order": order,
        "lower": lower,
        "upper": upper,
        "method": method,
    }
    result = _execute_operation_inner(
        operation,
        expr_str,
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
    warnings = _ignored_param_warnings(operation, provided)
    if warnings:
        result.setdefault("warnings", []).extend(warnings)
    return result


def _execute_operation_inner(
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
    """Execute a single math operation and return result dict.

    Success dicts include the internal keys ``_input_obj``/``_result_obj``
    with the live SymPy objects; callers must pop them before responding.
    """
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

    input_obj: Any = None
    result: Any = None

    # ── SYNTACTIC OPERATIONS ──
    if operation == "expand":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.expand(parsed)
    elif operation == "factor":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.factor(parsed)
    elif operation == "collect":
        if not variable:
            return {"success": False, "error": "collect requires variable parameter"}
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        var = _resolve_variable_symbol(parsed, variable, context)
        result = sp.collect(parsed, var)
    elif operation == "cancel":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.cancel(parsed)
    elif operation == "apart":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        var = _resolve_variable_symbol(parsed, variable or "x", context)
        result = sp.apart(parsed, var)
    elif operation == "together":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.together(parsed)
    elif operation == "trigsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.trigsimp(parsed)
    elif operation == "powsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.powsimp(parsed)
    elif operation == "radsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.radsimp(parsed)
    elif operation == "combsimp":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = sp.combsimp(parsed)

    # ── PARSE ONLY ──
    elif operation == "parse":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = parsed

    # ── NUMERIC EVALUATION ──
    elif operation == "evalf":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        if substitution:
            subs, subs_error = _build_subs_dict(substitution)
            if subs_error is not None:
                return subs_error
            parsed = parsed.subs(subs).doit()
        result = parsed.evalf()

    # ── SOLVE ──
    elif operation == "solve":
        if not variable:
            return {"success": False, "error": "solve requires variable parameter"}
        try:
            # The shared parser already converts a single '=' to Eq(...).
            parsed = _require_parse_with_assumptions(preprocessed)
            if isinstance(parsed, dict):
                return parsed
            input_obj = parsed
            v = _resolve_variable_symbol(parsed, variable, context)
            eq = parsed if isinstance(parsed, sp.Equality) else parsed
            solutions = sp.solve(eq, v)
            if not solutions:
                return {"success": False, "error": f"No solution found for {variable}"}
            sol = solutions[0]
            result = sp.Eq(v, sol)
            # Warn when float coefficients silently truncate the solution to a
            # numeric approximation (use exact fractions like 1/2 for exact
            # symbolic results).
            float_atoms = sorted(eq.atoms(sp.Float), key=str)
            warnings: list[str] = []
            if float_atoms:
                shown = ", ".join(str(f) for f in float_atoms[:3])
                warnings.append(
                    "Input contains float coefficients (" + shown + "); the "
                    "solution is numerically truncated. Use exact fractions "
                    "(e.g. 1/2 instead of 0.5) for exact symbolic results."
                )
            return {
                "success": True,
                "expression": str(result),
                "latex": sp.latex(result),
                "solution": str(sol),
                "solution_latex": sp.latex(sol),
                "all_solutions": [str(s) for s in solutions],
                "warnings": warnings,
                "operation": operation,
                "_input_obj": input_obj,
                "_result_obj": result,
            }
        except Exception as e:
            return {"success": False, "error": f"Solve failed: {e}"}

    # ── SIMPLIFY ──
    elif operation == "simplify":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
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
        subs, subs_error = _build_subs_dict(substitution)
        if subs_error is not None:
            return subs_error
        assert subs is not None
        input_obj = expr
        result = expr.subs(subs).doit()

    # ── ENGINE-BASED OPERATIONS ──
    elif operation in _ENGINE_OPS:
        expr_obj = _engine.parse(preprocessed, context)
        if not expr_obj.is_valid:
            return {"success": False, "error": f"Cannot parse: {expr_str}"}
        v = variable or "x"
        input_obj = expr_obj.sympy_expr

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
            input_obj = ode_expr
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
                    "_input_obj": input_obj,
                    "_result_obj": None,
                }
            else:  # eigenvects
                vects = _engine.matrix_eigenvects(expr_obj, context)
                return {
                    "success": True,
                    "eigenvectors": vects,
                    "operation": operation,
                    "_input_obj": input_obj,
                    "_result_obj": None,
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
        "_input_obj": input_obj,
        "_result_obj": result,
    }


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
    "evalf": OperationType.CUSTOM,
}

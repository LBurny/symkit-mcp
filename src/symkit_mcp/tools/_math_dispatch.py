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
from sympy.core.function import AppliedUndef

from symkit.domain.assumption_binding import apply_assumptions, resolve_assumed_symbol
from symkit.domain.derivation_session import OperationType
from symkit.domain.expr_io import dense_matrix_form
from symkit.domain.expression_parser import (
    parse_expression_string,
    parse_user_expression,
    preprocess_unicode,
)
from symkit.domain.value_objects import MathContext
from symkit.infrastructure.matrix_exp import matrix_exp_guard
from symkit.infrastructure.numeric_eval import numeric_evalf
from symkit.infrastructure.sympy_engine import (
    SymPyEngine,
    coupled_undefined_functions,
    nonpolynomial_ode_reason,
    restore_zero_root,
)
from symkit.infrastructure.vector_input import vector_operation
from symkit_mcp.tools._op_helpers import (
    antiderivative_warnings,
    applied_function_solve_error,
    assemble_solve_response,
    flat_matrix_equations,
    inequality_solve_error,
    integrate_operation,
    set_literal_solve_error,
    solve_variable_name_error,
    symbol_names,
)
from symkit_mcp.tools._state import get_context, get_session
from symkit_mcp.tools._system_solve import solve_system
from symkit_mcp.tools._unit_context import dimension_operation

_engine = SymPyEngine()

# Call-site names SymPy's namespace silently collapses to a symbol: ``S(t)``
# (SingletonRegistry) and ``N(t)`` (evalf) both evaluate to ``t`` (r14 task-15).
_DEGENERATE_CALL_NAMES = ("S", "N")


def _engine_failure(operation: str, error: str) -> str:
    """Render an engine failure with an actionable hint where one applies.

    SymPy's "Result depends on the sign of ..." names the symbols but not the
    remedy, so an agent could not tell that the fix is to state the signs (P5).
    """
    message = f"Operation '{operation}' failed"
    if error:
        message += f": {error}"
    if "depends on the sign of" in (error or ""):
        message += (
            " — pass the needed signs via assumptions=[...] (e.g. "
            "\"A is positive\"), or assume_for_step(), to decide the sign."
        )
    return message


def _effective_context(assumption_context: MathContext | None) -> MathContext:
    """Resolve the assumption set a math call actually runs under.

    The session's ``AssumptionEngine`` is the source of truth for step- and
    domain-level assumptions (invariant I3); before this merge they were
    silently ignored by ``math()``, which read only ``MathContext``.

    Precedence, weakest to strongest: the engine's merged view (domain defaults
    < global < session < step), then the explicit context. A stronger layer
    *replaces* a symbol's property set rather than unioning with it — unioning
    made a per-call ``x is negative`` conflict with a step-level ``x positive``
    and silently dropped both (invariant I3). The global context is never
    mutated; the merged view is local to the call.
    """
    context = (
        assumption_context if assumption_context is not None else get_context()
    )
    session = get_session()
    if session is None:
        return context

    engine_assumptions = session.assumption_engine.get_assumptions()
    if not engine_assumptions:
        return context

    merged: dict[str, dict[str, bool]] = {
        name: dict(props) for name, props in engine_assumptions.items()
    }
    for name, props in context.assumptions.items():
        merged[name] = dict(props)
    return MathContext(assumptions=merged)


def _preprocess(expr_str: Any) -> Any:
    """Convert Unicode math chars to SymPy-compatible ASCII."""
    if not isinstance(expr_str, str):
        return expr_str
    return rename_lambda_word(preprocess_unicode(expr_str))


#: A bare ``lambda`` word cannot be parsed: it is a Python keyword, and
#: ``preprocess_unicode`` maps "λ" straight into it.  The rename runs after that
#: Unicode pass, in the dispatcher, because the parser applies it again on the
#: way in; ``lambda_`` is what ``symkit.domain.formula`` maps "λ" to.  A LaTeX
#: ``\lambda`` is left to the LaTeX parser, which reads ``Symbol('lambda')``.
_LAMBDA_WORD = re.compile(r"(?<![\w.\\])lambda(?!\w)")


def rename_lambda_word(expr_str: str) -> str:
    """Rename a bare ``lambda`` word to ``lambda_`` (r20 W2)."""
    return _LAMBDA_WORD.sub("lambda_", expr_str)


def lambda_symbol_warning(expr_str: Any) -> str | None:
    """A client-facing note when a bare ``lambda`` word had to be renamed."""
    if not isinstance(expr_str, str):
        return None
    preprocessed = preprocess_unicode(expr_str)
    if rename_lambda_word(preprocessed) == preprocessed:
        return None
    return (
        "'lambda' is a Python keyword and cannot be a SymPy symbol, so it was "
        "read as 'lambda_'; use another name (e.g. 'lam') to avoid the rename."
    )


def _apply_context_assumptions(
    expr: sp.Basic, context: MathContext | None
) -> sp.Basic:
    """Bind the context's assumptions onto the free symbols of ``expr``.

    This lets ``assume({"x": "positive"})`` followed by ``math("simplify", ...)``
    produce assumption-aware results such as ``sqrt(x**2) -> x``.  Delegates to
    :func:`symkit.domain.assumption_binding.apply_assumptions`, the single
    implementation shared with the engine, the verifier and session replay
    (invariant I3).  Non-Basic inputs (python tuples/lists from comma parses)
    pass through unchanged — running ``.has`` on them would crash (run-018).
    """
    if context is None:
        return expr
    return apply_assumptions(expr, context.assumptions)


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
    return resolve_assumed_symbol(variable, props)


def _parse_math_expression(expr_str: str) -> tuple[sp.Expr | None, str | None]:
    """Parse a math expression using the unified parser.

    Supports SymPy strings, natural equations, Leibniz derivatives, Unicode/Greek
    math, and LaTeX. Returns (sympy_expr, error_message).
    """
    return parse_user_expression(expr_str, convert_equation=True)


def _build_subs_dict(
    substitution: dict[str, Any],
) -> tuple[dict[sp.Basic, Any] | None, dict[str, Any] | None]:
    """Parse a substitution mapping into SymPy objects (substitute/evalf)."""
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


def _rekey_subs_to_expression(
    expr: sp.Basic,
    subs: dict[sp.Basic, Any],
) -> dict[sp.Basic, Any]:
    """Rebind substitution keys to the symbols actually present in *expr*.

    Assumption-bearing symbols (``Symbol('c', positive=True)``) do not match the
    plain keys, so ``subs`` would silently no-op; rebind each key by name (run-008).
    """
    rebound: dict[sp.Basic, Any] = {}
    for key, val in subs.items():
        if expr.has(key):
            rebound[key] = val
            continue
        if isinstance(key, sp.Symbol):
            target = next(
                (s for s in expr.free_symbols if str(s) == str(key)), None
            )
            if target is not None:
                rebound[target] = val
                continue
        rebound[key] = val
    return rebound


def _build_ics_dict(
    ics: dict[str, Any], func: str, var: str
) -> tuple[dict[Any, Any] | None, dict[str, Any] | None]:
    """Parse an initial-condition mapping into SymPy form for ``dsolve``.

    Accepts ``{"V(0)": "V_0"}`` and ``{"x'(0)": "v_0"}`` (one prime per
    derivative order, run-018), parsing keys into ``f(point)`` /
    ``Derivative(...).subs(...)`` as ``sympy.dsolve`` expects.
    """
    f = sp.Function(func)
    v = sp.Symbol(var)
    parsed_ics: dict[Any, Any] = {}
    for key_str, value_str in ics.items():
        match = re.fullmatch(
            rf"{re.escape(func)}\s*('*)\s*\(\s*(.+?)\s*\)",
            str(key_str).strip(),
        )
        if match is None:
            return None, {
                "success": False,
                "error": (
                    f"Cannot parse initial condition '{key_str}'. Use "
                    f"\"{func}(0)\": \"<value>\" for the value and "
                    f"\"{func}'(0)\": \"<value>\" for a derivative initial value."
                ),
            }
        order = match.group(1).count("'")
        point, point_error = _parse_math_expression(match.group(2))
        if point is None:
            return None, {
                "success": False,
                "error": f"Cannot parse ics point in '{key_str}': {point_error}",
            }
        value, value_error = _parse_math_expression(str(value_str))
        if value is None:
            return None, {
                "success": False,
                "error": f"Cannot parse ics value '{value_str}': {value_error}",
            }
        key_obj = (
            f(point)
            if order == 0
            else sp.Derivative(f(v), (v, order)).subs(v, point)
        )
        parsed_ics[key_obj] = value
    return parsed_ics, None


def _parse_ode(
    expr_str: str, func: str, var: str
) -> tuple[sp.Basic | sp.Equality | None, str | None]:
    """Parse an ODE expression such as ``diff(C, t) + k*C`` into SymPy form.

    Supports ``diff(C, t)`` / ``diff(C(t), t)`` with optional order and Leibniz
    ``dC/dt`` / ``d^2C/dt^2``; the dependent variable is a SymPy ``Function``
    so ``C(t)`` is not rewritten as ``C*t``. Input without any derivative of
    ``func`` is rejected loudly (run-012: ``R*C*dV/dt + V`` returned an
    algebraic rearrangement disguised as an ODE solution).
    """
    _NOTATION_HINT = (
        f"Accepted notations: 'diff({func},{var})', 'diff({func},{var},N)', "
        f"'d{func}/d{var}', 'd^N{func}/d{var}^N' (any order N)."
    )

    result_str = preprocess_unicode(expr_str)

    # Leibniz notation, any order (higher orders before first order):
    # d^2C/dt^2, d^4w/dx^4, dC/dt.  Mismatched numerator/denominator orders
    # are left untouched so the parser fails loudly instead of guessing
    # (run-020: the hardcoded order-2 regex made d^4 input report "order not
    # supported" even though dsolve handles it fine).
    def _leibniz_ho_repl(m: re.Match[str]) -> str:
        n_num = m.group(1) or m.group(2)
        n_den = m.group(3) or m.group(4)
        if n_num != n_den:
            return m.group(0)
        return f"Derivative({func}({var}), ({var}, {n_num}))"

    result_str = re.sub(
        rf"d\s*(?:\^\s*(\d+)|\*\*\s*(\d+))\s*{re.escape(func)}\s*/\s*d\s*{re.escape(var)}"
        rf"\s*(?:\^\s*(\d+)|\*\*\s*(\d+))",
        _leibniz_ho_repl,
        result_str,
    )
    result_str = re.sub(
        rf"\bd\s*{re.escape(func)}\s*/\s*d\s*{re.escape(var)}\b",
        f"Derivative({func}({var}), {var})",
        result_str,
    )

    # Pattern: diff(C, t), diff(C(t), t), diff(C, t, 2), diff(C(t), t, 2)
    pattern = rf"diff\({func}\s*(?:\(\s*{var}\s*\))?\s*,\s*{var}(?:\s*,\s*(\d+))?\)"

    def _make_deriv(m: re.Match[str]) -> str:
        order_str = m.group(1)
        order = int(order_str) if order_str else 1
        if order == 1:
            return f"Derivative({func}({var}), {var})"
        return f"Derivative({func}({var}), ({var}, {order}))"

    result_str = re.sub(pattern, _make_deriv, result_str)

    # Replace any remaining bare dependent variable with the function call form.
    result_str = re.sub(rf"\b{func}\b(?!\s*\()", f"{func}({var})", result_str)

    # Delegate to the shared parser instead of rebuilding its local_dict stack
    # here. ``parse_expression_string`` already protects reserved names, binds
    # other call sites (e.g. a forcing term ``f(t)``) to undefined functions,
    # splits ``=`` into ``Eq``, and folds unevaluated divisions; the only extra
    # binding this operation needs is ``func`` itself as a Function, plus the
    # reserved call names SymPy would otherwise evaluate away.
    local_dict = {func: sp.Function(func)}
    for name in _DEGENERATE_CALL_NAMES:
        if name != func and re.search(rf"(?<![A-Za-z0-9_.]){name}\s*\(", result_str):
            local_dict[name] = sp.Function(name)
    expr, error = parse_expression_string(
        result_str,
        convert_equation=True,
        preprocess=False,  # result_str is already unicode/Leibniz-processed
        local_dict=local_dict,
    )
    if expr is None:
        return None, f"Cannot parse ODE. {_NOTATION_HINT}"

    # If the user gave an expression, turn it into an equation equal to 0.
    if not isinstance(expr, sp.Equality):
        expr = sp.Eq(expr, 0)

    if not expr.atoms(sp.Derivative):
        return None, (
            f"No derivative of {func} with respect to {var} found — dsolve "
            f"requires an ODE. {_NOTATION_HINT}"
        )
    return expr, None


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
                 {"simplify", "solve", "substitute", "parse", "evalf", "dimension"})


# ── Parameter-consumption audit ─────────────────────────────────────────
#
# Fail-loud discipline: a caller-supplied parameter must either be consumed
# by the requested operation or the call is rejected. Defaults that the
# caller did not deviate from never reject.

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
    "ics": None,
    "units": None,
}

_PARAM_USE: dict[str, frozenset[str]] = {
    "parse": frozenset(),
    "dimension": frozenset({"units"}),
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
    "integrate": frozenset({"variable", "lower", "upper", "method"}),
    "limit": frozenset({"variable", "point", "direction"}),
    "series": frozenset({"variable", "point", "order"}),
    "dsolve": frozenset({"variable", "with_respect_to", "ics"}),
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


def _unconsumed_params(operation: str, provided: dict[str, Any]) -> list[str]:
    """Parameters the caller set that the operation does not consume."""
    allowed = _PARAM_USE.get(operation, frozenset())
    rejected: list[str] = []
    for name, default in _KNOB_DEFAULTS.items():
        if name in allowed:
            continue
        if provided.get(name, default) != default:
            rejected.append(
                f"Parameter '{name}' is not used by operation "
                f"'{operation}' and the call was rejected."
            )
    return rejected


def _execute_operation(
    operation: str,
    expr_str: Any,
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
    ics: dict[str, Any] | None = None,
    units: dict[str, str] | None = None,
    assumption_context: MathContext | None = None,
) -> dict[str, Any]:
    """Execute a single math operation and return its result dict.
    Inapplicable parameters produce ``warnings`` entries (fail-loud);
    ``assumption_context`` scopes assumptions to this call.
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
        "ics": ics,
        "units": units,
    }
    # Unknown ops reach the dispatcher's own message (r17 task-17: 'sum' reported a
    # parameter error for an operation that does not exist).
    rejected = _unconsumed_params(operation, provided) if operation in ALL_OPS else []
    if rejected:
        return {"success": False, "error": "; ".join(rejected)}
    return _execute_operation_inner(
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
        ics=ics,
        units=units,
        assumption_context=assumption_context,
    )


def _execute_operation_inner(
    operation: str,
    expr_str: Any,
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
    ics: dict[str, Any] | None = None,
    units: dict[str, str] | None = None,
    assumption_context: MathContext | None = None,
) -> dict[str, Any]:
    """Execute one operation; see :func:`_execute_operation` for the contract."""
    preprocessed = _preprocess(expr_str)
    if (guard := matrix_exp_guard(operation, preprocessed, substitution)) is not None:
        return guard
    context = _effective_context(assumption_context)

    # Helper to parse with consistent error handling
    def _parse(expr: str) -> tuple[sp.Expr | None, str | None]:
        try:
            return _parse_math_expression(expr)
        except ValueError as exc:  # additive-scale guard (r16 task-05)
            return None, str(exc)

    # Helper to require a successful parse
    def _require_parse(expr: str) -> sp.Expr | dict[str, Any]:
        parsed, error = _parse(expr)
        if parsed is None:
            return {"success": False, "error": f"Cannot parse: {error}"}
        return parsed

    # Helper to require a successful parse and apply context assumptions
    def _require_parse_with_assumptions(expr: str) -> sp.Expr | dict[str, Any]:
        parsed = _require_parse(expr)
        if isinstance(parsed, dict) and "success" in parsed:
            return parsed
        if isinstance(parsed, dict):
            # ``factorint(1)`` / ``divisors(...)`` parse to a python dict; the
            # dispatch's error-dict convention must not swallow it (r17 task-17).
            return {"success": False, "error": f"Cannot use {expr}: it evaluates to a mapping, not an expression"}
        return _apply_context_assumptions(parsed, context)

    input_obj: Any = None
    result: Any = None
    op_warnings: list[str] = []
    extra: dict[str, Any] = {}

    # ── SYNTACTIC OPERATIONS ──
    if operation in _SYNTACTIC_OPS and operation not in ("collect", "apart"):
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        result = getattr(sp, operation)(parsed)
    elif operation == "collect":
        if not variable:
            return {"success": False, "error": "collect requires variable parameter"}
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        var = _resolve_variable_symbol(parsed, variable, context)
        result = sp.collect(parsed, var)
    elif operation == "apart":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        var = _resolve_variable_symbol(parsed, variable or "x", context)
        result = sp.apart(parsed, var)

    # ── PARSE ONLY ──
    elif operation == "parse":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = result = parsed
        extra["symbols"] = symbol_names(parsed)

    # ── NUMERIC EVALUATION ──
    elif operation == "evalf":
        parsed = _require_parse_with_assumptions(preprocessed)
        if isinstance(parsed, dict):
            return parsed
        input_obj = parsed
        subs: dict[sp.Basic, Any] | None = None
        if substitution:
            subs, subs_error = _build_subs_dict(substitution)
            if subs_error is not None:
                return subs_error
            subs = _rekey_subs_to_expression(parsed, subs or {})
        result, op_warnings = numeric_evalf(dense_matrix_form(parsed), subs)

    # ── SOLVE ──
    elif operation == "solve":
        try:
            # The shared parser already converts a single '=' to Eq(...).
            parsed = _require_parse_with_assumptions(preprocessed)
            if isinstance(parsed, dict):
                return parsed
            input_obj = parsed
            # A bracket list parses to a Matrix (run-020); a flat one is an
            # equation list, not a matrix op. A set literal has no solution
            # semantics at all (F3/F15).
            parsed = flat_matrix_equations(parsed)
            if isinstance(parsed, (set, frozenset)):
                return set_literal_solve_error()
            # Infer the solve variable when omitted: a single free symbol is
            # unambiguous; otherwise list the candidates instead of the terse
            # "solve requires variable parameter" (run-021).
            if not variable:
                if isinstance(parsed, sp.Basic):
                    free_names = {str(s) for s in parsed.free_symbols}
                elif isinstance(parsed, (list, tuple)):
                    free_names = {str(s) for eq in parsed for s in eq.free_symbols}
                else:
                    free_names = set()
                free = sorted(free_names)
                if len(free) == 1:
                    variable = free[0]
                else:
                    return {
                        "success": False,
                        "error": (
                            "solve requires the variable parameter; the "
                            f"expression has free symbols: {', '.join(free)}. "
                            "Pass one of them as variable."
                        ),
                    }
            # A comma-separated expression parses to a python tuple — treat it
            # as a system of equations (run-018).
            if isinstance(parsed, (list, tuple)):
                return solve_system(parsed, variable, context, input_obj, operation)
            # Curated refusals for a non-symbol solve variable and for a
            # relational input (inequalities), before SymPy can leak internals
            # or answer a misleading "No solution found" (F27).
            if (name_error := solve_variable_name_error(variable or "")) is not None:
                return name_error
            if (ineq_error := inequality_solve_error(parsed)) is not None:
                return ineq_error
            v = _resolve_variable_symbol(parsed, variable, context)
            eq = parsed
            solutions = list(sp.solve(eq, v))
            # Assumptions can cancel a factor that is nonzero in the symbol's
            # domain, silently dropping the zero root of a factored equation
            # (r14 task-15: I positive hid I*(beta*S/N - gamma) = 0 at I = 0).
            solutions, filtered, restored = restore_zero_root(eq, v, solutions)
            return assemble_solve_response(
                eq, v, solutions, filtered, restored,
                variable or "", operation, input_obj,
            )
        except Exception as e:
            curated = applied_function_solve_error(e)
            if curated is not None:
                return curated
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
        result = expr.subs(_rekey_subs_to_expression(expr, subs)).doit()
        if getattr(result, "atoms", None) and result.atoms(sp.nan, sp.zoo):
            # A singular substitution must not come back as success carrying
            # nan (r14 task-10: zeta=1 in the underdamped closed form).
            return {
                "success": False,
                "error": (
                    "Substitution is undefined here (nan/zoo): the expression "
                    "is singular at this value. The underdamped second-order "
                    "closed form (1/sqrt(1 - zeta**2)) is undefined at zeta=1; "
                    "critical damping needs the separate limit or reduced-"
                    "denominator form."
                ),
            }

    # ── DIMENSIONAL ANALYSIS ──
    elif operation == "dimension":
        return dimension_operation(preprocessed, units, get_session())

    elif operation in ("curl", "divergence"):
        return vector_operation(operation, expr_str, variable, context)

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
            outcome = integrate_operation(
                preprocessed, input_obj, expr_obj, variable, lower, upper,
                context, method, _engine,
            )
            if isinstance(outcome, dict):
                return outcome
            result, out = outcome
        elif operation == "limit":
            pt = point or "0"
            out = _engine.limit(expr_obj, v, pt, direction, context)
        elif operation == "series":
            pt = point or "0"
            out = _engine.series(expr_obj, v, pt, order, context)
        elif operation == "dsolve":
            func_var = with_respect_to or "t"
            # Parse as ODE: convert "diff(y,t) - k*y" or "dy/dt - k*y" to SymPy form
            ode_expr, ode_error = _parse_ode(preprocessed, v, func_var)
            if ode_expr is None:
                return {"success": False, "error": ode_error or "Cannot parse ODE"}
            # Context assumptions (k, m positive) shape the solution form; without
            # them sympy returns complex-root exponentials, not the trig form.
            ode_expr = _apply_context_assumptions(ode_expr, context)
            # Fail with an actionable message when the requested dependent
            # variable is not the one in the input.  Otherwise SymPy reports
            # "is not a solvable differential equation in u(t)", which reads as
            # if the equation were unsolvable (P5).
            applied = sorted(
                {a.func.__name__ for a in ode_expr.atoms(AppliedUndef)}
            )
            if applied and v not in applied:
                suggestion = ", ".join(f"variable='{name}'" for name in applied)
                return {
                    "success": False,
                    "error": (
                        f"dsolve: variable='{v}' does not appear in the input; "
                        f"the dependent function there is "
                        f"{', '.join(applied)}. Pass {suggestion} instead."
                    ),
                }
            # A second undefined function coupled to the dependent one (sharing
            # an additive term) makes the single equation underdetermined —
            # SymPy used to return a fake closed form silently (r14 task-15).
            coupled = coupled_undefined_functions(
                ode_expr, v, sorted(set(applied) - {v})
            )
            if coupled:
                names = ", ".join(f"{n}({func_var})" for n in coupled)
                return {
                    "success": False,
                    "error": (
                        f"coupled or underdetermined ODE: found undefined "
                        f"function(s) {names} besides the dependent variable "
                        f"{v}({func_var}); systems of ODEs are not supported yet."
                    ),
                }
            # sympy.dsolve does not raise on an unsolvable nonlinear ODE, it spins,
            # wedging the single-process server (round-complex). Refuse up front.
            hang_reason = nonpolynomial_ode_reason(ode_expr, v)
            if hang_reason:
                return {"success": False, "error": f"dsolve: {hang_reason}"}
            ics_objs: dict[Any, Any] | None = None
            if ics:
                ics_objs, ics_error = _build_ics_dict(ics, v, func_var)
                if ics_error is not None:
                    return ics_error
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
            out = _engine.dsolve(ode_obj, v, func_var, context, ics=ics_objs)
        elif operation in ("gradient", "laplacian"):
            coords = [c.strip() for c in (variable or "x,y,z").split(",")]  # not v: it defaults to "x" (D11)
            if operation == "gradient":
                out = _engine.gradient(expr_obj, coords, context)
            else:
                out = _engine.laplacian(expr_obj, coords, context)
        elif operation in ("det", "inv", "eigenvals", "eigenvects"):
            if operation == "det":
                out = _engine.matrix_det(expr_obj, context)
            elif operation == "inv":
                out = _engine.matrix_inv(expr_obj, context)
            elif operation == "eigenvals":
                vals = _engine.matrix_eigenvals(expr_obj, context)
                # A sympy Tuple keeps the result a valid Basic so the step
                # records into the chain and the display renders (run-017).
                result_obj = sp.Tuple(*[v.sympy_expr for v in vals])
                return {
                    "success": True,
                    "eigenvalues": [e.raw for e in vals],
                    "eigenvalues_latex": [e.latex for e in vals],
                    "expression": str(result_obj),
                    "latex": sp.latex(result_obj),
                    "operation": operation,
                    "_input_obj": input_obj,
                    "_result_obj": result_obj,
                }
            else:  # eigenvects
                vects = _engine.matrix_eigenvects(expr_obj, context)
                # As with eigenvals (run-017), wrap the result in a sympy Tuple so it
                # records into the session chain and renders (run-020).
                vects_obj: sp.Basic | None = None
                try:
                    items = []
                    for entry in vects:
                        val = sp.sympify(entry["eigenvalue"])
                        vec_objs = [sp.sympify(v) for v in entry["vectors"]]
                        items.append(
                            sp.Tuple(val, sp.Integer(entry["multiplicity"]), *vec_objs)
                        )
                    vects_obj = sp.Tuple(*items)
                except Exception:
                    vects_obj = None
                return {
                    "success": True,
                    "eigenvectors": vects,
                    "expression": str(vects_obj) if vects_obj is not None else "",
                    "latex": sp.latex(vects_obj) if vects_obj is not None else "",
                    "operation": operation,
                    "_input_obj": input_obj,
                    "_result_obj": vects_obj,
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

        if out is not None:
            if not out.is_valid:
                return {"success": False, "error": _engine_failure(operation, out.error)}
            result = out.sympy_expr

        if operation == "integrate":
            op_warnings.extend(antiderivative_warnings(result, lower, upper))

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
        **({"warnings": op_warnings} if op_warnings else {}),
        **extra,
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
    "evalf": OperationType.EVALF,
}

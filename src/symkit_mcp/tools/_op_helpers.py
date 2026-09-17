"""Operation-branch helpers extracted from the frozen math dispatcher.

``_math_dispatch.py`` is size-frozen by the modularity ratchet, so the
per-operation input guards and post-processing that grew with the r19 defects
live here: bracketed-system routing (F3), the set-literal refusal (F15), the
parse symbol list (F14), the ``integrate`` method / antiderivative handling
(F12/F13), and the scalar ``solve`` response assembly (F22/F27).
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.core.relational import Equality, Relational

_INTEGRATE_METHODS: tuple[str, ...] = ("auto", "risch")

# A Boolean must never leave the solve branch as an "expression": under a
# positive assumption on the solve variable, ``sp.Eq(Omega, 0)`` auto-evaluates
# to the Boolean ``False`` (positive implies nonzero), so the headline came
# back as "False" with ``solution: "0"`` (r19 F22).  SymPy can also hand a
# Boolean back where a root was expected; both are dropped.
_BOOLEAN_TYPES: tuple[type, ...] = (bool, sp.logic.boolalg.Boolean)

# A function's defining module identifies it as non-elementary: elementary
# antiderivatives (log, exp, trig) live under ``sympy.functions.elementary``,
# while anything the user cannot write with elementary functions (erfi, Si,
# Ei, bessel*, hyper, meijerg, gamma, zeta, ...) lives under ``*.special``.
_SPECIAL_MODULE_PREFIX = "sympy.functions.special"


def symbol_names(parsed: Any) -> list[str]:
    """Sorted free-symbol names for a ``parse`` response.

    A matrix literal has no single symbol set and a constant has none at all,
    so both answer with an empty list rather than crashing (F14).
    """
    if isinstance(parsed, sp.MatrixBase) or not isinstance(parsed, sp.Basic):
        return []
    return sorted({str(symbol) for symbol in parsed.free_symbols})


def flat_matrix_equations(parsed: Any) -> Any:
    """Turn a flat (row/column) matrix literal into a plain list of equations.

    The parser folds a bracket list ``[x+y-3, x-y-1]`` into a column vector
    (run-020), so the solve branch never saw the equation list and answered
    "No solution found for x, y". A genuine 2-D matrix is returned unchanged
    and keeps the pre-existing matrix-solve behavior (F3).
    """
    if not isinstance(parsed, sp.MatrixBase) or not parsed.shape or 0 in parsed.shape:
        return parsed
    rows, cols = parsed.shape
    if rows > 1 and cols > 1:
        return parsed
    entries = list(parsed)
    if any(isinstance(entry, sp.MatrixBase) for entry in entries):
        return parsed
    return entries


def set_literal_solve_error() -> dict[str, Any]:
    """Curated refusal for a ``{...}`` set literal handed to ``solve`` (F15)."""
    return {
        "success": False,
        "error": (
            "solve: sets are not supported; pass equations as a "
            'comma-separated list ("eq1, eq2") or a bracket list '
            '("[eq1, eq2]").'
        ),
    }


def integrate_method_error(method: str, lower: Any, upper: Any) -> str | None:
    """Reject an unsupported ``method`` value for ``integrate`` (F13)."""
    if method not in _INTEGRATE_METHODS:
        supported = ", ".join(repr(name) for name in _INTEGRATE_METHODS)
        return (
            f"integrate: method '{method}' is not supported; use one of "
            f"{supported}."
        )
    if method == "risch" and (lower is not None or upper is not None):
        return (
            "integrate: method 'risch' applies to indefinite integrals only; "
            "drop lower/upper or use method 'auto'."
        )
    return None


def _inline_integral_value(
    preprocessed: Any, input_obj: Any, variable: Any, lower: Any, upper: Any
) -> Any:
    """Inline integral value; ``False`` on failure, ``None`` if not applicable."""
    if variable is not None or lower is not None or upper is not None:
        return None
    if not isinstance(preprocessed, str) or not re.search(
        r"(?<![A-Za-z0-9_.])(?:integrate|Integral)\s*\(", preprocessed
    ):
        return None
    value = input_obj.doit() if input_obj.has(sp.Integral) else input_obj
    return value if not value.has(sp.Integral) else False


def _risch_integrate(expr: Any, variable: str) -> Any:
    """Indefinite integration through SymPy's Risch algorithm (F13)."""
    symbol = next(
        (s for s in expr.free_symbols if str(s) == variable), sp.Symbol(variable)
    )
    return sp.integrate(expr, symbol, risch=True)


def integrate_operation(
    preprocessed: Any,
    input_obj: Any,
    expr_obj: Any,
    variable: str | None,
    lower: str | None,
    upper: str | None,
    context: Any,
    method: str,
    engine: Any,
) -> Any:
    """Run the ``integrate`` branch without growing the frozen dispatcher.

    ``variable`` is the caller's value (``None`` when omitted; the inline
    nested-integral path keys off that). Returns ``(result, out)`` on success —
    ``out`` is the engine result object, or ``None`` when the value came back
    inline or from the Risch path — or an error dict.
    """
    symbol = variable or "x"
    if (error := integrate_method_error(method, lower, upper)) is not None:
        return {"success": False, "error": error}
    inline = (
        _inline_integral_value(preprocessed, input_obj, variable, lower, upper)
        if method == "auto"
        else None
    )
    if inline is False:
        return {
            "success": False,
            "error": (
                "integrate: the nested definite integral did not evaluate in "
                "closed form; pass the inner Integral with explicit lower/upper "
                "for the outer variable, or add assumptions."
            ),
        }
    if inline is not None:
        return inline, None
    if method == "risch":
        return _risch_integrate(input_obj, symbol), None
    return None, engine.integrate(expr_obj, symbol, lower, upper, context)


def antiderivative_warnings(result: Any, lower: Any, upper: Any) -> list[str]:
    """Warn when an indefinite antiderivative needs special functions (F12).

    The tool used to answer ``sqrt(pi)*erfi(x)/2`` for ``exp(x**2)`` with no
    disclosure that the result left the elementary functions. The warning does
    not change the success verdict or the expression.
    """
    if result is None or lower is not None or upper is not None:
        return []
    if not hasattr(result, "atoms"):
        return []
    names = sorted(
        {
            type(function).__name__
            for function in result.atoms(sp.Function)
            if (type(function).__module__ or "").startswith(_SPECIAL_MODULE_PREFIX)
        }
    )
    if not names:
        return []
    return [
        "Antiderivative uses special function(s): "
        + ", ".join(names)
        + " — not expressible with elementary functions"
    ]


def solve_variable_name_error(variable: str) -> dict[str, Any] | None:
    """Reject a ``solve`` variable that is not a plain symbol name (F27).

    ``math("solve", "v**4 - 2", variable="v**2")`` used to report "No solution
    found for v**2", which reads as "the equation has no solutions".  The real
    problem is the *variable* spelling.
    """
    if variable.strip().isidentifier():
        return None
    return {
        "success": False,
        "error": (
            "solve variable must be a symbol name; got "
            f"'{variable}'. To solve for a power, introduce a substitution "
            f"(e.g. u = {variable}) first."
        ),
    }


def inequality_solve_error(parsed: Any) -> dict[str, Any] | None:
    """Curated refusal when ``solve`` is handed a relational (F27).

    SymPy's ``solve_univariate_inequality`` failure text leaked the internal
    expression and algorithm name (``_DH/(_R*x**2) > 0 ... cannot be solved
    using solve_univariate_inequality``) and sometimes an ``'StrictLessThan'
    object is not iterable`` traceback.  ``Eq`` is not an inequality and stays
    on the normal solve path.
    """
    candidates = parsed if isinstance(parsed, (list, tuple)) else [parsed]
    relational = any(
        isinstance(entry, Relational) and not isinstance(entry, Equality)
        for entry in candidates
        if isinstance(entry, sp.Basic)
    )
    if not relational:
        return None
    return {
        "success": False,
        "error": (
            "inequality solving is not supported; use an equation (A = B) or "
            "check the sign of a simplified expression instead"
        ),
    }


_SOLVE_APPLIED_FORM_MESSAGE = (
    "solve could not handle these expressions (they contain applied functions "
    "such as f(t) or an unsupported form); substitute known values or reduce to "
    "algebraic equations in plain symbols first, or use dsolve for differential "
    "equations"
)

# Operand/attribute misuse, not "no solution": SymPy raises a bare TypeError
# naming internal classes (``FunctionClass``, ``UndefinedFunction``) when the
# expressions carry an applied function or a form it cannot treat algebraically.
_SOLVE_OPERAND_MARKERS: tuple[str, ...] = (
    "unsupported operand",
    "FunctionClass",
    "UndefinedFunction",
    "has no attribute",
)


def applied_function_solve_error(exc: BaseException) -> dict[str, Any] | None:
    """Curate the raw operand ``TypeError``/``AttributeError`` ``solve`` leaks (F35).

    A bracketed system whose solution values are compound expressions failed in
    the post-solve re-parse with ``"Solve failed: unsupported operand type(s)
    for ** or pow(): 'FunctionClass' and 'Integer'"`` — text naming SymPy
    internals and pointing nowhere (r19x-task-08).  Only operand/attribute
    failures are converted; a genuine empty result keeps its "No solution"
    answer.
    """
    if not isinstance(exc, (TypeError, AttributeError)):
        return None
    if not any(marker in str(exc) for marker in _SOLVE_OPERAND_MARKERS):
        return None
    return {"success": False, "error": _SOLVE_APPLIED_FORM_MESSAGE}


def _split_boolean_solutions(
    solutions: list[Any],
) -> tuple[list[Any], int]:
    """Drop Boolean entries SymPy handed back where a root was expected (F22)."""
    kept = [sol for sol in solutions if not isinstance(sol, _BOOLEAN_TYPES)]
    return kept, len(solutions) - len(kept)


def _select_headline_root(
    kept: list[Any], excluded: set[str]
) -> tuple[Any, str | None]:
    """First kept root the response does not itself report as excluded (F22).

    Among the non-excluded roots the historical preference is preserved: a root
    provably positive under the active assumptions wins, else one without a
    minus sign.  Falls back to the first kept root with an explicit warning when
    every root is excluded or restored.
    """
    candidates = [sol for sol in kept if str(sol) not in excluded]
    if not candidates:
        return kept[0], (
            "Every root was excluded by the active assumptions; the headline "
            "'solution' shows the first one that was restored — check "
            "all_solutions and the assumptions."
        )
    for sol in candidates:
        if getattr(sol, "is_positive", None):
            return sol, None
    for sol in candidates:
        if not sol.could_extract_minus_sign():
            return sol, None
    return candidates[0], None


def _solve_disclosure_warnings(
    eq: Any, reported_filtered: list[str], restored: bool, variable: str
) -> list[str]:
    """Float-truncation, root-filtering and zero-root-restore disclosures."""
    warnings: list[str] = []
    float_atoms = sorted(eq.atoms(sp.Float), key=str) if hasattr(eq, "atoms") else []
    if float_atoms:
        shown = ", ".join(str(f) for f in float_atoms[:3])
        warnings.append(
            "Input contains float coefficients (" + shown + "); the "
            "solution is numerically truncated. Use exact fractions "
            "(e.g. 1/2 instead of 0.5) for exact symbolic results."
        )
    if reported_filtered:
        warnings.append(
            "Solutions omitted by the active assumptions on "
            f"{variable}: {', '.join(reported_filtered)}."
        )
    if restored:
        warnings.append(
            f"The trivial root 0 was excluded by the assumptions on "
            f"{variable} and has been restored."
        )
    return warnings


def assemble_solve_response(
    eq: Any,
    v: Any,
    solutions: list[Any],
    filtered: list[str],
    restored: bool,
    variable: str,
    operation: str,
    input_obj: Any,
) -> dict[str, Any]:
    """Build the scalar ``solve`` response (extracted from the frozen dispatcher).

    Fixes the F22 headline contradiction: a restored root is kept in
    ``all_solutions`` but must not also be reported in
    ``filtered_by_assumptions``; the headline ``solution``/``expression`` must
    be the first kept *non-excluded* root and must never be a Boolean.
    """
    kept, dropped_booleans = _split_boolean_solutions(solutions)
    if not kept:
        return {"success": False, "error": f"No solution found for {variable}"}

    # A restored root was re-added because the assumptions had cancelled it, so
    # it is "excluded", never "filtered" in the same response (F22).
    reported_filtered = [s for s in filtered if s != "0"] if restored else list(filtered)
    excluded = set(reported_filtered) | ({"0"} if restored else set())
    sol, fallback_warning = _select_headline_root(kept, excluded)
    # ``evaluate=False`` keeps the headline an ``Eq`` even when the symbol's
    # assumptions make SymPy collapse it to a Boolean (F22).
    result = sp.Eq(v, sol, evaluate=False)
    warnings = _solve_disclosure_warnings(eq, reported_filtered, restored, variable)
    if len(kept) > 1:
        # The scalar path kept every root in ``all_solutions`` but the headline
        # showed one without saying so (r22 task-07); the system path already
        # discloses this ("first of N solutions").
        warnings.append(
            f"The headline 'solution' shows the first of {len(kept)} solutions; "
            "see all_solutions for the full set."
        )
    if dropped_booleans:
        warnings.insert(
            0,
            f"SymPy returned {dropped_booleans} Boolean value(s) in place of a "
            "solution under the active assumptions; dropped from the solution set.",
        )
    if fallback_warning is not None:
        warnings.append(fallback_warning)
    return {
        "success": True,
        "expression": str(result),
        "latex": sp.latex(result),
        "solution": str(sol),
        "solution_latex": sp.latex(sol),
        "all_solutions": [str(s) for s in kept],
        "filtered_by_assumptions": reported_filtered,
        "warnings": warnings,
        "operation": operation,
        "_input_obj": input_obj,
        "_result_obj": result,
    }

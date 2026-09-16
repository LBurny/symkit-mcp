"""System (multi-equation) ``solve`` response assembly.

Extracted from the math dispatcher so the tuple/list solve branch can apply the
active assumptions to every solution — the scalar branch gets this for free
because SymPy filters a single equation's roots, but ``solve`` on a system
ignores symbol assumptions and returned positive-violating equilibria such as
``(0, 0, 12, 0)`` with no disclosure (r16 task-20).  It also flags the
long-standing headline bias: ``solution`` only ever shows the first root while
the rest hide in ``all_solutions`` (r16 task-04/07/10/20).
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.value_objects import MathContext
from symkit_mcp.tools._op_helpers import applied_function_solve_error

# Asserted property -> predicate that is True when a solution value *provably*
# violates it.  Symbolic or otherwise undecidable values yield None and are
# always kept: a filter must never drop a root it cannot judge.
_VIOLATION_CHECKS: dict[str, Any] = {
    "positive": lambda v: v.is_nonpositive,
    "extended_positive": lambda v: v.is_nonpositive,
    "negative": lambda v: v.is_nonnegative,
    "extended_negative": lambda v: v.is_nonnegative,
    "nonnegative": lambda v: v.is_negative,
    "extended_nonnegative": lambda v: v.is_negative,
    "nonpositive": lambda v: v.is_positive,
    "extended_nonpositive": lambda v: v.is_positive,
    "nonzero": lambda v: v.is_zero,
    "zero": lambda v: v.is_nonzero,
    "real": lambda v: v.is_real is False,
    "rational": lambda v: v.is_rational is False,
    "integer": lambda v: v.is_integer is False,
    "irrational": lambda v: v.is_irrational is False,
}


def _solution_pairs(solution: Any, variables: list[sp.Symbol]) -> list[tuple[Any, Any]]:
    """Pair each solve variable with its value in one solution entry."""
    if isinstance(solution, dict):
        return [(sym, solution.get(sym)) for sym in variables]
    if isinstance(solution, (tuple, list, sp.Tuple)):
        return list(zip(variables, solution, strict=False))
    return [(variables[0], solution)] if variables else []


def solution_violations(
    solution: Any, variables: list[sp.Symbol], context: MathContext | None
) -> list[str]:
    """Assumption properties this solution provably violates (``"x positive"``)."""
    violations: list[str] = []
    for sym, value in _solution_pairs(solution, variables):
        if value is None:
            continue
        props = context.assumptions.get(str(sym), {}) if context else {}
        for name, asserted in props.items():
            check = _VIOLATION_CHECKS.get(name)
            if not asserted or check is None:
                continue
            try:
                if check(value) is True:
                    violations.append(f"{sym} {name}")
                    break
            except Exception:
                continue
    return violations


def _partition_solutions(
    solutions: list[Any], variables: list[sp.Symbol], context: MathContext | None
) -> tuple[list[Any], list[str], list[str]]:
    """Split solutions into kept ones and assumption-violating ones."""
    kept: list[Any] = []
    dropped: list[str] = []
    reasons: list[str] = []
    for solution in solutions:
        violations = solution_violations(solution, variables, context)
        if violations:
            dropped.append(str(solution))
            reasons.append(
                f"{solution} violates active assumption: {', '.join(violations)}"
            )
        else:
            kept.append(solution)
    return kept, dropped, reasons


def _assemble_system_response(
    solutions: Any,
    variables: list[sp.Symbol],
    context: MathContext | None,
    variable: str,
    operation: str,
    input_obj: Any,
) -> dict[str, Any]:
    """Normalize, assumption-filter and render one system's ``solve`` answer."""
    # sp.solve returns a dict for a single solution, a list of dicts/tuples
    # otherwise — normalize to a list (run-018; solutions[0] on the dict
    # raised a bare KeyError: 0).
    if isinstance(solutions, dict):
        solutions = [solutions]
    if not solutions:
        return {"success": False, "error": f"No solution found for {variable}"}

    kept, dropped, reasons = _partition_solutions(solutions, variables, context)
    if not kept:
        return {
            "success": False,
            "error": f"No solution found for {variable} under the active assumptions",
        }

    warnings: list[str] = []
    if dropped:
        warnings.append(
            "Solutions omitted by the active assumptions: " + "; ".join(reasons) + "."
        )
    if len(kept) > 1:
        warnings.append(
            f"headline 'solution' shows the first of {len(kept)} solutions; "
            "see all_solutions for the rest"
        )
    first = kept[0]
    # A compound answer re-parsed through ``sympify(str(first))`` raised a bare
    # operand TypeError naming SymPy internals (r19 F35).
    result = sp.sympify(str(first))
    return {
        "success": True,
        "expression": str(result),
        "latex": sp.latex(result),
        "solution": str(first),
        "solution_latex": sp.latex(result),
        "all_solutions": [str(s) for s in kept],
        "filtered_by_assumptions": dropped,
        "warnings": warnings,
        "operation": operation,
        "_input_obj": input_obj,
        "_result_obj": result,
    }


def solve_system(
    parsed: Any,
    variable: str,
    context: MathContext | None,
    input_obj: Any,
    operation: str,
) -> dict[str, Any]:
    """Solve a system of equations and build the math-tool response dict."""
    eqs = list(parsed)
    eq_syms: set[Any] = set()
    for eq in eqs:
        eq_syms |= set(eq.free_symbols)
    var_names = [name.strip() for name in variable.split(",") if name.strip()]
    variables = [
        next((s for s in eq_syms if str(s) == name), None) or sp.Symbol(name)
        for name in var_names
    ]
    try:
        solutions = sp.solve(eqs, variables)
        return _assemble_system_response(
            solutions, variables, context, variable, operation, input_obj
        )
    except (TypeError, AttributeError) as exc:
        curated = applied_function_solve_error(exc)
        if curated is not None:
            return curated
        raise

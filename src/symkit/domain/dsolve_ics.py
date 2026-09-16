"""Bounded application of ``dsolve`` initial conditions.

``sympy.dsolve(eq, f(v), ics=...)`` solves for the integration constants with
``solve``, which has no internal bound.  For a linear ODE whose characteristic
roots are nested radicals -- ``y''' - 7y'' + 16y' - 13y = 0`` with three initial
conditions -- that solve never returns and wedges the single-process MCP server
(r18 A1: >900 s live, >90 s under the probe cap).  The constants of a linear
general solution enter linearly, so a bounded linear solve recovers them in
milliseconds.  Past an operation budget the call refuses with a curated reason
instead of risking the process.

Pure domain module: depends only on SymPy.
"""

from __future__ import annotations

from typing import Any

import sympy as sp
from sympy.core.function import AppliedUndef

# Past this operation count the initial-condition system is refused rather than
# solved.  The style mirrors ``verification_guardrails.INTEGRATION_OPS_CAP``:
# bound the work, then report a refusal, never spin.
DSOLVE_ICS_OPS_CAP = 2000


def _condition_parts(key: Any, value: Any) -> tuple[int, sp.Basic, sp.Basic] | None:
    """Split one ``ics`` entry into ``(derivative_order, point, value)``."""
    if isinstance(key, AppliedUndef):
        return 0, key.args[0], value
    if isinstance(key, sp.Subs) and isinstance(key.args[0], sp.Derivative):
        return key.args[0].derivative_count, key.args[-1][0], value
    return None


def _integration_constants(
    general_rhs: sp.Basic, equation: sp.Basic
) -> list[sp.Symbol]:
    """The arbitrary constants the general solution adds beyond the ODE symbols."""
    return sorted(
        (s for s in general_rhs.free_symbols if s not in equation.free_symbols),
        key=str,
    )


def _refusal(detail: str) -> str:
    """A curated reason for skipping the bounded constant solve."""
    return (
        f"initial-condition solve skipped: {detail}. sympy.dsolve's constant "
        f"solve has no bound against these characteristic roots and would wedge "
        f"the server; take the general solution and apply the conditions "
        f"manually, or solve the initial-value problem numerically."
    )


def _particular_solution(
    equation: sp.Basic,
    general: sp.Equality,
    var: sp.Symbol,
    ics: dict[Any, Any],
) -> tuple[sp.Equality | None, str | None]:
    """Apply ``ics`` to ``general`` through a bounded linear solve.

    Returns ``(solution, None)`` on success, ``(None, reason)`` when the system
    is too costly or singular (refuse) and ``(None, None)`` when this route does
    not apply (the caller may fall back to ``sympy.dsolve``).
    """
    consts = _integration_constants(general.rhs, equation)
    equations: list[sp.Equality] = []
    for key, value in ics.items():
        parts = _condition_parts(key, value)
        if parts is None:
            return None, None
        order, point, target = parts
        equations.append(
            sp.Eq(sp.diff(general.rhs, var, order).subs(var, point), target)
        )
    if not consts or len(equations) != len(consts):
        return None, None
    if sp.count_ops(general.rhs) > DSOLVE_ICS_OPS_CAP:
        return None, _refusal("the general solution is too large to differentiate")
    try:
        matrix, rhs = sp.linear_eq_to_matrix(equations, consts)
    except Exception:
        # Nonlinear in the constants (separable/Bernoulli): not this route.
        return None, None
    if sp.count_ops(matrix) > DSOLVE_ICS_OPS_CAP:
        return None, _refusal("the initial-condition system is too large")
    try:
        solved = matrix.inv() * rhs
    except Exception:
        return None, _refusal("the initial-condition system is singular")
    particular = general.rhs.subs(dict(zip(consts, list(solved), strict=True)))
    return sp.Eq(general.lhs, particular), None


def _inconsistent_ics_reason() -> str:
    """Curated reason for a condition set SymPy's own constant solve cannot meet.

    ``sp.dsolve(..., ics=...)`` raises a bare ``ValueError: Couldn't solve for
    initial conditions`` when the conditions over-determine or contradict the
    constants.  That is a statement about the *conditions*, so it is reported
    through the same refusal channel as the bounded solve instead of leaking the
    raw exception (F8b).
    """
    return (
        "the initial conditions are inconsistent — no constants satisfy all of "
        "them (or the conditions are unsolvable in closed form); check the "
        "conditions for contradictions"
    )


def dsolve_with_ics(
    equation: sp.Basic,
    f: Any,
    var: sp.Symbol,
    ics: dict[Any, Any] | None,
) -> tuple[sp.Basic, str | None]:
    """``dsolve``, applying ``ics`` through a bounded linear solve when possible.

    Returns ``(general_or_particular_solution, refusal_reason)``; a non-``None``
    reason means no solution was produced and the caller must fail loud.
    """
    general = sp.dsolve(equation, f(var))
    if not ics:
        return general, None
    solution, reason = _particular_solution(equation, general, var, ics)
    if reason is not None:
        return general, reason
    if solution is not None:
        return solution, None
    # Constants do not enter linearly: hand back to sympy's own ICS handling.
    try:
        return sp.dsolve(equation, f(var), ics=ics), None
    except Exception:
        # A contradictory or over-determined condition set (task-16 audit) is
        # refused with a diagnostic reason, never a raw exception.
        return general, _inconsistent_ics_reason()

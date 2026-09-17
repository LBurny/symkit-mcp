"""Honesty guards for transform and ODE results.

- Laplace convergence conditions: ``noconds=True`` discarded the condition
  SymPy computed, so a step-like input with an unconstrained parameter could
  return a form valid only under unsatisfiable conditions with no disclosure
  (r23 F8).  The condition is inspected and, when it constrains free
  parameters, surfaced as a warning -- the transform itself is unchanged.
- dsolve verification: SymPy's truncated power-series route emits artifacts
  such as ``r(3)`` and an ``O(x**6)`` term that do not satisfy the ODE, yet the
  engine reported success (r23 F9).  ``checkodesol`` is consulted and a
  non-solution is refused with its residual.

Infrastructure module: owns SymPy calls the domain engine delegates to.
"""

from __future__ import annotations

from typing import Any

import sympy as sp
from sympy.core.function import AppliedUndef

# The degenerate case this disclosure exists for: a step edge whose parameter
# is unconstrained, so SymPy returns convergence conditions that no value can
# satisfy and the falling-edge form is silently unavailable.
_STEP_PARAMETER_WARNING = (
    "Laplace transform of step-like functions depends on parameter "
    "assumptions (sympy returned degenerate convergence conditions); declare "
    "parameters positive (e.g. 'tau is positive') for the falling-edge form"
)

# Beyond this operation count ``checkodesol`` is skipped: the check must not
# risk wedging the single-process server, and skipping only forgoes a refusal.
_DSOLVE_CHECK_OPS_CAP = 5000


def _is_unsatisfiable(cond: Any) -> bool:
    """True when no assignment makes *cond* true.

    ``satisfiable`` returns a dict rather than False for some conjunctions it
    cannot refute (e.g. ``(tau > 0) & (tau < 0) & Ne(1/tau, 0)``), so the
    relational is also collapsed to a set/boolean before giving up.
    """
    try:
        if sp.simplify(cond) is sp.S.false:
            return True
    except Exception:
        pass
    try:
        return cond.as_set() is sp.S.EmptySet
    except Exception:
        return False


def laplace_condition_warnings(cond: Any, *transform_vars: Any) -> list[str]:
    """Warnings for a Laplace convergence condition, if it warrants any.

    ``True``/``None`` means the transform converged unconditionally and needs
    no note.  A condition on the transform variables alone also adds nothing;
    a free parameter (the step edge, a decay rate) makes the result
    conditional and is disclosed.
    """
    if cond is None or cond is True:
        return []
    if cond is False or cond is sp.S.false:
        return [_STEP_PARAMETER_WARNING]
    free = set(cond.free_symbols) - set(transform_vars)
    if not free:
        return []
    if _is_unsatisfiable(cond):
        return [_STEP_PARAMETER_WARNING]
    names = ", ".join(sorted(str(sym) for sym in free))
    return [
        "Laplace transform is conditional: the convergence condition "
        f"depends on the parameter(s) {names} (sympy condition: {cond}); "
        "declare their signs/domains via assumptions to get an unconditional "
        "form."
    ]


def dsolve_artifact_reason(equation: Any, solution: Any) -> str | None:
    """A reason when *solution* does not satisfy *equation*, else ``None``.

    Only an explicit closed-form solution of a single-function ODE is judged:
    an implicit integral solution or a forcing term (a second undefined
    function) makes ``checkodesol``'s residual inconclusive, so it is left
    alone.  An exception, an undecidable result, or an oversized solution also
    leaves the historical behavior untouched.
    """
    if not isinstance(solution, sp.Equality):
        return None
    try:
        if sp.count_ops(solution) > _DSOLVE_CHECK_OPS_CAP:
            return None
        if solution.rhs.has(sp.Integral, sp.Derivative):
            return None
        if len({atom.func for atom in equation.atoms(AppliedUndef)}) > 1:
            return None
        ok, residual = sp.checkodesol(equation, solution)
    except Exception:
        return None
    if ok is not False:
        return None
    return (
        "the returned solution does not satisfy the equation "
        f"(residual {residual}; series artifacts like r(k) or O(x**n) "
        "indicate a truncated power-series ansatz); solve via "
        "ansatz/substitution instead"
    )

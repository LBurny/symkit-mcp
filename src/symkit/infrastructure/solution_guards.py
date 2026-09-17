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


# Trig bases whose symbolic power exposes the unbound heurisch recursion.
_TRIG_POWER_BASES = (sp.sin, sp.cos, sp.tan, sp.cot, sp.sec, sp.csc)

_TRIG_POWER_WEDGE_WARNING = (
    "the integrand has a trigonometric power with a symbolic exponent "
    "({powers}); SymPy's default heurisch route recurses without bound on this "
    "form, so it was routed through the bounded meijerg method and returned "
    "unevaluated. Substitute u = sin({var})**2 to reach the Beta-function "
    "form, or state numeric exponents."
)


def symbolic_trig_power_powers(integrand: Any, variable: Any) -> list[str]:
    """Rendered trig powers whose exponent free symbols exclude *variable*.

    Narrow by design: ``cos(theta)**2`` (numeric exponent) and ``x**(p-1)``
    (non-trig base) are not matched, so their integration is untouched. The
    comparison is by symbol *name* because the integration variable may carry
    assumptions while the integrand's symbol does not.
    """
    if not hasattr(integrand, "atoms"):
        return []
    var_name = str(variable)
    found: set[str] = set()
    for power in integrand.atoms(sp.Pow):
        base, exponent = power.base, power.exp
        if not isinstance(base, _TRIG_POWER_BASES) or not base.args:
            continue
        if var_name not in {str(sym) for sym in base.args[0].free_symbols}:
            continue
        if {str(sym) for sym in exponent.free_symbols} - {var_name}:
            found.add(str(power))
    return sorted(found)


def guarded_definite_integral(
    integrand: Any, variable: Any, lower: Any, upper: Any
) -> tuple[Any, list[str]]:
    """Definite integral with the symbolic-trig-power recursion guard (G10).

    Returns ``(result, warnings)``. The default route (and its behavior) is
    kept for every integrand the guard does not match. A matched integrand
    goes through ``meijerg=True``, which is bounded; if it still has no closed
    form the unevaluated integral is returned with a warning instead of letting
    ``heurisch`` recurse without bound. An exception in the guarded route also
    falls back to the unevaluated integral, never to the wedge.
    """
    powers = symbolic_trig_power_powers(integrand, variable)
    if not powers:
        return sp.integrate(integrand, (variable, lower, upper)), []
    try:
        result = sp.integrate(integrand, (variable, lower, upper), meijerg=True)
    except Exception:
        result = sp.Integral(integrand, (variable, lower, upper))
    if result.has(sp.Integral):
        warning = _TRIG_POWER_WEDGE_WARNING.format(
            powers=", ".join(powers), var=variable
        )
        return result, [warning]
    return result, []

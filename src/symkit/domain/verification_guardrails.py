"""Guardrails for automatic verification: keep checks bounded and warnings honest.

``sympy.integrate`` has no internal time limit, and the verification checks run it
on expressions that grow with every round. The MCP server is one process, so a
check that never returns blocks every other tool call for as long as it runs
(r17 task-01: reverse-integrating a 4th-order nested power wedged the server for
15+ minutes). :func:`reverse_integrate` bails out past a size budget so the caller
can report INCONCLUSIVE instead of risking the process. :func:`collect_warnings`
keeps the lightweight hints tied to the algebra rather than to the rendered
string.

Pure domain module: depends only on SymPy.
"""

from __future__ import annotations

import sympy as sp

# Past this size the reverse-integration check is skipped. The first integration
# of the r17 case lifted a 29-operation derivative to 701 operations and the
# second call never returned.
INTEGRATION_OPS_CAP = 300


def reverse_integrate(expr: sp.Basic, var: sp.Symbol, order: int) -> sp.Basic | None:
    """Integrate ``expr`` w.r.t. ``var`` ``order`` times, or ``None`` when too big.

    ``None`` means the check was skipped, not that the step is wrong.
    """
    for _ in range(order):
        if isinstance(expr, sp.Expr) and sp.count_ops(expr) > INTEGRATION_OPS_CAP:
            return None
        expr = sp.integrate(expr, var)
    return expr


def collect_warnings(output_expr: sp.Basic) -> list[str]:
    """Lightweight sanity hints for a verified output expression."""
    warnings: list[str] = []
    expr_str = str(output_expr)
    if "exp(" in expr_str:
        # No dimensional analysis yet: this stays a hint.
        warnings.append("Expression contains exp(...). Ensure the argument is dimensionless.")
    if "log(" in expr_str:
        warnings.append("Expression contains log(...). Ensure the argument is positive in the domain.")
    # Only a symbolic denominator can vanish; ``4*x**3/3`` is not a hazard (r17).
    denom = sp.fraction(sp.together(output_expr))[1] if isinstance(output_expr, sp.Expr) else None
    if denom is not None and denom.free_symbols:
        warnings.append("Expression contains division. Ensure denominators cannot be zero.")
    return warnings

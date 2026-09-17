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

import json
from collections.abc import Callable
from typing import Any

import sympy as sp

from symkit.domain.expr_io import evaluated_form
from symkit.domain.final_result import evaluate_pending, is_numerically_zero
from symkit.domain.value_objects import VerificationResult, VerificationStatus

# Past this size the reverse-integration check is skipped. The first integration
# of the r17 case lifted a 29-operation derivative to 701 operations and the
# second call never returned.
INTEGRATION_OPS_CAP = 300


def evalf_substitution_pairs(
    input_expressions: dict[str, str],
) -> list[tuple[str, str]] | None:
    """The substitution recorded for an ``evalf`` step (``input_substitution``).

    The verifier must replay the step's substitution; recomputing the archived
    *unsubstituted* input reported a correct ``evalf(..., substitution=...)`` as
    INCONCLUSIVE with ``details.expected`` showing the symbolic input (r18 A2).
    """
    raw = input_expressions.get("input_substitution")
    if not raw:
        return None
    try:
        mapping = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(mapping, dict) or not mapping:
        return None
    return [(str(key), str(value)) for key, value in mapping.items()]


def evalf_substitution_map(
    step: Any,
    assumptions: dict[str, dict[str, bool]],
    parse: Callable[[str, dict[str, dict[str, bool]]], sp.Basic | None],
) -> dict[sp.Basic, sp.Basic]:
    """The substitution recorded on an ``evalf`` step, ready for ``N(subs=...)``.

    ``parse`` is the verifier's assumption-aware parser, so a key/value with an
    assumption-bearing symbol still binds (r18 A2).  Values are applied by
    ``N(..., subs=...)`` at evaluation time, never exactly first: replaying
    ``n = 10**6`` in ``(1 + 1/n)**n`` through ``subs`` rebuilds the
    ~6-million-digit rational that wedges evalf (r18 A3).
    """
    pairs = evalf_substitution_pairs(step.input_expressions) or []
    mapping: dict[sp.Basic, sp.Basic] = {}
    for key_str, value_str in pairs:
        target = parse(key_str, assumptions)
        replacement = parse(value_str, assumptions)
        if target is not None and replacement is not None:
            mapping[evaluated_form(target)] = replacement
    return mapping


def verify_evalf(
    step: Any,
    input_expr: sp.Basic,
    output_expr: sp.Basic,
    assumptions: dict[str, dict[str, bool]],
    parse: Callable[[str, dict[str, dict[str, bool]]], sp.Basic | None],
) -> VerificationResult:
    """Verify an ``evalf`` step by independent numeric re-evaluation.

    Reproduces the substituted point recorded on the step (r18 A2) numerically
    through ``N(..., subs=...)`` rather than an exact pre-substitution, which
    would re-trigger the r18 A3 blow-up inside the verifier.  A genuinely
    mismatched output is still FAILED.
    """
    subs = evalf_substitution_map(step, assumptions, parse)
    options: dict[str, Any] = {"subs": subs} if subs else {}
    try:
        # N of an inert finite ``Sum`` drifts in double precision; the tool
        # evaluates it exactly via ``doit`` (r16 task-19 step 13).
        expected = complex(sp.N(evaluate_pending(input_expr), 20, **options))
        actual = complex(sp.N(output_expr, 20))
    except (TypeError, ValueError):
        # evalf over symbolic input (``2*x`` → ``2.0*x``): compare ``N(input)``
        # with the output; a mismatch stays INCONCLUSIVE.
        try:
            expected_sym = sp.N(evaluate_pending(input_expr), 20, **options)
            diff_sym = sp.simplify(expected_sym - output_expr)
        except (TypeError, ValueError):
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="evalf input/output is not purely numeric",
            )
        if is_numerically_zero(diff_sym):
            return VerificationResult.success(
                "Numeric evaluation verified (symbolic comparison)"
            )
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message="evalf output does not match the numeric evaluation of its input",
            details={"expected": str(expected_sym), "actual": str(output_expr)},
        )
    # Quadrature of an inert Integral needs a relative tolerance (task-18).
    quadrature = input_expr.has(sp.Integral) or output_expr.has(sp.Integral)
    tol = (1e-6 if quadrature else 1e-12) * max(1.0, abs(expected))
    if abs(expected - actual) < tol:
        return VerificationResult.success("Numeric evaluation verified")
    return VerificationResult.failure(
        "Numeric evaluation mismatch",
        expected=str(expected),
        actual=str(actual),
    )



def reverse_integrate(expr: sp.Basic, var: sp.Symbol, order: int) -> sp.Basic | None:
    """Integrate ``expr`` w.r.t. ``var`` ``order`` times, or ``None`` when too big.

    ``None`` means the check was skipped, not that the step is wrong.
    """
    for _ in range(order):
        if isinstance(expr, sp.Expr) and sp.count_ops(expr) > INTEGRATION_OPS_CAP:
            return None
        expr = sp.integrate(expr, var)
    return expr


def has_stuck_piecewise_derivative(expr: sp.Basic) -> bool:
    """Unevaluated ``Subs``/``Derivative`` of ``floor``/``ceiling`` present.

    sympy cannot differentiate the piecewise-constant ``floor``/``ceiling`` and
    leaves the derivative inert; at every non-breakpoint that derivative is 0
    (r22 task-05).
    """
    for node in sp.preorder_traversal(expr):
        if isinstance(node, (sp.Subs, sp.Derivative)) and node.expr.has(
            sp.floor, sp.ceiling
        ):
            return True
    return False


def drop_piecewise_constant_derivatives(expr: sp.Basic) -> sp.Basic:
    """Replace stuck ``floor``/``ceiling`` derivative terms with 0 (see above)."""
    return expr.replace(
        lambda node: isinstance(node, (sp.Subs, sp.Derivative))
        and node.expr.has(sp.floor, sp.ceiling),
        lambda _node: sp.Integer(0),
    )


def direct_differentiation_verdict(
    input_expr: sp.Basic, output_expr: sp.Basic, var: sp.Symbol, order: int
) -> VerificationResult | None:
    """VERIFIED when ``output_expr`` is the input's order-``order`` derivative.

    Reverse integration is blind whenever the antiderivative branches: with
    parameter symbols that carry no assumptions ``integrate`` returns a
    ``Piecewise`` and the comparison of the antiderivative with the input can
    conclude nothing, so every correct derivative of such a form was reported
    INCONCLUSIVE (r19 F37).  Recomputing the derivative directly is mechanical,
    has no integration constants and never branches.  ``None`` means the direct
    comparison did not conclude and the caller must fall back.
    """
    if not isinstance(input_expr, sp.Expr) or not isinstance(output_expr, sp.Expr):
        return None
    try:
        expected = sp.diff(evaluate_pending(input_expr), var, order)
        residual = sp.simplify(expected - evaluate_pending(output_expr))
    except (TypeError, ValueError, AttributeError):
        return None
    if not is_numerically_zero(residual):
        return None
    if has_stuck_piecewise_derivative(output_expr):
        # Recomputation only reproduces the same inert floor/ceiling derivative,
        # so a green here certifies nothing (r22 task-05).
        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            message=(
                "the output keeps an unevaluated floor/ceiling derivative "
                "(piecewise-constant, undefined at breakpoints); direct "
                "recomputation reproduces the same stuck form"
            ),
        )
    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        message="Differentiation verified by direct recomputation",
        reverse_check=True,
    )


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

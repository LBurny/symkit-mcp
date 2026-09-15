"""Bounded handling of matrix-exponential calls.

``Matrix.exp()`` / ``(Matrix(...)*t).exp()`` is evaluated eagerly by the parser.
For a general 3x3 (or larger) matrix SymPy expands ``exp(A)`` through the
eigen-decomposition of the characteristic polynomial; with nested-radical roots
that never returns and wedges the single-process MCP server (r18 A4: >750 s
live, >45 s under the probe cap).  A diagonal/triangular or at most 2x2 matrix
has a fast symbolic exponential and is left to the normal path; anything else is
either evaluated numerically (``evalf`` with numeric entries, via the same
Float-matrix Pade route as SymPy) or refused with a curated reason.  A symbolic
exponential of the risky shapes is never attempted, and a matrix is never
returned unless it was actually evaluated.

Pure infrastructure helper: depends on SymPy and the shared domain parser.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp

from symkit.domain.expression_parser import parse_user_expression

_EXP_SUFFIX = re.compile(r"\.\s*exp\s*\(\s*\)\s*$")
_EXP_PREFIX = re.compile(r"^exp\s*\(")


def matrix_exp_argument(text: str) -> str | None:
    """The argument of a matrix-exponential call, or ``None`` when not one.

    Recognizes ``(...).exp()`` and ``exp(...)``, and requires a ``Matrix(``
    literal so the scalar ``exp(7*t)`` is never treated as a matrix.
    """
    stripped = text.strip()
    if "Matrix" not in stripped:
        return None
    suffix = _EXP_SUFFIX.search(stripped)
    if suffix is not None:
        return stripped[: suffix.start()].strip()
    prefix = _EXP_PREFIX.match(stripped)
    if prefix is not None and stripped.endswith(")"):
        return stripped[prefix.end():-1].strip()
    return None


def _as_explicit(candidate: Any) -> sp.MatrixBase | None:
    """An explicit matrix for a parsed matrix object, or ``None``."""
    if isinstance(candidate, sp.MatrixBase):
        return candidate
    if isinstance(candidate, sp.MatrixExpr):
        try:
            return candidate.as_explicit()
        except Exception:
            return None
    return None


def _has_fast_symbolic_exponential(matrix: sp.MatrixBase) -> bool:
    """Diagonal/triangular or at most 2x2: SymPy's symbolic ``exp()`` is fast."""
    if max(matrix.shape) <= 2:
        return True
    try:
        return bool(matrix.is_diagonal() or matrix.is_upper or matrix.is_lower)
    except Exception:
        return False


def _substitution_map(substitution: dict[str, Any] | None) -> dict[sp.Basic, Any]:
    """Parse a recorded substitution into SymPy objects (best effort)."""
    mapping: dict[sp.Basic, Any] = {}
    for key, value in (substitution or {}).items():
        parsed_key, _ = parse_user_expression(str(key), convert_equation=False)
        parsed_value, _ = parse_user_expression(str(value), convert_equation=False)
        if parsed_key is not None and parsed_value is not None:
            mapping[parsed_key] = parsed_value
    return mapping


def _rekey(matrix: sp.MatrixBase, subs: dict[sp.Basic, Any]) -> dict[sp.Basic, Any]:
    """Rebind substitution keys to the symbols actually present in ``matrix``."""
    rebound: dict[sp.Basic, Any] = {}
    for key, value in subs.items():
        if matrix.has(key):
            rebound[key] = value
            continue
        if isinstance(key, sp.Symbol):
            target = next(
                (s for s in matrix.free_symbols if str(s) == str(key)), None
            )
            rebound[target if target is not None else key] = value
        else:
            rebound[key] = value
    return rebound


def _numeric_exponential(
    matrix: sp.MatrixBase, substitution: dict[str, Any] | None
) -> tuple[sp.MatrixBase | None, str | None]:
    """Numerically evaluate ``exp(matrix)``, or return a curated refusal."""
    subs = _substitution_map(substitution)
    if subs:
        matrix = matrix.subs(_rekey(matrix, subs))
    if matrix.free_symbols:
        names = ", ".join(sorted(str(s) for s in matrix.free_symbols))
        return None, (
            f"the matrix is still symbolic ({names}); sympy's symbolic matrix "
            "exponential runs an unbounded eigen-decomposition of the "
            "characteristic polynomial. Substitute numeric values for every "
            "symbol first (t=1, or float entries)."
        )
    try:
        return matrix.evalf().exp(), None
    except Exception as exc:
        return None, f"numeric matrix exponential failed: {type(exc).__name__}: {exc}"


def _success(operation: str, result: sp.MatrixBase) -> dict[str, Any]:
    """A math() success payload carrying the evaluated matrix."""
    return {
        "success": True,
        "expression": str(result),
        "latex": sp.latex(result),
        "operation": operation,
        "_input_obj": result,
        "_result_obj": result,
    }


def matrix_exp_guard(
    operation: str, text: Any, substitution: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Divert a risky matrix exponential before it is parsed and evaluated.

    Returns ``None`` when the expression is not a matrix exponential or its
    shape has a fast symbolic exponential; otherwise a math() payload that is
    either the numeric result (``evalf`` with numeric entries) or a curated
    refusal.  Never returns a matrix that was not evaluated.
    """
    if not isinstance(text, str):
        return None
    argument = matrix_exp_argument(text)
    if argument is None:
        return None
    try:
        parsed, _error = parse_user_expression(argument, convert_equation=False)
    except Exception:
        return None
    if not isinstance(parsed, (sp.MatrixBase, sp.MatrixExpr)):
        return None
    explicit = _as_explicit(parsed)
    if explicit is None or _has_fast_symbolic_exponential(explicit):
        return None
    if operation == "evalf":
        result, reason = _numeric_exponential(explicit, substitution)
        if result is not None:
            return _success(operation, result)
    else:
        reason = (
            "a symbolic matrix exponential of this size has no bounded "
            "evaluation in sympy; call evalf with numeric values instead."
        )
    return {
        "success": False,
        "error": f"math('{operation}'): matrix exponential: {reason}",
    }

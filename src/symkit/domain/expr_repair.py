"""Parser repair pass for matrix-aware and ``inv``-aware inputs.

SymPy's ``evaluate=False`` transformer preserves structural forms, but its
rewrite is wrong once a matrix is involved: ``Pow(Matrix, -1) * Matrix`` is
distributed element-wise over the right matrix's entries ("block broadcast")
and ``doit()`` cannot undo it (r23 F1).  Matrices are eager in SymPy, so a
parse that touched one is redone with normal evaluation.

The module also gives ``inv(Matrix)`` its mathematical meaning.  ``inv`` is not
a SymPy name, so the parser binds it to an undefined function and the call
stayed symbolically inert (r23 F2).  Only concrete ``MatrixBase`` arguments are
rewritten; symbolic arguments keep the undefined-function semantics.

Pure domain module: depends only on SymPy.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.core.function import AppliedUndef

# Matrix literal constructors: any parse that mentions one must be evaluated
# (the eager form is the only correct one).
_MATRIX_LITERAL_RE: re.Pattern[str] = re.compile(
    r"\b(?:Immutable|Mutable)?(?:Dense|Sparse)?Matrix\s*\("
)


def mentions_matrix_literal(expr_str: str) -> bool:
    """True when *expr_str* builds a matrix with a literal constructor."""
    return bool(_MATRIX_LITERAL_RE.search(expr_str))


def _is_matrix_pow(node: Any) -> bool:
    return isinstance(node, sp.Pow) and isinstance(node.base, sp.MatrixBase)


def has_matrix_distortion(expr: Any) -> bool:
    """True when an unevaluated parse left a matrix power inside a matrix.

    ``MatrixBase.has``/``.atoms`` do not see a matrix nested in another
    matrix's element (a mutable-matrix quirk), so the tree is walked with
    ``preorder_traversal``: any ``Pow(MatrixBase, n)`` node is the
    ``evaluate=False`` broadcast fingerprint (a bare top-level power is folded
    normally by ``_evaluate_matrix_powers``; re-evaluating it is harmless).
    """
    if not isinstance(expr, sp.Basic):
        return False
    return any(_is_matrix_pow(node) for node in sp.preorder_traversal(expr))


def _matrix_inv_query(node: Any) -> bool:
    return (
        isinstance(node, AppliedUndef)
        and node.func.__name__ == "inv"
        and len(node.args) == 1
        and isinstance(node.args[0], sp.MatrixBase)
    )


def _matrix_inverse(node: Any) -> Any:
    return node.args[0].inv()


def repair_inv_calls(expr: Any) -> Any:
    """Evaluate ``inv(Matrix)`` calls; leave symbolic ``inv`` untouched."""
    if not isinstance(expr, sp.Basic) or not expr.has(AppliedUndef):
        return expr
    return expr.replace(_matrix_inv_query, _matrix_inverse)


def repair_parsed_expression(
    parsed: Any,
    expr_str: str,
    local_dict: dict[str, Any],
    transformations: Any,
) -> Any:
    """Re-parse *parsed* with evaluation when it touched a matrix.

    Returns *parsed* unchanged for scalar/symbolic input.  A failed re-parse
    keeps the original object so downstream error handling is unchanged;
    ``inv`` repair then runs on whichever object survived (the re-parsed
    matrix or the unevaluated power the caller folds later).
    """
    if mentions_matrix_literal(expr_str) or has_matrix_distortion(parsed):
        try:
            # Lazy import: expression_parser imports this module at load time.
            from sympy.parsing.sympy_parser import parse_expr

            reparsed = parse_expr(
                expr_str, local_dict=local_dict, transformations=transformations
            )
            # ``evaluate=False`` yields an immutable matrix; the evaluated
            # ``Matrix(...)`` literal yields a mutable one, whose srepr is not a
            # ``Basic`` and fails the archive round-trip (r23 F1 follow-on).
            if isinstance(reparsed, sp.MatrixBase):
                reparsed = reparsed.as_immutable()
            parsed = reparsed
        except Exception:
            pass
    return repair_inv_calls(parsed)

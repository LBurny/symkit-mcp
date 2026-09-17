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


# A ``[[...],[...]]`` grid stands for a matrix, but SymPy builds a Python list
# only when the literal *is* the whole expression; embedded in a larger
# expression or an ``Eq`` side the list reaches ``sympify`` and dies (G5).  The
# literal is rewritten to the equivalent ``Matrix(...)`` constructor.  A ``[``
# that already sits inside a matrix constructor (including srepr forms such as
# ``ImmutableDenseMatrix([...])``) is skipped so nothing is double-wrapped.
_MATRIX_CTOR_TAIL_RE: re.Pattern[str] = re.compile(
    r"(?:(?:Immutable|Mutable)?(?:Dense|Sparse)?Matrix)\s*\(\s*$"
)
_EMPTY_LIST_ERROR = (
    "empty list literal is not a valid matrix; write Matrix([[...]]) with at "
    "least one row"
)


def _split_top_level(text: str) -> list[str]:
    """Split *text* on commas that are not nested inside brackets."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _find_closing_bracket(text: str, start: int) -> int:
    """Index of the ``]`` matching the ``[`` at *start*, or -1 if unbalanced."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _row_length(part: str) -> int:
    inner = part.strip()[1:-1]
    if not inner.strip():
        raise ValueError(_EMPTY_LIST_ERROR)
    return len(_split_top_level(inner))


def normalize_matrix_literals(expr_str: str) -> str:
    """Rewrite top-level row-grid literals to ``Matrix([[...]])``.

    A list-of-lists (every top-level item is itself a bracketed list) is the
    matrix row-grid form; rewriting it to the ``Matrix(...)`` constructor makes
    every parser entry point accept the same syntax as ``Matrix([[...]])``
    (G5).  Flat lists (column vectors) and existing constructor calls are left
    untouched.

    Raises:
        ValueError: an empty ``[]`` literal or a jagged grid
            (``[[1, 2], [3]]``), with a message naming the problem.
    """
    out: list[str] = []
    i = 0
    while i < len(expr_str):
        if expr_str[i] != "[" or _MATRIX_CTOR_TAIL_RE.search(expr_str[:i]):
            out.append(expr_str[i])
            i += 1
            continue
        close = _find_closing_bracket(expr_str, i)
        if close == -1:
            out.append(expr_str[i:])
            break
        literal = expr_str[i : close + 1]
        rows = _split_top_level(literal[1:-1])
        if rows and all(
            part.strip().startswith("[") and part.strip().endswith("]")
            for part in rows
        ):
            lengths = [_row_length(part) for part in rows]
            if len(set(lengths)) != 1:
                shown = ", ".join(str(n) for n in lengths)
                raise ValueError(
                    f"matrix literal rows must have equal length; got row "
                    f"lengths {shown}"
                )
            out.append(f"Matrix({literal})")
        elif not literal[1:-1].strip():
            raise ValueError(_EMPTY_LIST_ERROR)
        else:
            out.append(literal)
        i = close + 1
    return "".join(out)


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

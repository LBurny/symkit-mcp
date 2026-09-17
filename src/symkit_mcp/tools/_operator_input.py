"""Input normalization for expressions that already call the requested operation.

Clients routinely write the operation twice: ``operation="det"`` together with
``expression="det(Matrix([[1, 2], [3, 4]]))"``.  The parser binds most operator
names to their SymPy function, so the call is already applied during parsing and
the requested operation then runs a second time on its own result.  The outcome
depends on the operation: ``det`` crashes inside ``sp.Matrix(scalar)`` with a
leaked ``TypeError: Data type not understood`` (r23 G13), ``diff`` silently
returns the *second* derivative (``diff(x**3)`` -> ``6*x``), and ``eigenvals``
silently returns nothing.  Unwrapping the redundant call restores the reading
the client meant.

The same-named call is only stripped when it *is* the whole expression, so an
operator used inside a larger formula is untouched.  A two-argument call such as
``diff(sin(t), t)`` also supplies the variable when the caller passed none.

Presentation-layer module: it shapes requests, it does not do mathematics.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp

from symkit.domain.expr_io import is_srepr_form

_CALL_HEAD_RE: re.Pattern[str] = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(")
_BARE_NAME_RE: re.Pattern[str] = re.compile(r"[A-Za-z_]\w*")


def _split_single_call(text: str) -> tuple[str, list[str]] | None:
    """Return ``(name, args)`` when *text* is exactly one function call.

    Trailing text after the closing parenthesis (``det(x) + 1``) and unbalanced
    brackets both yield ``None``: only a call that wraps the whole expression is
    a candidate for unwrapping.
    """
    head = _CALL_HEAD_RE.match(text)
    if head is None:
        return None
    open_idx = head.end() - 1
    depth = 0
    args: list[str] = []
    start = open_idx + 1
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                if text[i + 1 :].strip():
                    return None
                args.append(text[start:i])
                return head.group(1), args
            if depth < 0:
                return None
        elif ch == "," and depth == 1:
            args.append(text[start:i])
            start = i + 1
    return None


def normalize_operator_input(
    operation: str, expr: Any, variable: str | None
) -> tuple[Any, str | None]:
    """Strip a redundant same-named wrapper from *expr*; infer *variable* if given.

    ``operation="det"`` + ``"det(Matrix([[...]]))"`` becomes ``"Matrix([[...]])"``.
    A two-argument call (``"diff(sin(t), t)"``) also yields ``variable="t"`` when
    the caller supplied none.  Anything else — non-strings, srepr forms, nested
    or multi-argument calls with an unrecognized tail — passes through unchanged.
    """
    if not isinstance(expr, str) or is_srepr_form(expr):
        return expr, variable
    call = _split_single_call(expr)
    if call is None:
        return expr, variable
    name, args = call
    if name != operation or not args:
        return expr, variable
    if len(args) == 1:
        return args[0].strip(), variable
    tail = args[1].strip()
    if len(args) == 2 and _BARE_NAME_RE.fullmatch(tail):
        return args[0].strip(), variable or tail
    return expr, variable


def _is_matrix_like(value: Any) -> bool:
    """True for matrices and for row grids that a matrix operation can consume."""
    if isinstance(value, (sp.MatrixBase, sp.MatrixExpr)):
        return True
    if isinstance(value, (list, tuple)) and value:
        rows = [row for row in value if isinstance(row, (list, tuple))]
        return len(rows) == len(value) and len({len(row) for row in rows}) == 1
    return False


def matrix_operand_error(operation: str, value: Any) -> dict[str, Any] | None:
    """Reject a non-matrix operand with an actionable message.

    Without this the matrix operations reach ``sp.Matrix(value)`` and surface
    SymPy's ``TypeError: Data type not understood; expecting list of lists``
    (r23 G13), which tells a client neither what went wrong nor how to fix it.
    """
    if _is_matrix_like(value):
        return None
    return {
        "success": False,
        "error": (
            f"Operation '{operation}' expects a matrix; got '{value}'. Pass the matrix "
            f"itself as the expression — Matrix([[1, 2], [3, 4]]) or [[1, 2], [3, 4]] — "
            f"with operation='{operation}'."
        ),
    }

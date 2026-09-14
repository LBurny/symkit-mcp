"""Vector-field input coercion for ``curl``/``divergence``.

Three shapes reach these operators: the comma-separated string form (parsed
to a Python tuple), a 3-element list or 3x1 Matrix, and the ``N.i/N.j/N.k``
basis form that gradient/laplacian emit.  This module normalizes all of them
into a ``sympy.vector`` field in ``CoordSys3D("N")`` and — crucially —
rejects scalar input loudly.  An unrecognized scalar used to be built into a
vacuous field whose curl/divergence is ``0`` with ``success: true``
(task-04); the accepted shapes are the only things that become a field.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sympy as sp
from sympy.vector import CoordSys3D, Vector, divergence
from sympy.vector import curl as _curl

from symkit.domain.assumption_binding import apply_assumptions
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.value_objects import MathContext

_REQUIREMENT = (
    'expects a 3-component vector field: provide "P, Q, R" '
    "(comma-separated components), a 3-element list or 3x1 Matrix, or "
    "components in terms of x, y, z"
)


class VectorInputError(ValueError):
    """Raised when the input is not a recognizable 3-component vector field."""


def vector_input_message(operation: str) -> str:
    """Actionable description of the accepted vector-field input forms."""
    return f"{operation} {_REQUIREMENT}"


def _sub_coords(expr: Any, coords: list[str], N: Any) -> Any:
    """Rewrite plain coordinate symbols to ``N.x/N.y/N.z`` by NAME.

    Substitution is by name because parsed symbols may carry assumptions
    (``Symbol('x', positive=True)``); a bare ``Symbol('x')`` key would not
    match and the substitution would silently no-op (run-017).
    """
    for index, name in enumerate(coords[:3]):
        target = next(
            (s for s in getattr(expr, "free_symbols", ()) if str(s) == name),
            None,
        )
        if target is not None:
            expr = expr.subs(target, (N.x, N.y, N.z)[index])
    return expr


def _parse_component(item: Any, N: Any) -> Any:
    """Parse one component (string or SymPy object) into a scalar expression."""
    if isinstance(item, str):
        expr, error = parse_expression_string(
            item, convert_equation=False, local_dict={"N": N}
        )
        if expr is None:
            raise VectorInputError(
                f"Cannot parse vector component '{item}': {error}"
            )
    elif isinstance(item, sp.Basic):
        expr = item
    else:
        expr = sp.sympify(item)
    if isinstance(expr, (Vector, sp.MatrixBase)):
        raise VectorInputError("each vector component must be a scalar expression")
    return expr


def _components_from_vector(vector: Vector, N: Any) -> list[Any]:
    """Extract ``[P, Q, R]`` from a ``sympy.vector`` field (missing -> 0)."""
    components = vector.components
    result: list[Any] = []
    for base in (N.i, N.j, N.k):
        value = components.get(base)
        if value is None:
            value = next(
                (v for k, v in components.items() if str(k) == str(base)),
                sp.Integer(0),
            )
        result.append(value)
    return result


def _components_from_matrix(matrix: sp.MatrixBase) -> list[Any]:
    """Extract ``[P, Q, R]`` from a 3x1 or 1x3 matrix."""
    if matrix.shape not in ((3, 1), (1, 3)):
        raise VectorInputError(_REQUIREMENT)
    return [sp.sympify(entry) for entry in matrix]


def normalize_derivatives(expr: Any) -> Any:
    """Canonicalize ``Derivative`` variable order so mixed partials cancel.

    SymPy keeps ``Derivative(f, x, z)`` and ``Derivative(f, z, x)`` distinct
    even though they are equal for a smooth ``f``; curl-of-gradient can
    therefore render residual mixed-partial terms that are mathematically
    zero.  Only ``Derivative`` atoms are rewritten, so first-order abstract
    derivatives and explicit results keep their form.
    """
    if not isinstance(expr, sp.Basic):
        return expr

    def _canonical(derivative: Any) -> Any:
        variables = derivative.variables
        ordered = tuple(sorted(variables, key=str))
        if ordered == variables:
            return derivative
        return sp.Derivative(derivative.expr, *ordered)

    return expr.replace(
        lambda node: isinstance(node, sp.Derivative), _canonical
    )


def _reassociate(expr: Any) -> Any:
    """Rebuild an unevaluated parse tree that contains basis vectors.

    ``parse_expression_string`` parses with ``evaluate=False``, so a sum of
    ``N.i`` products stays a generic ``Add`` of unflattened ``Mul`` nodes and
    never becomes a ``VectorAdd``.  Rebuilding through the ``*``/``+``
    operators triggers sympy.vector's constructors without changing the math.
    """
    if isinstance(expr, sp.Add):
        terms = [_reassociate(arg) for arg in expr.args]
        result = terms[0]
        for term in terms[1:]:
            result = result + term
        return result
    if isinstance(expr, sp.Mul):
        factors = [_reassociate(arg) for arg in expr.args]
        result = factors[0]
        for factor in factors[1:]:
            result = result * factor
        return result
    return expr


def _components_from_string(text: str, N: Any) -> list[Any]:
    """Parse a vector-field string; tuple, matrix and ``N.*`` forms are valid."""
    expr, error = parse_expression_string(
        text, convert_equation=False, local_dict={"N": N}
    )
    if expr is None:
        raise VectorInputError(f"Cannot parse vector field: {error}")
    if isinstance(expr, sp.Basic) and expr.atoms(Vector):
        expr = _reassociate(expr)
    if isinstance(expr, Vector):
        return _components_from_vector(expr, N)
    if isinstance(expr, sp.MatrixBase):
        return _components_from_matrix(expr)
    if isinstance(expr, (list, tuple)):
        if len(expr) != 3:
            raise VectorInputError(_REQUIREMENT)
        return [sp.sympify(item) for item in expr]
    raise VectorInputError(_REQUIREMENT)


def _extract_components(raw: Any, N: Any) -> list[Any]:
    """Coerce any accepted input shape into ``[P, Q, R]`` scalar components."""
    if isinstance(raw, Vector):
        return _components_from_vector(raw, N)
    if isinstance(raw, sp.MatrixBase):
        return _components_from_matrix(raw)
    if isinstance(raw, (list, tuple)):
        if len(raw) != 3:
            raise VectorInputError(_REQUIREMENT)
        return [_parse_component(item, N) for item in raw]
    if isinstance(raw, str):
        return _components_from_string(raw, N)
    raise VectorInputError(_REQUIREMENT)


def _build(
    raw: Any,
    coords: list[str],
    N: Any,
    assumptions: Mapping[str, Mapping[str, bool]] | None,
) -> Any:
    """Build a ``CoordSys3D`` field from any accepted input shape."""
    components = _extract_components(raw, N)
    basis = (N.i, N.j, N.k)
    field: Any = None
    for index, component in enumerate(components):
        component = apply_assumptions(component, assumptions)
        term = _sub_coords(component, coords, N) * basis[index]
        field = term if field is None else field + term
    return field if field is not None else 0 * N.i


def build_vector_field(obj: Any, coords: list[str], N: Any) -> Any:
    """Build a vector field from *obj* in the caller's coordinate system.

    Thin entry point for :class:`~symkit.infrastructure.sympy_engine.SymPyEngine`;
    scalar input raises :class:`VectorInputError` instead of silently becoming
    ``0 * N.i`` (task-04).
    """
    return _build(obj, coords, N, None)


def vector_operation(
    operation: str,
    raw: Any,
    variable: str | None,
    context: MathContext | None,
) -> dict[str, Any]:
    """Normalize *raw* and compute ``curl``/``divergence``.

    Returns the math dispatcher's result-dict contract (including the live
    ``_result_obj`` for session recording).  A non-vector input yields
    ``success: False`` with an actionable message rather than a silent zero.
    """
    coords = [c.strip() for c in (variable or "x,y,z").split(",")]
    assumptions = context.assumptions if context else None
    N = CoordSys3D("N")
    try:
        field = _build(raw, coords, N, assumptions)
    except VectorInputError as exc:
        detail = str(exc)
        if detail == _REQUIREMENT:
            detail = vector_input_message(operation)
        return {
            "success": False,
            "error": detail,
            "operation": operation,
            "_input_obj": None,
            "_result_obj": None,
        }
    result = _curl(field, N) if operation == "curl" else divergence(field, N)
    result = normalize_derivatives(result)
    if operation == "divergence":
        result = sp.simplify(result)
    return {
        "success": True,
        "expression": str(result),
        "latex": sp.latex(result),
        "operation": operation,
        "_input_obj": None,
        "_result_obj": result,
    }

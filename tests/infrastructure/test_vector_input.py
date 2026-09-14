"""Unit tests for :mod:`symkit.infrastructure.vector_input`.

The module centralizes vector-field input coercion so ``curl``/``divergence``
accept comma strings, lists, matrices and ``N.*`` basis notation, and reject
scalars instead of building a silent zero field.
"""

from __future__ import annotations

import pytest
import sympy as sp

from symkit.infrastructure.vector_input import (
    VectorInputError,
    build_vector_field,
    normalize_derivatives,
    vector_input_message,
    vector_operation,
)


def test_message_lists_supported_forms() -> None:
    msg = vector_input_message("curl")
    assert "curl" in msg
    assert "3-component" in msg
    assert "comma-separated" in msg
    assert "list" in msg
    assert "Matrix" in msg


def test_build_vector_field_rejects_scalar() -> None:
    from sympy.vector import CoordSys3D

    N = CoordSys3D("N")
    with pytest.raises(VectorInputError):
        build_vector_field(sp.Symbol("x") ** 2 + sp.Symbol("y"), ["x", "y", "z"], N)


def test_build_vector_field_from_tuple() -> None:
    from sympy.vector import CoordSys3D

    N = CoordSys3D("N")
    x, y = sp.symbols("x y")
    field = build_vector_field((x * y, y, x), ["x", "y", "z"], N)
    assert field.components[N.i] != 0


def test_vector_operation_list_input() -> None:
    result = vector_operation("curl", ["-y", "x", "0"], "x,y,z", None)
    assert result["success"], result
    assert result["expression"].replace(" ", "") == "2*N.k"


def test_vector_operation_scalar_fails() -> None:
    result = vector_operation("curl", "x**2 + y", "x,y,z", None)
    assert result["success"] is False
    assert "3-component" in result["error"]


def test_vector_operation_basis_notation() -> None:
    result = vector_operation("curl", "-y*N.i + x*N.j", "x,y,z", None)
    assert result["success"], result
    assert result["expression"].replace(" ", "") == "2*N.k"


def test_divergence_simplifies() -> None:
    result = vector_operation("divergence", "x*y, z*x, y*z", "x,y,z", None)
    assert result["success"], result
    assert result["expression"].replace(" ", "") == "2*N.y"


def test_normalize_derivatives_cancels_mixed_partials() -> None:
    """SymPy keeps ``Derivative(f, x, z)`` and ``Derivative(f, z, x)``
    distinct, so curl-of-gradient could render non-zero residual terms; the
    normalizer must collapse them to the literal zero vector."""
    from sympy.vector import CoordSys3D

    N = CoordSys3D("N")
    f = sp.Function("f")(N.x, N.y, N.z)
    residual = (
        sp.Derivative(f, N.x, N.z) * N.j - sp.Derivative(f, N.z, N.x) * N.j
    )
    assert str(normalize_derivatives(residual)) == "0"


def test_normalize_derivatives_preserves_abstract_first_order() -> None:
    """First-order abstract derivatives are already canonical and untouched."""
    from sympy.vector import CoordSys3D

    N = CoordSys3D("N")
    f = sp.Function("F3")(N.x, N.y, N.z)
    derivative = sp.Derivative(f, N.y)
    assert normalize_derivatives(derivative) == derivative
    assert normalize_derivatives(derivative).has(sp.Derivative)


def test_vector_operation_normalizes_mixed_partials() -> None:
    """A field whose component is a non-canonical mixed-partial difference is
    zero; the curl result must be the literal zero vector."""
    from sympy.vector import CoordSys3D

    N = CoordSys3D("N")
    f = sp.Function("f")(N.x, N.y, N.z)
    result = vector_operation(
        "curl",
        [
            sp.Derivative(f, N.z, N.x) - sp.Derivative(f, N.x, N.z),
            "0",
            "0",
        ],
        "x,y,z",
        None,
    )
    assert result["success"], result
    assert result["expression"] == "0", result["expression"]

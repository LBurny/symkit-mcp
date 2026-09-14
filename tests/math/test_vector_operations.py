"""Vector-operation input handling for ``math('curl'|'divergence')``.

Black-box regression (task-04): a scalar (or a field written with bare
``i/j/k`` symbols) was silently built into a vacuous zero field, so
``curl``/``divergence`` returned ``0`` with ``success:true`` for clearly
non-zero, non-vector input.  List/Matrix inputs crashed outright, and the
``N.i/N.j/N.k`` form emitted by gradient/laplacian could not be fed back
(operator chain broken).
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit_mcp.tools.math import register_math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    return mcp.tools


def test_gradient_default_coords_keep_all_components(
    fresh_session_manager: Any,
) -> None:
    """gradient without ``variable=`` must default to x,y,z — all three
    components present — not collapse to the single-variable default ``x``
    (round-13 D11: the dispatcher reused ``v = variable or 'x'``, so only the
    x-component survived and y/z stayed unmapped)."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"]("gradient", "f(x,y,z)", session=False)
    assert res["success"], res
    expr = res["expression"].replace(" ", "")
    assert "Derivative(f(N.x,N.y,N.z),N.x)" in expr, expr
    assert "Derivative(f(N.x,N.y,N.z),N.y)" in expr, expr
    assert "Derivative(f(N.x,N.y,N.z),N.z)" in expr, expr


def test_laplacian_default_coords_sum_all_dimensions(
    fresh_session_manager: Any,
) -> None:
    """laplacian without ``variable=`` must differentiate along x, y and z."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"]("laplacian", "x**2 + y**2 + z**2", session=False)
    assert res["success"], res
    assert res["expression"].replace(" ", "") == "6", res["expression"]


def test_curl_scalar_input_fails_loud(fresh_session_manager: Any) -> None:
    """A plain scalar is not a vector field: no silent zero."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"]("curl", "x**2 + y", variable="x,y,z", session=False)
    assert res["success"] is False, res
    assert "3-component" in res["error"], res["error"]
    assert "comma-separated" in res["error"], res["error"]


def test_divergence_scalar_input_fails_loud(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"]("divergence", "x**2 + y", variable="x,y,z", session=False)
    assert res["success"] is False, res
    assert "3-component" in res["error"], res["error"]


def test_curl_bare_unit_symbols_never_silent_zero(fresh_session_manager: Any) -> None:
    """``F1*i + F2*j + F3*k`` has no recognizable vector structure.

    It must either fail loudly or be computed correctly -- it must never be
    reported as a successful ``0``.
    """
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        "curl",
        "F1(x,y,z)*i + F2(x,y,z)*j + F3(x,y,z)*k",
        variable="x,y,z",
        session=False,
    )
    assert not (res.get("success") and res.get("expression") == "0"), res


def test_curl_list_input(fresh_session_manager: Any) -> None:
    """A 3-element list is a valid vector field."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"]("curl", ["-y", "x", "0"], variable="x,y,z", session=False)
    assert res["success"], res
    assert res["expression"].replace(" ", "") == "2*N.k", res["expression"]


def test_curl_matrix_input(fresh_session_manager: Any) -> None:
    """A 3x1 SymPy Matrix is a valid vector field."""
    _ = fresh_session_manager
    tools = _tools()
    field = sp.Matrix([["-y"], ["x"], ["0"]])
    res = tools["math"]("curl", field, variable="x,y,z", session=False)
    assert res["success"], res
    assert res["expression"].replace(" ", "") == "2*N.k", res["expression"]


def test_curl_basis_notation_feedback(fresh_session_manager: Any) -> None:
    """gradient output (``N.i/N.j/N.k`` + coord symbols) feeds straight into
    curl; grad is curl-free, so the closed loop must return 0."""
    _ = fresh_session_manager
    tools = _tools()
    grad = tools["math"](
        "gradient", "x**2 + y**2 + z**2", variable="x,y,z", session=False
    )
    assert grad["success"], grad
    assert "N.i" in grad["expression"]
    res = tools["math"]("curl", grad["expression"], variable="x,y,z", session=False)
    assert res["success"], res
    assert res["expression"] == "0", res["expression"]


def test_curl_n_notation_nonzero(fresh_session_manager: Any) -> None:
    """Explicit ``N.i/N.j`` input is parsed and gives the right curl."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        "curl", "-y*N.i + x*N.j", variable="x,y,z", session=False
    )
    assert res["success"], res
    assert res["expression"].replace(" ", "") == "2*N.k", res["expression"]


def test_curl_abstract_function_components(fresh_session_manager: Any) -> None:
    """Abstract-function components must produce the exact partial derivatives."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        "curl",
        "F1(x,y,z), F2(x,y,z), F3(x,y,z)",
        variable="x,y,z",
        session=False,
    )
    assert res["success"], res
    expr = res["expression"].replace(" ", "")
    assert "Derivative(F3(N.x,N.y,N.z),N.y)" in expr, expr
    assert "Derivative(F2(N.x,N.y,N.z),N.z)" in expr, expr


def test_divergence_abstract_function_components(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        "divergence",
        "F1(x,y,z), F2(x,y,z), F3(x,y,z)",
        variable="x,y,z",
        session=False,
    )
    assert res["success"], res
    expr = res["expression"].replace(" ", "")
    assert "Derivative(F1(N.x,N.y,N.z),N.x)" in expr, expr
    assert "Derivative(F3(N.x,N.y,N.z),N.z)" in expr, expr


def test_existing_comma_vector_tests_still_pass(fresh_session_manager: Any) -> None:
    """Guard the pre-existing comma-separated contract."""
    _ = fresh_session_manager
    tools = _tools()
    div = tools["math"](
        "divergence", "x*y, z*x, y*z", variable="x,y,z", session=False
    )
    assert div["success"], div
    assert div["expression"].replace(" ", "") == "2*N.y", div["expression"]
    cur = tools["math"]("curl", "y, z, x", variable="x,y,z", session=False)
    assert cur["success"], cur
    assert cur["expression"] != "0", cur["expression"]


def test_curl_gradient_text_feedback_is_zero(fresh_session_manager: Any) -> None:
    """grad is curl-free: the gradient's text output fed back into curl must be
    the literal zero vector, including for an abstract scalar f(x,y,z) whose
    mixed partials must cancel by variable-order normalization."""
    _ = fresh_session_manager
    tools = _tools()
    for scalar in ("x**2 + y**2 + z**2", "f(x,y,z)"):
        grad = tools["math"]("gradient", scalar, variable="x,y,z", session=False)
        assert grad["success"], grad
        res = tools["math"](
            "curl", grad["expression"], variable="x,y,z", session=False
        )
        assert res["success"], (scalar, res)
        assert res["expression"] == "0", (scalar, res["expression"])


def test_curl_abstract_components_keep_derivative_form(
    fresh_session_manager: Any,
) -> None:
    """Normalization must not evaluate abstract first-order derivatives away."""
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        "curl",
        "F1(x,y,z), F2(x,y,z), F3(x,y,z)",
        variable="x,y,z",
        session=False,
    )
    assert res["success"], res
    assert "Derivative(" in res["expression"], res["expression"]
    assert res["expression"] != "0", res["expression"]

"""``fourier`` -> ``ifourier`` must round-trip the original function.

r14 black-box (task-03): ``ifourier`` returned a branch-cut ``Piecewise``
constant or an unevaluated ``InverseFourierTransform`` that did not contain the
transform variable, and a bare ``ifourier`` (no ``with_respect_to``) inverts in
the frequency variable and returns the same variable -- a degenerate call that
yields a constant.  The engine now picks the dual variable on collision and
fails loud when the declared variable is absent.
"""

from __future__ import annotations

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools

X = sp.Symbol("x")


def _math():
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def _run(op: str, expr: str, **kwargs):
    return _math()(op, expr, session=False, **kwargs)


def test_gaussian_roundtrip_with_explicit_output_variable() -> None:
    forward = _run("fourier", "exp(-x**2)", variable="x", with_respect_to="k")
    assert forward["success"] is True, forward

    back = _run("ifourier", forward["expression"], variable="k", with_respect_to="x")
    assert back["success"] is True, back
    assert sp.simplify(sp.sympify(back["expression"]) - sp.exp(-X**2)) == 0


def test_gaussian_roundtrip_when_output_variable_defaults_to_input() -> None:
    """Without ``with_respect_to`` the caller defaults output to ``k`` too.

    The engine must not invert in ``k`` and return ``k``; it should fall back to
    the conventional dual variable and still recover the Gaussian.
    """
    forward = _run("fourier", "exp(-x**2)", variable="x", with_respect_to="k")
    assert forward["success"] is True, forward

    back = _run("ifourier", forward["expression"], variable="k")
    assert back["success"] is True, back
    result = sp.sympify(back["expression"])
    assert result.free_symbols, back
    assert sp.simplify(result - sp.exp(-X**2)) == 0


def test_non_gaussian_roundtrip() -> None:
    original = X * sp.exp(-X**2)
    forward = _run("fourier", "x*exp(-x**2)", variable="x", with_respect_to="k")
    assert forward["success"] is True, forward

    back = _run("ifourier", forward["expression"], variable="k", with_respect_to="x")
    assert back["success"] is True, back
    assert sp.simplify(sp.sympify(back["expression"]) - original) == 0


def test_ifourier_wrong_variable_is_structured_error() -> None:
    """Declaring a variable that is absent must not silently return 0."""
    result = _run("ifourier", "exp(-pi*k**2)", variable="x")

    assert result["success"] is False
    assert result.get("error")

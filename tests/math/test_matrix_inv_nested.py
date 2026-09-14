"""Nested attribute method calls such as ``Matrix(...).inv()``.

r14 black-box (task-05): a lone ``Matrix(...).inv()`` parsed, but as soon as
the attribute chain appeared inside a compound expression (subtraction,
product, parenthesized product) the parser died with
``Cannot parse: 'Attribute' object has no attribute 'id'`` -- an internal
SymPy ``EvaluateFalseTransformer`` bug.  Attribute chains have no unevaluated
form, so the parser retries with normal evaluation.
"""

from __future__ import annotations

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools

B = "Matrix([[1,2],[3,4]])"
C = "Matrix([[2,1],[1,3]])"

# (B*C)^-1 - C^-1 * B^-1 must be the zero matrix.
NESTED_INV_DIFFERENCE = f"({B}*{C}).inv() - {C}.inv()*{B}.inv()"


def _math():
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_nested_inv_inside_simplify_expression() -> None:
    result = _math()("simplify", NESTED_INV_DIFFERENCE, session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.zeros(2, 2)


def test_nested_inv_inside_evalf() -> None:
    result = _math()("evalf", f"{B}.inv()", session=False)

    assert result["success"] is True, result
    got = sp.sympify(result["expression"])
    assert got == sp.Matrix([[1, 2], [3, 4]]).inv().evalf()


def test_nested_inv_inside_det() -> None:
    result = _math()("det", f"{B}.inv()", session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.Rational(-1, 2)


def test_inv_method_call_times_matrix() -> None:
    result = _math()("simplify", f"{B}.inv()*{B}", session=False)

    assert result["success"] is True, result
    assert sp.sympify(result["expression"]) == sp.eye(2)

"""Finite ``Sum`` numeric evaluation must not cancel catastrophically.

r16 task-19: ``math("evalf", "Sum((-1)**n/n,(n,1,2000))")`` returned
``-0.70313 + 0.09375*I`` — an error of ~1e-2 plus a phantom imaginary part —
because SymPy substituted the index as a ``Float`` and accumulated in double
precision. The exact finite sum is ``-0.692897243059937``; the infinite sum
(whose path was already correct) must stay correct.
"""

from __future__ import annotations

from typing import Any

import pytest
import sympy as sp

from symkit_mcp.tools import math as math_tools

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def _reference(n: int) -> sp.Float:
    index = sp.Symbol("n")
    return sp.N(sp.Sum((-1) ** index / index, (index, 1, n)).doit(), 30)


@pytest.mark.parametrize("n", [1000, 1001, 2000])
def test_finite_alternating_harmonic_is_accurate(n: int) -> None:
    result = _math()("evalf", f"Sum((-1)**n/n,(n,1,{n}))", session=False)

    assert result["success"], result
    value = sp.sympify(result["expression"])
    reference = _reference(n)
    assert sp.Abs(sp.re(value) - reference) < sp.Float("1e-6", 30)
    assert sp.Abs(sp.im(value)) < sp.Float("1e-12", 30)
    # The old failure surfaced as a low-precision ``Float(..., precision=3)``
    # (e.g. 45/64); require genuine working precision instead.
    assert "precision=3," not in result["expression"].replace(" ", "")


def test_infinite_alternating_harmonic_stays_correct() -> None:
    result = _math()("evalf", "Sum((-1)**n/n,(n,1,oo))", session=False)

    assert result["success"], result
    value = sp.sympify(result["expression"])
    assert sp.Abs(value - sp.N(-sp.log(2), 30)) < sp.Float("1e-9", 30)
    assert sp.Abs(sp.im(value)) < sp.Float("1e-12", 30)

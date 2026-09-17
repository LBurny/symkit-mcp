"""Tool-surface regressions for the r23 fixes (F1, F2, F3, F8, F9).

F1 matrix product / F2 ``inv`` and the empty parse message / F3 ``evalf`` on a
tuple / F8 Laplace convergence-condition disclosure / F9 ``dsolve`` honesty
about a solution that does not satisfy the ODE.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


class TestMatrixProductF1:
    def test_matrix_quotient_product(self) -> None:
        result = _math()(
            "simplify",
            "Matrix([[1, 2], [3, 4]])**-1 * Matrix([[1, 1], [1, 0]])",
            session=False,
        )

        assert result["success"] is True, result
        got = sp.Matrix(sp.sympify(result["expression"]))
        assert got == sp.Matrix([[-1, -2], [1, sp.Rational(3, 2)]])


class TestInvAndParseMessageF2:
    def test_inv_of_matrix_evaluates(self) -> None:
        result = _math()("simplify", "inv(Matrix([[2, 1], [1, 3]]))", session=False)

        assert result["success"] is True, result
        got = sp.Matrix(sp.sympify(result["expression"]))
        assert got == sp.Matrix([[2, 1], [1, 3]]).inv()

    def test_nested_inv_is_identity(self) -> None:
        result = _math()(
            "simplify", "inv(inv(Matrix([[2, 1], [1, 3]])))", session=False
        )

        assert result["success"] is True, result
        got = sp.Matrix(sp.sympify(result["expression"]))
        assert got == sp.Matrix([[2, 1], [1, 3]])

    def test_unparseable_matrix_dot_reports_the_input(self) -> None:
        expression = "Matrix([[1,0],[0,1]]).dot(Matrix([[2,0],[0,3]]))"
        result = _math()("simplify", expression, session=False)

        assert result["success"] is False, result
        assert "Cannot parse" in result["error"]
        assert expression in result["error"]


class TestEvalfTupleF3:
    def test_evalf_tuple_does_not_crash(self) -> None:
        result = _math()("evalf", "(1/2, 1/3)", session=False)

        assert result["success"] is True, result
        got = sp.sympify(result["expression"])
        assert isinstance(got, tuple)
        assert float(got[0]) == 0.5
        assert abs(float(got[1]) - 1 / 3) < 1e-9


class TestLaplaceConvergenceF8:
    def test_degenerate_condition_is_disclosed(self) -> None:
        result = _math()("laplace", "Heaviside(tau - t)", variable="t", session=False)

        assert result["success"] is True, result
        assert "exp(-s*tau)/s" in result["expression"]
        warnings = result.get("warnings", [])
        assert any("tau" in note or "assum" in note for note in warnings), result

    def test_positive_parameter_behavior_unchanged(self) -> None:
        result = _math()(
            "laplace",
            "Heaviside(tau - t)",
            variable="t",
            assumptions=["tau is positive"],
            session=False,
        )

        assert result["success"] is True, result
        expected = (1 - sp.exp(-sp.Symbol("s") * sp.Symbol("tau"))) / sp.Symbol("s")
        got = sp.sympify(result["expression"])
        assert sp.simplify(got - expected) == 0


class TestDsolveHonestyF9:
    ODE = (
        "-hbar**2/(2*m)*Derivative(psi(x),(x,2)) + "
        "(m*omega**2*x**2/2 - E)*psi(x)"
    )

    def test_series_artifact_is_not_a_solution(self) -> None:
        result = _math()(
            "dsolve",
            self.ODE,
            variable="psi",
            with_respect_to="x",
            session=False,
        )

        assert result["success"] is False, result
        assert "does not satisfy" in result["error"]

    def test_damped_oscillator_still_verified(self) -> None:
        result = _math()(
            "dsolve",
            "diff(y, t, 2) + c*diff(y, t) + k*y",
            variable="y",
            with_respect_to="t",
            session=False,
        )

        assert result["success"] is True, result

    def test_gaussian_ode_still_verified(self) -> None:
        result = _math()(
            "dsolve",
            "diff(F, x) + 2*a*x*F",
            variable="F",
            with_respect_to="x",
            session=False,
        )

        assert result["success"] is True, result
        got = sp.sympify(result["expression"])
        assert got.rhs.has(sp.exp)

"""``variable``/``with_respect_to`` parameter integrity for ``math()``.

Two confirmed black-box defects (field card task-01):

- G4: a comma-separated ``variable`` (``"x, y"``) was handed to SymPy as one
  symbol name matching nothing, so ``diff`` returned a silent ``0`` with
  ``success: true`` (and no warning at all without a session).
- G5: the expression side is Unicode/lambda-preprocessed but the parameter was
  not, so ``diff(a*sin(b*λ), variable="λ")`` differentiated with respect to a
  nonexistent symbol and the step was even judged verified.

``solve`` (system variable lists) and the vector operations (coordinate lists)
legitimately accept commas and must not regress.
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


class TestCommaVariableRejectedForSingleVariableOps:
    def test_diff_comma_variable_does_not_return_silent_zero(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("diff", "x*y", variable="x, y", session=False)
        assert res["success"] is False, res
        assert res.get("expression") != "0"
        assert "single" in res["error"], res
        assert "variable" in res["error"], res

    def test_diff_comma_variable_rejected_with_session(
        self, fresh_session_manager: Any
    ) -> None:
        """The session=True path must fail the same way, not record a 0 step."""
        _ = fresh_session_manager
        res = _tools()["math"]("diff", "x*y", variable="x, y", session=True)
        assert res["success"] is False, res
        assert res.get("expression") != "0"

    def test_other_single_variable_ops_reject_a_comma_list(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        for operation in ("integrate", "limit", "series"):
            res = tools["math"](operation, "x*y", variable="x, y", session=False)
            assert res["success"] is False, (operation, res)
            assert "single" in res["error"], (operation, res)

    def test_solve_system_comma_variables_still_work(
        self, fresh_session_manager: Any
    ) -> None:
        """``solve`` genuinely consumes a comma-separated system variable list."""
        _ = fresh_session_manager
        res = _tools()["math"](
            "solve", "x + y - 2, x - y", variable="x, y", session=False
        )
        assert res["success"], res

    def test_vector_operations_comma_coordinates_still_work(
        self, fresh_session_manager: Any
    ) -> None:
        """``gradient``/``curl``/... take comma-separated coordinate lists."""
        _ = fresh_session_manager
        tools = _tools()
        grad = tools["math"](
            "gradient", "x**2 + y**2", variable="x,y,z", session=False
        )
        assert grad["success"], grad
        div = tools["math"](
            "divergence", "x*y, z*x, y*z", variable="x,y,z", session=False
        )
        assert div["success"], div


class TestLambdaParamMatchesRenamedExpression:
    def test_diff_lambda_variable_gives_the_correct_derivative(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("diff", "a*sin(b*λ)", variable="λ", session=False)
        assert res["success"], res
        expected = (
            sp.Symbol("a")
            * sp.Symbol("b")
            * sp.cos(sp.Symbol("b") * sp.Symbol("lambda_"))
        )
        assert sp.simplify(sp.sympify(res["expression"]) - expected) == 0, res

    def test_lambda_variable_emits_the_same_client_warning(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("diff", "a*sin(b*λ)", variable="λ", session=True)
        assert res["success"], res
        assert any("read as 'lambda_'" in w for w in res.get("warnings", [])), res

    def test_unicode_variable_is_normalized_like_the_expression(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        from symkit.domain.expression_parser import parse_user_expression

        res = _tools()["math"]("diff", "a*β**2", variable="β", session=False)
        assert res["success"], res
        # ``sp.sympify`` would fold ``beta`` into SymPy's native beta function;
        # the shared parser binds it as a Symbol like the input side does.
        got, error = parse_user_expression(res["expression"])
        assert error is None, error
        assert got is not None
        assert sp.simplify(
            got - 2 * sp.Symbol("a") * sp.Symbol("beta")
        ) == 0, res

    def test_plain_variable_unchanged_and_warning_free(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"]("diff", "x**3", variable="x", session=False)
        assert res["success"], res
        assert res["expression"] == "3*x**2", res
        assert not res.get("warnings"), res

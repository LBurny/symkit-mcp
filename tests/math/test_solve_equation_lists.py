"""``solve`` accepts equation systems in ``=` form (r23 G1).

The recommended system prompt advertises ``solve`` systems as ``"eq1, eq2"`` or
``"[eq1, eq2]"`` with ``variable="x, y"``.  The expression form (implicit
``= 0``) always worked, but every list whose elements carried an explicit ``=``
failed inside the shared parser with "cannot assign to expression here" before
the dispatcher's system branch could see it.  These tests pin the advertised
form, the existing expression-list behavior it must not disturb, and the
curated refusals for malformed or inequality input.
"""

from __future__ import annotations

from typing import Any

# ruff: noqa: F821  # MockMCP comes from tests/conftest.py
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools.session import register_session_tools


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _canonical(all_solutions: list[str]) -> list[str]:
    return [s.replace(" ", "") for s in all_solutions]


class TestEquationListsSolve:
    """The advertised comma and bracket equation systems."""

    def test_comma_equation_system_solves(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()(
            "solve", "x + y = 3, x - y = 1", variable="x, y", session=False
        )
        assert res["success"], res
        assert _canonical(res["all_solutions"]) == ["{x:2,y:1}"], res

    def test_bracket_equation_system_solves(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()(
            "solve", "[x + y = 3, x - y = 1]", variable="x, y", session=False
        )
        assert res["success"], res
        assert _canonical(res["all_solutions"]) == ["{x:2,y:1}"], res

    def test_single_bracket_equation_solves(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "[2*x = 4]", variable="x", session=False)
        assert res["success"], res
        assert _canonical(res["all_solutions"]) == ["{x:2}"], res


class TestMixedEquationAndExpressionList:
    """A list mixing an equation and a bare expression still runs."""

    def test_mixed_list_solves(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()(
            "solve", "x + y = 3, x - y", variable="x, y", session=False
        )
        assert res["success"], res
        assert _canonical(res["all_solutions"]) == ["{x:3/2,y:3/2}"], res


class TestExpressionListControlsUnchanged:
    """The expression form (implicit ``= 0``) must keep its exact behavior."""

    def test_comma_expression_list_unchanged(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x + y - 2, x - y", variable="x, y", session=False)
        assert res["success"], res
        assert _canonical(res["all_solutions"]) == ["{x:1,y:1}"], res

    def test_bracket_expression_list_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "[x + y - 2, x - y]", variable="x, y", session=False)
        assert res["success"], res
        assert _canonical(res["all_solutions"]) == ["{x:1,y:1}"], res

    def test_scalar_equation_unchanged(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x**2 - 4 = 0", variable="x", session=False)
        assert res["success"], res
        assert res["all_solutions"] == ["-2", "2"], res

    def test_scalar_equation_with_free_symbol_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x + y = 3", variable="x", session=False)
        assert res["success"], res
        assert res["all_solutions"] == ["3 - y"], res


class TestVariableHandling:
    """``variable`` inference and the comma list keep working."""

    def test_missing_variable_lists_candidates(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x = 3, 2*y = 4", session=False)
        assert res["success"] is False, res
        assert "variable" in res["error"], res
        assert "x" in res["error"] and "y" in res["error"], res


class TestCuratedRefusals:
    """Malformed and inequality lists get a clear, non-leaking answer."""

    def test_malformed_equation_element_names_the_element(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x + = 3, y = 1", variable="x, y", session=False)
        assert res["success"] is False, res
        assert "Cannot parse" in res["error"], res
        assert "x + = 3" in res["error"], res

    def test_inequality_comma_list_still_fails(
        self, fresh_session_manager: Any
    ) -> None:
        """No ``=`` mark means the pre-existing path is untouched."""
        _ = fresh_session_manager
        res = _math()("solve", "x > 1, x < 3", variable="x", session=False)
        assert res["success"] is False, res

    def test_relational_marker_list_is_not_read_as_equations(
        self, fresh_session_manager: Any
    ) -> None:
        """``>=``/``<=`` contain ``=`` but are not equations."""
        _ = fresh_session_manager
        res = _math()("solve", "x >= 1, x <= 3", variable="x", session=False)
        assert res["success"] is False, res

    def test_mixed_equation_and_inequality_is_curated(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x = 3, x > 1", variable="x", session=False)
        assert res["success"] is False, res
        assert "inequality" in res["error"].lower(), res


class TestEquationSystemRecording:
    """An equation-list solve records into the chain without a warning."""

    def test_session_records_the_equation_system_step(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("eq_list")
        res = tools["math"](
            "solve", "x + y = 3, x - y = 1", variable="x, y", session=True
        )
        assert res["success"], res
        assert res.get("step") == 1, res
        assert not any(
            "recording failed" in w.lower() for w in res.get("warnings", [])
        ), res

"""r19 black-box surface fixes: F3, F8, F12, F13, F14, F15, F16, F21.

Each test pins one verified defect from the r19 audit: a call that answered
wrongly (or leaked an internal exception) must now answer curately, while the
control cases that already behaved correctly stay unchanged.
"""

from __future__ import annotations

from typing import Any

from symkit.domain.expression_parser import parse_expression_string
from symkit_mcp.tools import math as math_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _math() -> Any:
    mcp = MockMCP()
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


# -- F3: bracketed equation systems must reach solve_system ------------------


class TestBracketedEquationSystems:
    def test_bracket_list_routes_to_system_solve(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "[x+y-3, x-y-1]", variable="x, y", session=False)
        assert res["success"], res
        assert res["all_solutions"][0].replace(" ", "") == "{x:2,y:1}"

    def test_bracket_eq_list_routes_to_system_solve(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _math()(
            "solve", "[Eq(x+y,3), Eq(x-y,1)]", variable="x, y", session=False
        )
        assert res["success"], res
        assert res["all_solutions"][0].replace(" ", "") == "{x:2,y:1}"

    def test_comma_list_control_still_solves(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _math()("solve", "x+y-3, x-y-1", variable="x, y", session=False)
        assert res["success"], res
        assert res["all_solutions"][0].replace(" ", "") == "{x:2,y:1}"

    def test_genuine_2d_matrix_keeps_previous_behavior(
        self, fresh_session_manager: Any
    ) -> None:
        """A real 2-D matrix literal is not an equation list and must keep the
        pre-existing answer (no regression on matrix-solve semantics)."""
        _ = fresh_session_manager
        res = _math()("solve", "[[x,1],[1,x]]", variable="x", session=False)
        assert res["success"] is False, res
        assert "No solution found" in res["error"]


# -- F15: set literals hand solve a curated refusal --------------------------


def test_set_literal_solve_is_curated(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("solve", "{x+y-3, x-y-1}", variable="x, y", session=False)
    assert res["success"] is False, res
    assert "set" in res["error"].lower()
    assert "comma-separated" in res["error"] or "bracket" in res["error"]
    assert "free_symbols" not in res["error"]


# -- F8: dsolve initial-condition diagnostics --------------------------------


def test_ics_error_message_uses_unambiguous_quoting(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    res = _math()(
        "dsolve", "diff(y,t) + y", variable="y", with_respect_to="t",
        ics={"bad": "0"}, session=False,
    )
    assert res["success"] is False, res
    assert '"y(0)": "<value>"' in res["error"], res["error"]
    assert '"y\'(0)": "<value>"' in res["error"], res["error"]
    # The old broken literal must be gone.
    assert "'y'(0)'" not in res["error"], res["error"]


def test_contradictory_ics_reports_inconsistency(fresh_session_manager: Any) -> None:
    """A full contradictory triple must not leak sympy's raw ValueError, and
    must not partially accept the conditions (task-16)."""
    _ = fresh_session_manager
    res = _math()(
        "dsolve", "diff(y,x,2) + y", variable="y", with_respect_to="x",
        ics={"y(0)": "0", "y'(0)": "0", "y(pi/2)": "5"}, session=False,
    )
    assert res["success"] is False, res
    assert "inconsistent" in res["error"].lower(), res["error"]
    assert "Couldn't solve for initial conditions" not in res["error"]
    assert "ValueError" not in res["error"]


def test_singular_ics_refusal_wording_unchanged(fresh_session_manager: Any) -> None:
    """Control: the singular-system refusal keeps its exact wording."""
    _ = fresh_session_manager
    res = _math()(
        "dsolve", "diff(y,x,2) + y", variable="y", with_respect_to="x",
        ics={"y'(0)": "0", "y(pi/2)": "5"}, session=False,
    )
    assert res["success"] is False, res
    assert "the initial-condition system is singular" in res["error"], res["error"]
    assert "wedge" in res["error"]


# -- F12: special-function antiderivatives carry a warning -------------------


def test_special_antiderivative_carries_warning(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("integrate", "exp(x**2)", variable="x", session=False)
    assert res["success"], res
    assert res["expression"] == "sqrt(pi)*erfi(x)/2", res["expression"]
    assert any("erfi" in w for w in res["warnings"]), res.get("warnings")
    assert any(
        "not expressible with elementary functions" in w for w in res["warnings"]
    )


def test_erf_antiderivative_carries_warning(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("integrate", "exp(-x**2/2)", variable="x", session=False)
    assert res["success"], res
    assert any("erf" in w for w in res.get("warnings", [])), res.get("warnings")


def test_elementary_antiderivative_has_no_special_warning(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    res = _math()("integrate", "x**2", variable="x", session=False)
    assert res["success"], res
    assert res["expression"] == "x**3/3", res["expression"]
    assert not any("special function" in w for w in res.get("warnings", []))


# -- F13: the advertised `method` parameter works for integrate --------------


def test_integrate_accepts_risch_method(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("integrate", "x**2", variable="x", method="risch", session=False)
    assert res["success"], res
    assert res["expression"] == "x**3/3", res["expression"]


def test_integrate_auto_method_is_the_default(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("integrate", "x**2", variable="x", method="auto", session=False)
    assert res["success"], res


def test_integrate_rejects_unknown_method(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("integrate", "x**2", variable="x", method="banana", session=False)
    assert res["success"] is False, res
    assert "'auto'" in res["error"] and "'risch'" in res["error"], res["error"]


# -- F14: the parse response reports the symbols it found --------------------


def test_parse_reports_symbol_list(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("parse", "x + y*z", session=False)
    assert res["success"], res
    assert res["symbols"] == ["x", "y", "z"], res.get("symbols")


def test_parse_symbols_empty_for_constant(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("parse", "5", session=False)
    assert res["success"], res
    assert res["symbols"] == []


def test_parse_symbols_empty_for_matrix(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()("parse", "[[x,y],[z,1]]", session=False)
    assert res["success"], res
    assert res["symbols"] == []


# -- F16: unreadable unit strings are named, not just echoed -----------------


def test_unreadable_unit_string_is_reported_with_hint(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    res = _math()(
        "dimension", "E - m*v**3",
        units={"E": "J", "m": "Kg", "v": "m/s"}, session=False,
    )
    assert res["success"], res
    assert res["unreadable_units"] == ["m: 'Kg'"], res.get("unreadable_units")
    assert "could not be read" in res["message"], res["message"]
    assert "did you mean 'kg'?" in res["message"], res["message"]
    # Compatibility: the symbol is still listed as unknown.
    assert res["unknown_symbols"] == ["m"]


def test_unreadable_unit_without_case_match_has_no_hint(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    res = _math()(
        "dimension", "E - m*v**3",
        units={"E": "J", "m": "blorp", "v": "m/s"}, session=False,
    )
    assert res["unreadable_units"] == ["m: 'blorp'"], res.get("unreadable_units")
    assert "could not be read" in res["message"]
    assert "did you mean" not in res["message"]


def test_true_unknown_symbol_control_is_unchanged(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    res = _math()(
        "dimension", "E - K*m*v**2",
        units={"E": "J", "m": "kg", "v": "m/s"}, session=False,
    )
    assert res["unknown_symbols"] == ["K"], res
    assert "unreadable_units" not in res, res
    assert res["message"] == (
        "Dimensional analysis incomplete: some symbols have unknown units (K)."
    )


# -- F21: prose input must not leak Python's SyntaxError wording --------------


def test_prose_syntax_error_is_curated() -> None:
    expr, err = parse_expression_string("f(x) = 1 = 2")
    assert expr is None
    assert err is not None
    assert not err.startswith("SyntaxError"), err
    assert "cannot parse the input as a mathematical expression" in err, err
    assert "cannot assign to function call" in err, err


def test_plain_invalid_syntax_is_curated() -> None:
    expr, err = parse_expression_string("The velocity is constant")
    assert expr is None
    assert err is not None
    assert not err.startswith("SyntaxError"), err
    assert "cannot parse the input as a mathematical expression" in err, err
    assert "invalid syntax" in err, err


def test_prose_error_is_curated_at_the_math_surface(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    res = _math()("parse", "f(x) = 1 = 2", session=False)
    assert res["success"] is False, res
    assert "SyntaxError" not in res["error"], res["error"]
    assert "cannot parse the input as a mathematical expression" in res["error"]

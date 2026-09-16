"""r19 wave-2 fixes (agent L): F22, F23, F24, F25, F26, F27, F6, F7.

Each test pins one verified defect from the r19 audit against the shipped wheel:

- F22 (P1) solve headline degrades under assumptions (``expression: "False"``,
  a filtered root resurrected as both kept and filtered, the useful root buried
  in ``all_solutions``).
- F23 (P3) an expression-valued assumption string is whitespace-shredded into
  meaningless property tokens and silently does nothing.
- F24 (P2) re-verification flips a definitive algebraic verdict via the
  dimension check with no discrepancy disclosure.
- F25 (P3) dimension-inconclusive reason misattributes fractional-power
  failures to "symbol units missing or unreadable".
- F26 (P3) matrix-operation steps silently lose ``input_srepr``.
- F27 (P3) solve failure shapes are raw/misleading (power variable, inequality,
  HTML-escaped comparators).
- F6  (P2) the library write path has no dimensional gate.
- F7  (P2) ``formula_add``-declared units are dropped in ``formulas_used``.
"""

from __future__ import annotations

import json
from typing import Any

import sympy as sp

from symkit_mcp.tools import _state
from symkit_mcp.tools._op_helpers import assemble_solve_response
from symkit_mcp.tools.formula import register_formula_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools
from symkit_mcp.tools.symbols import register_symbol_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    register_formula_tools(mcp)
    register_symbol_tools(mcp)
    return mcp.tools


def _dimension_check(step_dict: dict[str, Any]) -> Any:
    return json.loads(step_dict["verification_result"]).get("dimension_check")


# ── F22: solve headline must not be a Boolean or an excluded root ────────────

_RESONANCE = "-4*Omega*beta**2 - 2*Omega*(Omega**2 - omega0**2) = 0"
_RESONANCE_ASSUMPTIONS = [
    "Omega is positive",
    "beta is positive",
    "omega0 is positive",
]
_USEFUL_ROOT = "sqrt(-2*beta**2 + omega0**2)"


class TestSolveHeadlineUnderAssumptions:
    def test_headline_is_the_useful_root_not_a_boolean(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve",
            expression=_RESONANCE,
            variable="Omega",
            assumptions=_RESONANCE_ASSUMPTIONS,
            session=False,
        )
        assert res["success"], res
        # The headline must never be a bare Boolean.
        assert res["expression"] not in ("True", "False"), res
        assert res["expression"].startswith("Eq(Omega,"), res
        assert res["solution"] == _USEFUL_ROOT, res
        assert res["expression"] == f"Eq(Omega, {_USEFUL_ROOT})", res
        assert "False" not in res["latex"], res

    def test_restored_root_is_not_also_reported_as_filtered(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve",
            expression=_RESONANCE,
            variable="Omega",
            assumptions=_RESONANCE_ASSUMPTIONS,
            session=False,
        )
        assert "0" in res["all_solutions"], res
        assert "0" not in res["filtered_by_assumptions"], res
        assert f"-{_USEFUL_ROOT}" in res["filtered_by_assumptions"], res
        # The headline root is not one the response itself calls excluded.
        assert res["solution"] not in res["filtered_by_assumptions"], res

    def test_control_without_assumptions_is_byte_identical(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve", expression=_RESONANCE, variable="Omega", session=False
        )
        assert res["success"], res
        assert res["expression"] == "Eq(Omega, 0)", res
        assert res["solution"] == "0", res
        assert res["all_solutions"] == [
            "0",
            f"-{_USEFUL_ROOT}",
            _USEFUL_ROOT,
        ], res
        assert res["filtered_by_assumptions"] == [], res
        assert res["warnings"] == [], res

    def test_control_simple_root_filtering_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve",
            expression="Omega**2 - 4 = 0",
            variable="Omega",
            assumptions=["Omega is positive"],
            session=False,
        )
        assert res["success"], res
        assert res["expression"] == "Eq(Omega, 2)", res
        assert res["solution"] == "2", res
        assert res["filtered_by_assumptions"] == ["-2"], res

    def test_boolean_solution_is_dropped_with_a_warning(self) -> None:
        x = sp.Symbol("x")
        res = assemble_solve_response(
            sp.Integer(1), x, [sp.true, sp.Integer(2)], [], False, "x", "solve", None
        )
        assert res["success"], res
        assert res["all_solutions"] == ["2"], res
        assert res["solution"] == "2", res
        assert any("oolean" in w for w in res["warnings"]), res["warnings"]


# ── F27: curated solve failure shapes ───────────────────────────────────────


class TestSolveFailureShapes:
    def test_non_symbol_variable_is_curated(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve", expression="v**4 - 2", variable="v**2", session=False
        )
        assert res["success"] is False, res
        assert "symbol name" in res["error"], res["error"]
        assert "'v**2'" in res["error"], res["error"]
        assert "substitution" in res["error"], res["error"]
        assert "No solution found" not in res["error"], res["error"]

    def test_inequality_is_curated(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve", expression="DH/(R*T**2) > 0", variable="T", session=False
        )
        assert res["success"] is False, res
        assert res["error"] == (
            "inequality solving is not supported; use an equation (A = B) or "
            "check the sign of a simplified expression instead"
        ), res["error"]
        assert "solve_univariate_inequality" not in res["error"]
        assert "StrictGreaterThan" not in res["error"]

    def test_html_escaped_operator_is_curated(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="solve",
            expression="DH/(R*T**2) &gt; 0",
            variable="T",
            session=False,
        )
        assert res["success"] is False, res
        assert "HTML-escaped" in res["error"], res["error"]
        assert "&gt;" in res["error"], res["error"]
        assert "directly" in res["error"], res["error"]
        assert "expecting bool" not in res["error"], res["error"]


# ── F23: expression-valued assumption strings are rejected ──────────────────

_EXPR_ASSUMPTION = "Omega**2*b**2 + (Omega**2*m - k)**2 is positive"


class TestExpressionValuedAssumption:
    def test_is_rejected_with_a_curated_warning(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="simplify",
            expression="x + 0",
            assumptions=[_EXPR_ASSUMPTION],
            session=False,
        )
        assert res["success"], res
        assert res["expression"] == "x", res
        # Nothing was applied as garbage properties.
        assert not res.get("assumptions_applied"), res
        warnings = res.get("assumption_warnings") or []
        assert any(_EXPR_ASSUMPTION in w for w in warnings), res
        assert any("not supported" in w for w in warnings), res

    def test_valid_single_variable_assumption_control_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="simplify",
            expression="sqrt(x**2)",
            assumptions=["x is positive"],
            session=False,
        )
        assert res["success"], res
        assert res["expression"] == "x", res
        assert res["assumptions_applied"] == {"x": ["positive"]}, res
        assert not res.get("assumption_warnings"), res

    def test_unparseable_token_keeps_the_legacy_warning(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        res = _tools()["math"](
            operation="simplify",
            expression="x + 0",
            assumptions=["???"],
            session=False,
        )
        assert res["success"], res
        assert any(
            "Could not parse assumption" in w for w in res.get("warnings", [])
        ), res


# ── F24: the dimension check must not silently flip an algebraic verdict ─────


class TestDimensionDisagreement:
    def test_algebraic_verdict_survives_a_dimension_failure(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f24-disagreement")
        tools["register_symbol"]("rho", "density", unit="kg/m^3")
        tools["register_symbol"]("v", "velocity", unit="m/s")
        tools["math"]("simplify", "rho + v", session=True)

        res = tools["session_verify_step"](1)
        assert res["verification_status"] == "verified", res
        assert _dimension_check(res["step"]) is False, res
        assert res["verification"].get("dimension_issues"), res
        assert "disagree" in res["verification"].get("dimension_disagreement", ""), res

    def test_dimension_true_still_adds_to_a_verified_step(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f24-control-true")
        tools["register_symbol"]("rho", "density", unit="kg/m^3")
        tools["register_symbol"]("v", "velocity", unit="m/s")
        tools["math"]("simplify", "rho*v", session=True)

        res = tools["session_verify_step"](1)
        assert res["verification_status"] == "verified", res
        assert _dimension_check(res["step"]) is True, res
        assert "dimension_disagreement" not in res["verification"], res

    def test_without_algebraic_conclusion_dimension_may_set_status(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f24-control-inconclusive")
        tools["register_symbol"]("rho", "density", unit="kg/m^3")
        tools["register_symbol"]("v", "velocity", unit="m/s")
        # A manual step is algebraically inconclusive by design.
        tools["session_record_step"]("rho + v", "dimensionally impossible")

        res = tools["session_verify_step"](1)
        assert res["verification_status"] == "failed", res
        assert _dimension_check(res["step"]) is False, res


# ── F25: inconclusive reason names representability, not missing units ──────


class TestDimensionInconclusiveReason:
    def test_fractional_power_reason_is_named(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f25-fractional")
        tools["register_symbol"]("m", "mass", unit="kg")
        tools["register_symbol"]("L", "length", unit="m")
        tools["math"]("simplify", "sqrt(m)*L", session=True)

        step = tools["session_verify_step"](1)
        assert step["verification_status"] == "verified", step
        assert _dimension_check(step["step"]) is None, step
        assert step["verification"].get("dimension_inconclusive_reason") == (
            "fractional-power dimension not representable"
        ), step["verification"]

        summary = tools["session_verify_session"]()
        assert summary["dimension_inconclusive_steps"] == [1], summary
        joined = " ".join(summary.get("warnings", []))
        assert "fractional-power" in joined, summary
        assert "missing or unreadable" not in joined, summary

    def test_missing_unit_keeps_the_generic_wording(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f25-control-missing")
        tools["register_symbol"]("rho", "density", unit="kg/m^3")
        tools["math"]("simplify", "rho*v**2/2 + rho*v**2/2", session=True)

        summary = tools["session_verify_session"]()
        joined = " ".join(summary.get("warnings", []))
        assert "missing or unreadable" in joined, summary


# ── F26: matrix steps archive the input srepr ───────────────────────────────


class TestMatrixInputSrepr:
    def test_inverse_step_archives_the_matrix_input(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f26-matrix")
        tools["math"]("inv", "[[a,b],[c,d]]", session=True)

        row = tools["session_get_steps"]()["steps"][0]
        assert row["input_srepr"], row
        a, b, c, d = sp.symbols("a b c d")
        assert sp.sympify(row["input_srepr"]) == sp.Matrix([[a, b], [c, d]]), row
        assert "Symbol('a')" in row["input_srepr"], row

    def test_simplify_matrix_step_archives_the_input(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f26-matrix-simplify")
        tools["math"]("simplify", "[[a,b],[b,a]]", session=True)

        row = tools["session_get_steps"]()["steps"][0]
        a, b = sp.symbols("a b")
        assert row["input_srepr"], row
        assert sp.sympify(row["input_srepr"]) == sp.Matrix([[a, b], [b, a]]), row


# ── F6: dimensional gate on the library write path ──────────────────────────


_ENERGY_VARS = {
    "E": {"description": "energy", "unit": "J"},
    "m": {"description": "mass", "unit": "kg"},
    "v": {"description": "speed", "unit": "m/s"},
}


class TestLibraryDimensionGate:
    def test_formula_add_rejects_an_inconsistent_expression(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        res = tools["formula_add"](
            id="f6_bad_energy",
            name="Bad energy",
            sympy_str="E == m*v**3",
            latex="E = m v^3",
            variables=_ENERGY_VARS,
        )
        assert res["success"] is False, res
        assert "dimension" in res["error"].lower(), res["error"]
        assert "different dimensions" in res["error"], res["error"]
        # Nothing landed in the library.
        assert tools["formula_get"]("f6_bad_energy")["success"] is False

    def test_formula_add_consistent_control_still_saves(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        res = tools["formula_add"](
            id="f6_good_energy",
            name="Kinetic energy per mass unit",
            sympy_str="E == m*v**2",
            latex="E = m v^2",
            variables=_ENERGY_VARS,
        )
        assert res["success"] is True, res

    def test_formula_add_without_units_saves_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        res = tools["formula_add"](
            id="f6_no_units",
            name="Unconstrained relation",
            sympy_str="E == m*v**3",
            latex="E = m v^3",
            variables={
                "E": {"unit": "-"},
                "m": {"unit": "-"},
                "v": {"unit": "-"},
            },
        )
        assert res["success"] is True, res

    def test_session_complete_skips_dimensionally_inconsistent_auto_save(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f6-complete-bad")
        session = _state.get_session()
        assert session is not None
        session.load_formula(
            {"expression": "E = m*v**3", "variables": _ENERGY_VARS}
        )

        res = tools["session_complete"]()
        assert res["success"] is True, res
        assert res.get("saved") == {}, res
        assert "dimensionally inconsistent" in res.get("not_saved_reason", ""), res
        assert not res.get("saved_id"), res
        assert any(
            "dimensionally inconsistent" in w for w in res.get("warnings", [])
        ), res

    def test_session_complete_consistent_control_still_auto_saves(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f6-complete-good")
        session = _state.get_session()
        assert session is not None
        session.load_formula(
            {"expression": "E = m*v**2", "variables": _ENERGY_VARS}
        )

        res = tools["session_complete"]()
        assert res["success"] is True, res
        assert res.get("saved_id"), res
        assert not res.get("not_saved_reason"), res

    def test_session_complete_without_units_is_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("f6-complete-no-units")
        tools["math"]("simplify", "a*b", session=True)

        res = tools["session_complete"]()
        assert res["success"] is True, res
        assert res.get("saved_id"), res
        assert not res.get("not_saved_reason"), res


# ── F7: declared units survive into the session's formulas_used record ──────


def test_loaded_formula_units_reach_formulas_used(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("f7-units")

    add = tools["formula_add"](
        id="f7_energy",
        name="Energy relation",
        sympy_str="E == m*v**2",
        latex="E = m v^2",
        variables=_ENERGY_VARS,
    )
    assert add["success"], add

    load = tools["session_load_formula"]("E == m*v**2", formula_id="f7_energy")
    assert load["success"], load

    res = tools["session_complete"]()
    used = res["formulas_used"]["f7_energy"]["variables"]
    assert {name: meta["unit"] for name, meta in used.items()} == {
        "E": "J",
        "m": "kg",
        "v": "m/s",
    }, used

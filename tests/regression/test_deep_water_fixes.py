"""Deep-water black-box fixes (run-020/run-021).

Covers:
- E/I parsed as Symbols, not Euler's number / imaginary unit (WRONG+SILENT).
- assume_for_step accepts a string or list (schema/implementation mismatch).
- derive() recommends formulas added via formula_add in the same process
  (stale repository-only index) and vetoes target-variable-disjoint derived
  junk.
- Goal variable extraction strips English possessives ("Hooke's" → no ghost
  ``s``).
- check_symbol_conflicts sees user registrations even before any expression
  is loaded; unknown domains are preserved verbatim instead of silently
  degrading to "general".
- formula_remove deletes library overlay entries and derived results.
- eigenvects records a session step and renders latex (like eigenvals).
- dsolve accepts Leibniz notation of any order (d^4w/dx^4).
- parse() accepts matrix literals; parse errors are sanitized.
- limit with "+-" direction is a true bidirectional limit (mismatch fails
  loud instead of silently returning the right-hand limit).
- tool_categories reflects the actually registered tools.
- session_complete auto_save after resume does not overwrite the earlier
  record.
- assume() echoes assumptions_applied; solve infers a single free symbol.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_goal import DerivationGoal
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.formula_recommender import FormulaRecommender
from symkit.infrastructure.derivation_repository import (
    DerivationResult,
    get_repository,
)
from symkit.infrastructure.sympy_engine import SymPyEngine
from symkit_mcp.tools._math_dispatch import _parse_ode
from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.codegen import register_codegen_tools
from symkit_mcp.tools.formula import register_formula_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.orchestration import register_orchestration_tools
from symkit_mcp.tools.session import register_session_tools
from symkit_mcp.tools.symbols import register_symbol_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    register_assumption_tools(mcp)
    register_formula_tools(mcp)
    register_symbol_tools(mcp)
    register_codegen_tools(mcp)
    register_orchestration_tools(mcp)
    return mcp.tools


# ── F1: E/I are symbols ───────────────────────────────────────────────


def test_E_and_I_parse_as_symbols_not_constants():
    expr, err = parse_expression_string("E*I/L")
    assert err is None and expr is not None
    names = {str(s) for s in expr.free_symbols}
    assert names == {"E", "I", "L"}
    assert not expr.has(sp.E)  # Euler's number must not sneak in
    assert not expr.has(sp.I)  # imaginary unit must not sneak in


def test_constants_still_parse_as_constants():
    expr, err = parse_expression_string("pi*E_0 + exp(x)")
    assert err is None and expr is not None
    assert expr.has(sp.pi)
    assert expr.has(sp.exp(sp.Symbol("x")))
    # Subscripted E_0 is an ordinary symbol and must remain one.
    assert sp.Symbol("E_0") in expr.free_symbols


def test_beam_ode_with_E_and_I_solves_symbolically(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="d^2w/dx^2 + P*(L-x)/(E*I)",
        variable="w",
        with_respect_to="x",
        ics={"w(0)": "0", "w'(0)": "0"},
        session=False,
    )
    assert res["success"], res
    expr, err = parse_expression_string(res["expression"])
    assert err is None and isinstance(expr, sp.Equality)
    Em, Im, P, L, x = sp.symbols("E I P L x")
    expected = -P * x**2 * (3 * L - x) / (6 * Em * Im)
    assert sp.simplify(expr.rhs - expected) == 0


def test_codegen_declares_E_and_I(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["generate_output"](
        format="sympy_script",
        expressions=[{"name": "w_tip", "expr": "P*L**3/(3*E*I)", "description": "tip"}],
        operations=[],
    )
    assert res["success"], res
    script = res["script"]
    namespace: dict = {}
    exec(script, namespace)  # must not raise NameError
    assert sp.Symbol("E") in namespace["w_tip"].free_symbols
    assert sp.Symbol("I") in namespace["w_tip"].free_symbols


# ── F2: assume_for_step signature ─────────────────────────────────────


def test_assume_for_step_accepts_string(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("afs-string")
    res = tools["assume_for_step"](args="z positive")
    assert res["success"], res
    assert "z" in res["step_assumptions"]


def test_assume_for_step_accepts_list(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("afs-list")
    res = tools["assume_for_step"](args=["y", "real"])
    assert res["success"], res
    assert "y" in res["step_assumptions"]


# ── F3/F7: derive() freshness and pollution veto ──────────────────────


def test_derive_recommends_freshly_added_formula(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    add = tools["formula_add"](
        id="test13_like_pendulum_period",
        name="Pendulum period test entry",
        sympy_str="T == 2*pi*sqrt(L/g)",
        latex="T = 2\\pi\\sqrt{L/g}",
        variables={
            "T": {"description": "period", "unit": "-"},
            "L": {"unit": "-"},
            "g": {"unit": "-"},
        },
        domain="mechanics",
        tags=["pendulum", "test13"],
    )
    assert add["success"], add
    res = tools["derive"](
        goal="derive the pendulum period for small oscillations",
        domain="mechanics",
    )
    assert res["success"], res
    ids = [f["formula_id"] for f in res["recommended_formulas"]]
    assert "test13_like_pendulum_period" in ids


def test_recommender_vetoes_target_disjoint_derived_junk():
    repo = get_repository()
    repo.register(
        DerivationResult(
            id="junk_exp",
            name="maxwell-boltzmann-v_rms",
            expression="exp(x)",
            variables={"x": {"description": "", "unit": ""}},
            verified=True,
        )
    )
    repo.register(
        DerivationResult(
            id="good_vrms",
            name="maxwell-boltzmann-v_rms",
            expression="v_rms = sqrt(3*k_B*T/m)",
            variables={v: {"description": "", "unit": ""} for v in ("v_rms", "k_B", "T", "m")},
            verified=True,
        )
    )
    goal = DerivationGoal.from_text(
        "derive v_rms = sqrt(3*k_B*T/m) for the maxwell boltzmann distribution"
    )
    rec = FormulaRecommender(repository=repo)
    ids = [c["formula_id"] for c in rec.recommend(goal, top_k=5)]
    assert "good_vrms" in ids
    assert "junk_exp" not in ids


def test_formula_remove_library_entry(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    add = tools["formula_add"](
        id="junk_to_delete",
        name="junk entry",
        sympy_str="exp(x)",
        latex="e^x",
        variables={"x": {"unit": "-"}},
        tags=["junk"],
    )
    assert add["success"], add
    assert any(
        r["id"] == "junk_to_delete"
        for r in tools["formula_search"]("junk_to_delete")["results"]
    )
    rem = tools["formula_remove"]("junk_to_delete")
    assert rem["success"], rem
    assert not any(
        r["id"] == "junk_to_delete"
        for r in tools["formula_search"]("junk_to_delete")["results"]
    )


def test_formula_remove_derived_entry(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    repo = get_repository()
    repo.register(
        DerivationResult(id="junk_derived", name="junk", expression="exp(x)")
    )
    repo.save("junk_derived")
    rem = tools["formula_remove"]("junk_derived")
    assert rem["success"], rem
    assert repo.get("junk_derived") is None


def test_formula_remove_unknown_id_fails_loud(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    rem = tools["formula_remove"]("no_such_formula_id")
    assert not rem["success"]


# ── F4: possessive ghost variables ────────────────────────────────────


def test_goal_extraction_strips_possessives():
    goal = DerivationGoal.from_text(
        "derive Hooke's law elastic energy U = 1/2*k*x^2", "mechanics"
    )
    assert "s" not in goal.target_variables
    assert "U" in goal.target_variables
    goal2 = DerivationGoal.from_text(
        "derive the pendulum period from Newton's second law", "mechanics"
    )
    assert "s" not in goal2.target_variables


# ── F5/F6: symbol registry ────────────────────────────────────────────


def test_check_symbol_conflicts_sees_registry_only_symbols(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("conflicts")
    tools["register_symbol"](name="c_t13", meaning="speed of light", domain="optics")
    tools["register_symbol"](
        name="c_t13", meaning="specific heat capacity", domain="thermodynamics"
    )
    res = tools["check_symbol_conflicts"]()
    assert res["success"], res
    assert res["has_conflicts"], res
    assert any(c["symbol"] == "c_t13" for c in res["conflicts"])


def test_register_symbol_preserves_unknown_domain(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("domains")
    res = tools["register_symbol"](
        name="v_rel", meaning="relative velocity", domain="relativity"
    )
    assert res["success"], res
    assert res["registered"]["domain"] == "relativity"
    assert res.get("warning")  # non-silent: tells the user the domain is custom
    listed = tools["list_domain_symbols"](domain="relativity")
    assert any(s["name"] == "v_rel" for s in listed["symbols"])


# ── F8: eigenvects chain recording ────────────────────────────────────


def test_eigenvects_records_step_and_renders(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("eigvects")
    res = tools["math"](
        operation="eigenvects", expression="[[2,-1],[-1,2]]", session=True
    )
    assert res["success"], res
    assert res.get("step") is not None, res
    assert res["expression"]
    assert res["latex"] and res["latex"] != "$$$$"
    shown = tools["session_show"]()
    assert shown["sympy"]


# ── F9: nth-order Leibniz in dsolve ───────────────────────────────────


def test_parse_ode_accepts_fourth_order_leibniz():
    expr, err = _parse_ode("d^4w/dx^4 - q", "w", "x")
    assert err is None and expr is not None
    orders = {d.derivative_count for d in expr.atoms(sp.Derivative)}
    assert 4 in orders


def test_dsolve_fourth_order_beam(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](
        operation="dsolve",
        expression="d^4w/dx^4 - q/(Em*Iz)",
        variable="w",
        with_respect_to="x",
        session=False,
    )
    assert res["success"], res
    out = res["expression"]
    assert "C1" in out and "C4" in out and "q" in out


def test_parse_ode_rejects_mismatched_orders():
    expr, err = _parse_ode("d^3w/dx^2 - q", "w", "x")
    assert expr is None
    assert err is not None


# ── F10/F13: matrix literals and sanitized parse errors ───────────────


def test_parse_matrix_literal_returns_matrix():
    expr, err = parse_expression_string("[[a,b],[c,d]]")
    assert err is None and expr is not None
    assert isinstance(expr, sp.MatrixBase)
    assert expr.shape == (2, 2)
    assert expr.det() == sp.Symbol("a") * sp.Symbol("d") - sp.Symbol("b") * sp.Symbol("c")


def test_parse_error_message_is_sanitized():
    expr, err = parse_expression_string("(((")
    assert expr is None
    assert err is not None
    assert not err.startswith("(")
    # CPython words an unterminated-bracket tokenizer error differently across
    # versions ("unexpected EOF" on 3.11+, "EOF in multi-line statement" on
    # 3.10), so assert the reason survives rather than the exact phrasing.
    assert "EOF" in err


# ── F11: true bidirectional limits ────────────────────────────────────


def test_limit_bidirectional_mismatch_fails_loud():
    engine = SymPyEngine()
    expr = engine.parse("1/x")
    out = engine.limit(expr, "x", "0", "+-")
    assert not out.is_valid
    assert out.error and ("left" in out.error.lower() or "direction" in out.error.lower())


def test_limit_bidirectional_agreement_returns_value():
    engine = SymPyEngine()
    expr = engine.parse("sin(x)/x")
    out = engine.limit(expr, "x", "0", "+-")
    assert out.is_valid
    assert out.sympy_expr == 1


def test_limit_single_direction_still_works():
    engine = SymPyEngine()
    expr = engine.parse("1/x")
    out = engine.limit(expr, "x", "0", "+")
    assert out.is_valid and out.sympy_expr == sp.oo
    out = engine.limit(expr, "x", "0", "-")
    assert out.is_valid and out.sympy_expr == -sp.oo


# ── F12: tool_categories reflects reality ─────────────────────────────


def test_tool_categories_lists_all_registered_tools():
    from mcp.server.fastmcp import FastMCP

    from symkit_mcp.tools import register_all_tools

    mcp = FastMCP("t")
    register_all_tools(mcp)
    registered = set(mcp._tool_manager._tools.keys())  # noqa: SLF001
    fn = mcp._tool_manager._tools["tool_categories"].fn  # noqa: SLF001
    res = fn()
    listed = {t for cat in res["categories"] for t in cat["tools"]}
    assert listed == registered
    assert "formula_constants" not in listed
    assert "assume_for_step" in listed
    assert "formula_add" in listed


# ── F14: resume-then-complete does not overwrite ──────────────────────


def test_second_complete_saves_new_id(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    start = tools["session_start"]("double-save")
    sid = start["session_id"]
    tools["math"](operation="parse", expression="x**2 + 1", session=True)
    first = tools["session_complete"](auto_save=True, description="first save")
    assert first.get("saved_to"), first
    tools["session_resume"](session_id=sid)
    tools["math"](operation="diff", expression="x**2 + 1", variable="x", session=True)
    second = tools["session_complete"](auto_save=True, description="second save")
    assert second.get("saved_to"), second
    assert second["saved_id"] != first["saved_id"]
    repo = get_repository()
    assert repo.get(first["saved_id"]) is not None
    assert repo.get(second["saved_id"]) is not None


# ── F15/F16: echo and inference polish ────────────────────────────────


def test_assume_echoes_applied_assumptions(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["assume"]({"x": "positive real"})
    assert res["success"], res
    assert res["assumptions_applied"] == {"x": ["positive", "real"]}


def test_solve_infers_single_free_symbol(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](operation="solve", expression="x+1", session=False)
    assert res["success"], res
    assert res["solution"] == "Eq(x, -1)" or "-1" in res["solution"]


def test_solve_missing_variable_lists_free_symbols(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    res = tools["math"](operation="solve", expression="x+y", session=False)
    assert not res["success"]
    assert "x" in res["error"] and "y" in res["error"]

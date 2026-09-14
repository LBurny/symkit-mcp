"""Graded verification semantics and auto-verification coverage.

- ``overall`` is ``"verified"`` iff no step failed and at least one verified
  (inconclusive steps no longer poison the chain);
- dsolve steps are verified by substituting the solution back (checkodesol);
- limit steps are verified by numeric spot-checks near the point;
- evalf steps are verified by independent numeric re-evaluation;
- engine failures carry the underlying error cause.
"""

from __future__ import annotations

import json

import sympy as sp

from symkit_mcp.tools import _state
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py


def _tools():
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def test_overall_verified_with_mixed_verified_and_inconclusive(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("graded")
    tools["math"](operation="solve", expression="x**2 - 4 == 0", variable="x")
    tools["math"](operation="substitute", expression="x**2 - 4", substitution={"x": "2"})
    # A CUSTOM note step is always inconclusive.
    tools["session_record_step"]("x**2 - 4", "manual note")
    summary = tools["session_verify_session"]()
    assert summary["failed"] == 0
    assert summary["verified"] >= 2
    assert summary["inconclusive"] >= 1
    assert summary["overall"] == "verified"


def test_overall_failed_dominates(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("graded_fail")
    tools["math"](operation="simplify", expression="x + x")
    sess = _state.get_session()
    assert sess is not None
    # Corrupt the archived result to force a FAILED verification. Under
    # invariant I2 the machine-readable srepr is authoritative, so both it and
    # the display string must be changed to represent a genuinely wrong output.
    sess.steps[-1].output_expression = "3*x"
    sess.steps[-1].output_srepr = sp.srepr(3 * sp.Symbol("x"))
    res = tools["session_verify_step"](1)
    assert res["verification_status"] == "failed"
    summary = tools["session_verify_session"]()
    assert summary["overall"] == "failed"


def test_display_string_edit_does_not_change_verdict(fresh_session_manager):
    """Invariant I2: the display string is presentation, not the record.

    Editing only ``output_expression`` must not flip a verified step to failed;
    the archived ``output_srepr`` is what verification replays.
    """
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("display_only_edit")
    tools["math"](operation="simplify", expression="x + x")
    sess = _state.get_session()
    assert sess is not None
    sess.steps[-1].output_expression = "3*x"
    res = tools["session_verify_step"](1)
    assert res["verification_status"] == "verified"


def test_dsolve_step_auto_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("dsolve_verify")
    tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="v",
        with_respect_to="t",
    )
    sess = _state.get_session()
    assert sess is not None
    assert '"verified"' in sess.steps[-1].verification_result


def test_evalf_step_auto_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("evalf_verify")
    tools["math"](operation="evalf", expression="sqrt(2)*pi", session=True)
    sess = _state.get_session()
    assert sess is not None
    assert '"verified"' in sess.steps[-1].verification_result


def test_limit_step_auto_verified(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("limit_verify")
    tools["math"](operation="limit", expression="sin(x)/x", variable="x", point="0")
    sess = _state.get_session()
    assert sess is not None
    assert '"verified"' in sess.steps[-1].verification_result


def test_engine_parse_error_carries_cause():
    from symkit.infrastructure.sympy_engine import SymPyEngine

    engine = SymPyEngine()
    bad = engine.parse("x +")
    assert not bad.is_valid
    assert bad.error  # non-empty root cause, not a bare failure


def test_dsolve_failure_reports_root_cause(fresh_session_manager):
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("dsolve_err")
    # Function/variable mismatch: the ODE is in v(t) but we ask for u(t).
    res = tools["math"](
        operation="dsolve",
        expression="Derivative(v(t), t) = -k*v(t)",
        variable="u",
        with_respect_to="t",
    )
    assert not res["success"]
    assert res["error"] != "Operation 'dsolve' failed"
    assert "dsolve" in res["error"].lower()


def test_parse_ode_keeps_forcing_function_notation():
    from symkit_mcp.tools._math_dispatch import _parse_ode

    expr, error = _parse_ode("diff(v, t) = -k*v + f(t)", "v", "t")
    assert error is None
    assert expr is not None
    assert isinstance(expr, sp.Equality)
    assert expr.rhs.has(sp.Function("f")(sp.Symbol("t")))


def test_simplify_boolean_output_records_without_crash(fresh_session_manager):
    """Regression (run-008): simplify(Eq(...)) under assumptions returns a plain
    Python bool; the verifier's _difference crashed (Add - bool) and the step
    silently vanished from the chain."""
    _ = fresh_session_manager
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    tools = mcp.tools
    tools["session_start"]("bool_simplify")
    res = tools["math"](
        operation="simplify",
        expression="Eq(sqrt(4*m*k - c**2)/(2*m), sqrt(k/m - c**2/(4*m**2)))",
        assumptions=["m positive", "k positive", "c positive"],
        session=True,
    )
    assert res["success"], res
    assert res["expression"] == "True"
    assert res.get("step"), res.get("warnings")
    assert not any("Step recording failed" in w for w in res.get("warnings", []))


def test_manual_equation_steps_are_content_checked(fresh_session_manager):
    """D7 black-box: session_record_step judges the content of a recorded Eq."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("d7_manual_identity")
    good = tools["session_record_step"]("(a+b)**2 = a**2 + 2*a*b + b**2", "correct identity")
    false = tools["session_record_step"]("(a+b)**2 = a**2 + b**2", "pseudo identity")
    broken = tools["session_record_step"]("1 = 2", "broken arithmetic")
    assert good["verification_status"] == "success"
    assert false["verification_status"] == "pending_verification"
    assert broken["verification_status"] == "failed"
    summary = tools["session_verify_session"]()
    assert summary["failed"] == 1
    assert summary["failed_steps"] == [3]
    assert summary["overall"] == "failed"


def test_complete_skips_failed_symbolic_tail(fresh_session_manager):
    """D8 black-box: the headline is the last non-failed step, not the failed tail."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("d8_failed_tail")
    tools["math"](operation="simplify", expression="x + x")
    tools["math"](operation="simplify", expression="x + x")
    session = _state.get_session()
    assert session is not None
    # Corrupt the tail to a FAILED symbolic result sharing the lineage symbol,
    # so the legacy representative selection would pick it as the outcome.
    session.steps[-1].output_expression = "3*x"
    session.steps[-1].output_srepr = sp.srepr(3 * sp.Symbol("x"))
    session.steps[-1].verification_result = json.dumps(
        {"status": "failed", "message": "wrong", "details": {}}
    )
    result = tools["session_complete"](auto_save=False)
    assert result["final_expression"] == "2*x"
    assert result["final_expression_skipped_failed"] is True
    assert "step 2" in result["note"]


def test_complete_without_failed_step_has_no_fallback_fields(fresh_session_manager):
    """D8 regression guard: a clean session reports no fallback fields."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"]("d8_clean")
    tools["math"](operation="simplify", expression="x + x")
    result = tools["session_complete"](auto_save=False)
    assert "final_expression_skipped_failed" not in result
    assert "note" not in result
    assert result["final_expression"] == "2*x"

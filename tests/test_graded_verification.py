"""Graded verification semantics and auto-verification coverage.

- ``overall`` is ``"verified"`` iff no step failed and at least one verified
  (inconclusive steps no longer poison the chain);
- dsolve steps are verified by substituting the solution back (checkodesol);
- limit steps are verified by numeric spot-checks near the point;
- evalf steps are verified by independent numeric re-evaluation;
- engine failures carry the underlying error cause.
"""

from __future__ import annotations

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
    # Corrupt the recorded output to force a FAILED verification.
    sess.steps[-1].output_expression = "3*x"
    res = tools["session_verify_step"](1)
    assert res["verification_status"] == "failed"
    summary = tools["session_verify_session"]()
    assert summary["overall"] == "failed"


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

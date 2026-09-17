"""Round-22 verifier-surface fixes (lanes A/B findings, probe audit_session.py).

  S2  recorded "exact = truncated decimal" is not a flat failed (task-04)
  S3  recorded "pi = 3.14" stays failed WITH the residual disclosed (control)
  S4  definite integrate echoing an unevaluated Integral is not verified (task-15)
  S5  integrate 1/(2+cos x): floor branch term no longer defeats reverse check (task-05)
  S6  diff output with unevaluated floor derivative is not an empty green (task-05)
  S7  substitute with float constants: relative-tolerance match (task-06)
  S8  expand of an A-B input is not flagged suspect_identity; simplify still is (task-07)
  S9  failed tool-call steps are disclosed in verify_session (task-07)
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from symkit_mcp.tools._state import set_session
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools
from tests.conftest import MockMCP


def _tools() -> dict[str, Any]:
    mcp = MockMCP()
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _last_step_verdict(tools: dict[str, Any]) -> tuple[str, str]:
    steps = tools["session_get_steps"]().get("steps") or []
    last = steps[-1] if steps else {}
    vr = last.get("verification_result") or ""
    if isinstance(vr, str):
        with contextlib.suppress(ValueError):
            vr = json.loads(vr)
    if isinstance(vr, dict):
        return str(vr.get("status") or last.get("status") or ""), json.dumps(vr)
    return str(last.get("status") or ""), str(vr)


def test_recorded_truncated_decimal_equation_is_not_failed(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s2")
    recorded = tools["session_record_step"](
        expression="2*pi*sqrt(Rational(1,2)/Rational(98,10)) = 1.41922689511372874777622152433",
        description="numeric pendulum period",
    )
    summary = tools["session_verify_session"]()
    assert recorded["verification_status"] != "failed", recorded
    assert summary["overall"] != "failed", summary


def test_recorded_off_numeric_equation_fails_with_residual(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s3")
    recorded = tools["session_record_step"](
        expression="pi = 3.14", description="bad approximation"
    )
    verdict = json.dumps((recorded.get("step") or {}).get("verification_result", ""))
    assert recorded["verification_status"] == "failed", recorded
    assert "differ" in verdict, verdict


def test_unevaluated_definite_integral_echo_is_not_verified(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s4")
    tools["math"](
        "integrate", "x**3/(exp(x) - 1)", variable="x", lower="0", upper="oo",
        session=True,
    )
    status, blob = _last_step_verdict(tools)
    assert status != "verified", blob
    assert "unevaluated" in blob.lower(), blob


def test_floor_antiderivative_reverse_check_verifies(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s5")
    tools["math"]("integrate", "1/(2 + cos(x))", variable="x", session=True)
    status, blob = _last_step_verdict(tools)
    assert status == "verified", blob


def test_floor_derivative_output_is_not_an_empty_green(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s6")
    tools["math"](
        "diff",
        "2*sqrt(3)*(atan(sqrt(3)*tan(x/2)/3) + pi*floor((x/2 - pi/2)/pi))/3",
        variable="x",
        session=True,
    )
    status, blob = _last_step_verdict(tools)
    assert status != "verified", blob
    assert "floor" in blob.lower(), blob


def test_substitute_float_constants_match_with_relative_tolerance(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s7")
    tools["math"](
        "substitute",
        "(G*M*T**2/(4*pi**2))**(1/3)",
        substitution={"G": "6.67430e-11", "M": "5.9722e24", "T": "86164.0905"},
        session=True,
    )
    status, blob = _last_step_verdict(tools)
    assert status == "verified", blob


def test_expand_is_not_suspect_but_simplify_still_is(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s8")
    tools["math"]("expand", "(R*C)**2 - 4*L*C", session=True)
    _, expand_blob = _last_step_verdict(tools)
    # Control: a genuine two-sided difference (negated compound, r19 F1 sense).
    tools["math"]("simplify", "x**2 - x*(x + 1)", session=True)
    _, simplify_blob = _last_step_verdict(tools)
    assert "suspect_identity" not in expand_blob, expand_blob
    assert "suspect_identity" in simplify_blob, simplify_blob


def test_failed_operation_steps_are_disclosed(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s9")
    tools["math"]("simplify", "1 + 1", session=True)
    tools["math"]("solve", "R**2*C - 4*L < 0", variable="R", session=True)
    summary = tools["session_verify_session"]()
    assert summary.get("failed_operation_steps"), summary


def teardown_function() -> None:
    set_session(None)


def test_recorded_double_equals_numeric_equation_is_not_failed(
    fresh_session_manager: Any,
) -> None:
    """``A == B`` is the same recorded claim as ``A = B`` (r22v task-04): the
    fold-to-False rebuild must cover the Python-style spelling too."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s2b")
    recorded = tools["session_record_step"](
        expression="2*pi*sqrt(0.5/9.8) == 1.419226895113728659",
        description="numeric pendulum period, python-style equality",
    )
    assert recorded["verification_status"] != "failed", recorded
    verdict = json.dumps((recorded.get("step") or {}).get("verification_result", ""))
    assert "differ" in verdict, verdict


def test_recorded_double_equals_false_claim_discloses_residual(
    fresh_session_manager: Any,
) -> None:
    """``pi == 3.14`` is genuinely false: still failed, but with the residual."""
    _ = fresh_session_manager
    tools = _tools()
    tools["session_start"](name="r22-s2c")
    recorded = tools["session_record_step"](
        expression="pi == 3.14",
        description="deliberately false numeric claim",
    )
    assert recorded["verification_status"] == "failed", recorded
    verdict = json.dumps((recorded.get("step") or {}).get("verification_result", ""))
    assert "differ" in verdict, verdict

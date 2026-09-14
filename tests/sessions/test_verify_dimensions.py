"""Dimension checks wired into session verification (Wave B2)."""

from __future__ import annotations

import json
from typing import Any

from symkit_mcp.tools import _state, _unit_context
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools
from symkit_mcp.tools import symbols as symbol_tools

# MockMCP is provided by conftest.py


def _mcp() -> Any:
    mcp = MockMCP()  # noqa: F821
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    symbol_tools.register_symbol_tools(mcp)
    return mcp


def _start_with_units(mcp: Any) -> None:
    mcp.tools["session_start"]("dimension-test")
    mcp.tools["register_symbol"]("rho", "density", unit="kg/m^3")
    mcp.tools["register_symbol"]("v", "velocity", unit="m/s")


def _dimension_check_value(step_dict: dict[str, Any]) -> Any:
    return json.loads(step_dict["verification_result"]).get("dimension_check")


def test_verify_step_flags_dimension_mismatch(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    _start_with_units(mcp)

    mcp.tools["math"]("simplify", "rho + v", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert result["success"] is True
    assert result["verification_status"] == "failed"
    assert _dimension_check_value(result["step"]) is False
    assert result["verification"].get("dimension_issues")


def test_verify_session_overall_failed(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    _start_with_units(mcp)

    mcp.tools["math"]("simplify", "rho + v", session=True)

    summary = mcp.tools["session_verify_session"]()
    assert summary["success"] is True
    assert summary["overall"] == "failed"
    assert summary["failed"] >= 1


def test_verify_without_units_is_unchanged(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("no-units-test")

    mcp.tools["math"]("simplify", "(x + 1)**2", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert result["verification_status"] == "verified"
    assert _dimension_check_value(result["step"]) is None

    summary = mcp.tools["session_verify_session"]()
    assert summary["overall"] == "verified"


def test_formula_variable_units_feed_verification(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("formula-units-test")

    session = _state.get_session()
    assert session is not None
    session.load_formula(
        {
            "expression": "rho + v",
            "variables": {
                "rho": {"unit": "kg/m^3"},
                "v": {"unit": "m/s"},
            },
        }
    )

    result = mcp.tools["session_verify_step"](1)
    assert result["verification_status"] == "failed"
    assert _dimension_check_value(result["step"]) is False


def test_invalid_unit_string_warns_instead_of_crashing(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("bad-unit-test")

    session = _state.get_session()
    assert session is not None
    load_result = session.load_formula(
        {"expression": "x + y", "variables": {"x": {"unit": "not-a-unit!!"}}}
    )
    assert load_result["success"] is True

    out = _unit_context.with_unit_warnings(session, load_result)
    assert out.get("warnings")
    # A bad unit must degrade to "unknown", never raise.
    mcp.tools["math"]("simplify", "x + y", session=True)
    result = mcp.tools["session_verify_step"](2)
    assert result["success"] is True


def test_recorded_custom_step_is_not_judged_by_the_previous_step(
    fresh_session_manager: Any,
) -> None:
    """A manually recorded step asserts one result; the previous step's
    expression must not be dragged into its dimensional verdict.

    ``session_record_step`` archives the previous step's expression in
    ``input_srepr`` (``_add_step`` defaults it from ``prior_expr``). Reading
    that field made ``T_w + T_in`` — two temperatures added, plainly
    consistent — fail with the *previous* step's ``exp(x)`` complaint.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("stale-input-test")
    mcp.tools["register_symbol"]("T_in", "inlet temperature", unit="K")
    mcp.tools["register_symbol"]("T_w", "wall temperature", unit="K")
    mcp.tools["register_symbol"]("x", "axial coordinate", unit="m")

    # Step 1 is genuinely dimensionally wrong: exp() of a length.
    mcp.tools["session_record_step"]("T_in*exp(x)", "invalid: exp of a dimensioned argument")
    # Step 2 is trivially fine and must not inherit step 1's complaint.
    mcp.tools["session_record_step"]("T_w + T_in", "valid: two temperatures added")

    first = mcp.tools["session_verify_step"](1)
    second = mcp.tools["session_verify_step"](2)

    assert first["verification_status"] == "failed"
    assert _dimension_check_value(first["step"]) is False
    # The manual step stays INCONCLUSIVE algebraically (manual steps are never
    # reported as auto-verified), but its dimension verdict must be clean — it
    # must not inherit step 1's complaint.
    assert _dimension_check_value(second["step"]) is True
    assert second["verification_status"] == "inconclusive"

    summary = mcp.tools["session_verify_session"]()
    assert summary["failed"] == 1
    assert summary["failed_steps"] == [1]


def test_unregistered_symbol_stays_unknown(fresh_session_manager: Any) -> None:
    """An unregistered symbol must not inherit a built-in domain unit.

    Task-09: the unregistered wavenumber ``k`` was silently mapped to the
    pharmacokinetics default "rate constant" (``1/h``), so the physically
    correct ``k = pi/L`` was declared dimensionally inconsistent and a fully
    correct session reported ``overall == "failed"``.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("no-fabricated-units", domain="quantum_mechanics")
    mcp.tools["register_symbol"]("L", "box width", unit="m")

    mcp.tools["math"]("simplify", "k - pi/L", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert result["verification_status"] != "failed"
    assert _dimension_check_value(result["step"]) is None
    assert "k" in result["verification"].get("dimension_unknown_symbols", [])
    assert "k" not in result["verification"].get("dimensions", {})
    assert "L*k" not in json.dumps(result["verification"].get("dimension_issues", []))


def test_explicit_registration_makes_symbol_consistent(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("explicit-unit", domain="quantum_mechanics")
    mcp.tools["register_symbol"]("k", "wavenumber", unit="1/m")
    mcp.tools["register_symbol"]("L", "box width", unit="m")

    mcp.tools["math"]("simplify", "k - pi/L", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert _dimension_check_value(result["step"]) is True
    assert result["verification_status"] != "failed"

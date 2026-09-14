"""Tests for the ``math("dimension", ...)`` operation (Wave B2)."""

from __future__ import annotations

from typing import Any

from symkit_mcp.tools import math as math_tools

# MockMCP is provided by conftest.py


def _math_tool() -> Any:
    mcp = MockMCP()  # noqa: F821
    math_tools.register_math_tools(mcp)
    return mcp.tools["math"]


def test_dimension_catches_rho_plus_v() -> None:
    result = _math_tool()(
        "dimension",
        "rho + v",
        units={"rho": "kg/m^3", "v": "m/s"},
        session=False,
    )
    assert result["success"] is True
    assert result["consistent"] is False
    assert result["dimensionless"] is False
    assert result["issues"]
    assert "rho" in result["dimensions"]


def test_dimension_bernoulli_consistent() -> None:
    result = _math_tool()(
        "dimension",
        "g*z + p/rho + v**2/2",
        units={"g": "m/s^2", "z": "m", "p": "Pa", "rho": "kg/m^3", "v": "m/s"},
        session=False,
    )
    assert result["success"] is True
    assert result["consistent"] is True
    assert result["dimensionless"] is False
    assert result["issues"] == []


def test_dimension_without_units_is_graceful() -> None:
    result = _math_tool()("dimension", "x + 1", session=False)
    assert result["success"] is True
    assert result["consistent"] is None
    assert result["issues"] == []


def test_dimension_dimensionless_expression() -> None:
    result = _math_tool()("dimension", "v/v", units={"v": "m/s"}, session=False)
    assert result["success"] is True
    assert result["consistent"] is True
    assert result["dimensionless"] is True


def test_unknown_operation_still_reported() -> None:
    result = _math_tool()("definitely-not-an-op", "x", session=False)
    assert result["success"] is False
    assert "Unknown operation" in result["error"]


# --- D5: net dimension of the whole expression ------------------------------


def test_dimension_reports_net_result_dimension() -> None:
    result = _math_tool()(
        "dimension", "R*C", units={"R": "ohm", "C": "farad"}, session=False
    )
    assert result["result_dimension"] == {"time": 1}
    assert "time" in result["message"]


def test_dimension_net_dimension_for_product() -> None:
    result = _math_tool()(
        "dimension", "v*t", units={"v": "m/s", "t": "s"}, session=False
    )
    assert result["result_dimension"] == {"length": 1}


def test_dimension_net_dimension_is_null_when_unknown() -> None:
    result = _math_tool()("dimension", "v/t", units={"v": "m/s"}, session=False)
    assert result["consistent"] is None
    assert result["result_dimension"] is None


def test_dimension_net_dimension_is_empty_when_dimensionless() -> None:
    result = _math_tool()("dimension", "v/v", units={"v": "m/s"}, session=False)
    assert result["result_dimension"] == {}
    assert result["dimensionless"] is True
    assert "dimensionless" in result["message"]


# --- D6: derivative handling and accurate inconclusive reason ---------------


def test_derivative_reduces_when_units_are_declared() -> None:
    result = _math_tool()(
        "dimension",
        "m*Derivative(x(t),t)",
        units={"m": "kg", "x": "m", "t": "s"},
        session=False,
    )
    assert result["result_dimension"] == {"mass": 1, "length": 1, "time": -1}
    assert result["consistent"] is True


def test_derivative_with_missing_units_names_the_derivative() -> None:
    result = _math_tool()(
        "dimension",
        "m*Derivative(x(t),(t,2)) + k*x(t)",
        units={"m": "kg", "k": "N/m"},
        session=False,
    )
    assert result["consistent"] is None
    assert "derivative" in result["message"].lower()
    assert "non-integer exponent" not in result["message"].lower()


# --- Pure ratios with mismatched declared units (r15 task-15 / C-03) --------


def test_dimension_flags_wrong_unit_in_pure_ratio() -> None:
    """``L/R`` with ``L`` declared ``henry/second`` is not a valid coherence.

    ``henry/second`` is dimensionally ``ohm``, so the ratio collapses to
    dimensionless — but ``L`` and ``R`` are distinct quantities with different
    declared unit strings. Reporting a green ``consistent:true`` hid the unit
    error; the checker must name the conflicting pair instead.
    """
    result = _math_tool()(
        "dimension",
        "L/R",
        units={"L": "henry/second", "R": "ohm"},
        session=False,
    )
    assert result["success"] is True
    assert result["consistent"] is False
    assert result["issues"]
    assert any("L" in issue and "R" in issue for issue in result["issues"])


def test_dimension_accepts_correct_unit_in_pure_ratio() -> None:
    result = _math_tool()(
        "dimension", "L/R", units={"L": "henry", "R": "ohm"}, session=False
    )
    assert result["consistent"] is True
    assert result["issues"] == []
    assert result["result_dimension"] == {"time": 1}


def test_dimension_ratio_with_unregistered_symbol_is_inconclusive() -> None:
    result = _math_tool()("dimension", "L/R", units={"R": "ohm"}, session=False)
    assert result["consistent"] is None
    assert "L" in result["unknown_symbols"]


# --- Unregistered symbols carry no unit information (task-09 §4-b) ----------


def test_unregistered_symbol_is_unknown_not_fabricated() -> None:
    """A name collision with a domain catalogue must not assign a unit.

    ``k`` is a pharmacokinetics "rate constant" (``1/h``) in the built-in
    registry, but an unregistered ``k`` in an arbitrary session has *no* known
    unit.  Reporting it as dimensioned fabricated a false inconsistency
    (task-09).  This goes through ``dimension_operation`` with a fresh session
    registry (only built-in defaults) to pin the semantics.
    """
    from symkit.domain.symbol_registry import SymbolRegistry
    from symkit_mcp.tools._unit_context import dimension_operation

    class _Session:
        def __init__(self) -> None:
            self.symbol_registry = SymbolRegistry()
            self.formulas: dict = {}

    result = dimension_operation(
        "k", {"L": "m"}, _Session()  # type: ignore[arg-type]
    )

    assert result["consistent"] is None
    assert "k" in result["unknown_symbols"]
    assert "k" not in result["dimensions"]
    assert "k" not in result["units"]

"""G13: inequality-form assumptions must be refused loudly, never dropped.

Field card task-16 (relativity lane): ``assume_for_step(["v", "abs(v) < c"])``
returned ``success: true`` with ``step_assumptions: {}``, a merged view holding
only ``{v: {real: true}}`` and ``conflicts: []`` — the operator believed
``|v| < c`` was declared, but SymPy's assumption system cannot express
inequality constraints and nothing recorded the loss.  The shared clause
validator now refuses such clauses with a message naming the limitation, and
the refusal surfaces as an explicit conflict entry: never success with no trace.
"""

from __future__ import annotations

from symkit.domain.assumption_engine import (
    AssumptionEngine,
    AssumptionLevel,
    validate_assumption_clause,
)
from symkit.domain.math_domain import MathDomain
from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821

_LIMITATION_MARKERS = ("cannot express inequality", "notes/limitations")


def _engine() -> AssumptionEngine:
    return AssumptionEngine(domain=MathDomain.GENERAL)


def _tools() -> dict:
    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    register_assumption_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


# ---- validate_assumption_clause: the shared gate ---------------------------


class TestValidatorRefusesInequalityClauses:
    def test_abs_inequality_is_refused_with_limitation(self) -> None:
        error = validate_assumption_clause("v", ["abs(v)", "<", "c"])
        assert error is not None
        for marker in _LIMITATION_MARKERS:
            assert marker in error, error
        assert "abs(v) < c" in error, error

    def test_relational_operators_are_refused(self) -> None:
        for op in ("<", ">", "<=", ">="):
            error = validate_assumption_clause("x", [f"y {op} 1"])
            assert error is not None, op
            assert "cannot express inequality" in error, error

    def test_function_call_syntax_is_refused(self) -> None:
        error = validate_assumption_clause("v", ["abs(v)"])
        assert error is not None
        assert "cannot express inequality" in error, error

    def test_property_lists_still_pass(self) -> None:
        assert validate_assumption_clause("x", ["positive"]) is None
        assert validate_assumption_clause("x", ["positive", "real"]) is None
        assert validate_assumption_clause("rho_0", ["nonzero", "finite"]) is None


# ---- AssumptionEngine.assume: refusal leaves no state behind ---------------


class TestEngineRefusesInequalityClauses:
    def test_assume_returns_error_and_stores_nothing(self) -> None:
        engine = _engine()
        error = engine.assume("v", "abs(v)", "<", "c")
        assert error is not None
        assert "cannot express inequality" in error, error
        assert engine.get_assumptions_for_symbol("v") == {}

    def test_refusal_at_step_level_also_leaves_no_state(self) -> None:
        engine = _engine()
        error = engine.assume("v", "abs(v)", "<", "c", level=AssumptionLevel.STEP)
        assert error is not None
        assert engine.get_assumptions(AssumptionLevel.STEP) == {}

    def test_refusal_does_not_pollute_session_conflicts(self) -> None:
        engine = _engine()
        engine.assume("v", "abs(v)", "<", "c")
        # The refusal is a caller input error, not a session-level contradiction:
        # it must not make every later verified step read as "contradictory".
        assert engine.detect_conflicts() == []

    def test_valid_property_still_applies_after_a_refusal(self) -> None:
        engine = _engine()
        assert engine.assume("v", "abs(v)", "<", "c") is not None
        assert engine.assume("v", "positive") is None
        assert engine.get_assumptions_for_symbol("v") == {"positive": True}


# ---- assume_for_step: never success-with-empty-step-assumptions ------------


class TestAssumeForStepSurfacesRefusal:
    def test_assume_tool_returns_clean_failure(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("g13-assume")

        result = tools["assume"]({"v": "abs(v) < c"})

        assert result["success"] is False
        assert "cannot express inequality" in result["error"]

    def test_inequality_clause_is_a_clean_failure(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("g13")

        result = tools["assume_for_step"](["v", "abs(v) < c"])

        # A clean failure, never success-with-empty-step-assumptions.
        assert result["success"] is False
        assert "cannot express inequality" in result["error"]
        # Nothing was stored and no session-level conflict was invented.
        conflicts = tools["list_assumptions"]()
        assert "v" not in conflicts.get("assumptions", {})

    def test_valid_property_clause_still_works(self, fresh_session_manager) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("g13-ok")

        result = tools["assume_for_step"](["v", "positive"])

        assert result["success"] is True
        assert result["step_assumptions"]["v"] == {"positive": True}
        assert result["conflicts"] == []

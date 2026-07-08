"""Extended end-to-end derivation examples and edge-case coverage."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit_mcp.tools import (  # noqa: E402
    assumptions as assumptions_tools,
)
from symkit_mcp.tools import (  # noqa: E402
    codegen as codegen_tools,
)
from symkit_mcp.tools import (  # noqa: E402
    formula as formula_tools,
)
from symkit_mcp.tools import (  # noqa: E402
    math as math_tools,
)
from symkit_mcp.tools import (  # noqa: E402
    orchestration as orchestration_tools,
)
from symkit_mcp.tools import (  # noqa: E402
    session as session_tools,
)
from symkit_mcp.tools import (  # noqa: E402
    symbols as symbols_tools,
)

# MockMCP and fresh_session_manager are provided by conftest.py


def _register_all_tools(mcp: Any) -> None:
    """Register all tools needed for extended end-to-end tests."""
# ruff: noqa: F821  # MockMCP from conftest.py
    assumptions_tools.register_assumption_tools(mcp)
    formula_tools.register_formula_tools(mcp)
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    orchestration_tools.register_orchestration_tools(mcp)
    symbols_tools.register_symbol_tools(mcp)
    codegen_tools.register_codegen_tools(mcp)


class TestKinematicEquation:
    """Example: derive v = u + a*t from a = (v - u)/t."""

    def test_kinematic_equation(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("kinematics", domain="classical_mechanics")
        mcp.tools["session_load_formula"](
            "a = (v - u)/t",
            formula_id="acceleration",
        )
        result = mcp.tools["math"](
            "solve",
            expression="a - (v - u)/t",
            variable="v",
            session=True,
        )
        assert result["success"], result.get("error")
        assert "u" in result["expression"] and "a" in result["expression"]


class TestCircleArea:
    """Example: derive circle area via integration."""

    def test_circle_area_integral(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("circle_area")
        mcp.tools["math"]("integrate", expression="2*pi*r", variable="r", session=True)
        result = mcp.tools["math"]("simplify", expression="pi*r**2", session=True)
        assert result["success"]
        assert "pi" in result["expression"]


class TestLimitAndSeries:
    """Example: limit and series operations."""

    def test_limit_sin_x_over_x(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["math"](
            "limit",
            expression="sin(x)/x",
            variable="x",
            point="0",
        )
        assert result["success"]
        assert result["expression"] == "1"

    def test_series_exp_x(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["math"](
            "series",
            expression="exp(x)",
            variable="x",
            point="0",
            order=4,
        )
        assert result["success"]
        assert "x" in result["expression"]


class TestMatrixOperations:
    """Example: matrix determinant and eigenvalues."""

    def test_matrix_determinant(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["math"](
            "det",
            expression="[[a, b], [c, d]]",
        )
        assert result["success"]
        assert result["expression"] == "a*d - b*c"

    def test_matrix_eigenvalues(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["math"](
            "eigenvals",
            expression="[[2, 1], [1, 2]]",
        )
        assert result["success"]
        assert len(result["eigenvalues"]) == 2


class TestVectorCalculus:
    """Example: gradient of a scalar potential."""

    def test_gradient_of_potential(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["math"](
            "gradient",
            expression="x**2 + y**2 + z**2",
            variable="x,y,z",
        )
        assert result["success"]
        assert "2*N.x" in result["expression"]
        assert "2*N.y" in result["expression"]
        assert "2*N.z" in result["expression"]


class TestSessionRollback:
    """Example: rollback to a previous step and continue."""

    def test_rollback_and_continue(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("rollback")
        mcp.tools["session_load_formula"]("x**2 + 2*x + 1", formula_id="poly")
        mcp.tools["math"]("diff", expression="x**2 + 2*x + 1", variable="x", session=True)
        mcp.tools["math"]("expand", expression="2*x + 2", session=True)

        steps_before = mcp.tools["session_get_steps"]()
        mcp.tools["session_rollback"](to_step=1)
        result = mcp.tools["math"]("factor", expression="x**2 + 2*x + 1", session=True)
        assert result["success"]
        assert mcp.tools["session_get_steps"]()["count"] >= steps_before["count"] - 1


class TestSessionResume:
    """Example: save and resume a session."""

    def test_resume_saved_session(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["session_start"]("persist_test")
        session_id = result["session_id"]
        mcp.tools["session_load_formula"]("x**2", formula_id="poly")
        # Simulate leaving and coming back: save current session and clear global state
        from symkit_mcp.tools import _state
        _state._current_session = None

        resume = mcp.tools["session_resume"](session_id)
        assert resume["success"]
        result = mcp.tools["math"]("diff", expression="x**2", variable="x", session=True)
        assert result["success"]


class TestGoalProgressWithTarget:
    """Example: reaching a target expression updates progress."""

    def test_reaching_target_expression(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("target_test")
        mcp.tools["session_set_goal"](
            "derive (x + 1)**2",
        )
        mcp.tools["session_load_formula"]("x**2 + 2*x + 1", formula_id="poly")
        progress = mcp.tools["session_show"]()
        assert progress["success"]
        assert progress["progress"]["matches_target"] is True


class TestAssumptionConflicts:
    """Example: contradictory assumptions are detected."""

    def test_conflict_detection(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("conflict")
        mcp.tools["assume_for_step"]("x", "positive")
        mcp.tools["assume_for_step"]("x", "negative")
        summary = mcp.tools["check_assumption_conflicts"]()
        assert summary["success"]
        assert summary["has_conflicts"]
        assert any("both" in a.lower() for a in summary["warnings"])


class TestSymbolConflicts:
    """Example: ambiguous symbol usage is detected."""

    def test_symbol_conflict_detection(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("symbols", domain="fluid_dynamics")
        mcp.tools["register_symbol"]("u", "velocity", domain="fluid_dynamics")
        mcp.tools["register_symbol"]("u", "displacement", domain="solid_mechanics")
        mcp.tools["session_load_formula"]("u")
        result = mcp.tools["check_symbol_conflicts"]()
        assert result["success"]
        assert result["has_conflicts"]
        assert any("u" in w for w in result["warnings"])


class TestCodeGeneration:
    """Example: generate Python and LaTeX output."""

    def test_generate_python_function(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["generate_python_function"](
            name="tension",
            description="Calculate tension",
            parameters=[
                {"name": "M1", "type": "float", "description": "Mass 1"},
                {"name": "M2", "type": "float", "description": "Mass 2"},
            ],
            steps=[
                {
                    "description": "Total mass",
                    "expression": "M1 + M2",
                    "result_var": "M_total",
                },
            ],
            return_vars=["M_total"],
        )
        assert result["success"]
        assert "def tension" in result["code"]

    def test_generate_latex_derivation(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["generate_latex_derivation"](
            title="Kinematics",
            steps=[
                {"description": "Define velocity", "latex": "v = \\frac{dx}{dt}"},
            ],
            final_result="x(t) = x_0 + v t",
        )
        assert result["success"]
        assert "\\section" in result["latex"]


class TestSolveVerification:
    """Example: solve and verify the resulting equation in a session."""

    def test_solve_equation_in_session(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("solve_verify")
        mcp.tools["session_load_formula"]("a*x**2 + b*x + c = 0", formula_id="quadratic")
        result = mcp.tools["math"](
            "solve",
            expression="a*x**2 + b*x + c",
            variable="x",
            session=True,
        )
        assert result["success"]

        steps = mcp.tools["session_get_steps"]()
        assert steps["count"] >= 2

        verify = mcp.tools["session_verify_step"](2)
        assert verify["success"]
        assert verify["verification_status"] == "verified"


class TestManualRecordStep:
    """Example: record an externally-computed step and verify it."""

    def test_record_custom_step(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("manual")
        mcp.tools["session_load_formula"]("x**2", formula_id="poly")
        result = mcp.tools["session_record_step"](
            expression="2*x",
            description="hand-calculated derivative",
            operation="differentiate",
        )
        assert result["success"], result.get("error")
        assert result["step_number"] == 2

        steps = mcp.tools["session_get_steps"]()
        assert steps["count"] == 2


class TestRecordStepRobustParsing:
    """Regression tests: session_record_step must accept natural math notation."""

    def test_record_beta_omega_equation(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("k-omega")
        mcp.tools["session_set_goal"]("k-omega model")
        result = mcp.tools["session_record_step"](
            expression=(
                "Derivative(w, t) + u_j*Derivative(w, x_j) - alpha*P_k*w/k + "
                "beta*w**2 - Derivative((nu + sigma_w*nu_t)*Derivative(w, x_j), x_j)"
            ),
            description="closed omega equation",
            operation="custom",
        )
        assert result["success"], result.get("error")
        assert "beta" in result["latex"]

    def test_record_s_in_closure(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("k-omega")
        mcp.tools["session_set_goal"]("k-omega model")
        result = mcp.tools["session_record_step"](
            expression="nut * S**2",
            description="Pk closure",
            operation="closure_assumption",
        )
        assert result["success"], result.get("error")
        assert "S" in result["latex"]

    def test_record_leibniz_and_equations(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("rans")
        mcp.tools["session_set_goal"]("k-omega model")

        for expr, desc in [
            ("dk/dt = Pk - epsilon + Dk", "exact k equation"),
            (
                "tau_ij = nut * (dUi/dxj + dUj/dxi) - (2/3)*k*delta_ij",
                "Boussinesq closure",
            ),
            ("epsilon = betastar * k * w", "epsilon definition"),
        ]:
            result = mcp.tools["session_record_step"](
                expression=expr,
                description=desc,
                operation="derivation",
            )
            assert result["success"], f"{desc}: {result.get('error')}"
            assert result["step_number"] > 0

        steps = mcp.tools["session_get_steps"]()
        assert steps["count"] == 3


class TestManualRecordStepVerification:
    """Manual steps must not be falsely reported as automatically verified."""

    def test_record_step_forces_custom_operation(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("verification")
        result = mcp.tools["session_record_step"](
            expression="x**2",
            description="hand simplification",
            operation="simplify",
        )
        assert result["success"]
        assert result["step"]["operation"] == "custom"
        assert result["step"]["sympy_command"] == "manual_record"

    def test_record_step_does_not_spoof_verification(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("verification")
        result = mcp.tools["session_record_step"](
            expression="x + 1",
            description="claimed simplify",
            operation="simplify",
        )
        assert result["success"]
        assert result["verification_status"] != "success"

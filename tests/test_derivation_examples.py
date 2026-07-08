"""End-to-end derivation examples to verify the unified SymKit framework."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.derivation_session import SessionManager  # noqa: E402, F401
from symkit_mcp.tools import (  # noqa: E402
    assumptions as assumptions_tools,
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

# MockMCP is provided by conftest.py


def _register_all_tools(mcp: Any) -> None:
    """Register all tools needed for end-to-end derivation tests."""
# ruff: noqa: F821  # MockMCP from conftest.py
    assumptions_tools.register_assumption_tools(mcp)
    formula_tools.register_formula_tools(mcp)
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    orchestration_tools.register_orchestration_tools(mcp)


class TestKineticEnergyFromWork:
    """Example 1: Derive the work-energy theorem / kinetic energy."""

    def test_work_energy_derivation(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("work_energy")
        mcp.tools["session_load_formula"]("W = F * x", formula_id="work")
        mcp.tools["session_load_formula"]("F = m * a", formula_id="newton")

        # Substitute F = m*a into W
        result = mcp.tools["math"](
            "substitute", "W = F*x", substitution={"F": "m*a"}, session=True
        )
        assert result["success"], result.get("error")

        # The expression should now be W = m*a*x (SymPy prints it as a*m*x)
        current = str(mcp.tools["session_status"]()["current_expression"])
        assert ("a*m*x" in current) or ("m*a*x" in current)

        # Verify the substitution step does not crash on an equation
        result = mcp.tools["session_verify_step"]()
        assert result["success"]


class TestFirstOrderElimination:
    """Example 2: Derive C(t) = C0*exp(-k*t) from dC/dt = -k*C."""

    def test_first_order_elimination_ode(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("first_order_elimination", domain="pharmacokinetics")
        mcp.tools["session_set_goal"]("solve for C(t) in first-order elimination")
        mcp.tools["session_load_formula"](
            "Eq(diff(C(t), t), -k*C(t))", formula_id="rate_eq"
        )

        # Add assumptions for cleaner verification
        mcp.tools["assume_for_step"]("k", "positive")
        mcp.tools["assume_for_step"]("t", "positive")

        # Solve ODE: diff(C(t), t) + k*C(t) = 0, dependent variable C, independent t
        result = mcp.tools["math"](
            "dsolve",
            "diff(C(t), t) + k*C(t)",
            variable="C",
            with_respect_to="t",
            session=True,
        )
        assert result["success"], result.get("error")

        # Verify step
        result = mcp.tools["session_verify_step"]()
        assert result["success"]

        # Check progress toward target
        progress = mcp.tools["session_show"]()["progress"]
        assert progress["has_goal"] is True


class TestHighLevelDerive:
    """Example 3: Use high-level derive() with external sources."""

    def test_derive_with_scipy_external_source(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["derive"](
            "derive Planck energy using speed of light c and Planck constant h",
            given=["c", "h"],
            domain="classical_mechanics",
            external_sources=["scipy"],
        )
        assert result["success"], result.get("error")
        assert result["recommended_formulas"]
        sources = {r["source"] for r in result["recommended_formulas"]}
        # SciPy constants should be in the recommended sources
        assert any("scipy" in s for s in sources)

    def test_navier_stokes_pattern_selection(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["derive"](
            "derive incompressible Navier-Stokes equations from conservation laws",
            domain="fluid_dynamics",
            external_sources=["scipy"],
        )
        assert result["success"], result.get("error")
        assert result["pattern"] == "conservation+constitutive"
        assert result["goal"]["domain"] == "fluid_dynamics"
        assert result["recommended_formulas"] is not None


class TestExternalFormulaLoading:
    """Example 4: Load an external SciPy constant into the session."""

    def test_load_external_scipy_constant(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("physical_constants")
        mcp.tools["session_set_goal"]("speed of light")
        # Search for external formula and load one of the recommended ones
        result = mcp.tools["session_suggest_formulas"](top_k=5)
        assert result["success"], result.get("error")
        recommendations = result["recommendations"]
        assert recommendations
        scipy_formulas = [
            f for f in recommendations if "scipy" in f["source"]
        ]
        assert scipy_formulas, "No SciPy constants recommended"

        chosen = scipy_formulas[0]
        result = mcp.tools["session_load_formula"](
            chosen["expression"], formula_id=chosen["formula_id"], source="scipy"
        )
        assert result["success"], result.get("error")

        status = mcp.tools["session_status"]()
        loaded_ids = set(status["formulas_loaded"])
        assert chosen["formula_id"] in loaded_ids


class TestMathOperations:
    """Example 5: Exercise math() with diff, integrate, solve, substitute, expand."""

    def test_diff_and_integrate(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("math_ops")

        result = mcp.tools["math"]("diff", "x**3 + 2*x", variable="x", session=False)
        assert result["success"], result.get("error")
        assert "3*x**2" in result["expression"]
        assert "2" in result["expression"]

        result = mcp.tools["math"]("integrate", "3*x**2 + 2", variable="x", session=False)
        assert result["success"], result.get("error")
        assert "x**3" in result["expression"]
        assert "2*x" in result["expression"]

    def test_solve_quadratic(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("quadratic")
        result = mcp.tools["math"](
            "solve", "a*x**2 + b*x + c = 0", variable="x", session=False
        )
        assert result["success"], result.get("error")
        assert len(result["all_solutions"]) == 2
        assert any("sqrt" in s for s in result["all_solutions"])

    def test_substitute_and_expand(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("substitution")
        result = mcp.tools["math"](
            "substitute",
            "x**2 + y",
            substitution={"x": "a + b", "y": "c"},
            session=False,
        )
        assert result["success"], result.get("error")
        assert "a + b" in result["expression"]
        assert "c" in result["expression"]

        expanded = mcp.tools["math"]("expand", result["expression"], session=False)
        assert expanded["success"], expanded.get("error")
        assert "a**2" in expanded["expression"]
        assert "2*a*b" in expanded["expression"]
        assert "b**2" in expanded["expression"]

    def test_simplify_trigonometric(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("simplify")
        result = mcp.tools["math"](
            "simplify", "sin(x)**2 + cos(x)**2", variable="x", session=False
        )
        assert result["success"], result.get("error")
        assert result["expression"] == "1"


class TestDerivationOperations:
    """Example 6: Exercise derivation-level differentiate, integrate, solve, simplify."""

    def test_solve_for_in_session(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("solve_for_example")
        mcp.tools["session_load_formula"]("F = m*a", formula_id="newton")
        result = mcp.tools["math"]("solve", "F = m*a", variable="a", session=True)
        assert result["success"], result.get("error")
        current = str(mcp.tools["session_status"]()["current_expression"])
        assert "a" in current
        assert "F" in current
        assert "m" in current

    def test_differentiate_and_integrate_in_session(
        self, fresh_session_manager: SessionManager
    ) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("calculus")
        mcp.tools["session_load_formula"]("x**3 + 2*x", formula_id="poly")

        result = mcp.tools["math"]("diff", "x**3 + 2*x", variable="x", session=True)
        assert result["success"], result.get("error")
        assert "3*x**2" in result["expression"]

        current = str(mcp.tools["session_status"]()["current_expression"])
        result = mcp.tools["math"]("integrate", current, variable="x", session=True)
        assert result["success"], result.get("error")
        assert "x**3" in result["expression"]

    def test_simplify_and_add_note(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("simplify_note")
        mcp.tools["session_load_formula"](
            "sin(x)**2 + cos(x)**2 + x", formula_id="trig_plus_x"
        )
        result = mcp.tools["math"]("simplify", "sin(x)**2 + cos(x)**2 + x", session=True)
        assert result["success"], result.get("error")
        assert "x" in result["expression"]

        result = mcp.tools["session_add_note"](
            "sin²+cos² simplifies to 1", note_type="observation"
        )
        assert result["success"], result.get("error")

        result = mcp.tools["session_verify_session"]()
        assert result["success"]


class TestAssumptions:
    """Example 7: Assumption tools should affect math results."""

    def test_assume_for_step(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("assumptions")
        result = mcp.tools["assume_for_step"]("x", "positive")
        assert result["success"], result.get("error")
        assert result["step_assumptions"]["x"]["positive"] is True

        result = mcp.tools["assume_for_step"]("y", "real")
        assert result["success"], result.get("error")
        merged = result["merged_assumptions"]
        assert merged["x"]["positive"] is True
        assert merged["y"]["real"] is True

    def test_global_assume_affects_math(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["assume"]({"x": "positive"})
        result = mcp.tools["math"](
            "simplify", "sqrt(x**2)", variable="x", session=False
        )
        assert result["success"], result.get("error")
        assert result["expression"] == "x"

    def test_global_assume(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["assume"]({"t": "positive real"})
        assert result["success"], result.get("error")
        assert result["assumptions"]["t"]["positive"] is True
        assert result["assumptions"]["t"]["real"] is True


class TestSessionPersistence:
    """Example 8: Derivation session can be listed and resumed."""

    def test_list_and_resume_session(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("persist_test")
        mcp.tools["session_load_formula"]("E = m*c**2", formula_id="energy")
        first_id = mcp.tools["session_status"]()["session_id"]

        listed = mcp.tools["session_list"]()
        assert listed["success"]
        assert any(s["session_id"] == first_id for s in listed["sessions"])

        resumed = mcp.tools["session_resume"](first_id)
        assert resumed["success"], resumed.get("error")
        assert resumed["session_id"] == first_id


class TestFormulaTools:
    """Example 9: formula_* tools search SciPy constants without network."""

    def test_formula_constants(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        # formula_constants was replaced by formula_search with source="scipy".
        result = mcp.tools["formula_search"](
            "speed of light", source="scipy", limit=5
        )
        assert result["success"], result.get("error")
        assert result["total"] > 0
        names = {r["name"] for r in result["results"]}
        assert any("Speed of Light" in n for n in names)

    def test_formula_search_scipy(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        result = mcp.tools["formula_search"](
            "Planck constant", source="scipy", limit=5
        )
        assert result["success"], result.get("error")
        assert result["total"] > 0
        assert any("Planck" in r["name"] for r in result["results"])


class TestMathSessionRecording:
    """Example 10: math(session=True) records steps into the active derivation."""

    def test_math_records_step_in_session(
        self, fresh_session_manager: SessionManager
    ) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("math_session")
        mcp.tools["session_load_formula"]("x**3", formula_id="cubic")

        result = mcp.tools["math"](
            "diff", "x**3", variable="x", session=True
        )
        assert result["success"], result.get("error")
        assert result["step"] == 2
        assert "3*x**2" in result["expression"]

        status = mcp.tools["session_status"]()
        assert status["step_count"] == 2
        assert "3*x**2" in str(status["current_expression"])


class TestDerivationShow:
    """Example 11: session_show renders current expression without crashing."""

    def test_session_show(self, fresh_session_manager: SessionManager) -> None:
        _ = fresh_session_manager
        mcp = MockMCP()
        _register_all_tools(mcp)

        mcp.tools["session_start"]("show_test")
        mcp.tools["session_load_formula"]("y = sin(x)**2 + cos(x)**2", formula_id="trig")
        mcp.tools["math"]("simplify", "y = sin(x)**2 + cos(x)**2", session=True)

        result = mcp.tools["session_show"](show_steps=True)
        assert result["success"], result.get("error")
        assert result["session_name"] == "show_test"
        assert result["step_count"] == 2
        assert result["display_text"]

        steps = mcp.tools["session_get_steps"]()
        assert steps["success"]
        assert len(steps["steps"]) == 2

"""Tests for Phase 2 domain logic: DerivationPattern, SymbolRegistry, AssumptionEngine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src is on path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.assumption_engine import AssumptionEngine, AssumptionLevel  # noqa: E402
from symkit.domain.derivation_pattern import (  # noqa: E402
    DerivationPattern,
    get_pattern_template,
    list_patterns,
)
from symkit.domain.math_domain import MathDomain  # noqa: E402
from symkit.domain.symbol_registry import SymbolRegistry, SymbolScope  # noqa: E402


class TestDerivationPattern:
    """Tests for derivation pattern abstraction."""

    def test_from_string_recognizes_known_patterns(self):
        assert DerivationPattern.from_string("conservation+constitutive") == DerivationPattern.CONSERVATION_CONSTITUTIVE
        assert DerivationPattern.from_string("operator-correspondence") == DerivationPattern.OPERATOR_CORRESPONDENCE

    def test_from_string_defaults_to_direct_manipulation(self):
        assert DerivationPattern.from_string("unknown") == DerivationPattern.DIRECT_MANIPULATION

    def test_get_pattern_template_returns_template(self):
        template = get_pattern_template("variational")
        assert template.pattern == DerivationPattern.VARIATIONAL
        assert template.typical_steps
        assert template.suggested_operations

    def test_list_patterns_includes_all_patterns(self):
        result = list_patterns()
        pattern_names = {p["name"] for p in result["patterns"]}
        assert "conservation+constitutive" in pattern_names
        assert "operator-correspondence" in pattern_names
        assert "direct-manipulation" in pattern_names


class TestSymbolRegistry:
    """Tests for SymbolRegistry domain logic."""

    def test_domain_defaults_loaded(self):
        registry = SymbolRegistry()
        rho = registry.lookup("rho", MathDomain.FLUID_DYNAMICS)
        assert rho is not None
        assert rho.meaning == "Fluid density"
        assert rho.default_unit == "kg/m^3"

    def test_lookup_falls_back_to_general(self):
        registry = SymbolRegistry()
        # rho is registered in fluid_dynamics; lookup without domain should still find it
        rho = registry.lookup("rho")
        assert rho is not None

    def test_register_custom_symbol(self):
        registry = SymbolRegistry()
        registry.register(
            name="X",
            meaning="My custom variable",
            domain=MathDomain.GENERAL,
            scope=SymbolScope.USER,
            default_unit="m",
        )
        sem = registry.lookup("X")
        assert sem is not None
        assert sem.meaning == "My custom variable"
        assert sem.default_unit == "m"

    def test_detect_conflicts(self):
        registry = SymbolRegistry()
        registry.register("R", "Universal gas constant", MathDomain.THERMODYNAMICS)
        registry.register("R", "Electrical resistance", MathDomain.ELECTROMAGNETISM)
        conflicts = registry.detect_conflicts(["R"])
        assert len(conflicts) == 1
        assert conflicts[0]["symbol"] == "R"
        assert len(conflicts[0]["meanings"]) == 2

    def test_register_formula_symbols(self):
        registry = SymbolRegistry()
        registry.register_formula_symbols(
            formula_id="ns_momentum",
            symbol_names=["rho", "u", "p"],
            domain=MathDomain.FLUID_DYNAMICS,
        )
        rho = registry.lookup("rho", MathDomain.FLUID_DYNAMICS)
        assert rho.scope == SymbolScope.FORMULA
        assert rho.source_id == "ns_momentum"

    def test_suggest_assumptions(self):
        registry = SymbolRegistry()
        suggestions = registry.suggest_assumptions(["rho", "mu"], MathDomain.FLUID_DYNAMICS)
        assert "rho" in suggestions
        assert "positive" in suggestions["rho"]


class TestAssumptionEngine:
    """Tests for AssumptionEngine multi-level assumptions."""

    def test_domain_defaults_loaded(self):
        engine = AssumptionEngine(domain=MathDomain.FLUID_DYNAMICS)
        assumptions = engine.get_assumptions(level=AssumptionLevel.DOMAIN)
        assert "rho" in assumptions
        assert assumptions["rho"]["positive"] is True

    def test_session_overrides_domain(self):
        engine = AssumptionEngine(domain=MathDomain.FLUID_DYNAMICS)
        engine.assume("rho", "negative", level=AssumptionLevel.SESSION)
        merged = engine.get_assumptions()
        assert merged["rho"]["negative"] is True

    def test_step_overrides_session(self):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("x", "positive", level=AssumptionLevel.SESSION)
        engine.assume("x", "negative", level=AssumptionLevel.STEP)
        merged = engine.get_assumptions()
        assert merged["x"]["negative"] is True
        assert merged["x"]["positive"] is True

    def test_detect_conflicts(self):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("x", "positive", level=AssumptionLevel.SESSION)
        engine.assume("x", "negative", level=AssumptionLevel.STEP)
        conflicts = engine.detect_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["symbol"] == "x"
        assert conflicts[0]["conflict"] == ("positive", "negative")

    def test_unassume(self):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("x", "positive", level=AssumptionLevel.SESSION)
        engine.unassume("x", "positive", level=AssumptionLevel.SESSION)
        assert "x" not in engine.get_assumptions(level=AssumptionLevel.SESSION)

    def test_clear_level(self):
        engine = AssumptionEngine(domain=MathDomain.GENERAL)
        engine.assume("x", "positive", level=AssumptionLevel.STEP)
        engine.clear_level(AssumptionLevel.STEP)
        assert engine.get_assumptions(level=AssumptionLevel.STEP) == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

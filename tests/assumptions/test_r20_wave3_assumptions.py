"""r20 wave-3 assumption-clause validation.

An unfulfillable assumption used to be accepted silently:

* ``assume({"V - n*b": "positive"})`` echoed ``assumptions_applied`` but the
  key is an *expression*, not a symbol, so nothing was ever applied —
  ``simplify(sqrt((V - n*b)**2))`` stayed unsimplified with no warning;
* ``assume({"theta": "less than pi"})`` split the value on whitespace into
  three pseudo-properties (``less``, ``than``, ``pi``), none of which SymPy
  understands, and stored them.

Red line: an assumption that cannot be honored is either implemented or
explicitly refused — never silently stored.

Engine-level tests only: the MCP wiring that turns the rejection into
``{"success": False, "error": ...}`` lives in ``math.py``/``tools`` and is
owned by another wave.
"""

from __future__ import annotations

from symkit.domain.assumption_binding import ASSUMPTION_KEYWORDS
from symkit.domain.assumption_engine import (
    AssumptionEngine,
    AssumptionLevel,
    validate_assumption_clause,
)
from symkit.domain.math_domain import MathDomain


def _engine() -> AssumptionEngine:
    return AssumptionEngine(domain=MathDomain.GENERAL)


# --------------------------------------------------------------------------
# validate_assumption_clause — the shared contract.
# --------------------------------------------------------------------------


def test_validator_accepts_plain_symbol_and_known_properties() -> None:
    assert validate_assumption_clause("x", ["positive"]) is None
    assert validate_assumption_clause("S", ["nonzero", "real"]) is None
    assert validate_assumption_clause("rho_0", ["positive", "finite"]) is None


def test_validator_rejects_expression_key() -> None:
    error = validate_assumption_clause("V - n*b", ["positive"])
    assert error is not None
    assert "plain symbols" in error, error
    assert "V - n*b" in error, error


def test_validator_rejects_key_that_is_not_an_identifier() -> None:
    for key in ("", "a b", "x*y", "f(2)", "3n"):
        assert validate_assumption_clause(key, ["positive"]) is not None, key


def test_validator_rejects_python_keyword_key() -> None:
    error = validate_assumption_clause("lambda", ["positive"])
    assert error is not None and "lambda" in error, error


def test_validator_rejects_unknown_properties_and_lists_them() -> None:
    error = validate_assumption_clause("theta", ["less", "than", "pi"])
    assert error is not None
    assert "theta" in error, error
    assert "less, than, pi" in error, error
    assert "supported:" in error, error


def test_validator_reports_only_the_unknown_properties() -> None:
    error = validate_assumption_clause("x", ["positive", "shiny"])
    assert error is not None
    named = error.split(";")[0]
    assert "shiny" in named, error
    assert "positive" not in named, error


def test_validator_supported_vocabulary_matches_binding_whitelist() -> None:
    """Every whitelisted property must pass; a non-member must not."""
    for prop in ASSUMPTION_KEYWORDS:
        assert validate_assumption_clause("x", [prop]) is None, prop
    assert validate_assumption_clause("x", ["definitely_not_a_property"]) is not None


# --------------------------------------------------------------------------
# AssumptionEngine.assume — refusal must leave no state behind.
# --------------------------------------------------------------------------


def test_assume_rejects_expression_key_without_storing_anything() -> None:
    engine = _engine()
    error = engine.assume("V - n*b", "positive")
    assert error is not None and "not a symbol" in error, error
    assert engine.get_assumptions() == {}
    assert engine.get_assumptions_for_symbol("V - n*b") == {}


def test_assume_rejects_unknown_properties_without_storing_anything() -> None:
    engine = _engine()
    error = engine.assume("theta", "less", "than", "pi")
    assert error is not None and "unknown assumption properties" in error, error
    assert engine.get_assumptions() == {}


def test_assume_partially_unknown_clause_stores_nothing() -> None:
    """All-or-nothing: a single bad token must not leave the good one behind."""
    engine = _engine()
    error = engine.assume("x", "positive", "shiny")
    assert error is not None, error
    assert engine.get_assumptions_for_symbol("x") == {}


def test_assume_accepts_valid_clause_and_returns_none() -> None:
    engine = _engine()
    assert engine.assume("x", "positive") is None
    assert engine.get_assumptions_for_symbol("x") == {"positive": True}


def test_assume_rejection_does_not_disturb_earlier_assumptions() -> None:
    engine = _engine()
    assert engine.assume("x", "positive") is None
    assert engine.assume("V - n*b", "positive") is not None
    assert engine.get_assumptions_for_symbol("x") == {"positive": True}
    assert engine.get_assumptions() == {"x": {"positive": True}}


def test_assume_at_step_level_also_validates() -> None:
    engine = _engine()
    error = engine.assume("theta", "less", level=AssumptionLevel.STEP)
    assert error is not None, error
    assert engine.get_assumptions(AssumptionLevel.STEP) == {}


def test_domain_hints_still_load_through_the_validated_entry() -> None:
    """``__init__`` seeds domain defaults via ``assume``; those must survive."""
    engine = AssumptionEngine(domain=MathDomain.FLUID_DYNAMICS)
    assert engine.get_assumptions_for_symbol("rho") == {"positive": True}
    assert engine.get_assumptions_for_symbol("p") == {"real": True}
    assert engine.detect_conflicts() == []

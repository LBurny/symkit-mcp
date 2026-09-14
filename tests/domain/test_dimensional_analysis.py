"""Tests for expression-level dimensional consistency checking."""

import sympy as sp

from symkit.domain.dimensional_analysis import DimensionReport, check_expression_dimensions

UNITS = {"rho": "kg/m^3", "v": "m/s", "p": "Pa", "z": "m", "g": "m/s^2"}


def test_dimensionally_inconsistent_addition_is_caught():
    rho, v = sp.symbols("rho v")
    report = check_expression_dimensions(rho + v, UNITS)
    assert report.consistent is False
    assert any("rho" in issue or "kg" in issue for issue in report.issues)


def test_bernoulli_terms_are_consistent():
    g, z, p, rho, v = sp.symbols("g z p rho v")
    expr = g * z + p / rho + v**2 / 2
    report = check_expression_dimensions(expr, UNITS)
    assert report.consistent is True
    assert report.issues == []


def test_no_unit_info_yields_none():
    x = sp.symbols("x")
    report = check_expression_dimensions(x + 1, {})
    assert report.consistent is None


def test_unknown_symbols_are_reported_not_fatal():
    rho, mystery = sp.symbols("rho mystery")
    report = check_expression_dimensions(rho + mystery, UNITS)
    assert report.consistent is None or report.unknown_symbols
    assert "mystery" in report.unknown_symbols


def test_dimensions_field_records_known_symbols():
    rho, v = sp.symbols("rho v")
    report = check_expression_dimensions(rho * v, UNITS)
    assert report.dimensions["rho"] == {"mass": 1, "length": -3}
    assert report.dimensions["v"] == {"length": 1, "time": -1}


def test_unparseable_unit_is_treated_as_unknown():
    x = sp.symbols("x")
    report = check_expression_dimensions(x + 1, {"x": "not-a-unit!!"})
    assert report.consistent is None
    assert "x" in report.unknown_symbols


def test_transcendental_function_with_dimensioned_argument_flagged():
    v = sp.symbols("v")
    report = check_expression_dimensions(sp.sin(v), UNITS)
    assert report.consistent is False
    assert report.issues


def test_transcendental_function_with_dimensionless_argument_ok():
    x = sp.symbols("x")
    report = check_expression_dimensions(sp.exp(x), {"x": "1"})
    assert report.consistent is True


def test_power_with_unknown_exponent_is_indeterminate():
    x = sp.symbols("x")
    report = check_expression_dimensions(x ** sp.Symbol("n"), {"x": "m"})
    # An unknown exponent cannot be proven dimensionally consistent.
    assert report.consistent is None


def test_equation_sides_must_match():
    rho, v = sp.symbols("rho v")
    report = check_expression_dimensions(sp.Eq(rho, v), UNITS)
    assert report.consistent is False


def test_numeric_expression_with_units_present_is_consistent():
    report = check_expression_dimensions(sp.Integer(2), UNITS)
    assert report.consistent is True


def test_report_has_expected_fields():
    report = DimensionReport(consistent=None)
    assert report.issues == []
    assert report.unknown_symbols == []
    assert report.dimensions == {}
    assert report.indeterminate_reasons == []


def test_expression_dimension_public_wrapper():
    from symkit.domain.dimensional_analysis import expression_dimension

    rho, v = sp.symbols("rho v")
    units = {"rho": "kg/m^3", "v": "m/s"}
    assert expression_dimension(v / v, units) == {}
    assert expression_dimension(rho, units) == {"mass": 1, "length": -3}
    # Inconsistent sums still yield the dominant vector; mismatch reporting
    # is check_expression_dimensions' job (issues), not this wrapper's.
    assert expression_dimension(rho + v, units) == {"mass": 1, "length": -3}
    assert expression_dimension(rho, {}) is None  # no unit info


# --- Sandbox round 13 regression guards -------------------------------------


def test_fractional_power_of_dimensionless_base_is_dimensionless():
    """Re**0.8 / Pr**(1/3): a dimensionless base stays dimensionless.

    Engineering correlations are written with float exponents; bailing to
    ``indeterminate`` made every such relation unverifiable and let a real
    error (``Nu == 0.027*Re**0.8*Pr**(1/3)*D``) slip through undetected.
    """
    nu, re_, pr = sp.symbols("Nu Re Pr")
    report = check_expression_dimensions(nu - 0.023 * re_**0.8 * pr**0.4, {"Nu": "1", "Re": "1", "Pr": "1"})
    assert report.consistent is True, report.issues


def test_fractional_power_catches_length_leak():
    """A dimensioned factor left inside a fractional-power correlation is caught."""
    nu, re_, pr, d = sp.symbols("Nu Re Pr D")
    units = {"Nu": "1", "Re": "1", "Pr": "1", "D": "m"}
    report = check_expression_dimensions(nu - 0.027 * re_**0.8 * pr ** sp.Rational(1, 3) * d, units)
    assert report.consistent is False, (report.consistent, report.issues)


def test_dash_unit_means_dimensionless():
    """``"-"`` is the write-path's documented marker for a dimensionless quantity."""
    nu, re_, pr = sp.symbols("Nu Re Pr")
    report = check_expression_dimensions(nu - 0.023 * re_**0.8 * pr**0.4, {"Nu": "-", "Re": "-", "Pr": "-"})
    assert report.consistent is True, report.issues
    assert report.unknown_symbols == []


def test_dimensionless_word_also_accepted():
    a, b = sp.symbols("a b")
    report = check_expression_dimensions(a / b, {"a": "dimensionless", "b": "dimensionless"})
    assert report.consistent is True, report.issues
    assert report.unknown_symbols == []


def test_indeterminate_message_does_not_claim_unknown_symbols():
    """consistent=None with no unknown symbols must not blame unknown units."""
    x = sp.symbols("x")
    report = check_expression_dimensions(x ** sp.Symbol("n"), {"x": "m"})
    if report.consistent is None and not report.unknown_symbols:
        assert "unknown units" not in " ".join(report.issues) or report.issues == []


def test_user_registered_unit_wins_over_builtin_domain_default():
    """Built-in domain units must not shadow ``register_symbol(unit=...)``.

    The registry ships defaults for common names (``k`` → rate constant 1/h,
    ``V`` → volume of distribution L, ``rho``, ``p``, ``T``, ``nu``). First-wins
    merging silently discarded the user's unit, so the checker analysed a
    different physical quantity than the one the user declared.
    """
    from symkit.domain.symbol_registry import SymbolRegistry
    from symkit_mcp.tools._unit_context import collect_unit_map

    class _Session:
        def __init__(self) -> None:
            self.symbol_registry = SymbolRegistry()
            self.formulas: dict = {}

    session = _Session()
    session.symbol_registry.register("k", "thermal conductivity", default_unit="W/(m*K)")
    session.symbol_registry.register("V", "mean velocity", default_unit="m/s")
    session.symbol_registry.register("rho", "density", default_unit="g/cm^3")

    units = collect_unit_map(session)  # type: ignore[arg-type]

    assert units["k"] == "W/(m*K)"
    assert units["V"] == "m/s"
    assert units["rho"] == "g/cm^3"


def test_builtin_domain_defaults_are_not_unit_information():
    """Built-in domain defaults are hints, not declarations (task-09).

    An unregistered symbol must be unknown; a name collision with a domain
    catalogue (``rho``, ``k``, ``p``, ...) must never fabricate a dimension and
    turn a correct step red.
    """
    from symkit.domain.symbol_registry import SymbolRegistry
    from symkit_mcp.tools._unit_context import collect_unit_map

    class _Session:
        def __init__(self) -> None:
            self.symbol_registry = SymbolRegistry()
            self.formulas: dict = {}

    units = collect_unit_map(_Session())  # type: ignore[arg-type]

    assert "rho" not in units
    assert "k" not in units
    assert "p" not in units
    assert units == {}


# --- Zero-side equations and derivative reduction (D3/D6) -------------------


def test_equation_with_literal_zero_side_is_dimensionally_polymorphic():
    """``Eq(..., 0)`` must not be flagged: a literal zero is any unit's zero.

    A recorded dsolve step normalises its ODE to
    ``Eq(C*R*Derivative(v_C(t), t) - V + v_C(t), 0)``; the right-hand zero was
    compared against the lhs vector and a correct step was failed (D3).
    """
    C, R, V, t = sp.symbols("C R V t")
    v_c = sp.Function("v_C")
    expr = sp.Eq(C * R * sp.Derivative(v_c(t), t) + v_c(t) - V, 0)
    units = {"C": "farad", "R": "ohm", "V": "volt", "v_C": "volt", "t": "s"}
    report = check_expression_dimensions(expr, units)
    assert report.consistent is not False, report.issues


def test_equation_with_two_nonzero_mismatched_sides_still_fails():
    """The task-06 trap: no side is zero, so the mismatch must still be caught."""
    v, v0, a, t = sp.symbols("v v0 a t")
    report = check_expression_dimensions(
        sp.Eq(v**2, v0**2 + 2 * a * t),
        {"v": "m/s", "v0": "m/s", "a": "m/s^2", "t": "s"},
    )
    assert report.consistent is False, (report.consistent, report.issues)


def test_derivative_reduces_with_known_units():
    """dim(dF/dt) = dim(F) - dim(t) when both are declared."""
    m, x, t = sp.symbols("m x t")
    expr = m * sp.Derivative(sp.Function("x")(t), (t, 2))
    # kg * (m / s**2)
    report = check_expression_dimensions(expr, {"m": "kg", "x": "m", "t": "s"})
    assert report.consistent is True, report.issues
    from symkit.domain.dimensional_analysis import expression_dimension

    assert expression_dimension(expr, {"m": "kg", "x": "m", "t": "s"}) == {
        "mass": 1,
        "length": 1,
        "time": -2,
    }


def test_derivative_missing_units_records_its_own_reason():
    """The inconclusive cause must be attributed to the derivative (D6)."""
    m, t = sp.symbols("m t")
    expr = m * sp.Derivative(sp.Function("x")(t), t)
    report = check_expression_dimensions(expr, {"m": "kg"})
    assert report.consistent is None
    assert "derivative" in report.indeterminate_reasons
    assert "non_integer_exponent" not in report.indeterminate_reasons


def test_non_integer_exponent_records_its_own_reason():
    x = sp.symbols("x")
    report = check_expression_dimensions(x ** sp.Rational(1, 2), {"x": "m"})
    assert report.consistent is None
    assert "non_integer_exponent" in report.indeterminate_reasons
    assert "derivative" not in report.indeterminate_reasons


def test_matrix_expression_does_not_crash_the_checker():
    """A matrix step must not blow up dimensional analysis.

    ``MutableDenseMatrix`` has no ``is_number`` attribute, so the numeric-leaf
    test raised ``AttributeError`` and took down the whole
    ``session_verify_session`` call for any session holding a matrix step.
    """
    numeric = sp.Matrix([[1, 2], [3, 4]])
    assert check_expression_dimensions(numeric ** 2, {"rho": "kg/m^3"}).consistent is True

    symbolic = sp.Matrix([[sp.Symbol("a"), 0], [0, 1]])
    report = check_expression_dimensions(symbolic, {"a": "m"})
    assert report.consistent is None  # indeterminate, not a crash and not a failure


# --- Pure ratios with mismatched declared units (r15 task-15 / C-03) --------


def test_ratio_of_distinct_quantities_with_mismatched_units_is_flagged():
    """``L/R`` with ``L`` in ``henry/second`` must not be a green check.

    ``henry/second`` is dimensionally ``ohm``, so the quotient cancels to
    dimensionless under the declared units.  Two *distinct* quantities written
    with *different* unit strings collapsing to a dimensionless ratio is the
    signature of a mis-declared unit; the checker must report the conflicting
    pair rather than a vacuous ``consistent:true``.
    """
    L, R = sp.symbols("L R")
    report = check_expression_dimensions(L / R, {"L": "henry/second", "R": "ohm"})
    assert report.consistent is False, (report.consistent, report.issues)
    assert any("L" in issue and "R" in issue for issue in report.issues)


def test_ratio_of_distinct_quantities_with_consistent_units_passes():
    L, R = sp.symbols("L R")
    report = check_expression_dimensions(L / R, {"L": "henry", "R": "ohm"})
    assert report.consistent is True, report.issues
    assert report.issues == []


def test_ratio_with_unregistered_symbol_stays_unknown_not_fabricated():
    """r14 semantics: an unregistered symbol stays inconclusive, never guessed."""
    L, R = sp.symbols("L R")
    report = check_expression_dimensions(L / R, {"R": "ohm"})
    assert report.consistent is None
    assert "L" in report.unknown_symbols


def test_same_symbol_ratio_is_still_consistently_dimensionless():
    """A genuine ``v/v`` must keep passing — only distinct quantities warn."""
    v = sp.symbols("v")
    report = check_expression_dimensions(v / v, {"v": "m/s"})
    assert report.consistent is True
    assert report.issues == []


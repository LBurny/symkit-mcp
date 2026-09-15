"""Tests for display-string unit parsing and SI dimensional dependencies."""

import sympy as sp
from sympy.physics.units import joule, kelvin, kilogram, meter, mole, pascal, second

from symkit.domain.units import dimension_dependencies, parse_unit


def test_parse_plain_si():
    assert parse_unit("kg/m^3") == kilogram / meter**3


def test_parse_middle_dot_and_caret():
    assert parse_unit("Pa·s") == pascal * second


def test_parse_compound_with_parentheses():
    assert parse_unit("J/(mol·K)") == joule / (mole * kelvin)


def test_parse_dash_and_empty_mean_unknown():
    assert parse_unit("-") is None
    assert parse_unit("") is None


def test_parse_whitespace_only_is_unknown():
    assert parse_unit("   ") is None


def test_parse_garbage_returns_none():
    assert parse_unit("not-a-unit!!") is None


def test_parse_unknown_name_returns_none():
    assert parse_unit("furlongs_per_fortnight") is None


def test_parse_fullwidth_parentheses():
    assert parse_unit("J/（mol·K）") == joule / (mole * kelvin)


def test_parse_superscript_digits():
    assert parse_unit("m²/s²") == meter**2 / second**2
    assert parse_unit("m³") == meter**3


def test_dimension_dependencies_density():
    assert dimension_dependencies(kilogram / meter**3) == {"mass": 1, "length": -3}


def test_dimension_dependencies_dimensionless():
    assert dimension_dependencies(meter / meter) == {}


def test_dimension_dependencies_pressure_aliases():
    # Pa·s reduces to mass/(length·time)
    assert dimension_dependencies(pascal * second) == {
        "mass": 1,
        "length": -1,
        "time": -1,
    }


def test_dimension_dependencies_of_plain_number():
    assert dimension_dependencies(sp.Integer(2)) == {}


# --- Unit information is declaration-only (task-09 §4-b) --------------------


def test_collect_unit_map_ignores_builtin_domain_defaults():
    """Unregistered symbols must not inherit a domain's default unit.

    The registry ships a cross-domain catalogue (``k`` → rate constant ``1/h``,
    ``p`` → pressure ``Pa``, ``rho`` → density) as semantic hints.  Treating
    those hints as the session's unit information fabricated dimensions for
    unregistered symbols and failed physically correct steps (task-09:
    ``k = pi/L`` reported dimensionally inconsistent because ``k`` inherited
    a pharmacokinetics default).
    """
    from symkit.domain.symbol_registry import SymbolRegistry
    from symkit_mcp.tools._unit_context import collect_unit_map

    class _Session:
        def __init__(self) -> None:
            self.symbol_registry = SymbolRegistry()
            self.formulas: dict = {}

    assert collect_unit_map(_Session()) == {}  # type: ignore[arg-type]


def test_collect_unit_map_keeps_explicit_registrations():
    from symkit.domain.symbol_registry import SymbolRegistry, SymbolScope
    from symkit_mcp.tools._unit_context import collect_unit_map

    class _Session:
        def __init__(self) -> None:
            self.symbol_registry = SymbolRegistry()
            self.formulas: dict = {}

    session = _Session()
    session.symbol_registry.register(
        "k",
        "wavenumber",
        scope=SymbolScope.USER,
        default_unit="1/m",
    )

    assert collect_unit_map(session)["k"] == "1/m"  # type: ignore[arg-type]


# --- A fractional power is not an integer dimension vector (dim round 2) ----


def test_dimension_dependencies_rejects_fractional_powers():
    """``sqrt(m)`` cannot be written as integer base powers.

    ``int(power)`` turned ``length ** (1/3)`` into ``length ** 0``, which reads
    as *dimensionless* — so ``x`` declared in ``sqrt(m)`` was laundered into a
    dimensionless quantity and ``x**3`` came back ``consistent: true``.
    """
    assert dimension_dependencies(sp.sqrt(meter)) is None
    assert dimension_dependencies(meter ** sp.Rational(1, 3)) is None
    assert dimension_dependencies(meter ** sp.Rational(3, 2)) is None


def test_dimension_dependencies_integer_powers_still_work():
    assert dimension_dependencies(meter**2 / second) == {"length": 2, "time": -1}


# --- Real-world unit glyphs (dim lab round 2) -------------------------------


def test_micro_prefix_glyphs_resolve():
    """The SI micro prefix is written as U+00B5 or Greek mu U+03BC.

    ``um`` was in the namespace and resolved, while ``µm`` and ``μm`` — the
    spellings a physicist actually types — were silently UNKNOWN, which turned
    the whole expression inconclusive instead of checked.
    """
    for text in ("\u00b5m", "\u03bcm", "um"):
        assert dimension_dependencies(parse_unit(text)) == {"length": 1}, text
    for text in ("\u00b5s", "\u03bcs", "us"):
        assert dimension_dependencies(parse_unit(text)) == {"time": 1}, text


def test_temperature_glyphs_are_temperature():
    """``K`` resolved but ``°C``, ``℃`` and ``degC`` did not, so every
    thermodynamics card written in Celsius went inconclusive."""
    for text in ("K", "\u00b0C", "\u2103", "degC", "celsius"):
        assert dimension_dependencies(parse_unit(text)) == {"temperature": 1}, text
    for text in ("\u00b0F", "\u2109", "fahrenheit"):
        assert dimension_dependencies(parse_unit(text)) == {"temperature": 1}, text


def test_angle_glyphs_are_dimensionless():
    for text in ("deg", "rad", "\u00b0"):
        assert dimension_dependencies(parse_unit(text)) == {}, text


def test_steradian_is_dimensionless():
    """SI defines the steradian as a dimensionless derived unit; reporting a
    made-up ``steradian`` base quantity broke the "keys are base quantities"
    contract of the dimension vector."""
    for text in ("sr", "steradian"):
        assert dimension_dependencies(parse_unit(text)) == {}, text


def test_percent_glyphs_assert_dimensionless():
    from symkit.domain.units import is_dimensionless_marker

    for text in ("%", "\u2030", "ppm"):
        assert is_dimensionless_marker(text), text

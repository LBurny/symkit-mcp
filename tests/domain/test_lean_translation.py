import pytest
import sympy as sp

from symkit.domain.lean_translation import translate_equality
from symkit.domain.lean_types import UntranslatableError

x, y = sp.symbols("x y")


def test_ring_lane_simple_identity():
    # SymPy auto-collapses x + 2*x to 3*x, so use an unexpanded product.
    s = translate_equality(x * (x + 2), x**2 + 2 * x, name="symkit_step_001")
    assert (s.lane, s.target_type, s.variables, s.hypotheses) == ("ring", "ℝ", ("x",), ())
    assert "(2 : ℝ)" in s.lhs and "(2 : ℝ)" in s.rhs
    assert s.tactic_block == "ring"


def test_rational_constant_renders_as_real_division():
    # SymPy collapses Rational(1,2)*x + Rational(1,2)*x to x; keep the coefficient.
    s = translate_equality(sp.Rational(1, 2) * x, x / 2)
    assert "((1 : ℝ) / (2 : ℝ))" in s.lhs and s.lane == "ring"


def test_integral_float_becomes_integer():
    assert "(2 : ℝ)" in translate_equality(sp.Float(2.0) * x, 2 * x).lhs


def test_variable_denominator_requires_nonzero_assumption():
    with pytest.raises(UntranslatableError, match="nonzero"):
        translate_equality((x + y) / x, 1 + y / x)


def test_variable_denominator_with_assumption_uses_field_lane():
    s = translate_equality((x + y) / x, 1 + y / x, assumptions={"x": {"nonzero": True}})
    assert s.lane == "field" and s.hypotheses == ("h_x : x ≠ 0",)
    assert s.tactic_block == "field_simp [*]\n  ring"


def test_positive_assumption_renders_strict_inequality():
    # positive implies nonzero, but the stronger fact is what the user asked for.
    s = translate_equality((x + y) / x, 1 + y / x, assumptions={"x": {"positive": True}})
    assert s.lane == "field" and s.hypotheses == ("h_x : x > 0",)


def test_negative_assumption_renders_strict_inequality():
    s = translate_equality((x + y) / x, 1 + y / x, assumptions={"x": {"negative": True}})
    assert s.hypotheses == ("h_x : x < 0",)


def test_nonnegative_assumption_is_rendered_alongside_nonzero():
    s = translate_equality(
        (x + y) / x,
        1 + y / x,
        assumptions={"x": {"nonnegative": True, "nonzero": True}},
    )
    assert s.hypotheses == ("h_x : x ≠ 0", "h_x_nonneg : 0 ≤ x")


def test_compound_denominator_gets_generated_nonzero_hypotheses():
    # SymPy splits 1/(x*(x+1)) into x^-1 * (x+1)^-1; the compound factor x+1
    # earns its own `≠ 0` binder so field_simp can clear it.
    s = translate_equality(
        1 / (x * (x + 1)),
        1 / x - 1 / (x + 1),
        assumptions={"x": {"nonzero": True}},
    )
    assert s.lane == "field"
    assert s.hypotheses == ("h_x : x ≠ 0", "h_x_1 : ((1 : ℝ) + x) ≠ 0")


def test_sum_denominator_is_translatable_with_generated_hypothesis():
    s = translate_equality(
        (x**2 - y**2) / (x - y),
        x + y,
        assumptions={"x": {"nonzero": True}},
    )
    assert s.lane == "field"
    assert len(s.hypotheses) == 2
    assert any("≠ 0" in h and "(-y)" in h for h in s.hypotheses)


def test_untranslatable_reason_is_deterministic_and_actionable():
    def reason() -> str:
        with pytest.raises(UntranslatableError) as exc:
            translate_equality((x + y) / x, 1 + y / x)
        return str(exc.value)

    first, second = reason(), reason()
    assert first == second
    assert "x" in first and "nonzero" in first


@pytest.mark.parametrize(
    "expr,frag",
    [
        (sp.sin(x), "sin"),
        (x ** sp.Rational(1, 2), "exponent"),
        (sp.Float(0.1), "float"),
        (sp.Integral(x, x), "Integral"),
        (sp.Eq(x, y), "quality"),  # Eq→Eq 改写留 v2
    ],
)
def test_unsupported_constructs_raise(expr, frag):
    with pytest.raises(UntranslatableError, match=frag):
        translate_equality(expr, expr)


def test_imaginary_unit_switches_to_complex():
    # Note: sp.I*x*sp.I auto-simplifies to -x, so use an expression that keeps I.
    s = translate_equality(sp.I * x + sp.I * x, 2 * sp.I * x)
    assert s.target_type == "ℂ" and "Complex.I" in s.lhs


def test_illegal_identifier_is_sanitized():
    weird = sp.Symbol("x y")
    s = translate_equality(weird + weird, 2 * weird)
    assert s.variables[0] != "x y" and s.variables[0].isidentifier()

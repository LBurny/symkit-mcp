"""srepr-form strings must load through the user expression parser (r22).

``python_exec`` returns a result's ``srepr``; pasting that string into any
expression field must rebuild the object — including symbol assumptions —
instead of dying in the restricted text grammar.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.expr_io import try_load_srepr
from symkit.domain.expression_parser import parse_user_expression


class TestTryLoadSrepr:
    def test_constructor_form_with_assumptions_loads(self) -> None:
        obj = try_load_srepr(
            "Mul(Rational(1, 2), Symbol('c', positive=True), "
            "Pow(Symbol('k', positive=True), Rational(-1, 2)))"
        )
        assert obj is not None
        symbols = {s.name: s for s in obj.atoms(sp.Symbol)}
        assert symbols["c"].is_positive is True
        assert symbols["k"].is_positive is True

    def test_plain_text_is_not_srepr(self) -> None:
        assert try_load_srepr("x + 2") is None
        assert try_load_srepr("sin(x)") is None
        assert try_load_srepr("c/(2*sqrt(m*k))") is None

    def test_broken_constructor_falls_back(self) -> None:
        assert try_load_srepr("Mul(") is None
        assert try_load_srepr("Pow(x, 2") is None

    def test_evil_text_is_not_touched(self) -> None:
        assert try_load_srepr("__import__('os')") is None
        assert try_load_srepr("os.system('x')") is None

    def test_matrix_srepr_loads(self) -> None:
        obj = try_load_srepr("ImmutableDenseMatrix([[1, 2], [3, 4]])")
        assert isinstance(obj, sp.ImmutableDenseMatrix)


class TestParseUserExpressionSrepr:
    def test_srepr_form_parses_via_user_parser(self) -> None:
        expr, error = parse_user_expression(
            "Mul(Rational(1, 2), Symbol('c', positive=True), "
            "Pow(Symbol('m', positive=True), Rational(-1, 2)), "
            "Pow(Symbol('k', positive=True), Rational(-1, 2)))"
        )
        assert error is None
        assert expr is not None
        assert sp.simplify(expr - sp.symbols("c", positive=True) / (2 * sp.sqrt(
            sp.symbols("m", positive=True) * sp.symbols("k", positive=True)
        ))) == 0

    def test_equality_srepr_becomes_equation(self) -> None:
        expr, error = parse_user_expression("Equality(Symbol('x'), Integer(1))")
        assert error is None
        assert isinstance(expr, sp.Equality)
        assert expr.lhs == sp.Symbol("x") and expr.rhs == sp.Integer(1)

    def test_undefined_function_srepr_loads(self) -> None:
        expr, error = parse_user_expression("Function('f')(Symbol('x'))")
        assert error is None
        assert expr is not None
        assert isinstance(expr.func, sp.core.function.UndefinedFunction)

    def test_plain_expression_still_parses(self) -> None:
        expr, error = parse_user_expression("x**2 + 2*x + 1")
        assert error is None
        assert expr is not None
        # The user parser deliberately returns unevaluated arithmetic (see
        # expr_io.evaluated_form), so compare mathematically, not structurally.
        expected = sp.Symbol("x") ** 2 + 2 * sp.Symbol("x") + 1
        assert sp.simplify(expr - expected) == 0

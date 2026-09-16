"""Reserved ``S``/``N`` call sites must survive as undefined functions.

G7 (field card task-01): SymPy's ``S`` is the SingletonRegistry and ``N`` the
evalf shortcut, so ``S(x)`` evaluated to ``Symbol('x')`` — ``S(x)*x`` then
differentiated to ``2*x`` instead of ``x*S'(x) + S(x)``.  Bare ``S``/``N``
stay Symbols (reserved-name protection) and native calls such as
``beta(x, 2)``/``O(x**2)`` are untouched.

Hosted in its own module (rather than appended to ``test_expression_parser``)
because that file already sits at the bylaw §5.1 file-length hard cap.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.expression_parser import (
    parse_expression_string,
    parse_user_expression,
)


class TestSingletonCallSites:
    def test_singleton_registry_call_site_is_an_undefined_function(self) -> None:
        expr, error = parse_user_expression("S(x)*x")
        assert error is None, error
        assert expr is not None
        x = sp.Symbol("x")
        s_call = sp.Function("S")(x)
        assert expr.has(s_call), expr
        assert sp.simplify(expr.diff(x) - (x * sp.Derivative(s_call, x) + s_call)) == 0

    def test_evalf_call_site_is_an_undefined_function(self) -> None:
        expr, error = parse_user_expression("N(x)")
        assert error is None, error
        assert expr == sp.Function("N")(sp.Symbol("x"))

    def test_bare_singleton_names_stay_symbols(self) -> None:
        for source in ("S + 1", "N - 2"):
            expr, error = parse_user_expression(source)
            assert error is None, (source, error)
            assert sp.Symbol(source[0]) in expr.free_symbols, (source, expr)

    def test_singleton_call_survives_through_parse_expression_string(self) -> None:
        expr, error = parse_expression_string("S(x)")
        assert error is None, error
        assert expr == sp.Function("S")(sp.Symbol("x"))

    def test_native_beta_call_is_unchanged(self) -> None:
        expr, error = parse_user_expression("beta(x, 2)")
        assert error is None, error
        assert expr is not None and expr.func is sp.beta

    def test_big_o_is_unchanged(self) -> None:
        expr, error = parse_user_expression("O(x**2)")
        assert error is None, error
        assert expr == sp.O(sp.Symbol("x") ** 2)

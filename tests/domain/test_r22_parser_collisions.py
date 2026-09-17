"""r22 parser collisions: E1 alias and bare FunctionClass arguments (S11/S12)."""

from __future__ import annotations

import sympy as sp

from symkit.domain.expression_parser import parse_expression_string


class TestRound22ReservedCollisions:
    """r22: reserved-name collisions the parser used to reject (probe S11/S12).

    S11 (task-08): ``E1`` is sympy's plain-python ``expint`` alias, so a bare
    ``E1`` in a quotient crashed sympify (``SympifyError: <function E1 ...>``);
    like ``E``/``I`` it must bind as a protected symbol.

    S12 (task-10): ``beta(alpha, beta)`` means the beta *function* applied to a
    variable named beta; the bare occurrence resolved to the ``FunctionClass``
    itself, whose ``.args`` is a property — sympify died with "'property' object
    is not iterable".
    """

    def test_e1_binds_as_symbol_in_quotient(self):
        expr, error = parse_expression_string("E2/E1")
        assert error is None, error
        assert {str(s) for s in expr.free_symbols} == {"E1", "E2"}

    def test_beta_call_with_bare_reserved_argument(self):
        expr, error = parse_expression_string("beta(alpha, beta)")
        assert error is None, error
        assert expr.func is sp.beta
        assert sp.Symbol("beta") in expr.args
        assert sp.Symbol("alpha") in expr.args

    def test_zeta_call_with_bare_reserved_argument(self):
        # ``zeta`` with two arguments is the Hurwitz zeta function.
        expr, error = parse_expression_string("zeta(s, zeta)")
        assert error is None, error
        assert expr.func is sp.zeta
        assert sp.Symbol("zeta") in expr.args

    def test_pure_call_still_binds_native_function(self):
        expr, error = parse_expression_string("beta(alpha, x)")
        assert error is None, error
        assert expr.func is sp.beta

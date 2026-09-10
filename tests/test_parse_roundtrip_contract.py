"""Round-trip contract: ``str(parse(s))`` must re-parse to the identical object.

Regression net against string-mediated boundary corruption (e.g. ``v(t)``
silently becoming ``t*v`` when a stored string is re-parsed).
"""

from __future__ import annotations

import pytest
import sympy as sp

from symkit.domain.expression_parser import parse_expression_string

ROUNDTRIP_CASES = [
    "v(t)",
    "Derivative(v(t), t) = g - (1/2)*rho*C_d*A*v(t)**2/m",
    "Eq(v(t), sqrt(2)*sqrt(g)*sqrt(m)/(sqrt(A)*sqrt(C_d)*sqrt(rho)))",
    "1/2*rho*C_d*A*v_t**2 == m*g",
    "x**(1/6) + beta*y",
    "div(rho*u) + laplacian(p)",
    "sqrt(2*G*M/R)",
    "Derivative(y(x), x) + y(x)",
    "nu_tilde**4/(c_v1**3*nu**3 + nu_tilde**3)",
]


@pytest.mark.parametrize("source", ROUNDTRIP_CASES)
def test_str_roundtrip_is_identity(source):
    e1, err1 = parse_expression_string(source)
    assert err1 is None, err1
    assert e1 is not None
    e2, err2 = parse_expression_string(str(e1))
    assert err2 is None, err2
    assert e2 is not None
    assert sp.srepr(e1) == sp.srepr(e2)

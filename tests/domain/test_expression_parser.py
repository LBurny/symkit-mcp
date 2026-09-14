"""Tests for the shared expression parser."""

from __future__ import annotations

import pytest
import sympy as sp

from symkit.domain.expression_parser import (
    parse_expression_string,
    parse_user_expression,
    preprocess_leibniz_derivatives,
    preprocess_vector_calculus,
)


class TestUnicodePreprocessing:
    """Unicode math characters are converted to ASCII before parsing."""

    def test_greek_letters(self):
        expr, error = parse_expression_string("β * x**2")
        assert error is None
        assert "beta" in str(expr)

    def test_partial_to_d(self):
        expr, error = parse_expression_string("∂u/∂t")
        assert error is None
        assert "Derivative(u, t)" in str(expr)


class TestLeibnizDerivatives:
    """Leibniz notation dX/dY is converted to Derivative(...)."""

    def test_first_order_derivative(self):
        assert preprocess_leibniz_derivatives("dk/dt") == "Derivative(k, t)"

    def test_subscripted_derivative(self):
        assert preprocess_leibniz_derivatives("dUi/dxj") == "Derivative(Ui, xj)"

    def test_higher_order_derivative(self):
        assert preprocess_leibniz_derivatives("d^2k/dt^2") == "Derivative(k, (t, 2))"

    def test_derivative_inside_equation(self):
        expr, error = parse_expression_string("dk/dt = Pk - epsilon + Dk")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Derivative(k, t)"

    def test_boussinesq_closure(self):
        expr, error = parse_expression_string(
            "tau_ij = nut * (dUi/dxj + dUj/dxi) - (2/3)*k*delta_ij",
        )
        assert error is None
        assert expr.is_Equality


class TestMaterialDerivative:
    """Uppercase D/Dt is converted to Derivative(..., t)."""

    def test_material_derivative_fraction_form(self):
        expr, error = parse_expression_string("D(u)/Dt = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Derivative(u, t)"

    def test_material_derivative_function_form(self):
        expr, error = parse_expression_string("D/Dt(u) = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Derivative(u, t)"

    def test_material_derivative_in_transport_equation(self):
        expr, error = parse_expression_string(
            "D(rho)/Dt + Div(rho*u) = 0",
        )
        assert error is None
        assert expr.is_Equality
        lhs = str(expr.lhs)
        assert "Derivative(rho, t)" in lhs
        assert "Div(rho*u)" in lhs


class TestVectorCalculusParsing:
    """Vector-calculus operators parse as user-defined symbolic functions."""

    def test_div_parses(self):
        expr, error = parse_expression_string("div(rho*u) = 0")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "div(rho*u)"

    def test_grad_parses(self):
        expr, error = parse_expression_string("grad(p) = rho * grad(phi)")
        assert error is None
        assert expr.is_Equality
        assert "grad(p)" in str(expr.lhs)
        assert "grad(phi)" in str(expr.rhs)

    def test_curl_parses(self):
        expr, error = parse_expression_string("curl(u) = 0")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "curl(u)"

    def test_del_operator_parses(self):
        expr, error = parse_expression_string("Del(p) = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Del(p)"

    def test_laplacian_shorthand(self):
        assert preprocess_vector_calculus("Del^2(u)") == "laplacian(u)"
        assert preprocess_vector_calculus("Del**2(u)") == "laplacian(u)"
        assert preprocess_vector_calculus("nabla^2(u)") == "laplacian(u)"

    def test_convective_shorthand(self):
        assert preprocess_vector_calculus("(u*Del)*v") == "convective(u, v)"
        assert preprocess_vector_calculus("(u*nabla)*v") == "convective(u, v)"

    def test_navier_stokes_momentum_text_form(self):
        expr, error = parse_expression_string(
            "rho * (diff(u,t) + (u*Del)*u) = -Del(p) + mu*Del^2(u) + f"
        )
        assert error is None
        assert expr.is_Equality
        lhs_str = str(expr.lhs)
        rhs_str = str(expr.rhs)
        assert "Derivative(u, t)" in lhs_str
        assert "convective(u, u)" in lhs_str
        assert "Del(p)" in rhs_str
        assert "laplacian(u)" in rhs_str


class TestUppercaseVectorOperators:
    """Uppercase vector-calculus aliases parse as user-defined symbolic functions."""

    def test_uppercase_div_parses(self):
        expr, error = parse_expression_string("Div(rho*u) = 0")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Div(rho*u)"

    def test_uppercase_grad_parses(self):
        expr, error = parse_expression_string("Grad(p) = rho * Grad(phi)")
        assert error is None
        assert expr.is_Equality
        assert "Grad(p)" in str(expr.lhs)
        assert "Grad(phi)" in str(expr.rhs)

    def test_uppercase_dot_parses(self):
        expr, error = parse_expression_string(
            "Dot(Grad(u), Grad(u)) = 0"
        )
        assert error is None
        assert expr.is_Equality
        assert "Dot(Grad(u), Grad(u))" in str(expr.lhs)

    def test_uppercase_curl_parses(self):
        expr, error = parse_expression_string("Curl(u) = 0")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Curl(u)"

    def test_uppercase_laplacian_parses(self):
        expr, error = parse_expression_string("Laplacian(u) = f")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "Laplacian(u)"


class TestUserExpressionParser:
    """parse_user_expression auto-detects LaTeX and falls back to shared parser."""

    def test_latex_fraction(self):
        expr, error = parse_user_expression("x = \\frac{a}{b}")
        assert error is None
        assert expr.is_Equality
        assert str(expr.lhs) == "x"

    def test_latex_partial_derivative(self):
        expr, error = parse_user_expression("\\frac{\\partial u}{\\partial t}")
        assert error is None
        assert "Derivative" in str(expr)

    def test_latex_material_derivative_fraction(self):
        expr, error = parse_user_expression(r"\frac{D u}{D t} = f")
        assert error is None
        assert expr.is_Equality
        assert "Derivative(u, t)" in str(expr.lhs)

    def test_latex_material_derivative_prefix(self):
        expr, error = parse_user_expression(r"\frac{D}{Dt}(u) = f")
        assert error is None
        assert expr.is_Equality
        assert "Derivative(u, t)" in str(expr.lhs)

    def test_sympy_string_with_beta(self):
        expr, error = parse_user_expression("beta * omega**2")
        assert error is None
        assert "beta" in str(expr)

    def test_sympy_string_with_leibniz(self):
        expr, error = parse_user_expression("dk/dt = Pk - epsilon")
        assert error is None
        assert expr.is_Equality


class TestSpalartAllmarasEquation:
    """The user's original failing expression should parse successfully."""

    def test_sa_transport_equation(self):
        expr, error = parse_expression_string(
            "Eq(D(nu_tilde)/Dt, c_b1*S_tilde*nu_tilde - c_w1*f_w*(nu_tilde/d)**2 + "
            "(1/sigma)*Div((nu + nu_tilde)*Grad(nu_tilde)) + "
            "(c_b2/sigma)*Dot(Grad(nu_tilde), Grad(nu_tilde)))"
        )
        assert error is None, f"Parse error: {error}"
        assert expr.is_Equality
        lhs = str(expr.lhs)
        rhs = str(expr.rhs)
        assert "Derivative(nu_tilde, t)" in lhs
        assert "Div((nu + nu_tilde)*Grad(nu_tilde))" in rhs
        assert "Dot(Grad(nu_tilde), Grad(nu_tilde))" in rhs


class TestComplexExpressions:
    """Real-world expressions from PDE and turbulence workflows."""

    def test_navier_stokes_momentum(self):
        expr, error = parse_expression_string(
            "Derivative(u_i, t) + u_j * Derivative(u_i, x_j) = "
            "-1/rho * Derivative(p, x_i) + nu * Derivative(u_i, x_j, x_j)",
        )
        assert error is None
        assert expr.is_Equality

    def test_reynolds_decomposition(self):
        expr, error = parse_expression_string("u_i = U_i + u_prime_i")
        assert error is None
        assert expr.is_Equality

    def test_k_omega_transport(self):
        expr, error = parse_expression_string(
            "Derivative(omega, t) + U_j*Derivative(omega, x_j) - "
            "alpha*omega*P_k/k + beta*omega**2 - "
            "Derivative((nu + nu_t/sigma_omega)*Derivative(omega, x_j), x_j)",
        )
        assert error is None
        assert "beta" in str(expr)

    def test_substitution_with_beta(self):
        expr, error = parse_expression_string(
            "P_k = nut * S**2",
        )
        assert error is None
        assert expr.is_Equality

    def test_strain_rate_tensor_with_diff(self):
        expr, error = parse_expression_string(
            "S_ij = (dUi/dxj + dUj/dxi) / 2",
        )
        assert error is None
        assert expr.is_Equality

    def test_empty_expression(self):
        expr, error = parse_expression_string("")
        assert expr is None
        assert error is not None

    def test_invalid_syntax(self):
        expr, error = parse_expression_string("x +++ @#$")
        assert expr is None
        assert error is not None


class TestUnevaluatedDivisionNormalization:
    """parse_expr(evaluate=False) keeps numeric divisions unevaluated; they must
    fold into canonical Rational so fractional exponents evaluate numerically."""

    def test_simple_division_is_rational(self):
        expr, error = parse_expression_string("1/6")
        assert error is None
        assert expr == sp.Rational(1, 6)

    def test_fractional_exponent_is_rational(self):
        expr, error = parse_expression_string("x**(1/6)")
        assert error is None
        # structural check: the exponent must be a canonical Rational, not an
        # unevaluated Mul(1, 1/6)
        assert expr.exp == sp.Rational(1, 6)

    def test_numeric_fractional_power_value(self):
        expr, error = parse_expression_string("65.0**(1/6)")
        assert error is None
        assert isinstance(expr, sp.Float)
        assert abs(float(expr) - 2.0051747451504215) < 1e-12

    def test_deferred_derivative_preserved(self):
        expr, error = parse_expression_string("diff(y(x), x)")
        assert error is None
        assert expr.has(sp.Derivative)


class TestFunctionNotationRedLine:
    """Unknown ``name(...)`` call sites parse as undefined Functions.

    Red line: function notation must never silently degrade to implicit
    multiplication (``v(t)`` becoming ``v*t``).
    """

    def test_function_notation_parses_as_undefined_function(self):
        expr, err = parse_expression_string("v(t)")
        assert err is None and expr is not None
        assert isinstance(expr, sp.core.function.AppliedUndef)
        assert expr.func == sp.Function("v")
        assert expr.args == (sp.Symbol("t"),)

    def test_function_notation_inside_derivative_equation(self):
        expr, err = parse_expression_string(
            "Derivative(v(t), t) = g - (1/2)*rho*C_d*A*v(t)**2/m"
        )
        assert err is None and isinstance(expr, sp.Equality)
        assert isinstance(expr.lhs, sp.Derivative)
        assert expr.lhs.expr == sp.Function("v")(sp.Symbol("t"))
        # rhs must contain v(t)**2, never t**2*v
        assert expr.rhs.has(sp.Function("v")(sp.Symbol("t")) ** 2)

    def test_reserved_functions_keep_native_semantics(self):
        expr, err = parse_expression_string("sin(x) + sqrt(y) + beta(1, 2)")
        assert err is None and expr is not None
        assert expr.has(sp.sin(sp.Symbol("x")))
        assert not expr.atoms(sp.core.function.AppliedUndef)

    def test_implicit_multiplication_without_call_syntax_unchanged(self):
        expr, err = parse_expression_string("2 x + x*(y + 1)")
        assert err is None and expr is not None
        assert sp.simplify(expr - (2 * sp.Symbol("x") + sp.Symbol("x") * (sp.Symbol("y") + 1))) == 0

    def test_numeric_call_still_implicit_multiplication(self):
        expr, err = parse_expression_string("2(x + 1)")
        assert err is None and expr is not None
        assert sp.simplify(expr - (2 * sp.Symbol("x") + 2)) == 0


class TestStrRoundTrip:
    """``str(parse(s))`` must re-parse to the identical object.

    Regression net against string-mediated boundary corruption (e.g. ``v(t)``
    silently becoming ``t*v`` when a stored string is re-parsed).
    """

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
    def test_str_roundtrip_is_identity(self, source):
        e1, err1 = parse_expression_string(source)
        assert err1 is None, err1
        assert e1 is not None
        e2, err2 = parse_expression_string(str(e1))
        assert err2 is None, err2
        assert e2 is not None
        assert sp.srepr(e1) == sp.srepr(e2)


class TestEngineeringSymbolNames:
    """Q (heat) and O must work as variables, like E/I already do.

    ``Q`` is a SymPy assumptions singleton and ``O`` the Big-O class; without
    reserved-name protection ``Q = m*cp*dT`` failed with a raw
    ``AssumptionKeys object at 0x...`` message.
    """

    def test_heat_symbol_q_parses(self) -> None:
        expr, error = parse_user_expression("Q - m*cp*dT")
        assert error is None, error
        assert expr is not None
        assert {s.name for s in expr.free_symbols} >= {"Q", "m", "cp", "dT"}

    def test_big_o_still_means_big_o(self) -> None:
        expr, error = parse_user_expression("O(x**2)")
        assert error is None, error
        assert expr is not None
        assert "O(" in str(expr)  # call site keeps SymPy's Big-O semantics


class TestAdditiveScaleGuard:
    """A huge explicit sum must be rejected before its exact-rational lcm
    denominator chain explodes and wedges the server (r16 task-05)."""

    @staticmethod
    def _harmonic_terms(n: int) -> str:
        return " + ".join(f"1/{k}" for k in range(1, n + 1))

    def test_just_under_the_limit_parses(self):
        expr, error = parse_expression_string(self._harmonic_terms(999))
        assert error is None, error
        assert expr is not None

    def test_over_the_limit_is_rejected_with_closed_form_hint(self):
        with pytest.raises(ValueError) as excinfo:
            parse_expression_string(self._harmonic_terms(1001))
        message = str(excinfo.value)
        assert "1001" in message
        assert "Sum(1/k" in message

    def test_equation_side_is_guarded_too(self):
        with pytest.raises(ValueError):
            parse_expression_string("y = " + self._harmonic_terms(1001))


class TestMinMaxFunctionCalls:
    """Lowercase ``max``/``min`` call sites parse to SymPy ``Max``/``Min``.

    The 2026-09-14 SST derivation round: the parser bound ``max(`` to an
    undefined ``Function('max')``, so ``evalf("max(0.1, 0.05)")`` returned the
    call unevaluated and every SST mixing-function (F1/F2) identity was
    numerically unverifiable.
    """

    def test_lowercase_max_evaluates_numeric_args(self):
        expr, error = parse_expression_string("max(0.1, 0.05)")
        assert error is None, error
        assert abs(float(expr) - 0.1) < 1e-12

    def test_lowercase_min_stays_symbolic_for_symbols(self):
        expr, error = parse_expression_string("min(x, 0)")
        assert error is None, error
        assert expr == sp.Min(sp.Symbol("x"), 0)

    def test_uppercase_max_is_untouched(self):
        expr, error = parse_expression_string("Max(0.1, 0.05)")
        assert error is None, error
        assert abs(float(expr) - 0.1) < 1e-12

    def test_max_inside_limiter_expression(self):
        expr, error = parse_expression_string("a1*k/max(a1*omega, F2*S) - k/omega")
        assert error is None, error
        assert expr.has(sp.Max), str(expr)
        substituted = expr.subs({sp.Symbol("a1"): 2, sp.Symbol("k"): 3,
                                 sp.Symbol("omega"): 5, sp.Symbol("F2"): 7,
                                 sp.Symbol("S"): 11})
        assert abs(complex(sp.N(substituted)).real - (-201 / 385)) < 1e-12


class TestDualUseSymbolAndFunction:
    """A name used both bare and as a call site must not crash the parser.

    2026-09-14 defect: ``1/z + z(x)`` bound ``z`` to ``Function('z')`` for the
    call site, so the bare ``1/z`` died with an unhelpful ``SympifyError: z``.
    Single-letter names (``k``, ``omega``) make this the common shape for
    boundary-layer derivations.
    """

    def test_bare_symbol_plus_function_call_parses(self):
        expr, error = parse_expression_string("1/z + z(x)")
        assert error is None, error
        assert expr.has(sp.Symbol("z"))
        assert expr.has(sp.Function("z"))
        assert "z(x)" in str(expr)
        assert "__call" not in str(expr)

    def test_product_form_dual_use(self):
        expr, error = parse_expression_string("k*omega + k(x)")
        assert error is None, error
        assert expr.has(sp.Function("k"))
        assert expr.has(sp.Symbol("k"))
        assert "__call" not in str(expr)

    def test_single_use_forms_keep_existing_shapes(self):
        applied, _ = parse_expression_string("z(x) + 1")
        assert applied.has(sp.Function("z")(sp.Symbol("x")))
        bare, _ = parse_expression_string("1/k")
        assert sp.simplify(bare - 1 / sp.Symbol("k")) == 0

    def test_assumptions_bind_bare_symbol_not_call(self):
        positive_k = sp.Symbol("k", positive=True)
        expr, error = parse_expression_string(
            "k + k(x)", local_dict={"k": positive_k}
        )
        assert error is None, error
        assert expr.has(positive_k)
        assert expr.has(sp.Function("k"))
        assert "__call" not in str(expr)

    def test_simplify_dual_use_expression(self):
        expr, error = parse_expression_string("k(x) + k - k")
        assert error is None, error
        # evaluate=False keeps the additive terms; the value is k(x).
        assert sp.simplify(expr - sp.Function("k")(sp.Symbol("x"))) == 0


class TestFlatListLiteral:
    """A flat ``[a, b]`` list literal is a column vector, not an opaque list.

    2026-09-14 defect: only list-of-lists became a ``Matrix`` (run-020), so a
    flat list flowed into the execution layer and crashed with
    ``'list' object has no attribute 'evalf'`` / ``'replace'``.
    """

    def test_flat_list_becomes_column_matrix(self):
        expr, error = parse_expression_string("[1/1.168, 2+2]")
        assert error is None, error
        assert isinstance(expr, sp.MatrixBase)
        assert expr.shape == (2, 1)
        assert abs(float(expr[1]) - 4) < 1e-12

    def test_matrix_grid_still_supported(self):
        expr, error = parse_expression_string("[[1, 2], [3, 4]]")
        assert error is None, error
        assert isinstance(expr, sp.MatrixBase)
        assert expr.shape == (2, 2)

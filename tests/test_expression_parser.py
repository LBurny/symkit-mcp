"""Tests for the shared expression parser."""

from __future__ import annotations

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

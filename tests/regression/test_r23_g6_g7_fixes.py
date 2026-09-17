"""r23 acceptance re-run defects G6/G7, reproduced from the operator transcripts.

G6 mixed matrix/scalar recorded equations: ``M == Matrix([[1,1],[1,0]])`` is a
   bare-symbol definition, but the scalar identity machinery computed
   ``Symbol - Matrix`` and raised ``TypeError``, so the step landed on the
   "Automatic verification failed: TypeError..." crash fallback instead of the
   F6 definition reading.  Every scalar/matrix mix must reach an honest verdict.
G7 wrapped unevaluated definite integral: the honesty guard in
   ``_verify_definite_integration`` only inspected a *bare* ``Integral`` output,
   so an unevaluated integral wrapped in a coefficient
   (``Integral(f, (t, 0, pi))/2``) was "verified by numeric quadrature" by
   comparing the expression with itself.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.assumption_engine import AssumptionEngine
from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.final_result import recorded_step_verdict
from symkit.domain.recorded_claim import unevaluated_equality
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus
from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools
from symkit_mcp.tools.symbols import register_symbol_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _tools():
    mcp = MockMCP()
    register_session_tools(mcp)
    register_math_tools(mcp)
    register_assumption_tools(mcp)
    register_symbol_tools(mcp)
    return mcp.tools


def _start(tools, name):
    tools["session_start"](name=name)


def _make_step(
    input_expressions: dict[str, str],
    output_expression: str,
    sympy_command: str,
) -> DerivationStep:
    return DerivationStep(
        step_number=1,
        operation=OperationType.INTEGRATE,
        description="g7 integration",
        input_expressions=input_expressions,
        output_expression=output_expression,
        output_latex=output_expression,
        sympy_command=sympy_command,
    )


# --------------------------------------------------------------------------- G6


class TestG6MatrixDefinition:
    def test_bare_symbol_matrix_definition_is_inconclusive(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "g6-matrix-def")
        tools["session_record_step"](
            expression="M == Matrix([[1,1],[1,0]])",
            description="matrix definition of M",
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "inconclusive"
        assert "definition recorded" in result["verification_message"]
        assert "TypeError" not in result["verification_message"]
        assert "unsupported operand" not in result["verification_message"]
        assert "Automatic verification failed" not in result["verification_message"]

    def test_matrix_definition_domain_verdict_matches_f6_wording(self) -> None:
        expr = unevaluated_equality("M == Matrix([[1,1],[1,0]])")
        assert expr is not None
        status, message = recorded_step_verdict(expr)
        assert status == VerificationStatus.INCONCLUSIVE
        assert "definition or model constant" in message
        assert "definition recorded" in message
        assert "unproven, not disproven" in message

    def test_mixed_matrix_forms_never_raise(self) -> None:
        # At least three mixed shapes beyond ``M == Matrix(...)`` must reach a
        # verdict instead of a raw TypeError from ``lhs - rhs``.
        claims = [
            "Matrix([[1,1],[1,0]]) == M",
            "M == MatrixSymbol(\"A\", 2, 2)",
            "M == Matrix([[M, 1], [1, 0]])",
            "Matrix([[1,1],[1,0]]) == MatrixSymbol(\"A\", 2, 2)",
        ]
        allowed = {
            VerificationStatus.VERIFIED,
            VerificationStatus.FAILED,
            VerificationStatus.INCONCLUSIVE,
        }
        for claim in claims:
            expr = unevaluated_equality(claim)
            assert expr is not None, claim
            status, message = recorded_step_verdict(expr)
            assert status in allowed, (claim, status)
            assert "TypeError" not in message, (claim, message)
            assert "unsupported operand" not in message, (claim, message)
            assert "Mix of Matrix" not in message, (claim, message)

    def test_scalar_bare_symbol_definition_still_inconclusive(
        self, fresh_session_manager
    ) -> None:
        # F6 guard: the extension to matrix RHS must not disturb ``tau_c = pi/2``.
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "g6-scalar-guard")
        tools["session_record_step"](
            expression="tau_c = pi/2", description="scalar definition"
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "inconclusive"
        assert "definition recorded" in result["verification_message"]

    def test_true_concrete_matrix_identity_still_verified(self) -> None:
        # F7 guard: two concrete matrices keep the elementwise verdict.
        expr = unevaluated_equality(
            "Matrix([[1,1],[1,0]])**5 == Matrix([[8,5],[5,3]])"
        )
        assert expr is not None
        status, _ = recorded_step_verdict(expr)
        assert status == VerificationStatus.VERIFIED

    def test_false_concrete_matrix_equation_still_failed(self) -> None:
        expr = unevaluated_equality(
            "Matrix([[1,1],[1,0]])**5 == Matrix([[8,5],[5,4]])"
        )
        assert expr is not None
        status, message = recorded_step_verdict(expr)
        assert status == VerificationStatus.FAILED
        assert "[[0, 0], [0, -1]]" in message


# --------------------------------------------------------------------------- G7


class TestG7WrappedUnevaluatedIntegral:
    WRAPPED = "Integral(sin(7*t/2)/sin(t/2), (t, 0, pi))/2"

    def test_wrapped_unevaluated_integral_is_inconclusive(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "g7-wrapped")
        tools["math"](
            operation="integrate",
            expression="sin((3+1/2)*t)/(2*sin(t/2))",
            variable="t",
            lower=0,
            upper=sp.pi,
            session=True,
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "inconclusive"
        assert "unevaluated" in result["verification_message"]
        assert result["verification_status"] != "verified"

    def test_wrapped_unevaluated_integral_domain_level(self) -> None:
        step = _make_step(
            {"original": "sin((3+1/2)*t)/(2*sin(t/2))"},
            self.WRAPPED,
            sympy_command="integrate(expr, (t, 0, pi))",
        )
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.INCONCLUSIVE
        assert result.status != VerificationStatus.VERIFIED
        assert "unevaluated" in result.message

    def test_closed_form_definite_integral_still_verified(self) -> None:
        # Positive control: a real closed value carries no Integral node and
        # keeps the quadrature-verified green.
        step = _make_step(
            {"original": "x**2"},
            "1/3",
            sympy_command="integrate(expr, (x, 0, 1))",
        )
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED


# --------------------------------------------------------------------------- G8


class TestG8PositiveAssumptionValuePreservation:
    EXPR = (
        "sqrt((F0*(k - m*omega**2)/((k - m*omega**2)**2 + c**2*omega**2))**2"
        " + (F0*c*omega/((k - m*omega**2)**2 + c**2*omega**2))**2)"
    )

    def test_positive_assumption_simplify_is_verified(
        self, fresh_session_manager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "g8-damped-forced")
        for name, unit in (
            ("F0", "kg*m/s^2"),
            ("m", "kg"),
            ("c", "kg/s"),
            ("k", "kg/s^2"),
            ("omega", "1/s"),
        ):
            tools["register_symbol"](name=name, meaning=name, unit=unit)
        tools["assume"](
            variables=[
                "F0 is positive",
                "m is positive",
                "c is positive",
                "k is positive",
                "omega is positive",
            ]
        )
        tools["math"](operation="simplify", expression=self.EXPR, session=True)
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "verified"
        assert "changes expression value" not in result["verification_message"]

    def test_symbolic_zero_under_assumptions_verified_domain_level(self) -> None:
        engine = AssumptionEngine()
        for name in ("F0", "c", "k", "m", "omega"):
            engine.assume(name, "positive")
        step = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="g8 simplify under positivity",
            input_expressions={"original": self.EXPR},
            output_expression="F0/sqrt(c**2*omega**2 + (k - m*omega**2)**2)",
            output_latex="",
            sympy_command="simplify(expr)",
        )
        result = StepVerifier().verify_step(
            step, prior_expr=None, assumption_engine=engine
        )
        assert result.status == VerificationStatus.VERIFIED, result.message

    def test_genuine_value_change_still_failed(self) -> None:
        # Negative control: a residual that is genuinely nonzero under the very
        # same positivity assumptions must stay FAILED — the symbolic zero proof
        # may only certify an exact zero.
        engine = AssumptionEngine()
        engine.assume("x", "positive")
        engine.assume("y", "positive")
        step = DerivationStep(
            step_number=1,
            operation=OperationType.SIMPLIFY,
            description="g8 genuine value change",
            input_expressions={"original": "sqrt(x**2 + y**2)"},
            output_expression="x",
            output_latex="x",
            sympy_command="simplify(expr)",
        )
        result = StepVerifier().verify_step(
            step, prior_expr=None, assumption_engine=engine
        )
        assert result.status == VerificationStatus.FAILED

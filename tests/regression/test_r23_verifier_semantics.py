"""r23 verifier-semantics fixes (F4-F7), reproduced from the r23 sandbox cards.

F4 suspect_identity false positives (audit: `re(...)` simplify; task-14 step 2
   residual polynomial): the ``A - B`` advisory fired on inputs that were never
   submitted as an identity claim.
F5 step-level assumptions dropped (audit1): a step-recorded ``assumptions=[...]``
   never reached the equation verdict, so a true identity read as disproven.
F6 bare-symbol definition judged failed (audit4[4]): ``tau_c = pi/2`` is a
   definition, not a false identity (r13: axioms must not fail).
F7 matrix equations undecided (task-04 step 28): two concrete matrices were
   compared through the scalar machinery and fell back to inconclusive.
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_session import DerivationStep, OperationType
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.step_verifier import StepVerifier
from symkit.domain.value_objects import VerificationStatus
from symkit_mcp.tools.assumptions import register_assumption_tools
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821


def _tools():
    mcp = MockMCP()
    register_session_tools(mcp)
    register_math_tools(mcp)
    register_assumption_tools(mcp)
    return mcp.tools


def _start(tools, name):
    tools["session_start"](name=name)


def _archived_simplify(text: str, output_text: str) -> DerivationStep:
    """A simplify step as the live recorder archives it (user text + srepr)."""
    parsed, err = parse_expression_string(text, convert_equation=True)
    assert err is None and parsed is not None
    output, err = parse_expression_string(output_text, convert_equation=True)
    assert err is None and output is not None
    return DerivationStep(
        step_number=1,
        operation=OperationType.SIMPLIFY,
        description="archived simplify",
        input_expressions={"original": text},
        output_expression=str(output),
        output_latex=str(output),
        sympy_command="",
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(output),
    )


# --------------------------------------------------------------------------- F4


class TestF4SuspectIdentityFalsePositives:
    def test_re_wrapped_simplify_is_not_suspect(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f4-re")
        tools["math"](
            operation="simplify",
            expression="re((cos(a) + 1j*sin(a))*(cos(b) + 1j*sin(b)))",
            assumptions=["a is real", "b is real"],
            session=True,
        )
        result = tools["session_verify_session"]()
        assert result["suspect_identity_steps"] == []
        assert not any("suspect_identity_steps" in w for w in result.get("warnings", []))

    def test_residual_polynomial_is_not_suspect(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f4-poly")
        tools["math"](
            operation="simplify",
            expression=(
                "-(hbar**2/(2*m))*alpha*(alpha*x**2 - 1)"
                " + m*omega**2*x**2/2 - E"
            ),
            assumptions=[
                "m is positive", "omega is positive", "hbar is positive",
                "alpha is positive", "x is real", "E is real",
            ],
            session=True,
        )
        result = tools["session_verify_session"]()
        assert result["suspect_identity_steps"] == []

    def test_genuine_archived_difference_is_still_suspect(self):
        # `cos(2x) - (1 - 2 sin^2(2x))` is a real A - B claim; the advisory must
        # survive the narrower gate (task-11/task-13 semantics).
        step = _archived_simplify(
            "cos(2*x) - (1 - 2*sin(2*x)**2)", "-8*sin(x)**4 + 6*sin(x)**2"
        )
        result = StepVerifier().verify_step(step, prior_expr=None)
        assert result.status == VerificationStatus.VERIFIED
        assert result.details.get("suspect_identity") == "unreduced"


# --------------------------------------------------------------------------- F5


class TestF5StepAssumptionsReachVerdict:
    EQUATION = "2*a/z**2 == 2*a*z/(z**2)**(3/2)"

    def test_step_level_assumption_verifies(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f5-assumed")
        tools["session_record_step"](
            expression=self.EQUATION,
            description="axial dipole identity under z>0",
            assumptions=["z is positive"],
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "verified"

    def test_step_without_assumption_is_still_failed(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f5-control")
        tools["session_record_step"](
            expression=self.EQUATION, description="control: no assumption"
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "failed"

    def test_session_level_assumption_still_verifies(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f5-session")
        tools["assume"](variables=["z is positive"])
        tools["session_record_step"](
            expression=self.EQUATION, description="session-level assumption"
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "verified"

    def test_unassumed_abs_identity_is_not_verified(self, fresh_session_manager):
        # Negative control: without z>0, `Abs(z) = z` has no right to verify.
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f5-abs")
        tools["session_record_step"](expression="Abs(z) = z", description="control")
        result = tools["session_verify_step"](1)
        assert result["verification_status"] != "verified"


# --------------------------------------------------------------------------- F6


class TestF6BareSymbolDefinition:
    def test_bare_symbol_definition_is_inconclusive(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f6-def")
        tools["session_record_step"](
            expression="tau_c = pi/2", description="definition of critical delay"
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "inconclusive"
        assert "definition recorded" in result["verification_message"]

    def test_expression_lhs_false_equation_still_failed(self, fresh_session_manager):
        # Guard: the exemption is scoped to a lone-symbol LHS; a compound LHS
        # keeps the full (disproving) identity check.
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f6-guard")
        tools["session_record_step"](
            expression="x - y = 0", description="false identity"
        )
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "failed"


# --------------------------------------------------------------------------- F7


class TestF7MatrixEquations:
    FALSE_EQ = "Matrix([[1,1],[1,0]])**5 = Matrix([[8,5],[5,4]])"
    TRUE_EQ = "Matrix([[1,1],[1,0]])**5 = Matrix([[8,5],[5,3]])"

    def test_false_matrix_equation_fails_math_path(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f7-math-false")
        tools["math"](operation="simplify", expression=self.FALSE_EQ, session=True)
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "failed"
        assert "[[0, 0], [0, -1]]" in result["verification_message"]

    def test_true_matrix_identity_verifies_math_path(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f7-math-true")
        tools["math"](operation="simplify", expression=self.TRUE_EQ, session=True)
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "verified"

    def test_false_matrix_equation_fails_recorded_path(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f7-record-false")
        tools["session_record_step"](expression=self.FALSE_EQ, description="matrix")
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "failed"
        assert "[[0, 0], [0, -1]]" in result["verification_message"]

    def test_true_matrix_identity_verifies_recorded_path(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        _start(tools, "f7-record-true")
        tools["session_record_step"](expression=self.TRUE_EQ, description="matrix")
        result = tools["session_verify_step"](1)
        assert result["verification_status"] == "verified"

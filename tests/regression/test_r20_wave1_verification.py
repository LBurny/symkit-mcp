"""r20 Wave 1: verification-integrity regressions (crash guard, claim burial, audit read).

Three shipped defects, reproduced black-box on the r20 sandbox cards:

* D1 (P0 crash) a non-``Basic`` archived expression reached the dimensional
  post-check and ``session_verify_session`` died with ``AttributeError: 'dict'
  object has no attribute 'free_symbols'``.  A multi-variable ``solve`` archives a
  Python ``dict`` (``{Symbol('a'): Integer(6), ...}``) and a comma equation list
  parses to a ``tuple``; both flowed through ``safe_load_expression`` / the
  verifier's ``_parse`` unguarded.
* D2 (P1) ``math("simplify", "legendre(3, u) = 3*u**2/2 - 1/2")`` archived the
  step as ``verified`` while ``details.equation_identity.verdict`` read
  ``FALSE``: the asserted equation was never judged because ``simplify`` did not
  collapse it to a boolean.  An explicit equation the operator was given is a
  claim and must be judged on its own difference.
* D3 (P2) an adversarial/audit session whose only failed steps are hand-recorded
  assertions reads as overall ``failed`` with no disclosure that this is in fact
  a successful refutation.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from symkit.domain.derivation_session import (
    DerivationStep,
    OperationType,
    SessionManager,
)
from symkit.domain.dimensional_analysis import (
    _DimensionChecker,
    check_expression_dimensions,
)
from symkit.domain.expr_io import safe_load_expression
from symkit.domain.expression_parser import parse_expression_string
from symkit.domain.step_verifier import (
    StepVerifier,
    verification_result_to_json,
)
from symkit.domain.value_objects import (
    VerificationResult,
    VerificationStatus,
)
from symkit_mcp.tools import _state as state
from symkit_mcp.tools._session_views import verification_summary
from symkit_mcp.tools._unit_context import apply_dimension_to_step
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP / fresh_session_manager are provided by conftest.py
# ruff: noqa: F821

FALSE_CLAIM = "legendre(3, u) = 3*u**2/2 - 1/2"  # FALSE: LHS is P_3, RHS is P_2
TRUE_CLAIM = "legendre(2, u) = 3*u**2/2 - 1/2"
_DICT_SREPR = "{Symbol('a'): Integer(6), Symbol('b'): Integer(6), Symbol('d'): Integer(3)}"


def _tools() -> dict[str, Any]:
    mcp = MockMCP()  # noqa: F821
    register_math_tools(mcp)
    register_session_tools(mcp)
    return mcp.tools


def _archived(
    operation: OperationType,
    input_expression: str,
    output: sp.Basic,
    key: str = "original",
) -> DerivationStep:
    """A live-recorder-shaped archived step, input recorded under ``key``."""
    parsed, _ = parse_expression_string(input_expression, convert_equation=True)
    assert parsed is not None
    output_str = str(output)
    return DerivationStep(
        step_number=1,
        operation=operation,
        description="r20 wave1",
        input_expressions={key: input_expression},
        output_expression=output_str,
        output_latex=output_str,
        sympy_command="simplify(expr)",
        input_srepr=sp.srepr(parsed),
        output_srepr=sp.srepr(output),
    )


# ---- D1: non-Basic archived expressions must never reach the checker --------


class TestNonBasicArchivedExpressions:
    """A dict/tuple archive must load as ``None``, never as a container."""

    def test_safe_load_rejects_dict(self) -> None:
        assert safe_load_expression("{a: 6}", _DICT_SREPR) is None

    def test_safe_load_rejects_comma_tuple(self) -> None:
        assert safe_load_expression("a - 6, b - 6", "") is None

    def test_verifier_parse_rejects_non_basic(self) -> None:
        assert StepVerifier()._parse("{a: 6, b: 6}") is None

    def test_dimension_of_non_basic_is_unsupported(self) -> None:
        checker = _DimensionChecker({"a": "kg"})
        assert checker.dimension_of({"a": 1}) is None  # type: ignore[arg-type]
        assert checker.indeterminate is True
        assert "unsupported" in checker.indeterminate_reasons

    def test_check_expression_dimensions_non_basic_is_indeterminate(self) -> None:
        report = check_expression_dimensions({"a": 1}, {"a": "kg"})  # type: ignore[arg-type]
        assert report.consistent is None
        assert report.issues == []
        assert "unsupported" in report.indeterminate_reasons

    def test_apply_dimension_to_step_skips_non_basic_output(self, fresh_session_manager: SessionManager) -> None:
        session = fresh_session_manager.create("r20-nonbasic")
        step = DerivationStep(
            step_number=1,
            operation=OperationType.SOLVE,
            description="system solve",
            input_expressions={"operation": "solve", "equation": "a - 6, b - 6, d - 3"},
            output_expression="{a: 6, b: 6, d: 3}",
            output_latex="{a: 6, b: 6, d: 3}",
            sympy_command="solve(expr, a)",
            output_srepr=_DICT_SREPR,
        )
        step.verification_result = verification_result_to_json(
            VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Solver output is not an equality",
            )
        )
        session.steps.append(step)
        assert apply_dimension_to_step(session, 1, {"a": "kg"}) is None

    def test_verification_summary_survives_non_basic_solve_output(
        self, fresh_session_manager: SessionManager
    ) -> None:
        session = fresh_session_manager.create("r20-crash")
        solve = DerivationStep(
            step_number=1,
            operation=OperationType.SOLVE,
            description="system solve",
            input_expressions={"operation": "solve", "equation": "a - 6, b - 6, d - 3"},
            output_expression="{a: 6, b: 6, d: 3}",
            output_latex="{a: 6, b: 6, d: 3}",
            sympy_command="solve(expr, a)",
            output_srepr=_DICT_SREPR,
        )
        solve.verification_result = verification_result_to_json(
            VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                message="Solver output is not an equality",
            )
        )
        session.steps.append(solve)
        dim = DerivationStep(
            step_number=2,
            operation=OperationType.CUSTOM,
            description="recorded dimension check",
            input_expressions={"operation": "dimension", "consistent": "True"},
            output_expression="",
            output_latex="",
            sympy_command="dimension(expr)",
        )
        dim.verification_result = verification_result_to_json(
            VerificationResult(status=VerificationStatus.VERIFIED, message="ok")
        )
        session.steps.append(dim)

        summary = verification_summary(session)
        assert summary["failed"] == 0
        assert summary["inconclusive_steps"] == [1]
        assert summary["failed_steps"] == []


# ---- D2: a non-collapsed asserted equation is still a claim ----------------


class TestAssertedEquationClaim:
    """A false asserted equation must never read as a top-level VERIFIED step."""

    def test_false_equation_non_collapsed_fails(self) -> None:
        u = sp.Symbol("u")
        output = sp.Eq(-5 * u**3 + 3 * u**2 + 3 * u, 1)
        result = StepVerifier().verify_step(
            _archived(OperationType.SIMPLIFY, FALSE_CLAIM, output)
        )
        assert result.status == VerificationStatus.FAILED
        assert result.details.get("suspect_identity") == "numeric"
        assert "FALSE" in result.message

    def test_true_equation_non_collapsed_verifies(self) -> None:
        # legendre(2, u) simplifies to the claimed rhs, so the claim holds.
        result = StepVerifier().verify_step(
            _archived(OperationType.SIMPLIFY, TRUE_CLAIM, sp.true)
        )
        assert result.status == VerificationStatus.VERIFIED
        assert "asserted equation holds" in result.message

    def test_expand_true_equation_verifies(self) -> None:
        result = StepVerifier().verify_step(
            _archived(OperationType.EXPAND, "Eq((x - 1)*(x + 1), x**2 - 1)", sp.true)
        )
        assert result.status == VerificationStatus.VERIFIED

    def test_expand_false_equation_fails(self) -> None:
        x = sp.Symbol("x")
        output = sp.Eq(x**2 - 2 * x + 1, x**2 - 1)
        result = StepVerifier().verify_step(
            _archived(OperationType.EXPAND, "Eq((x - 1)**2, x**2 - 1)", output)
        )
        assert result.status == VerificationStatus.FAILED

    def test_non_equation_input_keeps_operator_fidelity(self) -> None:
        t = sp.Symbol("t")
        output = sp.simplify(sp.exp(-t) - sp.cos(t))
        result = StepVerifier().verify_step(
            _archived(OperationType.SIMPLIFY, "exp(-t) - cos(t)", output)
        )
        assert result.status == VerificationStatus.VERIFIED
        assert "output matches the recomputed operator result" in result.message

    def test_verified_never_coexists_with_false_equation_identity(self) -> None:
        u = sp.Symbol("u")
        x = sp.Symbol("x")
        cases = [
            _archived(
                OperationType.SIMPLIFY,
                FALSE_CLAIM,
                sp.Eq(-5 * u**3 + 3 * u**2 + 3 * u, 1),
            ),
            _archived(
                OperationType.EXPAND,
                "Eq((x - 1)**2, x**2 - 1)",
                sp.Eq(x**2 - 2 * x + 1, x**2 - 1),
            ),
        ]
        for step in cases:
            result = StepVerifier().verify_step(step)
            identity = result.details.get("equation_identity") or {}
            if identity.get("verdict") == "FALSE":
                assert result.status != VerificationStatus.VERIFIED, result.message

    def test_math_simplify_false_equation_chain_fails(
        self, fresh_session_manager: SessionManager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("r20-false-claim")
        tools["math"](operation="simplify", expression=FALSE_CLAIM, session=True)
        step = tools["session_verify_step"](1)
        assert step["verification_status"] == "failed"
        summary = tools["session_verify_session"]()
        assert summary["overall"] == "failed"
        assert summary["failed_steps"] == [1]

    def test_session_record_step_false_equation_fails(
        self, fresh_session_manager: SessionManager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("r20-recorded-false")
        recorded = tools["session_record_step"](
            expression=FALSE_CLAIM, description="recorded false assertion"
        )
        verify = tools["session_verify_step"](recorded["step_number"])
        assert verify["verification_status"] == "failed"


# ---- D3: an all-recorded-assertions "failed" chain is disclosed -------------


class TestAuditSessionReadability:
    """A refutation/audit that ends "failed" must say why it reads that way."""

    WARNING = (
        "failed steps are recorded assertions judged false — a successful "
        "refutation/audit reads as overall 'failed'"
    )

    def test_warns_when_all_failed_steps_are_recorded_assertions(
        self, fresh_session_manager: SessionManager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("r20-audit")
        tools["session_record_step"](
            expression=FALSE_CLAIM, description="refuted claim"
        )
        summary = tools["session_verify_session"]()
        assert summary["failed"] == 1
        assert self.WARNING in summary.get("warnings", [])

    def test_no_warning_when_failed_step_is_not_a_recorded_assertion(
        self, fresh_session_manager: SessionManager
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("r20-mixed")
        tools["math"](operation="simplify", expression="x + x")
        session = state.get_session()
        assert session is not None
        session.steps[-1].output_expression = "3*x"
        session.steps[-1].output_srepr = sp.srepr(3 * sp.Symbol("x"))
        tools["session_verify_step"](1)
        summary = tools["session_verify_session"]()
        assert summary["failed"] == 1
        assert self.WARNING not in summary.get("warnings", [])

"""D7: content sensitivity for manually recorded equality steps.

``session_record_step`` used to classify every hand-recorded step as
``CUSTOM`` and the verifier returned ``inconclusive`` without ever looking at
the expression, so a wrong coefficient (``(x+y)**3 = ...``) or a classic
pseudo-identity (``(a+b)**2 = a**2 + b**2``) could never be caught.  A
recorded ``Eq(a, b)`` is now content-checked: ``a - b`` simplifying to zero
verifies the identity, a nonzero numeric difference fails it, and a symbolic
difference stays inconclusive (a model equation/definition is an axiom, not a
derived identity).  Non-equation manual steps keep their old verdict.
"""

from __future__ import annotations

import json
from typing import Any

import sympy as sp

from symkit.domain.derivation_session import (
    DerivationSession,
    DerivationStep,
    OperationType,
)
from symkit.domain.final_result import recorded_step_verdict
from symkit.domain.value_objects import VerificationStatus


def _record(session: DerivationSession, text: str, description: str = "hand") -> DerivationStep:
    from symkit.domain.expression_parser import parse_user_expression

    expr, err = parse_user_expression(text)
    assert err is None and expr is not None
    prior = session.current_expression
    session.current_expression = expr
    return session._add_step(  # noqa: SLF001 - mirrors session_record_step
        operation=OperationType.CUSTOM,
        description=description,
        input_expressions={"original": text},
        output_expr=expr,
        sympy_command="manual_record",
        prior_expr=prior,
    )


def _payload(step: DerivationStep) -> dict[str, Any]:
    return json.loads(step.verification_result)


def _session() -> DerivationSession:
    return DerivationSession(session_id="d7", name="d7")


class TestCustomEqualityContent:
    def test_correct_manual_identity_is_verified(self) -> None:
        session = _session()
        step = _record(session, "(a+b)**2 = a**2 + 2*a*b + b**2")
        assert _payload(step)["status"] == "verified"
        assert "Identity verified" in _payload(step)["message"]

    def test_false_manual_identity_is_failed_with_difference(self) -> None:
        # (a+b)^2 = a^2 + b^2 is disproven by rational substitution (2*a*b is
        # nonzero), so a recorded equation is FAILED, not merely inconclusive
        # (task-17: buried coefficient errors must be caught, not shrugged off).
        session = _session()
        step = _record(session, "(a+b)**2 = a**2 + b**2")
        payload = _payload(step)
        assert payload["status"] == "failed"
        assert "2*a*b" in payload["message"]
        assert "not an identity" in payload["message"]

    def test_true_trig_identity_survives_plain_simplify(self) -> None:
        # task-17 step 15: plain simplify does not expand cos(6*x), so the true
        # identity used to be reported as "not an identity".  The trig fallback
        # must verify it.
        session = _session()
        step = _record(
            session,
            "cos(6*x) = 32*cos(x)**6 - 48*cos(x)**4 + 18*cos(x)**2 - 1",
        )
        payload = _payload(step)
        assert payload["status"] == "verified"
        assert "Identity verified" in payload["message"]

    def test_unproven_manual_equation_stays_inconclusive(self) -> None:
        # A model equation naming an undefined function cannot be sampled
        # (f(2) stays inert), so it stays inconclusive — unproven, not disproven.
        session = _session()
        step = _record(session, "f(x) = cos(x)")
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert "unproven, not disproven" in payload["message"]
        assert "not an identity" not in payload["message"]

    def test_numeric_contradiction_is_failed(self) -> None:
        session = _session()
        step = _record(session, "1 = 2")
        assert _payload(step)["status"] == "failed"
        assert "false" in _payload(step)["message"].lower()

    def test_non_equation_custom_step_keeps_old_verdict(self) -> None:
        session = _session()
        step = _record(session, "x**2 + 1")
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert payload["message"] == "Custom step: no automatic verification available"

    def test_identity_under_session_assumptions_is_verified(self) -> None:
        # sqrt(x**2) = x only holds for non-negative x; the session assumption
        # must reach the identity check through the shared binding path.
        session = _session()
        session.assumption_engine.assume("x", "positive")
        step = _record(session, "sqrt(x**2) = x")
        assert _payload(step)["status"] == "verified"


class TestDefinitionShapedEquations:
    """A bare-name LHS absent from the RHS reads as a definition (field B1).

    ``E_t == e_t + u_t_i**2/2 + k_t`` is a naming convention, not a claim about
    shared symbols; the identity check measured the name against its own
    expansion and called the definition "disproven".  A definition is true by
    fiat, so the verdict must stay inconclusive — the sides still differ, but a
    falsification claim answers the wrong question.  A compound LHS keeps the
    full identity check (D7).
    """

    def test_definition_is_inconclusive_not_disproven(self) -> None:
        session = _session()
        step = _record(session, "E_t == e_t + u_t_i**2/2 + k_t")
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert "definition" in payload["message"]
        assert "disproven" not in payload["message"]

    def test_averaged_equation_of_state_is_inconclusive(self) -> None:
        session = _session()
        step = _record(session, "p_b == rho_b*R_gas*T_t")
        assert _payload(step)["status"] == "inconclusive"

    def test_definition_message_still_discloses_the_difference(self) -> None:
        session = _session()
        step = _record(session, "E_t == e_t + u_t_i**2/2 + k_t")
        assert "u_t_i**2/2" in _payload(step)["message"]

    def test_lhs_occurring_on_rhs_stays_fully_checked(self) -> None:
        # x - y = 0 claims an identity between two shared symbols; the check
        # must not read it as a definition.
        session = _session()
        step = _record(session, "x - y = 0")
        payload = _payload(step)
        assert payload["status"] == "failed"

    def test_compound_lhs_definition_is_inconclusive(self) -> None:
        # task-07: rho_b*u_t_i == rho_b*u_b_i + m_i is a Favre decomposition
        # introducing the new unknown m_i.  A compound LHS is still a
        # definitional closure when the RHS names symbols absent from the LHS.
        session = _session()
        step = _record(session, "rho_b*u_t_i == rho_b*u_b_i + m_i")
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert "definition" in payload["message"]
        assert "disproven" not in payload["message"]

    def test_compound_lhs_message_names_introduced_symbols(self) -> None:
        session = _session()
        step = _record(session, "rho_b*u_t_i == rho_b*u_b_i + m_i")
        message = _payload(step)["message"]
        assert "m_i" in message
        assert "u_b_i" in message
        assert "share" in message and "symbols" in message
        assert "u_t_i" in message  # difference still disclosed

    def test_rhs_introducing_nothing_new_stays_disproven(self) -> None:
        # guard: both sides describe the same symbols, so the check is real.
        session = _session()
        step = _record(session, "(a+b)**2 = a**2 + b**2")
        assert _payload(step)["status"] == "failed"


class TestUnevaluatedApplications:
    """An unevaluated application has no free symbols but is not a constant.

    Recording the boundary condition ``f(0) == 0`` was judged FAILED ("the
    sides differ by f(0)"): ``f(0)`` carries no free symbols, so the constant
    branch treated it as a numeric value.  An unevaluated function application,
    integral, derivative or sum is not a checkable constant.
    """

    def test_boundary_condition_is_inconclusive(self) -> None:
        session = _session()
        step = _record(session, "f(0) == 0")
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert "unevaluated" in payload["message"]
        assert "f(0)" in payload["message"]

    def test_boundary_condition_against_constant_is_inconclusive(self) -> None:
        session = _session()
        step = _record(session, "g(0) == 1")
        assert _payload(step)["status"] == "inconclusive"

    def test_constant_contradiction_stays_failed(self) -> None:
        # guard: a genuinely constant difference keeps the numeric-FAILED branch.
        status, message = recorded_step_verdict(sp.Eq(5, 7, evaluate=False))
        assert status == VerificationStatus.FAILED
        assert "false" in message.lower()


class TestDerivativeEquationVacuity:
    """doit() collapses derivatives on plain symbols to 0 (field B2).

    Both sides of a recorded PDE collapsed to zero, so any two derivative
    equations verified as "both sides are equal" — a vacuous green for
    structural records.  A derivative identity whose evaluation produces real
    content (``d(x**2)/dx = 2*x``) must still verify.
    """

    def test_derivative_pde_is_not_verified(self) -> None:
        session = _session()
        step = _record(
            session,
            "Eq(Derivative(rho_b*u_t_i,t)+Derivative(rho_b*u_t_i*u_t_j,x_j),"
            " -Derivative(p_b,x_i)+Derivative(tau_b_ij-rho_b*R_ij,x_j))",
        )
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert "vacuous" in payload["message"]

    def test_derivative_rhs_zero_is_not_verified(self) -> None:
        session = _session()
        step = _record(session, "Eq(Derivative(rho_b,t) + Derivative(rho_b*u_t_j,x_j), 0)")
        assert _payload(step)["status"] == "inconclusive"

    def test_meaningful_derivative_identity_still_verifies(self) -> None:
        session = _session()
        step = _record(session, "Derivative(x**2, x) = 2*x")
        payload = _payload(step)
        assert payload["status"] == "verified"
        assert "Identity verified" in payload["message"]


class TestEquationIdentityDetails:
    def _simplify_step(self, session: DerivationSession, text: str) -> DerivationStep:
        from symkit.domain.expression_parser import parse_user_expression

        expr, err = parse_user_expression(text)
        assert err is None and expr is not None
        return session._add_step(  # noqa: SLF001
            operation=OperationType.SIMPLIFY,
            description="simplify equation",
            input_expressions={"original": text},
            output_expr=expr,
            sympy_command="simplify(expr)",
        )

    def test_true_equation_reports_identity_details(self) -> None:
        session = _session()
        step = self._simplify_step(session, "(a+b)**2 == a**2 + 2*a*b + b**2")
        payload = _payload(step)
        assert payload["status"] == "verified"  # operation fidelity unchanged
        identity = payload["details"]["equation_identity"]
        assert identity["is_identity"] is True
        assert identity["difference"] == "0"

    def test_false_equation_reports_non_identity_details_without_failing(self) -> None:
        session = _session()
        step = self._simplify_step(session, "(a+b)**2 == a**2 + b**2")
        payload = _payload(step)
        # A simplify/expand/factor step is judged on value preservation only;
        # the identity hint is informational and must not change the status.
        assert payload["status"] == "verified"
        identity = payload["details"]["equation_identity"]
        assert identity["is_identity"] is False
        assert "2*a*b" in identity["difference"]

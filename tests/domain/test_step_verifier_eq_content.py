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

from symkit.domain.derivation_session import (
    DerivationSession,
    DerivationStep,
    OperationType,
)


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

    def test_false_manual_identity_is_inconclusive_with_difference(self) -> None:
        session = _session()
        step = _record(session, "(a+b)**2 = a**2 + b**2")
        payload = _payload(step)
        assert payload["status"] == "inconclusive"
        assert "2*a*b" in payload["message"]
        assert "not an identity" in payload["message"]
        assert "notes/limitations" in payload["message"]

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

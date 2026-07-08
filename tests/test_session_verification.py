"""Tests for Phase 3 - DerivationSession automatic verification."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from symkit.domain.derivation_session import (  # noqa: E402
    SessionManager,
    SessionStatus,
    StepStatus,
)


@pytest.fixture
def session():
    manager = SessionManager()
    return manager.create(
        name="test",
        description="test session",
        domain="general",
        auto_persist=False,
    )


class TestSessionAutoVerification:
    def test_load_formula_step_is_verified(self, session):
        result = session.load_formula("x**2 + 3*x")
        assert result["success"] is True
        step = session.steps[0]
        assert step.status == StepStatus.SUCCESS
        assert '"verified"' in step.verification_result

    def test_simplify_step_is_verified(self, session):
        session.load_formula("(x + 1)**2")
        session.simplify()
        step = session.steps[1]
        assert step.status == StepStatus.SUCCESS
        assert "Simplify verified" in step.verification_result

    def test_differentiate_step_is_verified(self, session):
        session.load_formula("x**3")
        session.differentiate("x")
        step = session.steps[1]
        assert step.status == StepStatus.SUCCESS
        assert "reverse integration" in step.verification_result

    def test_substitute_step_is_verified(self, session):
        session.load_formula("x + y")
        session.substitute("x", "z")
        step = session.steps[1]
        assert step.status == StepStatus.SUCCESS
        assert "Substitution verified" in step.verification_result

    def test_solve_step_is_verified(self, session):
        session.load_formula("x - 5")
        session.solve_for("x")
        step = session.steps[1]
        assert step.status == StepStatus.SUCCESS


class TestSessionVerificationSummary:
    def test_verify_derivation_counts(self, session):
        session.load_formula("x**2")
        session.differentiate("x")
        summary = session.verify_derivation()
        assert summary["total"] == 2
        assert summary["verified"] == 2
        assert summary["failed"] == 0
        assert summary["inconclusive"] == 0
        assert summary["overall"] == "verified"

    def test_verify_derivation_after_inconclusive(self, session):
        # 自定义步骤没有自动验证，应标记为 inconclusive
        session.load_formula("x**2")
        session._add_step(
            operation=session.steps[0].operation.CUSTOM,  # noqa: SLF001
            description="manual note",
            input_expressions={"note": "observation"},
            output_expr=session.current_expression,
            sympy_command="# custom",
        )
        summary = session.verify_derivation()
        assert summary["total"] == 2
        assert summary["verified"] == 1
        assert summary["inconclusive"] == 1


class TestSessionCompleteVerification:
    def test_complete_includes_summary(self, session):
        session.load_formula("x**2")
        session.differentiate("x")
        result = session.complete()
        assert result["success"] is True
        assert "verification_summary" in result
        assert result["verification_summary"]["overall"] == "verified"
        assert session.status == SessionStatus.COMPLETED

    def test_complete_with_custom_step_not_verified(self, session):
        session.load_formula("x**2")
        session._add_step(  # noqa: SLF001
            operation=session.steps[0].operation.CUSTOM,
            description="note",
            input_expressions={"note": "observation"},
            output_expr=session.current_expression,
            sympy_command="# custom",
        )
        result = session.complete()
        assert result["verification_summary"]["overall"] == "inconclusive"

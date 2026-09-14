"""Tests for the Lean certification application use case."""

import json

import pytest
import sympy as sp

from symkit.application.lean_certification import certify_session
from symkit.domain.derivation_session import DerivationSession, StepStatus
from symkit.domain.lean_translation import translate_equality
from symkit.domain.lean_types import LeanOutcome, UntranslatableError


class FakeChecker:
    def __init__(self, proven=True):
        self._proven = proven
        self.seen = []

    def check(self, statements):
        self.seen = list(statements)
        return [
            LeanOutcome(s.name, self._proven, "" if self._proven else "unsolved goals")
            for s in statements
        ]


def _session_plain(tmp_path) -> DerivationSession:
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "session_t.json"
    session.load_formula("x + 2*x", formula_id="f1")
    session.simplify()  # SIMPLIFY 步骤；输入输出都在代数片段内（FakeChecker 不依赖具体内容）
    return session


def test_proven_step_embeds_lean_record(tmp_path):
    session = _session_plain(tmp_path)
    report = certify_session(session, FakeChecker(proven=True))
    simplify_step = next(s for s in session.steps if s.operation.value == "simplify")
    record = json.loads(simplify_step.verification_result)
    assert record["details"]["lean"]["status"] == "proven"
    assert record["details"]["lean"]["method"] == "lean_kernel"
    assert record["status"] == "verified"  # 既有判定原样保留
    row = next(
        r for r in report["steps"] if r["step_number"] == simplify_step.step_number
    )
    assert row["certification"] == "proven" and row["lane"] == "ring"
    assert report["summary"]["proven"] == 1


def test_untranslatable_step_reports_reason(tmp_path):
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.load_formula("sin(x) + 2*sin(x)", formula_id="f1")
    session.simplify()
    report = certify_session(session, FakeChecker())
    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "untranslatable" and "sin" in row["reason"]


def test_unproven_never_changes_step_status(tmp_path):
    session = _session_plain(tmp_path)
    before = [s.status for s in session.steps]
    report = certify_session(session, FakeChecker(proven=False))
    assert [s.status for s in session.steps] == before
    assert report["summary"]["unproven"] >= 1


def test_discrepancy_flags_failed_but_proven(tmp_path):
    session = _session_plain(tmp_path)
    step = next(s for s in session.steps if s.operation.value == "simplify")
    step.status = StepStatus.FAILED
    report = certify_session(session, FakeChecker(proven=True))
    assert report["discrepancies"] == [
        {"step_number": step.step_number, "kind": "lean_proven_but_step_failed"}
    ]


def test_results_persisted_to_session_json(tmp_path):
    session = _session_plain(tmp_path)
    certify_session(session, FakeChecker(proven=True))
    data = json.loads((tmp_path / "session_t.json").read_text(encoding="utf-8"))
    step = next(s for s in data["steps"] if s["operation"] == "simplify")
    assert json.loads(step["verification_result"])["details"]["lean"]["status"] == "proven"


def test_session_assumptions_reach_translated_statement(tmp_path):
    """A nonzero assumption registered with `assume` must become a Lean binder."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.assumption_engine.assume("x", "nonzero")
    session.assumption_engine.assume("y", "nonzero")
    session.load_formula("1/x + 1/y", formula_id="f1")
    session.simplify()
    checker = FakeChecker(proven=True)
    report = certify_session(session, checker)

    assert len(checker.seen) == 1
    assert checker.seen[0].hypotheses == ("h_x : x ≠ 0", "h_y : y ≠ 0")
    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "proven"
    assert "h_x : x ≠ 0" in row["statement"]  # report no longer hides the binders


def test_ring_step_does_not_inherit_an_unrelated_nonzero_binder(tmp_path):
    """A pure ring identity is unconditional; a session ``x ≠ 0`` must not leak in."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.assumption_engine.assume("x", "nonzero")
    session.load_formula("x*(x + 1)", formula_id="f1")
    session.simplify()  # ring lane
    checker = FakeChecker(proven=True)
    certify_session(session, checker)

    assert len(checker.seen) == 1
    assert checker.seen[0].lane == "ring"
    assert checker.seen[0].hypotheses == ()


def test_missing_denominator_factors_are_all_listed():
    """``1/(x*(x+1))`` without assumptions names both factors in one reason."""
    x = sp.Symbol("x")
    with pytest.raises(UntranslatableError) as exc:
        translate_equality(1 / (x * (x + 1)), 1 / x - 1 / (x + 1))
    reason = str(exc.value)
    assert "x + 1" in reason and "x" in reason
    assert "nonzero" in reason


class LaneChecker:
    """Unproven for field statements, proven for the cleared ring fallback."""

    def __init__(self):
        self.seen = []

    def check(self, statements):
        self.seen.extend(statements)
        return [
            LeanOutcome(s.name, s.lane == "ring", "" if s.lane == "ring" else "unsolved goals")
            for s in statements
        ]


def test_field_lane_falls_back_to_cleared_ring(tmp_path):
    """An unproven field goal is retried as its denominator-free ring identity."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.assumption_engine.assume("x", "nonzero")
    session.load_formula("1/x", formula_id="f1")
    session.simplify()  # field lane
    checker = LaneChecker()
    report = certify_session(session, checker)

    assert any(s.lane == "field" for s in checker.seen)
    assert any(s.lane == "ring" for s in checker.seen)
    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "proven"
    assert row["lane"] == "field+ring"
    step = next(s for s in session.steps if s.operation.value == "simplify")
    assert json.loads(step.verification_result)["details"]["lean"]["lane"] == "field+ring"

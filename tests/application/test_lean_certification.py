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
    # Non-trivial on purpose: the input and output must differ structurally, or
    # the step is classified `trivial` and never reaches the checker (B1).
    # Reduces to `x`, a ring identity the checker can translate.
    session.load_formula("x*(x + 1) - x**2", formula_id="f1")
    session.simplify()
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


def test_tautology_outranks_untranslatable(tmp_path):
    """A tautological goal is `trivial` even when it leaves the fragment: the
    triviality check runs before translation, so a no-op step such as
    `sin² + cos² = sin² + cos²` is not miscounted as untranslatable either (B1)."""
    from symkit.application.lean_certification import _goal_is_trivial

    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    x = sp.Symbol("x")
    tautology = sp.sin(x) ** 2 + sp.cos(x) ** 2
    assert _goal_is_trivial(tautology, tautology)

    with pytest.raises(UntranslatableError) as exc:
        translate_equality(sp.sin(x) ** 2, sp.Integer(1))
    assert "unsupported construct" in str(exc.value)


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
    session.load_formula("x*(x + 1) - x**2", formula_id="f1")
    session.simplify()  # ring lane, reduces to x (non-trivial)
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


def test_vacuous_field_retry_is_bucketed_trivial(tmp_path):
    """A cleared-denominator retry that is reflexivity must not certify `proven`.

    r18 task-18: the field lane's fallback clears denominators on both sides, and
    because the translator has already normalized the step's input the two
    numerators come out *identical* — the retry goal is ``X = X`` and Lean closes
    it by reflexivity without touching the step's algebra. Counting that as
    `proven` inflated the summary. The retry is now bucketed `trivial`, so it
    never reaches the checker.
    """
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.assumption_engine.assume("x", "nonzero")
    session.load_formula("1/x + 1/x**3", formula_id="f1")
    session.simplify()  # field lane: 1/x + 1/x³ -> (x² + 1)/x³
    checker = LaneChecker()
    report = certify_session(session, checker)

    assert any(s.lane == "field" for s in checker.seen)
    assert not any(s.lane == "ring" for s in checker.seen), "the vacuous retry must not be sent"
    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "trivial"
    assert "reflexivity" in (row["reason"] or "")
    step = next(s for s in session.steps if s.operation.value == "simplify")
    lean = json.loads(step.verification_result)["details"]["lean"]
    assert lean["lane"] == "field", "only the primary attempt belongs in the record"


# --- round-17 B1: trivial goals certify nothing and must not inflate `proven` ---


def _trivial_session(tmp_path) -> DerivationSession:
    """One step whose input and output are identical (``x*(x+1)`` is not
    rewritten by SymPy, so the simplify step is a tautological ``X = X``)."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.load_formula("x*(x + 1)", formula_id="f1")
    session.simplify()
    return session


def test_identical_sides_are_trivial_and_never_reach_lean(tmp_path):
    session = _trivial_session(tmp_path)
    checker = FakeChecker(proven=True)
    report = certify_session(session, checker)

    assert checker.seen == []  # a tautology is never sent to the kernel
    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "trivial"
    assert "identical" in row["reason"]
    assert report["summary"]["proven"] == 0
    assert report["summary"]["trivial"] == 1


def test_trivial_step_gets_no_lean_record(tmp_path):
    session = _trivial_session(tmp_path)
    certify_session(session, FakeChecker(proven=True))
    step = next(s for s in session.steps if s.operation.value == "simplify")
    record = json.loads(step.verification_result) if step.verification_result else {}
    assert "lean" not in record.get("details", {})


# --- round-17 C1: certify-time assumptions close the missing-denominator gap ---


def test_certify_time_assumptions_reach_the_statement(tmp_path):
    """A denominator assumption supplied at certify time must become a binder,
    so a missing `nonzero` no longer forces a session re-run."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.load_formula("1/x + 1/x**3", formula_id="f1")
    session.simplify()  # field lane; x has no session assumption
    checker = FakeChecker(proven=True)
    report = certify_session(session, checker, assumptions={"x": {"nonzero": True}})

    assert len(checker.seen) == 1
    assert checker.seen[0].hypotheses == ("h_x : x ≠ 0",)
    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "proven"


def test_missing_denominator_without_assumptions_stays_untranslatable(tmp_path):
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.load_formula("1/x + 1/x**3", formula_id="f1")
    session.simplify()
    report = certify_session(session, FakeChecker(proven=True))

    row = next(r for r in report["steps"] if r["operation"] == "simplify")
    assert row["certification"] == "untranslatable"
    assert "nonzero" in row["reason"]


def test_skipped_step_names_its_reason(tmp_path):
    """A skipped step must say why it is outside the certified fragment; a bare
    `skipped` with reason null read as an unexplained gap (round-lean task-01)."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    session.load_formula("x + 2*x", formula_id="f1")
    session.differentiate("x")  # not in ELIGIBLE_OPERATIONS
    report = certify_session(session, FakeChecker(proven=True))

    row = next(r for r in report["steps"] if r["operation"] == "differentiate")
    assert row["certification"] == "skipped"
    assert "differentiate" in row["reason"]
    assert "simplify" in row["reason"]

"""Tests for the standalone Lean oracle QA script."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import scripts.lean_oracle as lean_oracle

from symkit.domain.derivation_session import DerivationSession, StepStatus
from symkit.domain.lean_types import LeanOutcome, LeanStatement
from symkit.infrastructure.lean_toolchain import LeanStatus


class _AllProvenChecker:
    """Stand-in for LeanBatchChecker that proves every statement it sees."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.seen: list[LeanStatement] = []

    def check(self, statements: Sequence[LeanStatement]) -> list[LeanOutcome]:
        self.seen = list(statements)
        return [LeanOutcome(s.name, True) for s in statements]


def _write_failed_session(tmp_path: Path) -> Path:
    """Persist a real session whose SIMPLIFY step has been marked FAILED."""
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session.load_formula("x*(x + 2)", formula_id="f1")
    session.simplify()
    path = tmp_path / "session_t.json"
    session._persist_path = path
    session.save()
    step = next(s for s in session.steps if s.operation.value == "simplify")
    step.status = StepStatus.FAILED
    session.save()
    return path


def test_oracle_flags_false_negative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_failed_session(tmp_path)
    monkeypatch.setattr(
        lean_oracle,
        "detect_status",
        lambda: LeanStatus(True, "", lake_path="lake", workspace=str(tmp_path)),
    )
    monkeypatch.setattr(lean_oracle, "LeanBatchChecker", _AllProvenChecker)

    exit_code = lean_oracle.main([str(tmp_path)])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "session_t.json: step 2: lean_proven_but_step_failed" in out
    assert "oracle done: 1 discrepancy(ies)" in out


def test_oracle_unavailable_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        lean_oracle, "detect_status", lambda: LeanStatus(False, "no lake")
    )

    assert lean_oracle.main([str(tmp_path)]) == 2

    out = capsys.readouterr().out
    assert "no lake" in out
    assert "symkit-lean-setup" in out

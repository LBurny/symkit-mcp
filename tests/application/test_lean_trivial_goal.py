"""r18 C1: a tautological Lean goal must not be counted `proven`.

A ``together`` step such as ``(a/b) + (c/d)`` has structurally different input
and output, so the existing "input and output are identical" rule does not fire.
But after the field-to-ring fallback clears denominators both sides become the
same polynomial, so the kernel goal is ``X = X`` and ``ring`` proves it without
using the step's algebra.  It must be bucketed ``trivial``.

The real-kernel triple is gated on a ready Lean toolchain (see
``tests/infrastructure/test_lean_real.py`` for the same convention).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import sympy as sp

from symkit.application.lean_certification import (
    _statement_is_tautology,
    certify_session,
)
from symkit.domain.derivation_session import DerivationSession, OperationType
from symkit.domain.lean_types import LeanOutcome, LeanStatement
from symkit.infrastructure.lean_toolchain import detect_status

# ---------------------------------------------------------------------------
# Deterministic lane-aware checker: mimics the real kernel on these goals
# (the field tactic leaves the together step unsolved; ring closes the rest).
# ---------------------------------------------------------------------------


class _FieldUnprovenChecker:
    def __init__(self) -> None:
        self.seen: list[LeanStatement] = []

    def check(self, statements: Sequence[LeanStatement]) -> list[LeanOutcome]:
        self.seen = list(statements)
        return [
            LeanOutcome(s.name, s.lane == "ring", "" if s.lane == "ring" else "unsolved goals")
            for s in statements
        ]


def _session(tmp_path: Path, formula: str, *, assumes: Sequence[str] = ()) -> DerivationSession:
    session = DerivationSession(session_id="", name="t", auto_verify=True)
    session._persist_path = tmp_path / "s.json"
    for clause in assumes:
        symbol, prop = clause.split()
        session.assumption_engine.assume(symbol, prop)
    session.load_formula(formula, formula_id="f1")
    return session


def _together_step(session: DerivationSession) -> None:
    original = session.current_expression
    session._add_step(
        operation=OperationType.SIMPLIFY,
        description="together",
        input_expressions={"original": str(original)},
        output_expr=sp.together(original),
        sympy_command="together(expr)",
        prior_expr=original,
    )


def _only_math_row(report: dict[str, Any]) -> dict[str, Any]:
    return next(r for r in report["steps"] if r["operation"] == "simplify")


# ---------------------------------------------------------------------------
# The triple: tautological together -> trivial; ring identity -> proven;
# identical input/output -> trivial.
# ---------------------------------------------------------------------------


def test_together_tautology_is_trivial_not_proven(tmp_path: Path) -> None:
    session = _session(tmp_path, "a/b + c/d", assumes=("b nonzero", "d nonzero"))
    _together_step(session)
    checker = _FieldUnprovenChecker()
    report = certify_session(session, checker)

    row = _only_math_row(report)
    assert row["certification"] == "trivial"
    assert row["statement"] is None  # no `X = X` goal is shown as a proof
    assert report["summary"]["proven"] == 0
    assert report["summary"]["trivial"] == 1
    # The primary field statement is still sent, but the tautological retry is
    # never handed to the checker as a would-be proof.
    assert all(s.lhs != s.rhs for s in checker.seen)
    assert "certifies no algebra" in row["reason"]


def test_ring_identity_stays_proven_with_a_real_statement(tmp_path: Path) -> None:
    """Control 1: a genuine polynomial identity must remain `proven`."""
    session = _session(tmp_path, "x*(x + 1) - x**2")
    session.simplify()
    report = certify_session(session, _FieldUnprovenChecker())

    row = _only_math_row(report)
    assert row["certification"] == "proven"
    assert row["lane"] == "ring"
    assert row["statement"] and row["statement"].split(" = ")[0] != row["statement"].split(" = ")[1]
    assert report["summary"]["proven"] == 1


def test_identical_input_output_stays_trivial(tmp_path: Path) -> None:
    """Control 2: the pre-existing `X = X` rule is unchanged."""
    session = _session(tmp_path, "x*(x + 1)")
    session.simplify()
    checker = _FieldUnprovenChecker()
    report = certify_session(session, checker)

    assert checker.seen == []
    row = _only_math_row(report)
    assert row["certification"] == "trivial"
    assert "identical" in row["reason"]


def test_statement_tautology_helper() -> None:
    tautology = LeanStatement("s", "ℝ", ("x",), (), "x", "x", "ring")
    real_goal = LeanStatement("s", "ℝ", ("x",), (), "(x + 0)", "x", "ring")
    assert _statement_is_tautology(tautology)
    assert not _statement_is_tautology(real_goal)


# ---------------------------------------------------------------------------
# The same triple against the real Lean kernel (skipped when unavailable).
# ---------------------------------------------------------------------------

_STATUS = detect_status()


@pytest.mark.skipif(not _STATUS.available, reason="Lean toolchain not set up")
def test_real_kernel_tautology_is_trivial_but_real_identities_are_proven(
    tmp_path: Path,
) -> None:
    from symkit.infrastructure.lean_batch import LeanBatchChecker

    checker = LeanBatchChecker(Path(_STATUS.lake_path), Path(_STATUS.workspace), timeout=300)

    together = _session(tmp_path, "a/b + c/d", assumes=("b nonzero", "d nonzero"))
    _together_step(together)
    report = certify_session(together, checker)
    row = _only_math_row(report)
    assert row["certification"] == "trivial", row
    assert report["summary"]["proven"] == 0

    ring = _session(tmp_path, "x*(x + 1) - x**2")
    ring.simplify()
    report = certify_session(ring, checker)
    row = _only_math_row(report)
    assert row["certification"] == "proven" and row["lane"] == "ring", row

    field = _session(tmp_path, "1/x + 1/x**3", assumes=("x nonzero",))
    field.simplify()
    report = certify_session(field, checker)
    row = _only_math_row(report)
    assert row["certification"] == "proven", row
    assert "h_x : x ≠ 0" in (row["statement"] or "")

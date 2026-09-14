"""Real Lean toolchain smoke test; auto-skipped when no toolchain is installed."""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy as sp

from symkit.domain.lean_translation import translate_equality
from symkit.domain.lean_types import LeanStatement
from symkit.infrastructure.lean_batch import LeanBatchChecker
from symkit.infrastructure.lean_toolchain import detect_status

pytestmark = pytest.mark.lean

_status = detect_status()


@pytest.mark.skipif(not _status.available, reason="Lean toolchain not set up")
def test_real_lean_proves_trivial_identity():
    checker = LeanBatchChecker(Path(_status.lake_path), Path(_status.workspace))
    stmt = LeanStatement(
        "smoke", "ℝ", (), (), "((1 : ℝ) + (1 : ℝ))", "(2 : ℝ)", "ring"
    )
    assert checker.check([stmt])[0].proven is True


@pytest.mark.skipif(not _status.available, reason="Lean toolchain not set up")
def test_real_lean_proves_rational_identity_with_session_assumptions():
    x, y = sp.symbols("x y")
    stmt = translate_equality(
        1 / x + 1 / y,
        (x + y) / (x * y),
        assumptions={"x": {"nonzero": True}, "y": {"nonzero": True}},
        name="rational",
    )
    checker = LeanBatchChecker(Path(_status.lake_path), Path(_status.workspace))
    assert checker.check([stmt])[0].proven is True


@pytest.mark.skipif(not _status.available, reason="Lean toolchain not set up")
def test_real_lean_proves_compound_denominator_identity():
    x = sp.Symbol("x")
    stmt = translate_equality(
        1 / (x * (x + 1)),
        1 / x - 1 / (x + 1),
        assumptions={"x": {"nonzero": True}},
        name="compound",
    )
    checker = LeanBatchChecker(Path(_status.lake_path), Path(_status.workspace))
    assert checker.check([stmt])[0].proven is True

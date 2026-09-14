"""Tests for the batch Lean kernel checker (Task 3)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from symkit.domain.lean_types import LeanStatement
from symkit.infrastructure.lean_batch import LeanBatchChecker

_S1 = LeanStatement(
    "symkit_step_001", "ℝ", ("x",), (), "(x + (2 : ℝ) * x)", "((3 : ℝ) * x)", "ring"
)
_S2 = LeanStatement(
    "symkit_step_002", "ℝ", ("x",), ("h_x : x ≠ 0",), "((x + x) / x)", "(2 : ℝ)", "field"
)


def _shim(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_lake.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


def _checker(tmp_path: Path, prefix: list[str]) -> LeanBatchChecker:
    return LeanBatchChecker(Path("unused"), tmp_path, command_prefix=prefix)


def test_all_proven_on_exit_zero(tmp_path):
    prefix = _shim(tmp_path, "import sys; sys.exit(0)\n")
    out = _checker(tmp_path, prefix).check([_S1, _S2])
    assert [o.proven for o in out] == [True, True]
    assert (tmp_path / "SymkitCheck.lean").exists()


def test_error_line_maps_to_owning_statement(tmp_path):
    # an error line inside the second theorem block -> first proven, second unproven
    prefix = _shim(
        tmp_path,
        """
        import sys
        text = open(sys.argv[1], encoding="utf-8").read().splitlines()
        line = next(i for i, l in enumerate(text, 1) if "symkit_step_002" in l)
        print(f"SymkitCheck.lean:{line}:0: error: unsolved goals", file=sys.stderr)
        sys.exit(1)
        """,
    )
    out = _checker(tmp_path, prefix).check([_S1, _S2])
    assert (out[0].proven, out[1].proven) == (True, False)
    assert "unsolved goals" in out[1].detail


def test_timeout_marks_all_unproven(tmp_path):
    prefix = _shim(tmp_path, "import time; time.sleep(5)\n")
    checker = LeanBatchChecker(
        Path("unused"), tmp_path, timeout=0.5, command_prefix=prefix
    )
    out = checker.check([_S1])
    assert out[0].proven is False and "timeout" in out[0].detail


def test_render_file_headers_are_true_physical_lines():
    from symkit.infrastructure.lean_batch import render_file

    text, headers = render_file([_S1, _S2])
    lines = text.splitlines()
    for name, line in headers.items():
        assert lines[line - 1].startswith(f"theorem {name}")


def test_render_file_places_hypotheses_in_the_binder_list():
    from symkit.infrastructure.lean_batch import render_file

    stmt = LeanStatement(
        "with_binders",
        "ℝ",
        ("x",),
        ("h_x : x ≠ 0", "h_x_1 : (x + (1 : ℝ)) ≠ 0"),
        "((1 : ℝ) / x)",
        "((1 : ℝ) / x)",
        "field",
    )
    text, headers = render_file([stmt])
    line = text.splitlines()[headers["with_binders"] - 1]
    assert line == (
        "theorem with_binders (x : ℝ) (h_x : x ≠ 0) "
        "(h_x_1 : (x + (1 : ℝ)) ≠ 0) : ((1 : ℝ) / x) = ((1 : ℝ) / x) := by"
    )


def test_render_file_flat_tactic_block_indentation():
    """A field lane's `ring` must sit at the same level as `field_simp [*]`;
    a deeper indent makes Lean parse it as a new command and leave the goal."""
    from symkit.infrastructure.lean_batch import render_file

    text, _ = render_file([_S2])
    tactic_lines = [ln for ln in text.splitlines() if ln.strip() in {"field_simp [*]", "ring"}]
    assert tactic_lines == ["  field_simp [*]", "  ring"]


def test_unparsed_failure_never_marks_proven(tmp_path):
    # A non-zero exit whose output has no file:line errors (broken workspace,
    # missing imports) must not certify anything.
    prefix = _shim(
        tmp_path,
        "import sys; print('error: package Mathlib not found', file=sys.stderr); "
        "sys.exit(1)\n",
    )
    out = _checker(tmp_path, prefix).check([_S1, _S2])
    assert [o.proven for o in out] == [False, False]
    assert "lean failed" in out[0].detail


def test_header_carries_real_and_complex_instance_imports():
    """The translator binds variables as ℝ (or ℂ for √-1-containing steps), so
    the rendered file must import the base modules that provide their algebra
    instances; otherwise every `ring` goal fails with `OfNat ℝ n` synthesis
    errors (round-13 D13: two verified steps came back `lean_unproven`)."""
    from symkit.infrastructure.lean_batch import _HEADER

    assert "import Mathlib.Data.Real.Basic" in _HEADER

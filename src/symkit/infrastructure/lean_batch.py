"""Batch Lean kernel checker: render statements to one file, run ``lake env lean``.

A batch of :class:`~symkit.domain.lean_types.LeanStatement` objects is rendered
into a single ``SymkitCheck.lean`` in the (hidden) Lean workspace. The theorem
header line of each statement is recorded at render time so that kernel error
lines can be attributed to the owning statement. A Lean error only means the
automation could not discharge the goal; it never implies the step is wrong.
A timeout kills the whole ``lake`` process tree (see
:mod:`symkit.infrastructure.lean_process`) so no orphan keeps the elan lock.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

from symkit.domain.lean_types import LeanOutcome, LeanStatement
from symkit.infrastructure.lean_process import run_with_tree_timeout

_HEADER = (
    # Real.Basic supplies the ℝ algebra instances the translator's `(x : ℝ)`
    # binders rely on; without it every `ring` goal fails instance synthesis
    # (round-13 D13).
    "import Mathlib.Tactic.FieldSimp\n"
    "import Mathlib.Tactic.Ring\n"
    "import Mathlib.Data.Real.Basic\n"
)
_ERROR_RE = re.compile(r"^SymkitCheck\.lean:(\d+):\d+:\s*error:\s*(.*)$", re.MULTILINE)
_CHECK_FILE = "SymkitCheck.lean"


def render_file(statements: Sequence[LeanStatement]) -> tuple[str, dict[str, int]]:
    """Return ``(file_text, {statement_name: 1-based header line})``."""
    lines: list[str] = [*_HEADER.rstrip("\n").split("\n"), ""]
    headers: dict[str, int] = {}
    for stmt in statements:
        parts: list[str] = []
        if stmt.variables:
            parts.append(f"({' '.join(stmt.variables)} : {stmt.target_type})")
        parts.extend(f"({h})" for h in stmt.hypotheses)
        binders = (" " + " ".join(parts)) if parts else ""
        headers[stmt.name] = len(lines) + 1
        lines.append(f"theorem {stmt.name}{binders} : {stmt.lhs} = {stmt.rhs} := by")
        # Normalize indentation: tactic blocks are single-level sequences, so a
        # deeper-indented `ring` after `field_simp [*]` would be read as a new
        # command and the kernel would leave the goal unsolved.
        lines.extend(
            f"  {tactic.strip()}"
            for tactic in stmt.tactic_block.splitlines()
            if tactic.strip()
        )
        lines.append("")
    return "\n".join(lines), headers


def _parse_errors(output: str) -> list[tuple[int, str]]:
    """Extract ``(line, message)`` pairs from Lean's compiler diagnostics."""
    return [(int(m.group(1)), m.group(2).strip()) for m in _ERROR_RE.finditer(output)]


def _outcome_for(
    stmt: LeanStatement, headers: dict[str, int], errors: list[tuple[int, str]]
) -> LeanOutcome:
    """Attribute error lines to the last header at or before them."""
    ordered = sorted(headers.items(), key=lambda kv: kv[1])

    def owner(line: int) -> str:
        name = ""
        for candidate, start in ordered:
            if start <= line:
                name = candidate
        return name

    mine = [msg for line, msg in errors if owner(line) == stmt.name]
    return LeanOutcome(stmt.name, not mine, mine[0] if mine else "")


class LeanBatchChecker:
    """Render a batch of statements and check them with the Lean kernel once."""

    def __init__(
        self,
        lake_path: Path,
        workspace: Path,
        *,
        timeout: float | None = None,
        command_prefix: Sequence[str] | None = None,
    ) -> None:
        self._workspace = workspace
        self._timeout = (
            timeout
            if timeout is not None
            else float(os.environ.get("SYMKIT_LEAN_TIMEOUT", "120"))
        )
        self._prefix = (
            list(command_prefix)
            if command_prefix
            else [str(lake_path), "env", "lean"]
        )

    def check(self, statements: Sequence[LeanStatement]) -> list[LeanOutcome]:
        """Return one outcome per statement; never raises on kernel failure."""
        if not statements:
            return []
        text, headers = render_file(statements)
        (self._workspace / _CHECK_FILE).write_text(text, encoding="utf-8")
        try:
            returncode, stdout, stderr, timed_out = run_with_tree_timeout(
                [*self._prefix, _CHECK_FILE], self._workspace, self._timeout
            )
        except OSError as exc:
            return [LeanOutcome(s.name, False, f"runner error: {exc}") for s in statements]
        if timed_out:
            return [LeanOutcome(s.name, False, "timeout") for s in statements]
        if returncode == 0:
            return [LeanOutcome(s.name, True) for s in statements]
        errors = _parse_errors(stdout + "\n" + stderr)
        if not errors:
            # The run failed outside any theorem (broken workspace, missing
            # imports): nothing was kernel-checked, so nothing may be proven.
            tail = (stderr or stdout).strip().splitlines()
            summary = tail[-1][:200] if tail else f"exit code {returncode}"
            return [LeanOutcome(s.name, False, f"lean failed: {summary}") for s in statements]
        return [_outcome_for(s, headers, errors) for s in statements]

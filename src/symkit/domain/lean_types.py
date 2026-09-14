"""Shared types for the Lean certification lane (domain layer, no infra deps)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class UntranslatableError(ValueError):
    """Raised when an expression leaves the certifiable algebraic fragment."""


@dataclass(frozen=True)
class LeanStatement:
    """One equality claim to be kernel-checked (structured; infra renders text)."""

    name: str
    target_type: str  # "ℝ" | "ℂ"
    variables: tuple[str, ...]
    hypotheses: tuple[str, ...]  # rendered binders, e.g. "h_x : x ≠ 0"
    lhs: str
    rhs: str
    lane: str  # "ring" | "field"

    @property
    def tactic_block(self) -> str:
        return "field_simp [*]\n  ring" if self.lane == "field" else "ring"


@dataclass(frozen=True)
class LeanOutcome:
    name: str
    proven: bool
    detail: str = ""


class LeanChecker(Protocol):
    """Domain-owned interface; infrastructure provides the subprocess backend."""

    def check(self, statements: Sequence[LeanStatement]) -> list[LeanOutcome]: ...

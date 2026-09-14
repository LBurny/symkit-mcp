"""Run the Lean certification lane over persisted sessions and report disagreements
with the heuristic StepVerifier. Exit 1 when any step is Lean-proven but
StepVerifier-failed (a likely verifier false negative).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from symkit.application.lean_certification import certify_session
from symkit.domain.derivation_session import DerivationSession
from symkit.domain.paths import user_sessions_dir
from symkit.infrastructure.lean_batch import LeanBatchChecker
from symkit.infrastructure.lean_toolchain import detect_status

_SETUP_HINT = "run `symkit-lean-setup` once in a terminal to install Lean 4 + Mathlib"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the optional ``sessions_dir`` positional argument."""
    parser = argparse.ArgumentParser(
        prog="lean-oracle",
        description="Cross-audit persisted sessions with the Lean kernel.",
    )
    parser.add_argument(
        "sessions_dir",
        nargs="?",
        default=None,
        help="directory holding session_*.json (default: the user sessions dir)",
    )
    return parser.parse_args(argv)


def _unavailable(status_reason: str) -> int:
    """Print the graceful-degradation notice and return the unavailable code."""
    print(f"Lean certification lane is unavailable: {status_reason}")
    print(_SETUP_HINT)
    return 2


def main(argv: list[str] | None = None) -> int:
    """Run the oracle over a session directory and return the process exit code."""
    args = _parse_args(argv)
    status = detect_status()
    if not status.available:
        return _unavailable(status.reason)
    if not status.lake_path or not status.workspace:
        return _unavailable("toolchain status is incomplete")
    checker = LeanBatchChecker(Path(status.lake_path), Path(status.workspace))
    sessions_dir = (
        Path(args.sessions_dir) if args.sessions_dir else user_sessions_dir()
    )
    false_negatives = 0
    total = 0
    for path in sorted(sessions_dir.glob("session_*.json")):
        try:
            session = DerivationSession.load(path)
        except (OSError, ValueError, KeyError):
            continue
        report = certify_session(session, checker)
        for discrepancy in report["discrepancies"]:
            print(
                f"{path.name}: step {discrepancy['step_number']}: "
                f"{discrepancy['kind']}"
            )
            total += 1
            if discrepancy["kind"] == "lean_proven_but_step_failed":
                false_negatives += 1
    print(f"oracle done: {total} discrepancy(ies)")
    return 1 if false_negatives else 0


if __name__ == "__main__":
    raise SystemExit(main())

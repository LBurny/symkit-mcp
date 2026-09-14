"""Lean kernel certification tool for derivation sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from symkit.application.lean_certification import certify_session
from symkit.infrastructure.lean_batch import LeanBatchChecker
from symkit.infrastructure.lean_toolchain import detect_status
from symkit_mcp.tools._state import get_session


def register_certification_tools(mcp: Any) -> None:
    """Register Lean certification tools."""

    @mcp.tool(
        meta={
            "category": "Verification",
            "example": "session_certify()",
        }
    )
    def session_certify() -> dict[str, Any]:
        """Re-prove eligible algebraic steps of the current session with the Lean 4 kernel.

        Steps from simplify/expand/factor/combine whose expressions stay inside the
        rational-algebra fragment are translated to Lean theorems and checked with
        ring/field_simp. The result is attached to each step's verification record
        under details.lean; existing verification verdicts are never modified.
        Requires a one-time `symkit-lean-setup` to install Lean 4 + Mathlib.

        Returns:
            Certification report: per-step status (proven/unproven/untranslatable/
            skipped), summary counts, and verifier disagreements.
        """
        session = get_session()
        if session is None:
            return {"success": False, "error": "No active session. Use session_start() first."}
        status = detect_status()
        if not status.available or not status.lake_path or not status.workspace:
            return {
                "success": False,
                "lean_available": False,
                "reason": status.reason,
                "setup": (
                    "Run `symkit-lean-setup` once in a terminal — it ships with this "
                    "package (same pip install). It downloads elan + Lean 4 + a "
                    "prebuilt Mathlib cache (one-time, ~1-2 GB, requires network). "
                    "Re-run session_certify() afterwards; lean_available flips to "
                    "true when the toolchain is ready."
                ),
            }
        checker = LeanBatchChecker(Path(status.lake_path), Path(status.workspace))
        report = certify_session(session, checker)
        report["toolchain"] = status.toolchain
        return report

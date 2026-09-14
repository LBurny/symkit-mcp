"""Lean kernel certification tool for derivation sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from symkit.application.lean_certification import certify_session
from symkit.infrastructure.lean_batch import LeanBatchChecker
from symkit.infrastructure.lean_toolchain import (
    describe_environment,
    detect_status,
    setup_command,
)
from symkit_mcp.tools._state import get_session


def _normalize_assumptions(
    raw: Any,
) -> dict[str, dict[str, bool]] | None | Literal[False]:
    """Coerce a caller's assumptions into ``{symbol: {property: True}}``.

    Accepts the engine's own shape (``{"x": {"nonzero": True}}``), a string
    (``"cp nonzero x positive"``) or a list (``["cp", "nonzero"]``). ``None``
    (nothing supplied) and the empty forms all yield an empty mapping; only a
    genuinely malformed shape returns ``False``, which is unambiguous because a
    valid result is always a ``dict``.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        tokens: list[Any] = raw.split()
    elif isinstance(raw, (list, tuple)):
        tokens = list(raw)
    else:
        return False
    if len(tokens) % 2 != 0:
        return False
    parsed: dict[str, dict[str, bool]] = {}
    for index in range(0, len(tokens), 2):
        symbol = str(tokens[index])
        facts = str(tokens[index + 1]).split()
        parsed.setdefault(symbol, {}).update(dict.fromkeys(facts, True))
    return parsed


def register_certification_tools(mcp: Any) -> None:
    """Register Lean certification tools."""

    @mcp.tool(
        meta={
            "category": "Verification",
            "example": "lean_status()",
        }
    )
    def lean_status() -> dict[str, Any]:
        """Check whether the optional Lean 4 kernel backend is ready, without changing anything.

        Read-only and side-effect free: it never runs Lean and never downloads, so
        it is safe to call before deciding whether to certify. Reports the resolved
        toolchain, Mathlib, and workspace paths, where each was resolved from,
        which layer is missing, and the exact command to fix it. Use this instead
        of listing directories or running `lake --version` yourself.

        Returns:
            Environment report: availability, per-layer status (toolchain/Mathlib/
            workspace), `resolved_from` (ELAN_HOME, SYMKIT_DATA_DIR, lake source),
            `missing` layer names, and `next_step` guidance.
        """
        return describe_environment()

    @mcp.tool(
        meta={
            "category": "Verification",
            "example": 'session_certify(assumptions="cp nonzero")',
        }
    )
    def session_certify(
        assumptions: dict[str, dict[str, bool]] | list[str] | str | None = None,
    ) -> dict[str, Any]:
        """Re-prove eligible algebraic-equality steps of the current session with the Lean 4 kernel.

        Steps from simplify/expand/factor/combine/cancel whose expressions stay
        inside the rational-algebra fragment are translated to Lean theorems and
        checked with ring/field_simp. The result is attached to each step's
        verification record under details.lean; existing verification verdicts are
        never modified. Steps whose input and output are identical (x = x, 0 = 0)
        are reported as trivial and excluded from the proven count.
        Requires a one-time `symkit-lean-setup` to install Lean 4 + Mathlib.

        Args:
            assumptions: Extra per-symbol facts to bind as hypotheses, e.g.
                {"cp": {"nonzero": True}} or "cp nonzero x positive". Use this to
                satisfy a denominator-nonzero requirement without re-running the
                derivation; steps that recorded their own assumptions keep them.

        Returns:
            Certification report: per-step status (proven/unproven/trivial/
            untranslatable/skipped), summary counts, and verifier disagreements.
        """
        session = get_session()
        if session is None:
            return {"success": False, "error": "No active session. Use session_start() first."}
        extra = _normalize_assumptions(assumptions)
        if extra is False:
            return {
                "success": False,
                "error": "assumptions must be a mapping, or alternating "
                "symbol/property pairs such as \"cp nonzero x positive\".",
            }
        status = detect_status()
        if not status.available or not status.lake_path or not status.workspace:
            return {
                "success": False,
                "lean_available": False,
                "reason": status.reason,
                "setup": (
                    f"Run the one-time Lean setup once in a terminal: {setup_command()} "
                    "— it ships with this package (same pip install) and downloads "
                    "elan + Lean 4 + a prebuilt Mathlib cache (one-time, ~1-2 GB, "
                    "requires network). Re-run session_certify() afterwards; "
                    "lean_available flips to true when the toolchain is ready."
                ),
                "diagnose": (
                    "Call lean_status() for the resolved paths, the missing layer, "
                    "and the exact next command."
                ),
            }
        checker = LeanBatchChecker(Path(status.lake_path), Path(status.workspace))
        report = certify_session(session, checker, assumptions=extra)
        report["toolchain"] = status.toolchain
        return report

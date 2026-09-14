"""Guards on the ``session_complete`` library write.

2026-09-14 SST round: a 16-step derivation whose trailing steps were residual
self-checks auto-saved ``expression: '0'`` with ``verified: true`` into the
formula library — searchable as a formula whose content is literally ``0`` —
and a chain carrying unreduced differences (``suspect_identity``) received the
same ``verified: true`` label.

Second 2026-09-14 turbine round: preferring "the last symbolic derivation
output" saved verification *probes* (residuals, mid-substitution forms) as the
formula in two out of two sessions. The library write now skips entirely when
the outcome is a bare constant; the operator records the real formula with
``formula_add``.

Display semantics are unchanged: a trailing zero self-check stays the
``final_expression`` headline (r14 task-08). Only the library artifact changes.
"""

from __future__ import annotations

from typing import Any

import yaml

from symkit.infrastructure import derivation_repository as repo_mod
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821

_TRIVIAL_RESIDUAL = (
    "k(x)*Derivative(omega(x), x) + omega(x)*Derivative(k(x), x) "
    "- Derivative(k(x)*omega(x), x)"
)


def _tools() -> dict:
    mcp = MockMCP()
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    return mcp.tools


def _isolate(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    repo_mod._repository = None  # reset global repo singleton


class TestAutoSaveSkipsBareConstant:
    def test_trailing_zero_check_skips_library_write(
        self, fresh_session_manager: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        _isolate(tmp_path, monkeypatch)
        tools = _tools()
        tools["session_start"](name="sst-pollution", domain="fluid_dynamics")
        tools["math"]("simplify", "beta*k*omega + P_k*x", session=True)
        tools["math"]("simplify", _TRIVIAL_RESIDUAL, session=True)

        result = tools["session_complete"](description="probe", auto_save=True)
        assert result["success"] is True, result
        # r14 task-08 display semantics keep the zero headline...
        assert result["final_expression"] == "0"
        # ...and the library write is skipped: the last symbolic output is a
        # verification probe, not the formula. The operator records the real
        # formula with formula_add.
        assert "saved_to" not in result
        assert any(
            "auto_save skipped" in w and "formula_add" in w
            for w in result.get("warnings", [])
        ), result.get("warnings")

    def test_pure_zero_check_session_saves_nothing(
        self, fresh_session_manager: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        _isolate(tmp_path, monkeypatch)
        tools = _tools()
        tools["session_start"](name="zero-only", domain="general")
        tools["session_load_formula"](expression="c*x + t", formula_id="f1")
        tools["math"]("simplify", "c*x + t - (c*x + t)", session=True)

        result = tools["session_complete"](auto_save=True)
        assert result["success"] is True, result
        assert "saved_to" not in result
        assert any(
            "auto_save skipped" in w for w in result.get("warnings", [])
        ), result.get("warnings")


class TestSuspectBlocksVerifiedLabel:
    def test_suspect_step_saves_verified_false(
        self, fresh_session_manager: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        _isolate(tmp_path, monkeypatch)
        tools = _tools()
        tools["session_start"](name="suspect-gate", domain="general")
        tools["math"]("simplify", "a + b", session=True)
        tools["math"]("simplify", "x - (y + 1)", session=True)

        result = tools["session_complete"](auto_save=True)
        assert result["success"] is True, result
        assert any(
            "unreduced" in w for w in result.get("warnings", [])
        ), result.get("warnings")
        with open(result["saved_to"], encoding="utf-8") as f:
            record = yaml.safe_load(f)
        assert record["verified"] is False

    def test_clean_session_keeps_verified_true(
        self, fresh_session_manager: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        _ = fresh_session_manager
        _isolate(tmp_path, monkeypatch)
        tools = _tools()
        tools["session_start"](name="clean-gate", domain="general")
        tools["math"]("simplify", "a + b", session=True)

        result = tools["session_complete"](auto_save=True)
        assert result["success"] is True, result
        with open(result["saved_to"], encoding="utf-8") as f:
            record = yaml.safe_load(f)
        assert record["verified"] is True


class TestTargetWarningScoping:
    """``complete()`` must not warn about a missed target when none was set.

    2026-09-14 turbine round, defect #4: a text-only goal (no target
    expression, no target variables, default ``derive_expression`` form) can
    never match, yet ``complete()`` unconditionally warned "Current expression
    does not match the derivation target" — pure noise for the common
    natural-language-goal flow.
    """

    def test_text_only_goal_has_no_target_warning(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](
            name="text-goal", goal="推导涡轮级的气动热力学方程"
        )
        tools["math"]("simplify", "a + b", session=True)
        result = tools["session_complete"](auto_save=False)
        assert result["success"] is True, result
        warnings = result.get("warnings", [])
        assert not any(
            "does not match the derivation target" in w for w in warnings
        ), warnings

    def test_explicit_target_miss_still_warns(self) -> None:
        from symkit.domain.derivation_goal import DerivationGoal
        from symkit.domain.derivation_session import DerivationSession

        session = DerivationSession(session_id="tgt-warn", name="tgt-warn")
        goal = DerivationGoal.from_text("derive y", domain="general")
        goal.target_expression = "y"
        session.set_goal(goal)
        session.load_formula("a*b", formula_id="f1")
        result = session.complete()
        assert any(
            "does not match the derivation target" in w
            for w in result.get("warnings", [])
        ), result.get("warnings")

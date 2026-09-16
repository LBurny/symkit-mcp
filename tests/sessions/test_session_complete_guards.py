"""Guards on the ``session_complete`` library write and its report fields.

Merged from two micro files on the same completion exit:

- 2026-09-14 SST round: a 16-step derivation whose trailing steps were residual
  self-checks auto-saved ``expression: '0'`` with ``verified: true`` into the
  formula library — searchable as a formula whose content is literally ``0`` —
  and a chain carrying unreduced differences (``suspect_identity``) received the
  same ``verified: true`` label.
- Second 2026-09-14 turbine round: preferring "the last symbolic derivation
  output" saved verification *probes* (residuals, mid-substitution forms) as the
  formula in two out of two sessions. The library write now skips entirely when
  the outcome is a bare constant; the operator records the real formula with
  ``formula_add``.

Display semantics are unchanged: a trailing zero self-check stays the
``final_expression`` headline (r14 task-08). Only the library artifact changes.

Also covers the two other ``session_complete`` report contracts:

- r18 C2: the unreduced-difference warning must not claim an unwritten save —
  with ``auto_save=false`` nothing is written, yet the response once said
  "the formula is saved with verified=false"; only the save claim follows the
  flag, the suspect half is true and stays.
- ``session_show`` and ``session_complete`` must agree on what the derivation
  produced (2026-09-12 pure-formula round: ``complete()`` reported the outcome
  while ``session_show`` kept the raw current expression — different answers to
  the same question in 4 of 5 cards).
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


# r18 C2: the save claim in the suspect warning follows the auto_save flag.
def _suspect_session(tools: dict, name: str) -> None:
    tools["session_start"](name)
    # A genuine two-sided difference whose value is nonzero (2xy), so the step
    # carries details.suspect_identity="unreduced".
    tools["math"](operation="expand", expression="(x + y)**2 - (x**2 + y**2)", session=True)


def _suspect_warning(result: dict) -> str:
    matches = [w for w in result.get("warnings", []) if "unreduced difference" in w]
    assert matches, result.get("warnings")
    return matches[0]


def test_auto_save_false_warning_does_not_claim_a_save(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    _suspect_session(tools, "c2-no-save")

    result = tools["session_complete"](auto_save=False)

    warning = _suspect_warning(result)
    assert "suspect_identity" in warning  # the true half is preserved
    assert "auto_save=false" in warning
    assert "nothing was saved" in warning
    assert "the formula is saved" not in warning
    assert "saved_to" not in result


def test_auto_save_true_warning_still_reports_the_save(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    tools = _tools()
    _suspect_session(tools, "c2-save")

    result = tools["session_complete"](auto_save=True)

    warning = _suspect_warning(result)
    assert warning == (
        "1 step(s) recorded an unreduced difference (suspect_identity); "
        "the formula is saved with verified=false"
    )


class TestOutcomeReporting:
    def test_show_agrees_with_complete(self, fresh_session_manager):
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="outcome-agreement")
        tools["session_load_formula"](expression="a+b", formula_id="f1")
        tools["math"](operation="expand", expression="(a+b)**2", session=True)
        tools["math"](operation="evalf", expression="1/3", session=True)

        show = tools["session_show"]()
        complete = tools["session_complete"](
            auto_save=False, require_target_match=False
        )

        assert show["result_expression"] == complete["final_expression"]
        assert show["result_latex"] == complete["final_latex"]
        # The raw current expression stays visible, but under its own name.
        assert show["latex"] == "0.333333333333333"
        assert show["result_expression"] == "a**2 + 2*a*b + b**2"

    def test_zero_self_check_is_the_outcome_for_all_sources(
        self, fresh_session_manager
    ):
        """r14 task-08: the closing step outputs ``0`` but used to be skipped.

        ``session_show.result_expression`` and ``session_complete.final_expression``
        must report the zero convergence step, not the earlier unevaluated
        symbolic step.
        """
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"](name="zero-convergence")
        tools["session_load_formula"](expression="c*x + t", formula_id="f1")
        tools["math"](
            operation="simplify",
            expression="c*x + t - (c*x + t)",
            session=True,
        )
        tools["session_add_note"](note="residual is exactly zero")

        show = tools["session_show"]()
        complete = tools["session_complete"](
            auto_save=False, require_target_match=False
        )

        assert show["result_expression"] == complete["final_expression"] == "0"
        assert show["result_latex"] == complete["final_latex"]

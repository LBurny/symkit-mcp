"""r20 Wave 2: record-and-provenance defects in the MCP recording layer.

Six defects, each reproduced black-box on the r20 sandbox cards:

- D1 ``session_record_step`` archived ``input_srepr`` from the *previous* step's
  output, so a hand-recorded step claimed an input it never consumed (9 cards).
- D2 a recorded ``dimension`` step carried "no automatic verification
  available" until a later ``verify_pass`` backfilled its own verdict (4 cards).
- D3 ``session_add_note(note_type="failure")`` and the failed-call trace landed
  with ``status="success"``.
- D4 the automatic ``math`` step description truncated the assertion at 50 chars.
- D5 the non-Basic guard blamed "a comma-separated list" for a matrix input.
- D6 ``assume`` silently accepted pseudo-properties ("less than pi") and
  expression-valued keys.
"""

from __future__ import annotations

import json
from typing import Any

import sympy as sp

from symkit.domain.derivation_session import DerivationSession
from symkit.domain.expr_io import safe_load_expression
from symkit_mcp.tools import _state
from symkit_mcp.tools._unit_context import _DIMENSION_STEP_MESSAGES
from symkit_mcp.tools.math import register_math_tools
from symkit_mcp.tools.session import register_session_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821  # MockMCP from conftest.py

_MEASURED = "x**2 + y**2 + z**2 + w**2 + u**2 + v**2 + t**2 + s**2"


def _tools() -> dict[str, Any]:
    mcp = MockMCP()  # noqa: F821
    register_session_tools(mcp)
    register_math_tools(mcp)
    return mcp.tools


def _steps(tools: dict[str, Any]) -> list[dict[str, Any]]:
    return tools["session_get_steps"]()["steps"]


def _verification_payload(row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(row["verification_result"])


# ---- D1: a manual step's input is the claim it submits ----------------------


class TestManualStepInputSrepr:
    def test_input_srepr_is_the_claim_not_the_previous_output(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("manual-input")
        tools["math"]("simplify", "2*x", session=True)

        tools["session_record_step"]("x**2 + 1", "hand-computed result")

        steps = _steps(tools)
        assert steps[1]["input_srepr"] == sp.srepr(sp.sympify("x**2 + 1"))
        assert steps[1]["input_srepr"] != steps[0]["output_srepr"]

    def test_recorded_equation_archives_its_own_sides(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("manual-equation")
        tools["math"]("simplify", "a - b", session=True)

        tools["session_record_step"]("a = b", "asserted relation")

        steps = _steps(tools)
        assert "Equality(Symbol('a'), Symbol('b'))" in steps[1]["input_srepr"]
        assert steps[1]["input_srepr"] != steps[0]["output_srepr"]

    def test_boolean_claim_archives_a_sympy_boolean(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("manual-boolean")
        tools["math"]("simplify", "2*x", session=True)

        tools["session_record_step"]("2*x = 2*x", "tautology")

        steps = _steps(tools)
        archived = steps[1]["input_srepr"]
        # ``srepr(True)`` (a python bool) is "True", which does not round-trip;
        # the archived form must be the SymPy boolean.
        assert archived != sp.srepr(True)
        assert safe_load_expression("", archived) == sp.true
        assert steps[1]["output_srepr"] == sp.srepr(sp.true)

    def test_manual_step_inherits_session_assumptions(
        self, fresh_session_manager: Any
    ) -> None:
        """A manual record under a session assumption snapshots it (r20 task-14 S3).

        ``math`` steps already archived the session's assumption strings; a
        manually recorded step used to carry ``[]`` instead, so the two step
        kinds disagreed inside one session.
        """
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("manual-assumptions")
        tools["assume"]({"k": "positive real"})

        tools["session_record_step"]("k*m", "manual step under assumption")

        row = _steps(tools)[0]
        assert row["assumptions"] == ["k is positive real"]


# ---- D2: a recorded dimension step carries its verdict at record time -------


class TestDimensionVerdictAtRecordTime:
    def _record(self, tools: dict[str, Any], expression: str, units: dict[str, str]) -> Any:
        tools["session_start"]("dimension-record")
        out = tools["math"]("dimension", expression, units=units, session=True)
        assert out["success"] is True, out
        return out

    def test_inconsistent_dimension_step_is_failed_immediately(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        out = self._record(tools, "p + v", {"p": "Pa", "v": "m/s"})
        assert out["consistent"] is False

        row = _steps(tools)[0]
        payload = _verification_payload(row)
        assert row["status"] == "failed"
        assert payload["status"] == "failed"
        assert payload["message"] == _DIMENSION_STEP_MESSAGES[False]
        assert payload["dimension_check"] is False

    def test_consistent_dimension_step_is_verified_immediately(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        out = self._record(tools, "v*t", {"v": "m/s", "t": "s"})
        assert out["consistent"] is True

        row = _steps(tools)[0]
        payload = _verification_payload(row)
        assert row["status"] == "success"
        assert payload["status"] == "verified"
        assert payload["message"] == _DIMENSION_STEP_MESSAGES[True]
        assert payload["dimension_check"] is True

    def test_undetermined_dimension_step_stays_pending(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        out = self._record(tools, "rho*v**2/2", {"rho": "kg/m^3"})
        assert out["consistent"] is None

        row = _steps(tools)[0]
        payload = _verification_payload(row)
        assert row["status"] == "pending_verification"
        assert payload["status"] == "inconclusive"
        assert payload["message"] == _DIMENSION_STEP_MESSAGES[None]
        assert payload["dimension_check"] is None

    def test_recorded_dimensions_reach_the_step_verdict(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        self._record(tools, "v*t", {"v": "m/s", "t": "s"})

        payload = _verification_payload(_steps(tools)[0])
        assert payload["details"]["dimensions"] == {"v": {"length": 1, "time": -1},
                                                    "t": {"time": 1}}


# ---- D3: a failure is recorded as a failure ---------------------------------


class TestFailureRecordsAreFailed:
    def test_failure_note_status_is_failed(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("failure-note")

        tools["session_add_note"]("the solver diverged", note_type="failure")

        assert _steps(tools)[-1]["status"] == "failed"

    def test_failure_note_is_persisted_as_failed(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("failure-note-persist")
        tools["session_add_note"]("the solver diverged", note_type="failure")

        session = _state.get_session()
        assert session is not None and session._persist_path is not None
        reloaded = DerivationSession.load(session._persist_path)

        assert reloaded.steps[-1].status.value == "failed"

    def test_observation_note_status_is_unchanged(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("observation-note")

        tools["session_add_note"]("an observation", note_type="observation")

        assert _steps(tools)[-1]["status"] == "success"

    def test_failed_math_call_trace_status_is_failed(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("failure-trace")

        failed = tools["math"](
            "substitute", "1/x", substitution={"x": "0"}, session=True
        )
        assert failed["success"] is False, failed

        trace = _steps(tools)[-1]
        assert trace["input_expressions"]["note_type"] == "failure"
        assert trace["status"] == "failed"

    def test_failure_records_stay_out_of_verification_counts(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("failure-counts")
        tools["math"]("simplify", "(x + 1)**2", session=True)

        tools["session_add_note"]("the solver diverged", note_type="failure")
        tools["math"]("substitute", "1/x", substitution={"x": "0"}, session=True)

        summary = tools["session_verify_session"]()
        assert summary["total"] == 1, summary
        assert summary["failed_steps"] == [], summary
        assert summary["overall"] == "verified", summary


# ---- D4: the automatic description keeps the whole assertion ----------------


class TestMathStepDescription:
    def test_long_expression_is_not_truncated(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("description")

        tools["math"]("parse", _MEASURED, session=True)

        description = _steps(tools)[0]["description"]
        assert description == f"parse: {_MEASURED}"

    def test_explicit_description_is_untouched(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("description-explicit")

        tools["math"]("parse", _MEASURED, session=True, description="my own label")

        assert _steps(tools)[0]["description"] == "my own label"


# ---- D5: the non-Basic guard names the real input kinds ---------------------


class TestRecordStepGuardMessage:
    def test_matrix_input_is_now_a_supported_step(
        self, fresh_session_manager: Any
    ) -> None:
        # r23 F1/F7 graduated concrete matrices to a supported input kind:
        # the r20 guard only fires for non-Basic inputs (lists / tuples) now,
        # and a recorded matrix step gets an honest inconclusive verdict.
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("matrix-step")

        result = tools["session_record_step"](
            "Matrix([[a, b], [c, d]])", "matrix input"
        )

        assert result["success"] is True
        summary = tools["session_verify_session"]()
        assert summary["failed_steps"] == [], summary
        assert summary["verified"] == 0, summary

    def test_list_input_message_names_lists(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("list-guard")

        result = tools["session_record_step"]("[a, b, c]", "list input")

        assert result["success"] is False
        assert "lists" in result["error"]
        assert "session_add_note" in result["error"]

    def test_comma_tuple_still_says_single_expression(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("tuple-guard")

        result = tools["session_record_step"]("x + y, z", "accidental tuple")

        assert result["success"] is False
        assert "single expression" in result["error"].lower()


# ---- D6: assume validates keys and property vocabulary ----------------------


class TestAssumeClauseValidation:
    def test_pseudo_property_tokens_are_rejected(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["assume"]({"theta": "less than pi"})

        assert result["success"] is False, result
        assert result.get("error"), result
        assert tools["show_assumptions"]()["assumptions"] == {}

    def test_expression_key_is_rejected(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["assume"]({"V - n*b": "positive"})

        assert result["success"] is False, result
        assert result.get("error"), result
        assert tools["show_assumptions"]()["assumptions"] == {}

    def test_rejection_applies_no_assumption_from_the_same_call(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["assume"]({"x": "positive", "theta": "less than pi"})

        assert result["success"] is False, result
        assert tools["show_assumptions"]()["assumptions"] == {}

    def test_valid_clause_is_still_applied(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["assume"]({"x": "positive real"})

        assert result["success"] is True, result
        assert tools["show_assumptions"]()["assumptions"]["x"] == {
            "positive": True,
            "real": True,
        }

    def test_clause_list_form_rejects_an_expression_key(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["assume"](["V - n*b is positive"])

        assert result["success"] is False, result
        assert tools["show_assumptions"]()["assumptions"] == {}


# ---- lambda: a Python keyword cannot be a parsed symbol ---------------------


class TestLambdaKeywordSymbol:
    """``lambda`` is a Python keyword, so ``parse_expr`` cannot take it.

    ``preprocess_unicode`` maps "λ" to ``lambda``, and the dispatcher's own
    Unicode pass is repeated by the parser, so the rename to ``lambda_`` (the
    name ``symkit.domain.formula`` already uses for "λ") has to happen after it.
    """

    def test_unicode_lambda_parses(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["math"]("simplify", "λ**2 + λ", session=False)

        assert result["success"] is True, result
        assert "lambda_" in result["expression"]
        assert any("lambda_" in w for w in result.get("warnings", [])), result

    def test_ascii_lambda_word_is_renamed(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()

        result = tools["math"](
            "diff", "lambda*x**2", variable="x", session=False
        )

        assert result["success"] is True, result
        assert result["expression"] == "2*lambda_*x"

    def test_rename_is_named_in_the_recorded_step(
        self, fresh_session_manager: Any
    ) -> None:
        _ = fresh_session_manager
        tools = _tools()
        tools["session_start"]("lambda-step")

        tools["math"]("simplify", "λ*x", session=True)

        step = _steps(tools)[-1]
        assert step["output_expression"] == "lambda_*x"
        assert "Symbol('lambda_')" in step["input_srepr"]

    def test_similar_names_are_left_alone(self, fresh_session_manager: Any) -> None:
        _ = fresh_session_manager
        tools = _tools()

        for expression in ("lambdas*x", "x**2 + 1", "x.lambda"):
            result = tools["math"]("simplify", expression, session=False)
            assert not any("lambda" in w for w in result.get("warnings", [])), result

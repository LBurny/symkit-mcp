"""What a completed session reports as its outcome.

Two defects from the 2026-09-12 complex-derivation black-box round
(`symkit-mcp-test-complex`):

* ``complete()["final_expression"]`` was ``str(current_expression)``, i.e. the
  *last* step no matter what it was.  A trailing ``evalf`` probe (a numeric
  residual, ``-1.0``, a constant) therefore became the delivered answer in all
  five cards.  ``representative_expression()`` already exists for exactly this
  selection and is what auto-save uses.
* ``insert_note_after_step`` copied the previous step's output onto the note,
  so a pure-text note was recorded as if it had produced that value (and could
  then be picked up by target matching).
"""

from __future__ import annotations

import sympy as sp

from symkit.domain.derivation_goal import DerivationGoal
from symkit.domain.derivation_session import DerivationSession, OperationType


def _session(name: str) -> DerivationSession:
    return DerivationSession(session_id=f"{name}-id", name=name)


class TestNoteDoesNotInheritOutput:
    def test_note_records_no_computed_output(self):
        session = _session("note-fidelity")
        session.load_formula("x**2 + y**2", formula_id="f1")
        previous_output = session.steps[0].output_expression

        session.insert_note_after_step(after_step=1, note="pure text note")

        note = session.steps[1]
        assert note.operation == OperationType.CUSTOM
        assert note.output_expression == ""
        assert note.output_srepr == ""
        assert note.output_expression != previous_output


class TestFinalExpressionIsTheConclusion:
    def test_trailing_numeric_probe_does_not_become_the_answer(self):
        session = _session("outcome-fidelity")
        goal = DerivationGoal.from_text("derive F", domain="general")
        goal.target_variables = ["F"]
        session.set_goal(goal)
        session.load_formula("m*a", formula_id="f1")
        session.substitute("a", "F/m")  # symbolic conclusion: F

        session._add_step(  # noqa: SLF001 - the public tools route through here
            operation=OperationType.EVALF,
            description="trailing numeric probe",
            input_expressions={"original": "1/3"},
            output_expr=sp.Float("0.333333333333333", 15),
            sympy_command="math('evalf', ...)",
        )
        # `math()` assigns the live result straight onto the session
        # (tools/math.py), which is how a probe hijacks the reported answer.
        session.current_expression = sp.Float("0.333333333333333", 15)

        result = session.complete()

        assert result["success"] is True
        assert result["final_expression"] == "F"
        assert "0.333" not in result["final_expression"]

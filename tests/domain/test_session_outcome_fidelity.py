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


class TestOutcomeAfterChangeOfVariables:
    """A derivation that ends by renaming its variables still has an outcome.

    The lineage walk in ``representative_expression`` keeps candidates whose free
    symbols overlap the running lineage, so a *renaming* substitution (``x -> y``)
    shares no name with the earlier steps and the walk falls back to the
    pre-substitution expression (r17 audit1, 1.9.0).
    """

    def test_renaming_substitution_is_the_outcome(self):
        session = _session("rename-outcome")
        session.load_formula("x**2 + 2*x + 1", formula_id="f1")
        session.substitute("x", "y - 1")

        result = session.complete()

        final = sp.sympify(result["final_expression"])
        assert sp.simplify(final - sp.sympify("2*y + (y - 1)**2 - 1")) == 0
        assert not final.free_symbols & {sp.Symbol("x")}

    def test_substitution_sharing_a_symbol_is_still_the_outcome(self):
        session = _session("shared-symbol-outcome")
        session.load_formula("x*y + x", formula_id="f1")
        session.substitute("x", "z + 1")

        result = session.complete()

        assert sp.Symbol("z") in sp.sympify(result["final_expression"]).free_symbols

    def test_note_between_two_renames_does_not_stale_the_outcome(self):
        session = _session("note-in-rename-chain")
        session.load_formula("x**2 + 2*x + 1", formula_id="f1")
        session.substitute("x", "y - 1")
        session.insert_note_after_step(len(session.steps), "observing the rewrite")
        # A pure rename shares no symbol with the lineage, so it can only be
        # reached through the consume-the-previous-output chain — a note (empty
        # output) must not reset that chain memory (r17 review).
        session.substitute("y", "z + 1")

        result = session.complete()

        z = sp.Symbol("z")
        assert sp.sympify(result["final_expression"]) == z**2 + 2 * z + 1

    def test_trailing_hand_recorded_definition_is_not_the_outcome(self):
        session = _session("custom-outcome")
        session.load_formula("x**2 + 2*x + 1", formula_id="f1")
        session.substitute("x", "y - 1")
        session._add_step(  # noqa: SLF001 - the public tools route through here
            operation=OperationType.CUSTOM,
            description="hand-recorded definition",
            input_expressions={"original": "E = m*c**2"},
            output_expr=sp.Eq(sp.Symbol("E"), sp.Symbol("m") * sp.Symbol("c") ** 2),
            sympy_command="manual_record",
        )

        result = session.complete()

        final = sp.sympify(result["final_expression"])
        assert sp.Symbol("E") not in final.free_symbols
        assert sp.Symbol("y") in final.free_symbols


class TestEarlyZeroCheckDoesNotBecomeTheOutcome:
    """An exact ``0`` is the conclusion only when it is the *last* one.

    The r14 rule "an exact zero convergence self-check is the conclusion" was
    implemented by returning on the first zero output, so a mid-derivation
    residual check hijacked the reported answer of everything that followed
    (r17: tasks 02/03/04/05 all delivered ``0``/``0.0`` instead of the result).
    """

    def test_later_symbolic_result_wins_over_an_early_zero(self):
        session = _session("early-zero-outcome")
        session.load_formula("x**2 - 1", formula_id="f1")
        session._add_step(  # noqa: SLF001 - the public tools route through here
            operation=OperationType.SIMPLIFY,
            description="mid-derivation residual check",
            input_expressions={"original": "(x - 1)*(x + 1) - (x**2 - 1)"},
            output_expr=sp.Integer(0),
            sympy_command="math('simplify', ...)",
        )
        session._add_step(  # noqa: SLF001
            operation=OperationType.SIMPLIFY,
            description="the actual result",
            input_expressions={"original": "(x**2 - 1)/(x + 1)"},
            output_expr=sp.Symbol("x") - 1,
            sympy_command="math('simplify', ...)",
        )

        result = session.complete()

        assert sp.sympify(result["final_expression"]) == sp.Symbol("x") - 1

    def test_trailing_zero_self_check_is_still_the_conclusion(self):
        session = _session("trailing-zero-outcome")
        session.load_formula("x**2 - 1", formula_id="f1")
        session._add_step(  # noqa: SLF001
            operation=OperationType.SIMPLIFY,
            description="closing convergence self-check",
            input_expressions={"original": "(x**2 - 1) - (x - 1)*(x + 1)"},
            output_expr=sp.Integer(0),
            sympy_command="math('simplify', ...)",
        )

        result = session.complete()

        assert sp.sympify(result["final_expression"]) == sp.Integer(0)

"""Dimension checks wired into session verification (Wave B2)."""

from __future__ import annotations

import json
from typing import Any

from symkit.domain.derivation_session import DerivationSession
from symkit_mcp.tools import _state, _unit_context
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools
from symkit_mcp.tools import symbols as symbol_tools

# MockMCP is provided by conftest.py


def _mcp() -> Any:
    mcp = MockMCP()  # noqa: F821
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    symbol_tools.register_symbol_tools(mcp)
    return mcp


def _start_with_units(mcp: Any) -> None:
    mcp.tools["session_start"]("dimension-test")
    mcp.tools["register_symbol"]("rho", "density", unit="kg/m^3")
    mcp.tools["register_symbol"]("v", "velocity", unit="m/s")


def _dimension_check_value(step_dict: dict[str, Any]) -> Any:
    return json.loads(step_dict["verification_result"]).get("dimension_check")


def test_verify_step_flags_dimension_mismatch(fresh_session_manager: Any) -> None:
    """The mismatch is reported on the dimension check without silently
    replacing an algebraic verdict (r19 F24: the simplify identity is verified
    algebraically, so the step status stays verified and the dimensional
    finding is attached separately with a disagreement warning)."""
    _ = fresh_session_manager
    mcp = _mcp()
    _start_with_units(mcp)

    mcp.tools["math"]("simplify", "rho + v", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert result["success"] is True
    assert result["verification_status"] == "verified"
    assert _dimension_check_value(result["step"]) is False
    assert result["verification"].get("dimension_issues")
    assert result["verification"].get("dimension_disagreement")


def test_verify_session_discloses_dimension_failure(fresh_session_manager: Any) -> None:
    """``overall`` reflects the algebraic checks, so a dimension failure is
    disclosed separately rather than silently changing the chain verdict
    (r19 F24)."""
    _ = fresh_session_manager
    mcp = _mcp()
    _start_with_units(mcp)

    mcp.tools["math"]("simplify", "rho + v", session=True)

    summary = mcp.tools["session_verify_session"]()
    assert summary["success"] is True
    assert summary["overall"] == "verified"
    assert summary["dimension_failed_steps"] == [1]
    assert any("inconsisten" in w.lower() for w in summary.get("warnings", [])), summary


def test_verify_without_units_is_unchanged(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("no-units-test")

    mcp.tools["math"]("simplify", "(x + 1)**2", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert result["verification_status"] == "verified"
    assert _dimension_check_value(result["step"]) is None

    summary = mcp.tools["session_verify_session"]()
    assert summary["overall"] == "verified"


def test_formula_variable_units_feed_verification(fresh_session_manager: Any) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("formula-units-test")

    session = _state.get_session()
    assert session is not None
    session.load_formula(
        {
            "expression": "rho + v",
            "variables": {
                "rho": {"unit": "kg/m^3"},
                "v": {"unit": "m/s"},
            },
        }
    )

    result = mcp.tools["session_verify_step"](1)
    # The units reach the checker; the algebraic verdict stands (r19 F24).
    assert _dimension_check_value(result["step"]) is False
    assert result["verification"].get("dimension_issues")


def test_invalid_unit_string_warns_instead_of_crashing(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("bad-unit-test")

    session = _state.get_session()
    assert session is not None
    load_result = session.load_formula(
        {"expression": "x + y", "variables": {"x": {"unit": "not-a-unit!!"}}}
    )
    assert load_result["success"] is True

    out = _unit_context.with_unit_warnings(session, load_result)
    assert out.get("warnings")
    # A bad unit must degrade to "unknown", never raise.
    mcp.tools["math"]("simplify", "x + y", session=True)
    result = mcp.tools["session_verify_step"](2)
    assert result["success"] is True


def test_recorded_custom_step_is_not_judged_by_the_previous_step(
    fresh_session_manager: Any,
) -> None:
    """A manually recorded step asserts one result; the previous step's
    expression must not be dragged into its dimensional verdict.

    ``session_record_step`` archives the previous step's expression in
    ``input_srepr`` (``_add_step`` defaults it from ``prior_expr``). Reading
    that field made ``T_w + T_in`` — two temperatures added, plainly
    consistent — fail with the *previous* step's ``exp(x)`` complaint.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("stale-input-test")
    mcp.tools["register_symbol"]("T_in", "inlet temperature", unit="K")
    mcp.tools["register_symbol"]("T_w", "wall temperature", unit="K")
    mcp.tools["register_symbol"]("x", "axial coordinate", unit="m")

    # Step 1 is genuinely dimensionally wrong: exp() of a length.
    mcp.tools["session_record_step"]("T_in*exp(x)", "invalid: exp of a dimensioned argument")
    # Step 2 is trivially fine and must not inherit step 1's complaint.
    mcp.tools["session_record_step"]("T_w + T_in", "valid: two temperatures added")

    first = mcp.tools["session_verify_step"](1)
    second = mcp.tools["session_verify_step"](2)

    assert first["verification_status"] == "failed"
    assert _dimension_check_value(first["step"]) is False
    # The manual step stays INCONCLUSIVE algebraically (manual steps are never
    # reported as auto-verified), but its dimension verdict must be clean — it
    # must not inherit step 1's complaint.
    assert _dimension_check_value(second["step"]) is True
    assert second["verification_status"] == "inconclusive"

    summary = mcp.tools["session_verify_session"]()
    assert summary["failed"] == 1
    assert summary["failed_steps"] == [1]


def test_unregistered_symbol_stays_unknown(fresh_session_manager: Any) -> None:
    """An unregistered symbol must not inherit a built-in domain unit.

    Task-09: the unregistered wavenumber ``k`` was silently mapped to the
    pharmacokinetics default "rate constant" (``1/h``), so the physically
    correct ``k = pi/L`` was declared dimensionally inconsistent and a fully
    correct session reported ``overall == "failed"``.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("no-fabricated-units", domain="quantum_mechanics")
    mcp.tools["register_symbol"]("L", "box width", unit="m")

    mcp.tools["math"]("simplify", "k - pi/L", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert result["verification_status"] != "failed"
    assert _dimension_check_value(result["step"]) is None
    assert "k" in result["verification"].get("dimension_unknown_symbols", [])
    assert "k" not in result["verification"].get("dimensions", {})
    assert "L*k" not in json.dumps(result["verification"].get("dimension_issues", []))


def test_explicit_registration_makes_symbol_consistent(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("explicit-unit", domain="quantum_mechanics")
    mcp.tools["register_symbol"]("k", "wavenumber", unit="1/m")
    mcp.tools["register_symbol"]("L", "box width", unit="m")

    mcp.tools["math"]("simplify", "k - pi/L", session=True)

    result = mcp.tools["session_verify_step"](1)
    assert _dimension_check_value(result["step"]) is True
    assert result["verification_status"] != "failed"


def test_declared_units_survive_session_reload(
    fresh_session_manager: Any, tmp_path: Any
) -> None:
    """Declared units are session state and must survive a save/load cycle.

    A fresh server process resumes a session from the JSON on disk. Unit
    declarations live in ``symbol_registry``, which the session payload did not
    carry, so the reloaded session knew no units at all — while
    ``lookup_symbol`` still answered with the *built-in catalogue* default
    (``rho`` -> ``kg/m^3``), which the checker deliberately refuses to use. The
    wrong answer looked plausible and nothing reported the loss.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("unit-persistence")
    # g/cm^3 is deliberately not the built-in default for rho, so a catalogue
    # leak cannot masquerade as a surviving declaration.
    mcp.tools["register_symbol"]("rho", "density", unit="g/cm^3")
    mcp.tools["register_symbol"]("v", "velocity", unit="m/s")

    session = _state.get_session()
    assert session is not None
    path = session.save(tmp_path / "session_unit_persistence.json")

    # Stand in for a second server process: drop the in-memory session and
    # rebuild it from the file alone.
    _state.set_session(None)
    _state.set_session(DerivationSession.load(path))

    out = mcp.tools["math"]("dimension", "rho*v**2/2")
    assert out["units"] == {"rho": "g/cm^3", "v": "m/s"}
    assert out["consistent"] is True


def test_reloaded_units_are_reported_as_registrations(
    fresh_session_manager: Any, tmp_path: Any
) -> None:
    """After a reload the unit must come back as a user registration, not as a
    catalogue default the checker ignores."""
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("unit-persistence-scope")
    mcp.tools["register_symbol"]("rho", "density", unit="g/cm^3")

    session = _state.get_session()
    assert session is not None
    path = session.save(tmp_path / "session_unit_scope.json")

    reloaded = DerivationSession.load(path)
    lookups = reloaded.symbol_registry.list_symbols()
    explicit = {s.name: s.default_unit for s in lookups if s.default_unit == "g/cm^3"}
    assert explicit == {"rho": "g/cm^3"}


def test_inconclusive_dimensional_check_is_disclosed(
    fresh_session_manager: Any,
) -> None:
    """A chain must not report a bare ``overall: verified`` when the dimensional
    check ran but reached no conclusion.

    With one symbol's unit missing, ``dimension_check`` is ``None`` and the
    algebraic verdict stands — correct, but the session summary said nothing,
    so "verified" was indistinguishable from "and the units are fine".
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("partial-units-disclosure")
    mcp.tools["register_symbol"]("rho", "density", unit="kg/m^3")

    mcp.tools["math"]("simplify", "rho*v**2/2 + rho*v**2/2", session=True)

    step = mcp.tools["session_verify_step"](1)
    assert step["verification_status"] == "verified"
    assert _dimension_check_value(step["step"]) is None
    assert step["verification"]["dimension_unknown_symbols"] == ["v"]

    summary = mcp.tools["session_verify_session"]()
    assert summary["overall"] == "verified"
    assert summary["dimension_inconclusive_steps"] == [1]
    assert any("no conclusion" in w for w in summary.get("warnings", []))


def test_session_without_units_is_not_annotated(fresh_session_manager: Any) -> None:
    """No declared units means no dimensional check was attempted.

    That is not an inconclusive *result* and must not be reported as one.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("no-units-no-annotation")

    mcp.tools["math"]("simplify", "(x + 1)**2", session=True)

    summary = mcp.tools["session_verify_session"]()
    assert summary["overall"] == "verified"
    assert "dimension_inconclusive_steps" not in summary
    assert not summary.get("warnings")


def test_disclosure_reaches_session_show(
    fresh_session_manager: Any,
) -> None:
    """Every verdict surface discloses the same thing (``session_show`` renders
    its own verification summary)."""
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("partial-units-surfaces")
    mcp.tools["register_symbol"]("rho", "density", unit="kg/m^3")
    mcp.tools["math"]("simplify", "rho*v**2/2 + rho*v**2/2", session=True)

    shown = mcp.tools["session_show"]()
    assert shown["verification_summary"]["dimension_inconclusive_steps"] == [1]


def test_fractional_exponent_unit_stays_unknown(fresh_session_manager: Any) -> None:
    """A declaration like ``sqrt(m)`` must not be laundered into "dimensionless".

    ``int(power)`` truncated ``length ** (1/3)`` to ``length ** 0``, so the
    symbol read as dimensionless and the whole expression came back
    ``consistent: true`` — a silent wrong *verdict*, not just a missing one.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("fractional-unit")

    for unit in ("sqrt(m)", "m^(1/3)", "m^0.5"):
        out = mcp.tools["math"]("dimension", "x**3", units={"x": unit}, session=False)
        assert out["consistent"] is None, (unit, out)
        assert out["unknown_symbols"] == ["x"], (unit, out)
        assert out.get("dimensions", {}).get("x") is None, (unit, out)


def test_register_symbol_persists_its_declaration(
    fresh_session_manager: Any,
) -> None:
    """Declaring a unit must reach disk on its own.

    It only did so when some *later* step happened to save the session, so a
    server restart right after declaring units resumed a session that knew
    nothing about them — the same silent loss as the missing payload field, via
    a different trigger (30 declarations, no steps, fresh process).
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("persist-on-register")
    mcp.tools["register_symbol"]("rho", "density", unit="g/cm^3")
    mcp.tools["register_symbol"]("v", "velocity", unit="m/s")

    session = _state.get_session()
    assert session is not None
    persist_path = session._persist_path  # noqa: SLF001 - the file the server writes
    assert persist_path is not None
    reloaded = DerivationSession.load(persist_path)
    assert reloaded.symbol_registry.unit_declarations() == {"rho": "g/cm^3", "v": "m/s"}


def test_registration_outranks_a_loaded_formulas_unit(
    fresh_session_manager: Any,
) -> None:
    """Documented precedence: an explicit declaration for *this derivation*
    outranks the unit a library formula carries.

    ``collect_unit_map`` applied the formula's variable units last, so loading a
    formula silently overwrote what the user had registered for the same symbol
    — the code contradicted its own "weakest source first" docstring.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("unit-precedence")
    mcp.tools["register_symbol"]("p", "pressure in my derivation", unit="mol")

    session = _state.get_session()
    assert session is not None
    session.load_formula({"expression": "p + q", "variables": {"p": {"unit": "Pa"}}})

    out = mcp.tools["math"]("dimension", "p", session=False)
    assert out["units"]["p"] == "mol"
    assert out["dimensions"]["p"] == {"amount_of_substance": 1}


def test_formula_units_still_used_when_nothing_is_registered(
    fresh_session_manager: Any,
) -> None:
    """The precedence fix must not drop the formula source for symbols the user
    never declared."""
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("formula-only-units")

    session = _state.get_session()
    assert session is not None
    session.load_formula({"expression": "p + q", "variables": {"p": {"unit": "Pa"}}})

    out = mcp.tools["math"]("dimension", "p + q", session=False)
    assert out["dimensions"]["p"] == {"mass": 1, "length": -1, "time": -2}
    assert "q" in out["unknown_symbols"]


def test_recorded_dimension_step_keeps_an_undetermined_dimension(
    fresh_session_manager: Any,
) -> None:
    """A recorded dimension step must not collapse "unknown" into
    "dimensionless": ``result_dimension or {}`` wrote ``{}`` for a ``null``
    verdict, so the step's provenance and the live response disagreed — and
    downstream readers saw "dimensionless" where the tool had said "no idea".
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("dimension-null-provenance")

    out = mcp.tools["math"]("dimension", "rho*v**2/2", units={"rho": "kg/m^3"},
                            session=True)
    assert out["consistent"] is None
    assert out["result_dimension"] is None

    row = mcp.tools["session_get_steps"]()["steps"][0]
    recorded = json.loads(row["input_expressions"]["result_dimension"])
    assert recorded is None, row["input_expressions"]
    assert row["input_expressions"]["consistent"] == "None"


def test_dimension_message_does_not_claim_a_net_dimension_when_inconsistent(
    fresh_session_manager: Any,
) -> None:
    """``exp(L)`` was reported as "found inconsistencies" *and* "has net
    dimension: dimensionless" in the same sentence."""
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("dimension-message")

    bad = mcp.tools["math"]("dimension", "exp(L)", units={"L": "m"}, session=False)
    assert bad["consistent"] is False
    assert "net dimension" not in bad["message"]
    assert "inconsisten" in bad["message"].lower()

    good = mcp.tools["math"]("dimension", "v*t", units={"v": "m/s", "t": "s"},
                             session=False)
    assert good["consistent"] is True
    assert "net dimension" in good["message"]


def test_recorded_inconsistent_dimension_step_fails_the_chain(
    fresh_session_manager: Any,
) -> None:
    """A recorded ``dimension`` step that found an inconsistency must fail the
    step and the chain.

    It used to sit in the chain as CUSTOM/inconclusive ("no automatic
    verification available") while the tool had *just* said the expression is
    dimensionally inconsistent, so `overall` and `failed_steps` showed no trace
    of a finding the user had already been handed.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("dimension-step-failed")

    out = mcp.tools["math"]("dimension", "p + v", units={"p": "Pa", "v": "m/s"},
                            session=True)
    assert out["consistent"] is False

    step = mcp.tools["session_verify_step"](1)
    assert step["verification_status"] == "failed"
    assert _dimension_check_value(step["step"]) is False

    summary = mcp.tools["session_verify_session"]()
    assert summary["overall"] == "failed"
    assert summary["failed_steps"] == [1]


def test_recorded_dimension_step_does_not_contradict_its_own_units(
    fresh_session_manager: Any,
) -> None:
    """A ``units=`` call must not leave contradictory verification details.

    The post-check re-judged the archived expression against the *session's*
    declarations — which do not include units passed per call — so a step that
    had resolved temperature was annotated ``dimension_unknown_symbols: ["x"]``.
    """
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("dimension-step-consistent")

    out = mcp.tools["math"]("dimension", "x", units={"x": "\u00b0C"}, session=True)
    assert out["consistent"] is True

    step = mcp.tools["session_verify_step"](1)
    assert _dimension_check_value(step["step"]) is True
    assert step["verification_status"] == "verified"
    assert step["verification"]["dimensions"] == {"x": {"temperature": 1}}
    assert "dimension_unknown_symbols" not in step["verification"]


def test_recorded_undetermined_dimension_step_stays_inconclusive(
    fresh_session_manager: Any,
) -> None:
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("dimension-step-undetermined")

    out = mcp.tools["math"]("dimension", "rho*v**2/2", units={"rho": "kg/m^3"},
                            session=True)
    assert out["consistent"] is None

    step = mcp.tools["session_verify_step"](1)
    assert step["verification_status"] == "inconclusive"
    assert _dimension_check_value(step["step"]) is None


def test_register_symbol_warns_about_an_unreadable_unit(
    fresh_session_manager: Any,
) -> None:
    """``formula_add`` warned about units it could not read; ``register_symbol``
    accepted them in silence, so the symbol quietly counted as unknown in every
    later check and the user only found out when a result came back
    ``inconclusive``."""
    _ = fresh_session_manager
    mcp = _mcp()
    mcp.tools["session_start"]("unit-warning")

    bad = mcp.tools["register_symbol"]("Lp", "sound pressure level", unit="dB")
    assert bad["success"] is True
    assert bad["warning"] and "dB" in bad["warning"]

    good = mcp.tools["register_symbol"]("q", "heat flux", unit="W/m^2")
    assert good["warning"] is None

    dimensionless = mcp.tools["register_symbol"]("eta", "efficiency", unit="%")
    assert dimensionless["warning"] is None

    unknown_domain = mcp.tools["register_symbol"]("z", "thing", domain="not_a_domain",
                                                 unit="m")
    assert unknown_domain["warning"] and "not_a_domain" in unknown_domain["warning"]

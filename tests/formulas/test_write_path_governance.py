"""Write-path governance for the formula library (Wave C2).

Covers the contracts that close the review findings:
1. ``formula_add`` rejects variables without a unit; ``"-"`` is the explicit
   "unknown/dimensionless" sentinel and unparseable units only warn.
2. Successful ``formula_add`` / ``session_complete(auto_save=True)`` responses
   surface structurally/textually similar existing formulas via ``similar_to``.
3. Auto-save backfills variable units from the session unit context instead of
   writing empty strings.
4. ``formula_promote`` persists ``curated: true``; ``formula_get`` exposes it;
   ``formula_stats`` exposes ``structural_duplicate_groups``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from symkit.application.formula_catalog import FormulaCatalog
from symkit.infrastructure import derivation_repository as repo_mod
from symkit.infrastructure.formula_files import YamlFormulaFileSource
from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore
from symkit_mcp.tools import _state
from symkit_mcp.tools import formula as formula_tools
from symkit_mcp.tools import math as math_tools
from symkit_mcp.tools import session as session_tools
from symkit_mcp.tools import symbols as symbol_tools

# MockMCP is provided by conftest.py
# ruff: noqa: F821


def _write_yaml(root: Path, category: str, fid: str, **data) -> Path:
    d = root / category
    d.mkdir(parents=True, exist_ok=True)
    payload = {"id": fid, "name": fid, "sympy_str": "x + 1", "category": category, **data}
    path = d / f"{fid}.yaml"
    path.write_text(yaml.dump(payload, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def gov_env(tmp_path, fresh_session_manager, monkeypatch):
    """Catalog + session/math/symbol/formula tools over tmp-backed stores."""
    _ = fresh_session_manager
    staging = repo_mod.get_repository()._formulas_dir  # noqa: SLF001
    seed, curated = tmp_path / "seed", tmp_path / "curated"
    seed.mkdir()
    curated.mkdir()
    store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
    store.open()
    catalog = FormulaCatalog(
        store,
        YamlFormulaFileSource(),
        seed_dir=seed,
        staging_dir=staging,
        curated_dir=curated,
    )
    monkeypatch.setattr(_state, "_catalog", catalog)
    mcp = MockMCP()  # noqa: F821
    formula_tools.register_formula_tools(mcp)
    session_tools.register_session_tools(mcp)
    math_tools.register_math_tools(mcp)
    symbol_tools.register_symbol_tools(mcp)
    yield SimpleNamespace(
        mcp=mcp.tools, catalog=catalog, staging=staging, curated=curated
    )
    store.close()


def _add(tools, **overrides):
    payload = {
        "id": "governed",
        "name": "Governed formula",
        "sympy_str": "x + 1",
        "latex": "x + 1",
        "variables": {"x": {"description": "value", "unit": "-"}},
    }
    payload.update(overrides)
    return tools["formula_add"](**payload)


class TestUnitRequirement:
    def test_missing_unit_is_rejected(self, gov_env):
        res = _add(gov_env.mcp, variables={"x": {"description": "value"}})
        assert res["success"] is False, res
        assert "unit" in res["error"].lower()
        assert gov_env.catalog.get("governed") is None

    def test_empty_unit_is_rejected(self, gov_env):
        res = _add(gov_env.mcp, variables={"x": {"unit": ""}})
        assert res["success"] is False, res
        assert "unit" in res["error"].lower()
        assert gov_env.catalog.get("governed") is None

    def test_explicit_dash_unit_is_accepted(self, gov_env):
        res = _add(gov_env.mcp)
        assert res["success"] is True, res
        assert "warnings" not in res

    def test_unparseable_unit_warns_but_persists(self, gov_env):
        res = _add(gov_env.mcp, variables={"x": {"unit": "not-a-unit!!"}})
        assert res["success"] is True, res
        assert any("Could not interpret unit" in w for w in res.get("warnings", []))


class TestSimilarTo:
    def test_add_surfaces_structurally_similar_formula(self, gov_env):
        first = _add(
            gov_env.mcp,
            id="bern_a",
            sympy_str="g*z + p/rho + v**2/2",
            variables={
                "g": {"unit": "-"}, "z": {"unit": "-"}, "p": {"unit": "-"},
                "rho": {"unit": "-"}, "v": {"unit": "-"},
            },
        )
        assert first["success"], first
        second = _add(
            gov_env.mcp,
            id="bern_b",
            sympy_str="g*z + p/rho + u**2/2",
            variables={
                "g": {"unit": "-"}, "z": {"unit": "-"}, "p": {"unit": "-"},
                "rho": {"unit": "-"}, "u": {"unit": "-"},
            },
        )
        assert second["success"], second
        assert "bern_a" in [s["id"] for s in second["similar_to"]]

    def test_no_similar_key_when_library_is_empty(self, gov_env):
        res = _add(gov_env.mcp)
        assert res["success"] is True
        assert "similar_to" not in res


class TestCurationSurface:
    def test_promote_persists_curated_and_get_exposes_it(self, gov_env):
        _write_yaml(
            gov_env.staging, "derived", "pend-abc123",
            name="Pendulum period", sympy_str="T = 2*pi*sqrt(l/g)",
        )
        gov_env.catalog.ensure_fresh()
        res = gov_env.mcp["formula_promote"]("pend-abc123", new_id="pendulum_period")
        assert res["success"], res
        assert res.get("curated") is True, res

        got = gov_env.mcp["formula_get"]("pendulum_period")
        assert got["success"], got
        assert got["formula"]["curated"] is True

        path = next(gov_env.curated.rglob("pendulum_period.yaml"))
        assert yaml.safe_load(path.read_text(encoding="utf-8"))["curated"] is True

    def test_stats_exposes_structural_duplicate_groups(self, gov_env):
        _write_yaml(gov_env.staging, "derived", "d1",
                    sympy_str="g*z + p/rho + v**2/2")
        _write_yaml(gov_env.staging, "derived", "d2",
                    sympy_str="g*z + p/rho + u**2/2")
        res = gov_env.mcp["formula_stats"]()
        assert res["success"], res
        assert res["structural_duplicate_groups"] == 1
        # Alpha-equivalent, but the content hashes (and thus exact dup groups) differ.
        assert res["duplicate_groups"] == 0


class TestAutoSaveUnits:
    def test_autosave_backfills_units_from_session_context(self, gov_env):
        tools = gov_env.mcp
        tools["session_start"]("unit-save", goal="solve for x")
        tools["register_symbol"]("m", "mass", unit="kg")
        tools["register_symbol"]("g", "gravity", unit="m/s^2")
        assert tools["math"](
            "solve", "m*g*x == F", variable="x", session=True
        )["success"]

        done = tools["session_complete"](auto_save=True)
        assert done["success"], done
        saved = repo_mod.get_repository().get(done["saved_id"])
        assert saved is not None
        units = {name: meta["unit"] for name, meta in saved.variables.items()}
        assert units["g"] == "m/s^2"
        assert units["m"] == "kg"
        assert units["F"] == "-"
        assert all(unit != "" for unit in units.values())

    def test_autosave_surfaces_similar_existing_formula(self, gov_env):
        # Alpha-equivalent to the solved ``Eq(x, E/(g*m))``; content differs.
        _write_yaml(gov_env.curated, "derived", "similar_shape",
                    sympy_str="y = R/(s*t)")
        gov_env.catalog.ensure_fresh()
        tools = gov_env.mcp
        tools["session_start"]("save-similar", goal="solve for x")
        tools["register_symbol"]("m", "mass", unit="kg")
        tools["register_symbol"]("g", "gravity", unit="m/s^2")
        tools["math"]("solve", "m*g*x == F", variable="x", session=True)

        done = tools["session_complete"](auto_save=True)
        assert done["success"], done
        assert "similar_shape" in [
            s["id"] for s in done.get("similar_to", [])
        ], done


class TestPromotePreservesMetadata:
    """Promotion must not discard metadata the index does not model.

    Sandbox round 13: promoting a verified staging entry wrote ``verified:
    false`` into the curated copy — a silent loss of the verification verdict
    (which also feeds the ranking boost), plus assumptions/limitations/
    derivation_steps/session_ids.
    """

    def test_promote_keeps_verification_and_rich_metadata(self, tmp_path: Path) -> None:
        from symkit.application.formula_catalog import FormulaCatalog
        from symkit.infrastructure.formula_index_store import SqliteFormulaIndexStore

        staging = tmp_path / "derived"
        curated = tmp_path / "library"
        (staging / "general").mkdir(parents=True)
        curated.mkdir(parents=True)
        (staging / "general" / "promoted_probe-abc123.yaml").write_text(
            "id: promoted_probe-abc123\n"
            "name: Promoted probe\n"
            "sympy_str: a*b\n"
            "category: general\n"
            "variables:\n  a: {description: A, unit: kg}\n  b: {description: B, unit: m}\n"
            "verified: true\n"
            "verified_at: '2026-09-13T00:00:00'\n"
            "verification_method: step_verifier\n"
            "assumptions:\n- 无粘\n"
            "limitations:\n- 仅层流\n"
            "derivation_steps:\n- step one\n"
            "session_ids:\n- abc123\n"
            "application_context: pipe flow\n",
            encoding="utf-8",
        )
        from symkit.infrastructure.formula_files import YamlFormulaFileSource

        store = SqliteFormulaIndexStore(tmp_path / "index.sqlite3")
        store.open()
        catalog = FormulaCatalog(
            store, YamlFormulaFileSource(),
            seed_dir=tmp_path / "seed", staging_dir=staging, curated_dir=curated,
        )

        promoted = catalog.promote("promoted_probe-abc123")

        payload = yaml.safe_load(
            (curated / "general" / f"{promoted.id}.yaml").read_text(encoding="utf-8")
        )
        assert payload["verified"] is True
        assert payload["verification_method"] == "step_verifier"
        assert payload["assumptions"] == ["无粘"]
        assert payload["limitations"] == ["仅层流"]
        assert payload["derivation_steps"] == ["step one"]
        assert payload["session_ids"] == ["abc123"]
        assert payload["application_context"] == "pipe flow"
        assert payload["variables"]["a"]["unit"] == "kg"
        # curated is still stamped by the promotion itself
        assert payload["curated"] is True


class TestEmptyVariablesAllowed:
    """``variables={}`` must be accepted: the error text has always said so.

    The guard was ``if not variables``, so an empty mapping was rejected while
    the message promised "can be empty {}". With units now mandatory per
    variable, that made a formula with no free symbols impossible to add.
    """

    def test_empty_variables_is_accepted(self, gov_env):
        tools = gov_env.mcp
        out = tools["formula_add"](
            "constant_identity", "Constant identity", "2 + 2", latex="2+2",
            variables={}, category="probe",
        )
        assert out["success"] is True, out
        assert out["formula_id"] == "constant_identity"

    def test_missing_variables_still_rejected(self, gov_env):
        tools = gov_env.mcp
        out = tools["formula_add"](
            "no_vars_kw", "No vars", "2 + 2", latex="2+2",
            variables=None, category="probe",
        )
        assert out["success"] is False
        assert "variables" in out["error"]


class TestLoadedFormulaUnits:
    """A formula's declared variable units must reach the dimension checker.

    ``formula_get(load_into_session=True)`` handed only the expression string to
    ``session.load_formula``, so the curated per-variable ``unit`` metadata that
    ``formula_get`` itself displays was never usable: the documented unit source
    "the unit declared on each loaded formula's variables" was unreachable from
    the MCP surface, and the verify chain saw no units at all.
    """

    def test_formula_get_load_carries_variable_units(self, gov_env):
        tools = gov_env.mcp
        added = _add(
            tools,
            id="dim_load",
            name="Dim load",
            sympy_str="v*t",
            latex="v t",
            variables={"v": {"unit": "m/s"}, "t": {"unit": "s"}},
        )
        assert added["success"] is True, added
        tools["session_start"]("formula-units")

        loaded = tools["formula_get"]("dim_load", load_into_session=True)
        assert loaded["session_loaded"] is True, loaded

        out = tools["math"]("dimension", "v*t", session=False)
        assert out["units"] == {"v": "m/s", "t": "s"}
        assert out["consistent"] is True, out
        assert out["result_dimension"] == {"length": 1}

    def test_formula_without_units_still_loads_and_stays_graceful(self, gov_env):
        tools = gov_env.mcp
        added = _add(tools, id="no_units", name="No units", variables={"x": {"unit": "-"}})
        assert added["success"] is True, added
        tools["session_start"]("no-unit-formula")

        loaded = tools["formula_get"]("no_units", load_into_session=True)
        assert loaded["session_loaded"] is True, loaded

        out = tools["math"]("dimension", "x + 1", session=False)
        assert out["consistent"] is True, out

    def test_unparseable_variable_unit_warns_and_stays_unknown(self, gov_env):
        """A library unit the parser cannot read must degrade, not fail."""
        tools = gov_env.mcp
        added = _add(tools, id="odd_units", name="Odd units",
                     sympy_str="x + y", variables={"x": {"unit": "not-a-unit!!"}})
        assert added["success"] is True, added
        tools["session_start"]("odd-unit-formula")

        loaded = tools["formula_get"]("odd_units", load_into_session=True)
        assert loaded["session_loaded"] is True, loaded
        out = tools["math"]("dimension", "x + y", session=False)
        assert out["consistent"] is None
        assert "x" in out["unknown_symbols"]

"""Tests for the formula search framework.

Covers query normalization, domain alias resolution, Wikidata adapter
multi-strategy search, and the MCP tool bridge into derivation sessions.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from symkit.domain import formula_library as _formula_library_module
from symkit.domain.formula_library import FormulaEntry, FormulaLibrary
from symkit.domain.formula_search_query import (
    expand_query_variants,
    normalize_formula_query,
    normalize_formula_search_inputs,
    resolve_domain_alias,
)
from symkit.infrastructure.adapters.local_formula import LocalFormulaAdapter
from symkit.infrastructure.adapters.wikidata_formulas import (
    WikidataFormulaAdapter,
)


@pytest.fixture(autouse=True)
def _isolated_user_formula_dirs(tmp_path, monkeypatch):
    """Keep default-constructed libraries away from the real user data dir.

    ``FormulaLibrary()`` resolves the user overlay and derived directories;
    tests here must not depend on the developer machine's actual contents.
    Bundled seeds are unaffected (they come from the wheel resources).
    """
    monkeypatch.setattr(
        _formula_library_module, "user_library_dir", lambda: tmp_path / "user_library"
    )
    monkeypatch.setattr(
        _formula_library_module, "user_derived_dir", lambda: tmp_path / "user_derived"
    )

class TestQueryNormalization:
    """Free-text formula queries are normalized for reliable matching."""

    def test_lowercase_and_trim(self):
        assert normalize_formula_query("  Reynolds Number  ") == "reynolds number"

    def test_en_dash_to_hyphen(self):
        assert normalize_formula_query("Navier–Stokes equations") == "navier-stokes equations"

    def test_em_dash_to_hyphen(self):
        assert normalize_formula_query("Navier—Stokes equations") == "navier-stokes equations"

    def test_minus_sign_to_hyphen(self):
        assert normalize_formula_query("Navier−Stokes equations") == "navier-stokes equations"

    def test_multiple_spaces_collapsed(self):
        assert normalize_formula_query("Navier  Stokes   equations") == "navier stokes equations"

    def test_parenthetical_removed(self):
        assert normalize_formula_query("Reynolds number (Re)") == "reynolds number"

    def test_expand_variants(self):
        variants = expand_query_variants("Navier-Stokes equations")
        assert "navier-stokes equations" in variants
        assert "navier stokes equations" in variants
        assert "ns equations" in variants
        # Should be deduplicated
        assert len(variants) == len(set(variants))

    def test_resolve_domain_alias(self):
        assert resolve_domain_alias("fluid_dynamics") == "fluid_dynamics"
        assert resolve_domain_alias("fluid_mechanics") == "fluid_dynamics"
        assert resolve_domain_alias("cfd") == "fluid_dynamics"
        assert resolve_domain_alias("quantum_mechanics") == "quantum_mechanics"
        assert resolve_domain_alias("pk") == "pharmacokinetics"
        assert resolve_domain_alias("general_relativity") == "general_relativity"
        assert resolve_domain_alias("unknown_domain") is None

    def test_normalize_inputs(self):
        result = normalize_formula_search_inputs("NS equations", "fluid_dynamics")
        assert result["query"] == "ns equations"
        assert result["domain"] == "fluid_dynamics"
        assert "navier-stokes equations" in result["query_variants"]

class TestWikidataAdapterSearch:
    """Wikidata adapter uses multiple search strategies and scores results."""

    def _mock_sparql_response(self, items: list[dict[str, str]]) -> dict:
        """Build a minimal SPARQL results JSON payload."""
        bindings = []
        for item in items:
            bindings.append({
                "item": {"type": "uri", "value": item["uri"]},
                "itemLabel": {"xml:lang": "en", "type": "literal", "value": item["label"]},
                "formula": {
                    "datatype": "http://www.w3.org/1998/Math/MathML",
                    "type": "literal",
                    "value": item["formula"],
                },
                "description": {"xml:lang": "en", "type": "literal", "value": item.get("description", "")},
            })
        return {"results": {"bindings": bindings}}

    @patch("symkit.infrastructure.adapters.wikidata_formulas.httpx.Client")
    def test_search_finds_label_match(self, mock_client_class: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._mock_sparql_response([
            {
                "uri": "http://www.wikidata.org/entity/Q201321",
                "label": "Navier–Stokes equations",
                "formula": "<math>...</math>",
                "description": "system of nonlinear PDEs",
            },
        ])

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = WikidataFormulaAdapter()
        results = adapter.search("Navier-Stokes equations", limit=3)
        adapter.close()

        assert len(results) == 1
        assert results[0].id == "Q201321"
        assert results[0].name == "Navier–Stokes equations"
        assert results[0].extra.get("strategy") == "label_and_alias"
        assert results[0].extra.get("score") == 0.85

    @patch("symkit.infrastructure.adapters.wikidata_formulas.httpx.Client")
    def test_search_by_category_resolves_domain_alias(self, mock_client_class: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._mock_sparql_response([
            {
                "uri": "http://www.wikidata.org/entity/Q375175",
                "label": "Euler equations",
                "formula": "<math>...</math>",
                "description": "inviscid flow equations",
            },
        ])

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = WikidataFormulaAdapter()
        results = adapter.search_by_category("fluid_dynamics", "Euler equations", limit=3)
        adapter.close()

        assert len(results) == 1
        assert results[0].id == "Q375175"
        # Verify that the SPARQL query includes the resolved category QID
        call_args = mock_client.get.call_args
        sparql = call_args[1]["params"]["query"] if call_args else ""
        assert "Q4323994" in sparql

    @patch("symkit.infrastructure.adapters.wikidata_formulas.httpx.Client")
    def test_parse_search_results_detects_mathml(self, mock_client_class: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._mock_sparql_response([
            {
                "uri": "http://www.wikidata.org/entity/Q201321",
                "label": "Navier–Stokes equations",
                "formula": "<math xmlns='http://www.w3.org/1998/Math/MathML'><mrow><mi>x</mi></mrow></math>",
            },
        ])

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        adapter = WikidataFormulaAdapter()
        results = adapter.search("Navier-Stokes equations", limit=1)
        adapter.close()

        assert results[0].extra.get("is_mathml") is True
        assert "formula_get" in results[0].extra.get("load_hint", "")

    @patch("symkit.infrastructure.adapters.wikidata_formulas.httpx.Client")
    def test_api_fallback_when_sparql_fails(self, mock_client_class: MagicMock) -> None:
        """When SPARQL is rate-limited, the adapter falls back to the Wikidata API."""
        sparql_error = MagicMock()
        sparql_error.raise_for_status.side_effect = Exception("429 rate limit")

        search_response = MagicMock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            "search": [
                {
                    "id": "Q201321",
                    "label": "Navier–Stokes equations",
                    "description": "PDEs for fluid motion",
                },
                {
                    "id": "Q138039177",
                    "label": "Navier-Stokes Equations",
                    "description": "book",
                },
            ],
        }

        claims_response = MagicMock()
        claims_response.raise_for_status.return_value = None
        claims_response.json.return_value = {
            "claims": {
                "P2534": [{
                    "mainsnak": {
                        "datavalue": {
                            "value": "\\partial_t \\mathbf{u} + ...",
                            "type": "string",
                        },
                    },
                }],
            },
        }

        no_claims_response = MagicMock()
        no_claims_response.raise_for_status.return_value = None
        no_claims_response.json.return_value = {"claims": {}}

        mock_client = MagicMock()
        # First SPARQL call fails; then API search; then claims for Q201321; then claims for Q138039177 (no P2534).
        mock_client.get.side_effect = [
            sparql_error, search_response, claims_response, no_claims_response
        ]
        mock_client_class.return_value = mock_client

        adapter = WikidataFormulaAdapter()
        results = adapter.search("Navier-Stokes equations", limit=3)
        adapter.close()

        assert len(results) == 1
        assert results[0].id == "Q201321"
        assert results[0].extra.get("strategy") == "api_fallback"
        assert "partial_t" in results[0].latex

class TestWikidataGetFormula:
    """formula_get prefers the Wikidata web API and falls back to SPARQL."""

    @patch("symkit.infrastructure.adapters.wikidata_formulas.httpx.Client")
    def test_get_formula_prefers_api_latex(self, mock_client_class: MagicMock) -> None:
        """API-first path returns the original P2534 LaTeX and entity metadata."""
        def _fake_get(_url: str, params: dict[str, Any] | None = None, **_kw: Any) -> MagicMock:
            action = (params or {}).get("action")
            response = MagicMock()
            response.raise_for_status.return_value = None
            if action == "wbgetclaims":
                response.json.return_value = {
                    "claims": {
                        "P2534": [{
                            "mainsnak": {
                                "datavalue": {
                                    "value": "\\rho (\\partial_t \\mathbf{u} + \\mathbf{u} \\cdot \\nabla \\mathbf{u}) = -\\nabla p + \\mu \\nabla^2 \\mathbf{u}",
                                    "type": "string",
                                },
                            },
                        }],
                    },
                }
            elif action == "wbgetentities":
                response.json.return_value = {
                    "entities": {
                        "Q201321": {
                            "labels": {"en": {"value": "Navier–Stokes equations"}},
                            "descriptions": {"en": {"value": "PDEs for fluid motion"}},
                        },
                    },
                }
            else:
                response.json.return_value = {}
            return response

        mock_client = MagicMock()
        mock_client.get.side_effect = _fake_get
        mock_client_class.return_value = mock_client

        adapter = WikidataFormulaAdapter()
        result = adapter.get_formula("Q201321")
        adapter.close()

        assert result is not None
        assert result.id == "Q201321"
        assert result.name == "Navier–Stokes equations"
        assert result.description == "PDEs for fluid motion"
        assert "rho" in result.latex
        assert result.source == "wikidata"

    @patch("symkit.infrastructure.adapters.wikidata_formulas.httpx.Client")
    def test_get_formula_falls_back_to_sparql_when_api_has_no_formula(self, mock_client_class: MagicMock) -> None:
        """If the API item lacks P2534, get_formula falls back to SPARQL."""
        def _fake_get(url: str, params: dict[str, Any] | None = None, **_kw: Any) -> MagicMock:
            action = (params or {}).get("action")
            response = MagicMock()
            response.raise_for_status.return_value = None
            if action == "wbgetclaims":
                # API has no P2534 formula
                response.json.return_value = {"claims": {}}
            elif action == "wbgetentities":
                response.json.return_value = {
                    "entities": {
                        "Q201321": {
                            "labels": {"en": {"value": "Navier–Stokes equations"}},
                            "descriptions": {"en": {"value": "PDEs for fluid motion"}},
                        },
                    },
                }
            elif url == "https://query.wikidata.org/sparql":
                response.json.return_value = {
                    "results": {
                        "bindings": [{
                            "itemLabel": {"xml:lang": "en", "type": "literal", "value": "Navier–Stokes equations"},
                            "description": {"xml:lang": "en", "type": "literal", "value": "PDEs for fluid motion"},
                            "formula_sparql": {
                                "datatype": "http://www.w3.org/1998/Math/MathML",
                                "type": "literal",
                                "value": "<math>rho</math>",
                            },
                        }],
                    },
                }
            else:
                response.json.return_value = {}
            return response

        mock_client = MagicMock()
        mock_client.get.side_effect = _fake_get
        mock_client_class.return_value = mock_client

        adapter = WikidataFormulaAdapter()
        result = adapter.get_formula("Q201321")
        adapter.close()

        assert result is not None
        assert result.id == "Q201321"
        assert "rho" in result.latex

class TestFormulaSearchTool:
    """MCP formula_search tool normalizes inputs and adds LLM workflow hints."""

    def test_tool_normalizes_domain_and_query(self) -> None:
        """Lightweight unit test: ensure the tool uses normalized values."""
        from symkit.domain.formula_search_query import normalize_formula_search_inputs

        result = normalize_formula_search_inputs(
            "Navier–Stokes equations", "fluid_dynamics"
        )
        assert result["query"] == "navier-stokes equations"
        assert result["domain"] == "fluid_dynamics"
        assert "ns equations" in result["query_variants"]

class TestLocalFormulaLibrary:
    """The local YAML library loads entries and supports ranked search."""

    def test_loads_default_library(self):
        """Default library path points to the bundled formulas/library directory."""
        library = FormulaLibrary()
        assert library.list_formula_ids()
        assert "reynolds_number" in library.list_formula_ids()

    def test_search_by_name_returns_ranked_results(self):
        library = FormulaLibrary()
        results = library.search("Reynolds number", limit=5)
        assert results
        scores = [score for score, _entry in results]
        assert scores == sorted(scores, reverse=True)
        top_id = results[0][1].id
        assert top_id == "reynolds_number"

    def test_search_by_alias(self):
        library = FormulaLibrary()
        results = library.search("ns equations", limit=5)
        ids = {entry.id for _score, entry in results}
        assert "ns_incompressible" in ids

    def test_search_by_domain(self):
        library = FormulaLibrary()
        results = library.search("", domain="fluid_dynamics", limit=10)
        ids = {entry.id for _score, entry in results}
        assert "ns_incompressible" in ids

    def test_generic_stopwords_do_not_match_all_formulas(self):
        library = FormulaLibrary()
        # "Einstein field equations" has no match in the bundled local library.
        # The generic word "equations" must not return every fluid formula.
        results = library.search("Einstein field equations", limit=10)
        ids = {entry.id for _score, entry in results}
        assert "ns_incompressible" not in ids
        assert "euler_equations_inviscid" not in ids

    def test_add_or_update_persists_entry(self, tmp_path):
        library = FormulaLibrary(tmp_path)
        entry = FormulaEntry(
            id="test_drag_force",
            name="Drag force",
            sympy_str="F_d == 1/2 * rho * v**2 * C_d * A",
            latex="F_d = \\\\frac{1}{2} \\\\rho v^2 C_d A",
            domain="fluid_dynamics",
            category="fluid_dynamics",
            description="Test drag formula",
            aliases=["drag"],
            tags=["drag", "force"],
            variables={"F_d": {"description": "drag force"}},
        )
        library.add_or_update(entry)

        assert (tmp_path / "fluid_dynamics" / "test_drag_force.yaml").exists()

        # Re-load from disk
        library2 = FormulaLibrary(tmp_path)
        reloaded = library2.get("test_drag_force")
        assert reloaded is not None
        assert reloaded.name == "Drag force"
        assert reloaded.variables["F_d"]["description"] == "drag force"

class TestLocalFormulaAdapter:
    """LocalFormulaAdapter exposes the library via the BaseAdapter interface."""

    def test_search_returns_formula_info(self):
        adapter = LocalFormulaAdapter()
        results = adapter.search("Reynolds number", limit=3)
        assert results
        top = results[0]
        assert top.id == "reynolds_number"
        assert top.source == "local"
        assert top.sympy_str
        assert "load_hint" in top.extra

    def test_get_formula_by_id(self):
        adapter = LocalFormulaAdapter()
        result = adapter.get_formula("reynolds_number")
        assert result is not None
        assert result.name == "Reynolds number"
        assert result.source == "local"

    def test_list_categories(self):
        adapter = LocalFormulaAdapter()
        categories = adapter.list_categories()
        assert "fluid_dynamics" in categories

if __name__ == "__main__":
    unittest.main()

class TestDerivedCorpus:
    """Derived formulas (formulas/derived) must be searchable, not just seeds
    and the user overlay (black-box run-002 finding: an existing SA model
    formula was invisible to formula_search)."""

    def test_derived_formulas_are_searchable(self, tmp_path):
        import yaml

        derived = tmp_path / "derived" / "fluid_dynamics"
        derived.mkdir(parents=True)
        (derived / "sa_model.yaml").write_text(
            yaml.safe_dump({
                "id": "sa_turbulence_model",
                "name": "Spalart-Allmaras turbulence model",
                "sympy_str": "dnu_tilde_dt == c_b1*S_tilde*nu_tilde - c_w1*f_w*(nu_tilde/d)**2",
                "domain": "fluid_dynamics",
                "category": "fluid_dynamics",
                "tags": ["turbulence", "rans", "spalart-allmaras"],
                "description": "Spalart-Allmaras one-equation RANS turbulence model",
            }),
            encoding="utf-8",
        )
        lib = FormulaLibrary(derived_path=tmp_path / "derived")
        hits = lib.search("spalart allmaras turbulence model")
        assert any(entry.id == "sa_turbulence_model" for _score, entry in hits)

    def test_user_overlay_overrides_derived_entry(self, tmp_path):
        import yaml

        derived = tmp_path / "derived"
        overlay = tmp_path / "library"
        for root, name in ((derived, "derived version"),
                           (overlay, "overlay version")):
            (root / "x").mkdir(parents=True, exist_ok=True)
            (root / "x" / "dup.yaml").write_text(
                yaml.safe_dump({"id": "dup", "name": name}), encoding="utf-8")
        lib = FormulaLibrary(library_path=overlay, derived_path=derived)
        assert lib.get("dup").name == "overlay version"

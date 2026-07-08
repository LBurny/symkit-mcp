"""
Wikidata Formula Adapter - Look up formulas from Wikidata

Wikidata is the most powerful public source of structured formulas:
- P2534: Defining Formula - LaTeX format
- P4020: Dimension
- P7235: Variable description

Uses SPARQL queries via the Wikidata Query Service.
Direct precise retrieval, no RAG.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from sympy.parsing.latex import parse_latex

from symkit.domain.formula_search_query import (
    expand_query_variants,
    normalize_formula_query,
    resolve_domain_alias,
)

from .base import BaseAdapter, FormulaInfo

# Wikidata SPARQL endpoint
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Wikidata entity URI prefix, used to extract QIDs from result bindings.
_WIKIDATA_ENTITY_PREFIX = "http://www.wikidata.org/entity/"

# Datatype used by Wikidata for MathML formula values.
_MATHML_DATATYPE = "http://www.w3.org/1998/Math/MathML"

# Commonly used Wikidata properties
WD_PROPS = {
    "defining_formula": "P2534",  # Defining formula
    "dimension": "P4020",  # Dimension
    "quantity_symbol": "P7235",  # Symbol
    "instance_of": "P31",  # Instance of
    "subclass_of": "P279",  # Subclass of
    "described_by_source": "P1343",  # Described by source
}

# Score weights for each search strategy. Higher is better.
_STRATEGY_SCORES = {
    "label_and_alias": 0.85,
    "description": 0.5,
    "symbol": 0.65,
    "domain_only": 0.3,
}


class WikidataFormulaAdapter(BaseAdapter):
    """
    Wikidata formula lookup adapter

    Provides lookup of physical quantities and formulas from Wikidata.

    Example:
        adapter = WikidataFormulaAdapter()
        results = adapter.search("Reynolds number")
        formula = adapter.get_formula("Q179057")
    """

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def source_name(self) -> str:
        return "wikidata"

    def _get_client(self) -> httpx.Client:
        """Get the HTTP client (lazy-loaded)."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                headers={
                    "User-Agent": "SymKit/1.0 (https://github.com/symkit; formula-mcp)",
                    "Accept": "application/sparql-results+json",
                },
            )
        return self._client

    def _execute_sparql(self, query: str) -> dict[str, Any]:
        """Run a SPARQL query."""
        client = self._get_client()
        response = client.get(WIKIDATA_SPARQL_ENDPOINT, params={"query": query, "format": "json"})
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def search(self, query: str, limit: int = 10) -> list[FormulaInfo]:
        """
        Search for formulas across Wikidata.

        Uses a multi-strategy pipeline: exact label match, normalized label
        substring match (with dash-variant expansion), alias match, description
        match, and formula-symbol match. Results are deduplicated and scored.

        Args:
            query: Search keyword (e.g., "Reynolds number", "Arrhenius")
            limit: Maximum number of results to return

        Returns:
            List of matching formulas ordered by relevance score.
        """
        return self._search_with_strategies(query, None, limit)

    def search_by_category(
        self, category: str, query: str = "", limit: int = 20
    ) -> list[FormulaInfo]:
        """
        Search for formulas by category.

        Args:
            category: Category (e.g., "mechanics", "thermodynamics")
            query: Additional keyword filter
            limit: Maximum number of results to return
        """
        canonical_category = resolve_domain_alias(category) or category
        return self._search_with_strategies(query, canonical_category, limit)

    def _search_with_strategies(
        self, query: str, category: str | None, limit: int
    ) -> list[FormulaInfo]:
        """Run SPARQL search and fall back to the Wikidata web API if needed.

        The Wikidata Query Service can be aggressively rate-limited during
        outages.  We therefore use a single SPARQL label+alias query first, then
        fall back to the more reliable (but slower) web API entity search.
        """
        normalized = normalize_formula_query(query)
        variants = expand_query_variants(query) if query else []

        seen: set[str] = set()
        scored_results: list[tuple[float, FormulaInfo]] = []
        sparql_failed = False

        # Primary: SPARQL label + altLabel (fastest when healthy).
        if normalized:
            try:
                sparql = self._build_label_sparql(variants, category, limit)
                data = self._execute_sparql(sparql)
                for info in self._parse_search_results(data):
                    if info.id in seen:
                        continue
                    seen.add(info.id)
                    info.extra = info.extra or {}
                    info.extra["score"] = _STRATEGY_SCORES.get("label_and_alias", 0.85)
                    info.extra["strategy"] = "label_and_alias"
                    scored_results.append((info.extra["score"], info))
            except Exception as e:
                print(f"Wikidata SPARQL label search failed: {e}")
                sparql_failed = True

        # If SPARQL failed or returned nothing, try the web API fallback.
        if not scored_results:
            api_results = self._search_via_api(query, limit)
            if api_results:
                return api_results

        # If API fallback also returned nothing, try remaining SPARQL strategies.
        if not scored_results and normalized and not sparql_failed:
            secondary_strategies: list[tuple[str, str]] = [
                ("description", self._build_description_sparql(variants, category, limit)),
                ("symbol", self._build_symbol_sparql(variants, category, limit)),
            ]
            if category:
                secondary_strategies.append(("domain_only", self._build_domain_sparql(category, limit)))

            for strategy_name, sparql in secondary_strategies:
                if len(scored_results) >= limit:
                    break
                try:
                    data = self._execute_sparql(sparql)
                    for info in self._parse_search_results(data):
                        if info.id in seen:
                            continue
                        seen.add(info.id)
                        score = _STRATEGY_SCORES.get(strategy_name, 0.5)
                        info.extra = info.extra or {}
                        info.extra["score"] = score
                        info.extra["strategy"] = strategy_name
                        scored_results.append((score, info))
                except Exception as e:
                    print(f"Wikidata strategy '{strategy_name}' failed: {e}")

        # Final fallback: API search if no SPARQL strategy produced results.
        if not scored_results:
            return self._search_via_api(query, limit)

        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [info for _, info in scored_results[:limit]]

    def _search_via_api(self, query: str, limit: int) -> list[FormulaInfo]:
        """Search Wikidata using the web API entity search, then filter by P2534.

        This is used as a fallback when the Wikidata Query Service (SPARQL) is
        rate-limited or unavailable.  It calls ``wbsearchentities`` to find
        candidate items by label/alias, then fetches the P2534 claim for each
        candidate to confirm it has a defining formula.
        """
        if not query:
            return []

        try:
            api_url = "https://www.wikidata.org/w/api.php"
            search_params = {
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                # Fetch extra candidates because some will lack a P2534 claim.
                "limit": min(limit * 3, 50),
            }
            response = self._get_client().get(
                api_url, params=search_params, timeout=self._timeout
            )
            response.raise_for_status()
            payload = response.json()
            search_results = payload.get("search", [])

            results: list[FormulaInfo] = []
            for entity in search_results:
                qid = entity.get("id", "")
                if not qid or qid in {info.id for info in results}:
                    continue

                formula_latex = self._fetch_formula_string_via_api(qid)
                if not formula_latex:
                    continue

                results.append(
                    FormulaInfo(
                        id=qid,
                        name=entity.get("label", ""),
                        expression=formula_latex,
                        latex=formula_latex,
                        sympy_str="",
                        source="wikidata",
                        description=entity.get("description", ""),
                        url=f"https://www.wikidata.org/wiki/{qid}",
                        extra={
                            "score": 0.75,
                            "strategy": "api_fallback",
                            "formula_datatype": "string",
                            "is_mathml": False,
                            "load_hint": f'formula_get("{qid}", source="wikidata")',
                        },
                    )
                )
                if len(results) >= limit:
                    break

            return results
        except Exception as e:
            print(f"Wikidata API search fallback failed: {e}")
            return []

    def _escape_sparql_string(self, value: str) -> str:
        """Escape a string for safe insertion into a SPARQL query."""
        return value.replace('\\', '\\\\').replace('"', '\\"').replace("\n", " ")

    def _dash_variant(self, term: str, target_var: str = "?itemLabel") -> str:
        """Return a SPARQL filter that matches both hyphen and en dash forms.

        If ``term`` contains no hyphens, the en dash variant would be identical,
        so only one CONTAINS clause is emitted.
        """
        en_dash_term = term.replace("-", "\u2013")
        term_filter = f'CONTAINS(LCASE({target_var}), "{self._escape_sparql_string(term)}")'
        if term == en_dash_term:
            return term_filter
        return f'{term_filter} || CONTAINS(LCASE({target_var}), "{self._escape_sparql_string(en_dash_term)}")'

    def _build_label_sparql(self, variants: list[str], category: str | None, limit: int) -> str:
        """Build a SPARQL query that matches item labels and alt labels (with dash variants)."""
        clean_variants = [v for v in variants if v]
        if not clean_variants:
            clean_variants = [""]
        label_filters = " || ".join(self._dash_variant(v, "?itemLabel") for v in clean_variants)
        alt_filters = " || ".join(self._dash_variant(v, "?altLabel") for v in clean_variants)
        category_clause = self._category_clause(category) if category else ""
        return f'''
        SELECT DISTINCT ?item ?itemLabel ?formula ?description WHERE {{
          ?item wdt:P2534 ?formula.
          ?item rdfs:label ?itemLabel.
          FILTER(LANG(?itemLabel) = "en")
          FILTER({label_filters})
          OPTIONAL {{
            ?item skos:altLabel ?altLabel.
            FILTER(LANG(?altLabel) = "en")
            FILTER({alt_filters})
          }}
          {category_clause}
          OPTIONAL {{
            ?item schema:description ?description.
            FILTER(LANG(?description) = "en")
          }}
        }}
        LIMIT {limit}
        '''

    def _build_description_sparql(self, variants: list[str], category: str | None, limit: int) -> str:
        """Build a SPARQL query that matches schema:description."""
        filters = " || ".join(
            f'CONTAINS(LCASE(?description), "{self._escape_sparql_string(v)}")'
            for v in variants if v
        )
        category_clause = self._category_clause(category) if category else ""
        return f'''
        SELECT DISTINCT ?item ?itemLabel ?formula ?description WHERE {{
          ?item wdt:P2534 ?formula.
          ?item rdfs:label ?itemLabel.
          ?item schema:description ?description.
          FILTER(LANG(?itemLabel) = "en")
          FILTER(LANG(?description) = "en")
          FILTER({filters})
          {category_clause}
        }}
        LIMIT {limit}
        '''

    def _build_symbol_sparql(self, variants: list[str], category: str | None, limit: int) -> str:
        """Build a SPARQL query that matches the quantity symbol (P7235)."""
        filters = " || ".join(
            f'LCASE(?symbol) = "{self._escape_sparql_string(v)}"'
            for v in variants if v
        )
        category_clause = self._category_clause(category) if category else ""
        return f'''
        SELECT DISTINCT ?item ?itemLabel ?formula ?description WHERE {{
          ?item wdt:P2534 ?formula.
          ?item wdt:P7235 ?symbol.
          ?item rdfs:label ?itemLabel.
          FILTER(LANG(?itemLabel) = "en")
          FILTER({filters})
          {category_clause}
          OPTIONAL {{
            ?item schema:description ?description.
            FILTER(LANG(?description) = "en")
          }}
        }}
        LIMIT {limit}
        '''

    def _build_domain_sparql(self, category: str, limit: int) -> str:
        """Build a SPARQL query that returns formulas within a category."""
        category_mapping = {
            "mechanics": "Q11397",
            "thermodynamics": "Q11473",
            "electromagnetism": "Q12453",
            "optics": "Q11413",
            "quantum": "Q11424",
            "quantum_mechanics": "Q11424",
            "fluid": "Q4323994",
            "fluid_dynamics": "Q4323994",
            "fluid_mechanics": "Q4323994",
            "chemistry": "Q2329",
            "pharmacokinetics": "Q899794",
            "general_relativity": "Q335",
            "gravity": "Q335",
            "gravitation": "Q335",
            "relativity": "Q335",
            "cosmology": "Q338",
            "astrophysics": "Q338",
        }
        qid = category_mapping.get(category.lower(), category)
        return f'''
        SELECT DISTINCT ?item ?itemLabel ?formula ?description WHERE {{
          ?item wdt:P2534 ?formula.
          ?item wdt:P31/wdt:P279* wd:{qid}.
          ?item rdfs:label ?itemLabel.
          FILTER(LANG(?itemLabel) = "en")
          OPTIONAL {{
            ?item schema:description ?description.
            FILTER(LANG(?description) = "en")
          }}
        }}
        LIMIT {limit}
        '''

    def _category_clause(self, category: str) -> str:
        """Return a SPARQL clause that restricts results to a Wikidata category."""
        category_mapping = {
            "mechanics": "Q11397",
            "thermodynamics": "Q11473",
            "electromagnetism": "Q12453",
            "optics": "Q11413",
            "quantum": "Q11424",
            "quantum_mechanics": "Q11424",
            "fluid": "Q4323994",
            "fluid_dynamics": "Q4323994",
            "fluid_mechanics": "Q4323994",
            "chemistry": "Q2329",
            "pharmacokinetics": "Q899794",
            "general_relativity": "Q335",
            "gravity": "Q335",
            "gravitation": "Q335",
            "relativity": "Q335",
            "cosmology": "Q338",
            "astrophysics": "Q338",
        }
        qid = category_mapping.get(category.lower(), category)
        return f"?item wdt:P31/wdt:P279* wd:{qid}."

    def _fetch_entity_metadata_via_api(self, qid: str) -> dict[str, Any]:
        """Fetch entity label and description from the Wikidata web API."""
        try:
            api_url = "https://www.wikidata.org/w/api.php"
            params = {
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|descriptions",
                "languages": "en",
                "format": "json",
            }
            response = self._get_client().get(api_url, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
            entity = payload.get("entities", {}).get(qid, {})
            labels = entity.get("labels", {})
            descriptions = entity.get("descriptions", {})
            return {
                "name": labels.get("en", {}).get("value", ""),
                "description": descriptions.get("en", {}).get("value", ""),
            }
        except Exception as e:
            print(f"Wikidata API entity metadata fetch failed for {qid}: {e}")
            return {}

    def _build_formula_info_from_api(self, qid: str) -> FormulaInfo | None:
        """Build a FormulaInfo entirely from the Wikidata web API (no SPARQL).

        Fetches the P2534 LaTeX string and entity metadata in parallel to keep
        latency low inside MCP calls.
        """
        with ThreadPoolExecutor(max_workers=2) as executor:
            formula_future = executor.submit(self._fetch_formula_string_via_api, qid)
            metadata_future = executor.submit(self._fetch_entity_metadata_via_api, qid)
            latex_formula = formula_future.result(timeout=self._timeout)
            metadata = metadata_future.result(timeout=self._timeout)

        if not latex_formula:
            return None

        name = metadata.get("name", "")
        description = metadata.get("description", "")

        sympy_expr = None
        sympy_str = ""
        try:
            sympy_expr = parse_latex(latex_formula)
            sympy_str = str(sympy_expr)
        except Exception:
            sympy_str = latex_formula

        variables = self._extract_variables_from_latex(latex_formula)

        return FormulaInfo(
            id=qid,
            name=name,
            expression=sympy_expr if sympy_expr is not None else latex_formula,
            latex=latex_formula,
            sympy_str=sympy_str,
            variables=variables,
            source="wikidata",
            description=description,
            url=f"https://www.wikidata.org/wiki/{qid}",
            extra={},
        )

    def get_formula(self, formula_id: str) -> FormulaInfo | None:
        """
        Get details of a single formula.

        Prefers the Wikidata web API (`wbgetclaims` for P2534 LaTeX and
        `wbgetentities` for labels/descriptions) because it returns the original
        LaTeX string and is generally faster and more available than the SPARQL
        Query Service. Falls back to SPARQL only when the API has no defining
        formula for the item.

        Args:
            formula_id: Wikidata Q number (e.g., "Q179057")

        Returns:
            Detailed formula information
        """
        # Remove any possible prefix
        qid = formula_id.upper()
        if not qid.startswith("Q"):
            qid = f"Q{qid}"

        # Fast path: build everything from the Wikidata web API.
        api_result = self._build_formula_info_from_api(qid)
        if api_result is not None:
            return api_result

        # Fallback: SPARQL may still have a formula when the API lacks P2534.
        # The SPARQL value is often MathML, so we keep it as the raw formula string.
        sparql = f"""
        SELECT ?itemLabel ?description ?formula_sparql ?dimension ?symbol WHERE {{
          BIND(wd:{qid} AS ?item)
          ?item wdt:P2534 ?formula_sparql.
          ?item rdfs:label ?itemLabel.
          FILTER(LANG(?itemLabel) = "en")
          OPTIONAL {{
            ?item schema:description ?description.
            FILTER(LANG(?description) = "en")
          }}
          OPTIONAL {{ ?item wdt:P4020 ?dimension. }}
          OPTIONAL {{ ?item wdt:P7235 ?symbol. }}
        }}
        LIMIT 1
        """

        try:
            data = self._execute_sparql(sparql)
            bindings = data.get("results", {}).get("bindings", [])

            if not bindings:
                return None

            binding = bindings[0]
            name = binding.get("itemLabel", {}).get("value", "")
            description = binding.get("description", {}).get("value", "")
            dimension = binding.get("dimension", {}).get("value", "")
            symbol = binding.get("symbol", {}).get("value", "")

            # SPARQL returns the rendered formula (often MathML). Try to get the
            # original LaTeX from the web API one more time; if that fails, use
            # the SPARQL value as a last resort.
            latex_formula = self._fetch_formula_string_via_api(qid)
            if not latex_formula:
                latex_formula = binding.get("formula_sparql", {}).get("value", "")

            # Try to parse LaTeX as SymPy
            sympy_expr = None
            sympy_str = ""
            try:
                sympy_expr = parse_latex(latex_formula)
                sympy_str = str(sympy_expr)
            except Exception:
                sympy_str = latex_formula  # Fall back to raw string

            # Extract variables
            variables = self._extract_variables_from_latex(latex_formula)

            return FormulaInfo(
                id=qid,
                name=name,
                expression=sympy_expr if sympy_expr is not None else latex_formula,
                latex=latex_formula,
                sympy_str=sympy_str,
                variables=variables,
                source="wikidata",
                description=description,
                url=f"https://www.wikidata.org/wiki/{qid}",
                extra={
                    "dimension": dimension,
                    "symbol": symbol,
                },
            )
        except Exception as e:
            print(f"Wikidata get_formula SPARQL error: {e}")
            return None

    def _fetch_formula_string_via_api(self, qid: str) -> str:
        """Fetch the original P2534 LaTeX string from the Wikidata web API.

        Falls back to an empty string if the item has no P2534 claim or the
        request fails.
        """
        try:
            api_url = "https://www.wikidata.org/w/api.php"
            params = {
                "action": "wbgetclaims",
                "entity": qid,
                "property": WD_PROPS["defining_formula"],
                "format": "json",
            }
            response = self._get_client().get(api_url, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
            claims = payload.get("claims", {}).get(WD_PROPS["defining_formula"], [])
            if claims:
                value = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
                if isinstance(value, str):
                    return value
        except Exception as e:
            print(f"Wikidata API formula fetch failed for {qid}: {e}")
        return ""

    def list_categories(self) -> list[str]:
        """List available formula categories."""
        return [
            "mechanics",
            "thermodynamics",
            "electromagnetism",
            "optics",
            "quantum",
            "fluid",
            "chemistry",
            "pharmacokinetics",
        ]

    def _parse_search_results(self, data: dict[str, Any]) -> list[FormulaInfo]:
        """Parse SPARQL search results.

        The SPARQL endpoint returns the *rendered* formula value, which is often
        MathML.  We preserve that value and add a hint that ``formula_get``
        should be used to obtain the original LaTeX/SymPy representation.
        """
        results = []
        bindings = data.get("results", {}).get("bindings", [])

        for binding in bindings:
            item_uri = binding.get("item", {}).get("value", "")
            qid = item_uri.split(_WIKIDATA_ENTITY_PREFIX)[-1] if item_uri else ""
            formula_value = binding.get("formula", {}).get("value", "")
            formula_datatype = binding.get("formula", {}).get("datatype", "")
            is_mathml = formula_datatype == _MATHML_DATATYPE or formula_value.strip().startswith("<math")

            # Try to convert to a SymPy expression.  LaTeX values work directly;
            # MathML values fall back to the raw string and are enriched later
            # by ``formula_get`` via the Wikidata web API.
            sympy_str = ""
            sympy_expr = None
            latex_value = formula_value
            try:
                if not is_mathml:
                    sympy_expr = parse_latex(formula_value)
                    sympy_str = str(sympy_expr)
            except Exception:
                sympy_str = formula_value

            results.append(
                FormulaInfo(
                    id=qid,
                    name=binding.get("itemLabel", {}).get("value", ""),
                    expression=sympy_expr if sympy_expr else formula_value,
                    latex=latex_value,
                    sympy_str=sympy_str,
                    source="wikidata",
                    description=binding.get("description", {}).get("value", ""),
                    url=f"https://www.wikidata.org/wiki/{qid}" if qid else "",
                    extra={
                        "formula_datatype": formula_datatype,
                        "is_mathml": is_mathml,
                        "load_hint": f'formula_get("{qid}", source="wikidata")',
                    },
                )
            )

        return results

    def _extract_variables_from_latex(self, latex_str: str) -> dict[str, dict[str, Any]]:
        """Extract variables from a LaTeX formula."""
        variables: dict[str, dict[str, Any]] = {}

        # Common single-letter variables
        single_vars = re.findall(r"(?<![a-zA-Z])([a-zA-Z])(?![a-zA-Z])", latex_str)

        # Subscripted variables (e.g., v_0, T_c)
        subscript_vars = re.findall(r"([a-zA-Z])_\{?([a-zA-Z0-9]+)\}?", latex_str)

        # Greek letters
        greek_vars = re.findall(
            r"\\(alpha|beta|gamma|delta|epsilon|theta|lambda|mu|nu|rho|sigma|tau|omega|Omega)",
            latex_str,
        )

        for var in single_vars:
            if var not in ["d", "e", "i"]:  # Exclude differential symbol, natural log, imaginary unit
                variables[var] = {"type": "variable"}

        for base, sub in subscript_vars:
            var_name = f"{base}_{sub}"
            variables[var_name] = {"type": "variable", "subscript": sub}

        for greek in greek_vars:
            variables[greek] = {"type": "variable", "greek": "True"}

        return variables

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "WikidataFormulaAdapter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()

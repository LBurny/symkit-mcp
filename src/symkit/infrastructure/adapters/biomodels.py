"""
BioModels Adapter - Source for pharmacology / PK-PD model formulas

BioModels is a database of biological mathematical models maintained by EMBL-EBI:
- Thousands of published PK/PD, metabolism, and signaling models
- SBML (Systems Biology Markup Language) format
- Includes kinetic equations, parameters, and units

API docs: https://www.ebi.ac.uk/biomodels/docs/

Key extractions:
- Kinetic Laws (reaction rate formulas)
- Rate Constants
- Species (substance concentrations)

Direct precise retrieval, no RAG.
"""

import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from .base import BaseAdapter, FormulaInfo

# BioModels API endpoint
BIOMODELS_API = "https://www.ebi.ac.uk/biomodels"


class BioModelsAdapter(BaseAdapter):
    """
    BioModels SBML formula adapter

    Focused on pharmacokinetics (PK) and pharmacodynamics (PD) models.

    Example:
        adapter = BioModelsAdapter()
        results = adapter.search("pharmacokinetics")
        model = adapter.get_formula("BIOMD0000000012")
    """

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def source_name(self) -> str:
        return "biomodels"

    def _get_client(self) -> httpx.Client:
        """Get the HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                headers={
                    "User-Agent": "SymKit/1.0",
                    "Accept": "application/json",
                },
            )
        return self._client

    def search(self, query: str, limit: int = 10) -> list[FormulaInfo]:
        """
        Search BioModels models.

        Args:
            query: Search keyword (e.g., "pharmacokinetics", "Michaelis-Menten")
            limit: Maximum number of results to return

        Returns:
            List of matching models
        """
        client = self._get_client()

        try:
            # Use the BioModels search API
            response = client.get(
                f"{BIOMODELS_API}/search",
                params={
                    "query": query,
                    "numResults": limit,
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_search_results(data)
        except Exception as e:
            print(f"BioModels search error: {e}")
            return []

    def search_pk_models(self, drug: str = "", limit: int = 10) -> list[FormulaInfo]:
        """
        Search specifically for pharmacokinetic models.

        Args:
            drug: Drug name (optional)
            limit: Maximum number of results to return
        """
        query = f"pharmacokinetics {drug}".strip()
        return self.search(query, limit)

    def search_pd_models(self, effect: str = "", limit: int = 10) -> list[FormulaInfo]:
        """
        Search specifically for pharmacodynamic models.

        Args:
            effect: Effect type (optional)
            limit: Maximum number of results to return
        """
        query = f"pharmacodynamics {effect}".strip()
        return self.search(query, limit)

    def search_enzyme_kinetics(self, enzyme: str = "", limit: int = 10) -> list[FormulaInfo]:
        """
        Search for enzyme kinetics models (Michaelis-Menten, etc.).

        Args:
            enzyme: Enzyme name (optional)
            limit: Maximum number of results to return
        """
        query = f"enzyme kinetics {enzyme}".strip()
        return self.search(query, limit)

    def get_formula(self, formula_id: str) -> FormulaInfo | None:
        """
        Get model details and extract formulas.

        Args:
            formula_id: BioModels ID (e.g., "BIOMD0000000012")

        Returns:
            Model information (including extracted kinetic formulas)
        """
        client = self._get_client()

        try:
            # Fetch model information
            info_response = client.get(
                f"{BIOMODELS_API}/model/{formula_id}", params={"format": "json"}
            )
            info_response.raise_for_status()
            model_info = info_response.json()

            # Download the SBML file
            sbml_response = client.get(
                f"{BIOMODELS_API}/model/download/{formula_id}",
                params={"filename": f"{formula_id}_url.xml"},
            )
            sbml_response.raise_for_status()
            sbml_content = sbml_response.text

            # Parse SBML and extract formulas
            kinetic_laws = self._extract_kinetic_laws(sbml_content)

            # Combine all kinetic formulas into one string
            formulas_text = "\n".join([f"{kl['reaction_id']}: {kl['math']}" for kl in kinetic_laws])

            return FormulaInfo(
                id=formula_id,
                name=model_info.get("name", formula_id),
                expression=formulas_text,
                latex="",  # SBML formulas are not in LaTeX format
                sympy_str=formulas_text,
                variables=self._extract_variables(kinetic_laws),
                source="biomodels",
                category="pharmacokinetics"
                if "pharmacokinetic" in model_info.get("name", "").lower()
                else "biology",
                description=model_info.get("description", ""),
                url=f"https://www.ebi.ac.uk/biomodels/{formula_id}",
                tags=self._extract_tags(model_info),
                extra={
                    "kinetic_laws": kinetic_laws,
                    "publication": model_info.get("publication", {}),
                    "authors": model_info.get("authors", []),
                },
            )
        except Exception as e:
            print(f"BioModels get_formula error: {e}")
            return None

    def get_kinetic_laws(self, model_id: str) -> list[dict[str, Any]]:
        """
        Get the list of kinetic laws directly from a model.

        Args:
            model_id: BioModels ID

        Returns:
            List of kinetic laws, each containing:
            - reaction_id: Reaction ID
            - name: Reaction name
            - math: Mathematical expression (MathML converted to string)
            - parameters: Parameter table
        """
        client = self._get_client()

        try:
            response = client.get(
                f"{BIOMODELS_API}/model/download/{model_id}",
                params={"filename": f"{model_id}_url.xml"},
            )
            response.raise_for_status()
            return self._extract_kinetic_laws(response.text)
        except Exception as e:
            print(f"BioModels get_kinetic_laws error: {e}")
            return []

    def list_categories(self) -> list[str]:
        """List commonly used BioModels categories."""
        return [
            "pharmacokinetics",
            "pharmacodynamics",
            "enzyme_kinetics",
            "metabolism",
            "signaling",
            "cell_cycle",
            "immunology",
        ]

    def _parse_search_results(self, data: dict[str, Any]) -> list[FormulaInfo]:
        """Parse search results."""
        results = []
        models = data.get("models", [])

        for model in models:
            model_id = model.get("id", "")
            results.append(
                FormulaInfo(
                    id=model_id,
                    name=model.get("name", model_id),
                    expression="",  # Search results do not contain full formulas
                    latex="",
                    sympy_str="",
                    source="biomodels",
                    description=model.get("description", "")[:200],  # Truncate
                    url=f"https://www.ebi.ac.uk/biomodels/{model_id}",
                    tags=self._extract_tags(model),
                )
            )

        return results

    def _extract_kinetic_laws(self, sbml_content: str) -> list[dict[str, Any]]:
        """Extract kinetic laws from SBML."""
        kinetic_laws = []

        try:
            # Parse XML (BioModels is a trusted source)
            root = ET.fromstring(sbml_content)  # nosec B314

            # SBML namespaces
            namespaces = {
                "sbml": "http://www.sbml.org/sbml/level2/version4",
                "sbml3": "http://www.sbml.org/sbml/level3/version1/core",
                "mathml": "http://www.w3.org/1998/Math/MathML",
            }

            # Try different SBML versions
            for ns_prefix in ["sbml", "sbml3", ""]:
                ns = namespaces.get(ns_prefix, "")
                ns_str = f"{{{ns}}}" if ns else ""

                # Find all reactions
                reactions = root.findall(f".//{ns_str}reaction")
                if not reactions:
                    reactions = root.findall(".//reaction")

                for reaction in reactions:
                    reaction_id = reaction.get("id", "")
                    reaction_name = reaction.get("name", reaction_id)

                    # Find kineticLaw
                    kinetic_law = reaction.find(f"{ns_str}kineticLaw") or reaction.find(
                        "kineticLaw"
                    )

                    if kinetic_law is not None:
                        # Extract MathML and convert to string
                        math_elem = kinetic_law.find(".//{http://www.w3.org/1998/Math/MathML}math")
                        if math_elem is None:
                            math_elem = kinetic_law.find(".//math")

                        math_str = (
                            self._mathml_to_string(math_elem) if math_elem is not None else ""
                        )

                        # Extract parameters
                        params = self._extract_parameters(kinetic_law, ns_str)

                        kinetic_laws.append(
                            {
                                "reaction_id": reaction_id,
                                "name": reaction_name,
                                "math": math_str,
                                "parameters": params,
                            }
                        )

                if kinetic_laws:
                    break

        except Exception as e:
            print(f"SBML parsing error: {e}")

        return kinetic_laws

    def _mathml_to_string(self, math_elem: ET.Element) -> str:
        """Convert MathML to a readable string."""
        if math_elem is None:
            return ""

        def process_node(node: ET.Element) -> str:
            tag = node.tag.split("}")[-1]  # Remove namespace

            if tag == "ci":
                return node.text.strip() if node.text else ""
            elif tag == "cn":
                return node.text.strip() if node.text else "0"
            elif tag == "apply":
                children = list(node)
                if not children:
                    return ""
                op = children[0].tag.split("}")[-1]
                args = [process_node(c) for c in children[1:]]

                if op == "times":
                    return " * ".join(args)
                elif op == "divide":
                    return f"({args[0]}) / ({args[1]})" if len(args) >= 2 else ""
                elif op == "plus":
                    return " + ".join(args)
                elif op == "minus":
                    if len(args) == 1:
                        return f"-{args[0]}"
                    return f"({args[0]}) - ({args[1]})"
                elif op == "power":
                    return f"({args[0]})**({args[1]})" if len(args) >= 2 else ""
                elif op == "exp":
                    return f"exp({args[0]})" if args else "exp(0)"
                elif op == "ln":
                    return f"ln({args[0]})" if args else "ln(1)"
                else:
                    return f"{op}({', '.join(args)})"
            else:
                # Recursively process child nodes
                return "".join(process_node(c) for c in node)

        try:
            result: str = process_node(math_elem)
            return result
        except Exception:
            return ET.tostring(math_elem, encoding="unicode")

    def _extract_parameters(self, kinetic_law: ET.Element, ns_str: str) -> list[dict[str, Any]]:
        """Extract parameters of a kinetic law."""
        params = []

        param_elems = kinetic_law.findall(f"{ns_str}listOfParameters/{ns_str}parameter")
        if not param_elems:
            param_elems = kinetic_law.findall(".//parameter")

        for param in param_elems:
            params.append(
                {
                    "id": param.get("id", ""),
                    "name": param.get("name", ""),
                    "value": param.get("value", ""),
                    "units": param.get("units", ""),
                }
            )

        return params

    def _extract_variables(self, kinetic_laws: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Extract variables from kinetic laws."""
        variables: dict[str, dict[str, Any]] = {}

        for kl in kinetic_laws:
            # Extract from parameters
            for param in kl.get("parameters", []):
                param_id = param.get("id", "")
                if param_id:
                    variables[param_id] = {
                        "type": "parameter",
                        "value": param.get("value"),
                        "unit": param.get("units"),
                    }

            # Extract variable names from the formula string
            math_str = kl.get("math", "")
            # Simple variable extraction (identifiers starting with a letter)
            var_matches = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", math_str)
            for var in var_matches:
                if var not in variables and var not in ["exp", "ln", "log", "sin", "cos"]:
                    variables[var] = {"type": "variable"}

        return variables

    def _extract_tags(self, model_info: dict[str, Any]) -> list[str]:
        """Extract model tags."""
        tags = []

        name = model_info.get("name", "").lower()
        desc = model_info.get("description", "").lower()

        # Infer tags from name and description
        if "pharmacokinetic" in name or "pharmacokinetic" in desc:
            tags.append("pharmacokinetics")
        if "pharmacodynamic" in name or "pharmacodynamic" in desc:
            tags.append("pharmacodynamics")
        if "michaelis" in name or "michaelis" in desc:
            tags.append("enzyme_kinetics")
        if "metabolism" in name or "metabolism" in desc:
            tags.append("metabolism")
        if "absorption" in desc:
            tags.append("absorption")
        if "elimination" in desc or "clearance" in desc:
            tags.append("elimination")
        if "compartment" in desc:
            tags.append("compartmental")

        return tags

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "BioModelsAdapter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()

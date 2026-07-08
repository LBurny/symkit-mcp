"""DerivationGoal — Goal-aware derivation goal object.

Parses natural-language goals into a structured goal representation, used to
drive pattern selection, formula recommendation, and step planning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import sympy as sp

from symkit.domain.expression_parser import parse_expression_string

# Domain keyword mapping: used to infer domain from goal text
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "fluid_dynamics": ["fluid", "navier", "stokes", "flow", "incompressible", "viscosity"],
    "quantum_mechanics": ["quantum", "schrodinger", "heisenberg", "wave function", "operator"],
    "electromagnetism": ["maxwell", "electromagnetic", "electric", "magnetic", "field"],
    "thermodynamics": ["thermo", "entropy", "enthalpy", "temperature", "heat", "ideal gas"],
    "solid_mechanics": ["solid", "structure", "stress", "strain", "elasticity", "beam"],
    "optics": ["optics", "light", "lens", "interference", "diffraction"],
    "pharmacokinetics": ["pharmacokinetics", "pk", "drug", "elimination", "dose", "compartment"],
    "differential_eq": ["differential equation", "ode", "pde", "partial differential"],
    "linear_algebra": ["matrix", "eigenvalue", "linear system", "vector"],
    "calculus": ["derivative", "integral", "limit", "series"],
}

# Common assumption keywords
_ASSUMPTION_KEYWORDS: list[str] = [
    "incompressible",
    "compressible",
    "steady state",
    "steady-state",
    "unsteady",
    "inviscid",
    "viscous",
    "linear",
    "nonlinear",
    "irrotational",
    "conservative",
    "isothermal",
    "adiabatic",
    "isentropic",
    "ideal gas",
    "constant density",
    "constant temperature",
    "no friction",
    "no heat transfer",
    "first-order",
    "second-order",
]


# Math tokens that indicate an expression candidate is actually symbolic
_MATH_TOKEN_RE = re.compile(r"[\+\-\*/=^(){}\[\]0-9]")


# Single-letter tokens that are common English articles/pronouns and should not be
# treated as variables when the surrounding text has no math tokens.
_ARTICLE_STOPWORDS: set[str] = {"a", "i"}


# General stopwords for filtering candidates.  Note: because the variable extractor
# already skips multi-letter words without subscripts, this list primarily affects
# single-letter candidates and subscripted forms (e.g., x_of_t).
_VARIABLE_STOPWORDS: set[str] = {
    "the", "and", "for", "from", "with", "that", "this", "into", "about",
    "an", "as", "at", "be", "by", "in", "is", "it", "its", "no", "not",
    "of", "on", "or", "so", "to", "up", "us", "we", "do", "does", "did",
    "has", "have", "had", "can", "will", "would", "should", "may", "might",
    "must", "shall", "was", "were", "been", "being", "am", "are", "if",
    "then", "than", "there", "their", "them", "they", "he", "she", "his",
    "her", "him", "our", "me", "my", "you", "your", "but", "yet", "nor",
    "without", "onto", "through", "during", "before", "after",
    "above", "below", "between", "among", "within", "against", "under",
    "over", "again", "further", "once", "here", "when", "where", "why",
    "how", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "same", "own", "very", "now", "these", "those", "which",
    "who", "whom", "whose", "what", "whatever", "whichever", "whoever",
    "whomever", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "derive", "solve", "show", "prove", "find",
    "obtain", "simplify", "calculate", "compute", "reduce", "eliminate",
    "using", "expression", "equation", "function",
    "model", "law", "formula", "value",
}


def _has_math_tokens(text: str) -> bool:
    """Return True if the text contains characters that look like math operators."""
    return bool(_MATH_TOKEN_RE.search(text))


@dataclass
class DerivationGoal:
    """Structured derivation goal."""

    text: str
    target_expression: str | None = None
    target_form: str | None = None
    target_variables: list[str] = field(default_factory=list)
    domain: str = ""
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "target_expression": self.target_expression,
            "target_form": self.target_form,
            "target_variables": self.target_variables,
            "domain": self.domain,
            "assumptions": self.assumptions,
        }

    @classmethod
    def from_text(cls, text: str, domain: str = "") -> DerivationGoal:
        """Parse a goal from natural-language goal text."""
        target_expression = cls._extract_target_expression(text)
        target_form = cls._extract_target_form(text)
        target_variables = cls._extract_variables(text)
        detected_domain = domain or cls._detect_domain(text)
        assumptions = cls._extract_assumptions(text)

        return cls(
            text=text,
            target_expression=target_expression,
            target_form=target_form,
            target_variables=target_variables,
            domain=detected_domain,
            assumptions=assumptions,
        )

    @classmethod
    def _extract_target_expression(cls, text: str) -> str | None:
        """Try to extract the target expression from the goal text.

        Supports:
        - "derive X from Y" takes X
        - "show that X = Y" takes the equality
        - target expression enclosed in quotes

        To avoid capturing natural-language phrases (e.g., "the escape velocity
        of a planet"), the candidate must contain math tokens and be parseable.
        """
        # Try matching "derive <expr> from ..."
        match = re.search(
            r"(?:derive|find|obtain|simplify)\s+([a-zA-Z0-9_\^\*\+\-/\(\)\[\]\s,=.]+?)(?:\s+from|\s+where|$)",
            text,
            re.IGNORECASE,
        )
        if match:
            expr = match.group(1).strip()
            if cls._is_valid_expression_candidate(expr):
                return cls._normalize_expression(expr)

        # Try matching an expression inside quotes
        match = re.search(
            r"['\"]([a-zA-Z0-9_\^\*\+\-/\(\)\[\]\s,=.]+)['\"]",
            text,
        )
        if match:
            expr = match.group(1).strip()
            if cls._is_valid_expression_candidate(expr):
                return cls._normalize_expression(expr)

        return None

    @classmethod
    def _is_valid_expression_candidate(cls, expr: str) -> bool:
        """Return True if the extracted string looks like a mathematical expression."""
        if len(expr) < 3:
            return False
        if not _has_math_tokens(expr):
            return False
        # Reject long natural-language phrases that happen to contain an operator.
        non_op_tokens = [
            token
            for token in expr.split()
            if token and not all(ch in "=+-*/^()[]{}" for ch in token)
        ]
        if len(non_op_tokens) > 4:
            return False
        # Ensure it parses as a SymPy expression.
        try:
            parsed = parse_target_expression(cls._normalize_expression(expr))
        except Exception:
            return False
        return parsed is not None

    @classmethod
    def _normalize_expression(cls, expr: str) -> str:
        """Replace ^ with ** in the target expression for SymPy parsing."""
        return expr.replace("^", "**")

    @classmethod
    def _extract_target_form(cls, text: str) -> str | None:
        """Infer the target form."""
        lowered = text.lower()

        # solve for X
        match = re.search(r"(?:solve|find|express)\b(?:\s+\w+)?\s+for\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", lowered)
        if match:
            return f"solve_for_{match.group(1)}"

        # show equality / prove
        if any(phrase in lowered for phrase in ["show that", "prove that", "demonstrate that", "equality"]):
            return "show_equality"

        # reduce / eliminate variables
        if any(phrase in lowered for phrase in ["reduce", "eliminate", "fewer variables", "in terms of"]):
            return "reduce_symbols"

        # expand / approximate
        if any(phrase in lowered for phrase in ["expand", "approximate", "series"]):
            return "expand_series"

        # default
        return "derive_expression"

    @classmethod
    def _extract_variables(cls, text: str) -> list[str]:
        """Extract possible mathematical symbol variables.

        Includes: ASCII single letters, letters with subscripts, and Greek letters.
        English articles like "a" and "I" are only kept when the surrounding text
        contains math tokens, indicating an actual equation context.
        """
        # ASCII single letters or subscript forms (e.g., x_1, rho_0)
        ascii_candidates = re.findall(r"\b([a-zA-Z](?:_[a-zA-Z0-9]+)?)\b", text)
        # Greek letters (Unicode)
        greek_candidates = re.findall(r"[\u03B1-\u03C9\u0391-\u03A9]", text)

        has_math = _has_math_tokens(text)
        variables: list[str] = []
        for cand in ascii_candidates:
            if len(cand) > 1 and "_" not in cand:
                continue
            # In plain natural-language text, drop article-like single letters.
            if len(cand) == 1 and not has_math and cand.lower() in _ARTICLE_STOPWORDS:
                continue
            if cand.lower() in _VARIABLE_STOPWORDS:
                continue
            variables.append(cand)
        variables.extend(greek_candidates)

        # Deduplicate and preserve order
        seen: set[str] = set()
        unique: list[str] = []
        for v in variables:
            if v not in seen:
                seen.add(v)
                unique.append(v)
        return unique

    @classmethod
    def _detect_domain(cls, text: str) -> str:
        """Detect domain based on keywords."""
        lowered = text.lower()
        best_domain = ""
        best_score = 0
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lowered)
            if score > best_score:
                best_score = score
                best_domain = domain
        return best_domain

    @classmethod
    def _extract_assumptions(cls, text: str) -> list[str]:
        """Extract common assumptions explicitly appearing in the text."""
        lowered = text.lower()
        found = []
        for kw in _ASSUMPTION_KEYWORDS:
            if kw in lowered:
                found.append(kw)
        return found


def parse_target_expression(expr_str: str) -> sp.Basic | None:
    """Try to parse the target expression string into a SymPy object."""
    expr, _ = parse_expression_string(expr_str.replace("^", "**"), convert_equation=True)
    return expr

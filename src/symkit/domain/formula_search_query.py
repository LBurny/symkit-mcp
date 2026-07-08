"""Query normalization utilities for formula search.

This module turns the free-text queries that LLMs produce into the canonical
forms understood by the Wikidata / SciPy / BioModels adapters. It handles:

- Unicode dash normalization (en dash, em dash, minus sign → hyphen)
- Lowercasing and whitespace cleanup
- Domain-name alias resolution (``fluid_dynamics`` → ``fluid``)
- Formula-name alias expansion (``NS equations`` → ``Navier-Stokes equations``)

"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any, cast

from symkit.resources import load_yaml_resource


def _load_config() -> dict[str, Any]:
    """Load the bundled formula-search configuration."""
    return cast("dict[str, Any]", load_yaml_resource("formula_search_config.yaml"))


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    """Cached configuration object."""
    return _load_config()


@lru_cache(maxsize=1)
def _domain_alias_map() -> dict[str, str]:
    """Return a flat alias → canonical-domain mapping."""
    cfg = _config()
    return cast("dict[str, str]", cfg.get("domain_aliases", {}))


@lru_cache(maxsize=1)
def _formula_alias_map() -> dict[str, list[str]]:
    """Return canonical-name → list-of-aliases mapping."""
    cfg = _config()
    return cast("dict[str, list[str]]", cfg.get("formula_aliases", {}))


@lru_cache(maxsize=1)
def _reverse_formula_alias_map() -> dict[str, str]:
    """Return alias → canonical-name mapping for quick lookup."""
    reverse: dict[str, str] = {}
    for canonical, aliases in _formula_alias_map().items():
        reverse[canonical] = canonical
        for alias in aliases:
            reverse[normalize_formula_query(alias)] = canonical
    return reverse


# Unicode characters that should be treated as ASCII hyphens when normalizing
# formula queries.  This includes hyphen-minus, hyphen, non-breaking hyphen,
# figure dash, en dash, em dash, horizontal bar, minus sign, and fullwidth
# variants.
_DASH_CHARS = frozenset({
    "-",      # hyphen-minus / ASCII hyphen (U+002D)
    "\u2010", # hyphen (U+2010)
    "\u2011", # non-breaking hyphen (U+2011)
    "\u2012", # figure dash (U+2012)
    "\u2013", # en dash (U+2013)
    "\u2014", # em dash (U+2014)
    "\u2015", # horizontal bar (U+2015)
    "\u2212", # minus sign (U+2212)
    "\uFE63", # small hyphen-minus (U+FE63)
    "\uFF0D", # fullwidth hyphen-minus (U+FF0D)
})


_DASH_NORMALIZE_RE = re.compile(
    "[" + "".join(re.escape(ch) for ch in _DASH_CHARS) + "]+"
)


# Parenthetical content is removed after normalization to create a cleaner
# base query.  (e.g. "Navier-Stokes equations (fluid dynamics)" becomes
# "navier-stokes equations").
_PAREN_RE = re.compile(r"\s*\([^)]*\)")


# Multiple spaces / tabs / newlines collapse to a single space.
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_formula_query(query: str) -> str:
    """Return a normalized form of a free-text formula query.

    The normalized form is suitable for case-insensitive substring matching
    across adapters that may store labels using different dash/space styles.

    Steps:
    1. Unicode normalization (NFKC) to collapse compatibility characters.
    2. Lowercase.
    3. Replace all dash-like characters with a single hyphen.
    4. Strip parenthetical qualifiers.
    5. Collapse whitespace and trim.

    Examples
    --------
    >>> normalize_formula_query("Navier–Stokes equations")
    'navier-stokes equations'
    >>> normalize_formula_query("  NS  equations   ")
    'ns equations'
    >>> normalize_formula_query("Reynolds number (Re)")
    'reynolds number'
    """
    if not isinstance(query, str):
        return ""

    text = unicodedata.normalize("NFKC", query.strip())
    text = text.lower()
    text = _DASH_NORMALIZE_RE.sub("-", text)
    text = _PAREN_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    # Remove leading/trailing hyphens left by normalization
    text = text.strip("-")
    return text


def expand_query_variants(query: str) -> list[str]:
    """Generate normalized search variants for a query.

    Variants include:
    - The normalized base query.
    - The query with hyphens replaced by spaces (and vice versa).
    - Known aliases from the bundled formula-search config.

    The returned list is ordered from most specific to most general, with
    duplicates removed.
    """
    base = normalize_formula_query(query)
    if not base:
        return []

    variants: list[str] = [base]

    # Dash/space swap variants
    if " " in base:
        variants.append(base.replace(" ", "-"))
    if "-" in base:
        variants.append(base.replace("-", " "))

    # Alias expansion from config
    reverse_map = _reverse_formula_alias_map()
    canonical = reverse_map.get(base)
    if canonical:
        # Add canonical form and all its aliases, normalized
        variants.append(canonical)
        for alias in _formula_alias_map().get(canonical, []):
            variants.append(normalize_formula_query(alias))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def resolve_domain_alias(domain: str | None) -> str | None:
    """Map a free-text domain name to the canonical domain used by adapters.

    Returns ``None`` if the input is empty or not a recognized alias.
    """
    if not domain:
        return None
    normalized = normalize_formula_query(domain)
    # Also accept underscores and hyphens interchangeably
    normalized = normalized.replace("-", "_")
    return _domain_alias_map().get(normalized)


def normalize_formula_search_inputs(query: str, domain: str | None = None) -> dict[str, Any]:
    """Normalize both query and domain for a formula search.

    Returns a dict with the normalized ``query``, ``domain``,
    ``query_variants`` and ``load_hint`` for LLM guidance.
    """
    canonical_domain = resolve_domain_alias(domain)
    variants = expand_query_variants(query)
    return {
        "query": normalize_formula_query(query),
        "domain": canonical_domain,
        "query_variants": variants,
    }

"""
Formula Adapters - External formula source adapters

Provides a unified interface for multiple formula sources:
- Wikidata: Cross-domain formulas (SPARQL) - precise retrieval
- BioModels: Pharmacology / PK-PD models (SBML) - precise retrieval
- SciPy: Physical constants (CODATA)

Design principles:
- Direct precise retrieval, no RAG (to avoid formula errors)
- Unified FormulaInfo return format
- Lazy import of network adapters
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseAdapter, FormulaInfo
from .scipy_constants import ScipyConstantsAdapter

if TYPE_CHECKING:
    from .biomodels import BioModelsAdapter
    from .wikidata_formulas import WikidataFormulaAdapter

__all__ = [
    "BaseAdapter",
    "FormulaInfo",
    "ScipyConstantsAdapter",
    "get_wikidata_adapter",
    "get_biomodels_adapter",
]


def get_wikidata_adapter() -> WikidataFormulaAdapter:
    """Get the Wikidata adapter (lazy import, requires network)."""
    from .wikidata_formulas import WikidataFormulaAdapter

    return WikidataFormulaAdapter()


def get_biomodels_adapter() -> BioModelsAdapter:
    """Get the BioModels adapter (lazy import, requires network)."""
    from .biomodels import BioModelsAdapter

    return BioModelsAdapter()

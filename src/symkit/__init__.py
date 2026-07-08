"""
SymKit - Neurosymbolic Forge Core Library

Where Neural Meets Symbolic.

This is the core domain library for symbolic reasoning,
independent of the MCP transport layer.
"""

__version__ = "0.2.5"

from symkit.application.use_cases import (
    CalculateUseCase,
    DeriveUseCase,
    SimplifyUseCase,
    VerifyUseCase,
)
from symkit.domain.entities import Derivation, DerivationStep, Expression
from symkit.domain.value_objects import MathContext, VerificationResult

__all__ = [
    # Entities
    "Expression",
    "Derivation",
    "DerivationStep",
    # Value Objects
    "MathContext",
    "VerificationResult",
    # Use Cases
    "CalculateUseCase",
    "SimplifyUseCase",
    "DeriveUseCase",
    "VerifyUseCase",
]

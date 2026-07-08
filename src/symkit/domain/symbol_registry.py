"""SymbolRegistry — Symbol semantics registry.

Resolves semantic ambiguity of same-name symbols across domains (e.g., R can be
the gas constant, electrical resistance, or the Rydberg constant), and supports
symbol source tracking, conflict detection, and domain default semantics loading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from symkit.domain.math_domain import DOMAIN_ASSUMPTION_HINTS, MathDomain


class SymbolScope(str, Enum):
    """Symbol scope."""

    GLOBAL = "global"            # Globally common symbols
    DOMAIN = "domain"            # Domain default symbols
    SESSION = "session"          # Symbols in the current derivation session
    FORMULA = "formula"          # Symbols from a specific formula
    USER = "user"                # Explicitly registered by the user


@dataclass
class SymbolSemantics:
    """Semantic record for a single symbol."""

    name: str
    meaning: str
    domain: MathDomain = MathDomain.GENERAL
    scope: SymbolScope = SymbolScope.USER
    default_unit: str | None = None
    common_assumptions: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_id: str | None = None  # Source formula/session/document ID
    source_type: str = "manual"   # "formula" | "session" | "domain_default" | "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "meaning": self.meaning,
            "domain": self.domain.value,
            "scope": self.scope.value,
            "default_unit": self.default_unit,
            "common_assumptions": self.common_assumptions,
            "aliases": self.aliases,
            "source_id": self.source_id,
            "source_type": self.source_type,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Default symbol semantics per domain
# ═══════════════════════════════════════════════════════════════════════════════

_DOMAIN_DEFAULT_SYMBOLS: dict[MathDomain, dict[str, SymbolSemantics]] = {
    MathDomain.FLUID_DYNAMICS: {
        "rho": SymbolSemantics(
            name="rho",
            meaning="Fluid density",
            domain=MathDomain.FLUID_DYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="kg/m^3",
            common_assumptions=["positive"],
        ),
        "mu": SymbolSemantics(
            name="mu",
            meaning="Dynamic viscosity",
            domain=MathDomain.FLUID_DYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="Pa*s",
            common_assumptions=["positive"],
        ),
        "nu": SymbolSemantics(
            name="nu",
            meaning="Kinematic viscosity",
            domain=MathDomain.FLUID_DYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="m^2/s",
            common_assumptions=["positive"],
        ),
        "u": SymbolSemantics(
            name="u",
            meaning="Velocity vector (x-component or full vector)",
            domain=MathDomain.FLUID_DYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="m/s",
        ),
        "p": SymbolSemantics(
            name="p",
            meaning="Pressure",
            domain=MathDomain.FLUID_DYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="Pa",
        ),
    },
    MathDomain.QUANTUM_MECHANICS: {
        "hbar": SymbolSemantics(
            name="hbar",
            meaning="Reduced Planck constant",
            domain=MathDomain.QUANTUM_MECHANICS,
            scope=SymbolScope.DOMAIN,
            default_unit="J*s",
            common_assumptions=["positive"],
        ),
        "psi": SymbolSemantics(
            name="psi",
            meaning="Wave function",
            domain=MathDomain.QUANTUM_MECHANICS,
            scope=SymbolScope.DOMAIN,
            source_type="domain_default",
        ),
        "H": SymbolSemantics(
            name="H",
            meaning="Hamiltonian operator",
            domain=MathDomain.QUANTUM_MECHANICS,
            scope=SymbolScope.DOMAIN,
            default_unit="J",
            source_type="domain_default",
        ),
    },
    MathDomain.ELECTROMAGNETISM: {
        "R": SymbolSemantics(
            name="R",
            meaning="Electrical resistance",
            domain=MathDomain.ELECTROMAGNETISM,
            scope=SymbolScope.DOMAIN,
            default_unit="Ohm",
            common_assumptions=["positive"],
        ),
        "epsilon_0": SymbolSemantics(
            name="epsilon_0",
            meaning="Vacuum permittivity",
            domain=MathDomain.ELECTROMAGNETISM,
            scope=SymbolScope.DOMAIN,
            default_unit="F/m",
            common_assumptions=["positive"],
        ),
    },
    MathDomain.THERMODYNAMICS: {
        "R": SymbolSemantics(
            name="R",
            meaning="Universal gas constant",
            domain=MathDomain.THERMODYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="J/(mol*K)",
            common_assumptions=["positive"],
        ),
        "T": SymbolSemantics(
            name="T",
            meaning="Absolute temperature",
            domain=MathDomain.THERMODYNAMICS,
            scope=SymbolScope.DOMAIN,
            default_unit="K",
            common_assumptions=["positive"],
        ),
    },
    MathDomain.PHARMACOKINETICS: {
        "k": SymbolSemantics(
            name="k",
            meaning="Rate constant",
            domain=MathDomain.PHARMACOKINETICS,
            scope=SymbolScope.DOMAIN,
            default_unit="1/h",
            common_assumptions=["positive"],
        ),
        "V": SymbolSemantics(
            name="V",
            meaning="Volume of distribution",
            domain=MathDomain.PHARMACOKINETICS,
            scope=SymbolScope.DOMAIN,
            default_unit="L",
            common_assumptions=["positive"],
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Symbol registry
# ═══════════════════════════════════════════════════════════════════════════════

class SymbolRegistry:
    """
    Symbol semantics registry.

    Maintains semantics for each symbol under different scopes/domains, supporting:
    - Register symbol semantics (user/formula/session)
    - Look up semantics by name and domain
    - Conflict detection (same name, different meaning)
    - Source tracking
    """

    def __init__(self) -> None:
        self._symbols: dict[str, list[SymbolSemantics]] = {}
        self._register_domain_defaults()

    def _register_domain_defaults(self) -> None:
        """Load all domain default symbols."""
        for _domain, symbols in _DOMAIN_DEFAULT_SYMBOLS.items():
            for _name, sem in symbols.items():
                self._symbols.setdefault(_name, []).append(sem)

    def register(
        self,
        name: str,
        meaning: str,
        domain: MathDomain | str = MathDomain.GENERAL,
        scope: SymbolScope = SymbolScope.USER,
        default_unit: str | None = None,
        common_assumptions: list[str] | None = None,
        aliases: list[str] | None = None,
        source_id: str | None = None,
        source_type: str = "manual",
    ) -> SymbolSemantics:
        """Register a symbol's semantics."""
        if isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        sem = SymbolSemantics(
            name=name,
            meaning=meaning,
            domain=domain,
            scope=scope,
            default_unit=default_unit,
            common_assumptions=common_assumptions or [],
            aliases=aliases or [],
            source_id=source_id,
            source_type=source_type,
        )
        self._symbols.setdefault(name, []).append(sem)
        return sem

    def register_formula_symbols(
        self,
        formula_id: str,
        symbol_names: list[str],
        domain: MathDomain | str = MathDomain.GENERAL,
    ) -> list[SymbolSemantics]:
        """Batch-register symbols from a formula (use domain default semantics if available; otherwise mark as unknown)."""
        if isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        registered: list[SymbolSemantics] = []
        for sym in symbol_names:
            existing = self.lookup(sym, domain)
            if existing:
                # Re-register with formula source for provenance
                registered.append(
                    self.register(
                        name=sym,
                        meaning=existing.meaning,
                        domain=existing.domain,
                        scope=SymbolScope.FORMULA,
                        default_unit=existing.default_unit,
                        common_assumptions=existing.common_assumptions,
                        source_id=formula_id,
                        source_type="formula",
                    )
                )
            else:
                registered.append(
                    self.register(
                        name=sym,
                        meaning=f"Symbol from formula '{formula_id}'",
                        domain=domain,
                        scope=SymbolScope.FORMULA,
                        source_id=formula_id,
                        source_type="formula",
                    )
                )
        return registered

    def lookup(
        self,
        name: str,
        domain: MathDomain | str | None = None,
        scope: SymbolScope | None = None,
    ) -> SymbolSemantics | None:
        """Look up symbol semantics, preferring an exact domain and scope match."""
        if domain is not None and isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        entries = self._symbols.get(name, [])
        if not entries:
            return None

        # Prefer exact domain match, then GENERAL, then any
        candidates = entries
        if domain is not None:
            domain_matches = [e for e in entries if e.domain == domain]
            if domain_matches:
                candidates = domain_matches
            else:
                general_matches = [e for e in entries if e.domain == MathDomain.GENERAL]
                if general_matches:
                    candidates = general_matches

        if scope is not None:
            scope_matches = [e for e in candidates if e.scope == scope]
            if scope_matches:
                candidates = scope_matches
        else:
            # When no scope requested, prefer non-domain sources (formula/session/user)
            # so that explicit registrations override domain defaults.
            non_domain = [e for e in candidates if e.scope != SymbolScope.DOMAIN]
            if non_domain:
                candidates = non_domain

        return candidates[0] if candidates else None

    def lookup_all(self, name: str) -> list[SymbolSemantics]:
        """Return all semantic records for a symbol."""
        return list(self._symbols.get(name, []))

    def detect_conflicts(self, names: list[str]) -> list[dict[str, Any]]:
        """Detect whether same-name symbols in the list have semantic conflicts (same meaning/domain is not considered a conflict)."""
        conflicts = []
        for name in names:
            entries = self._symbols.get(name, [])
            if len(entries) > 1:
                meanings = sorted({e.meaning for e in entries})
                domains = {e.domain.value for e in entries}
                if len(meanings) > 1 or len(domains) > 1:
                    conflicts.append({
                        "symbol": name,
                        "meanings": meanings,
                        "domains": sorted(domains),
                        "entries": [e.to_dict() for e in entries],
                    })
        return conflicts

    def suggest_assumptions(
        self,
        names: list[str],
        domain: MathDomain | str | None = None,
    ) -> dict[str, list[str]]:
        """Recommend assumptions based on symbol semantics."""
        if domain is not None and isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        suggestions: dict[str, list[str]] = {}
        for name in names:
            sem = self.lookup(name, domain)
            if sem and sem.common_assumptions:
                suggestions[name] = sem.common_assumptions
        return suggestions

    def list_symbols(
        self,
        domain: MathDomain | str | None = None,
        scope: SymbolScope | None = None,
    ) -> list[SymbolSemantics]:
        """List symbols."""
        if domain is not None and isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        results = []
        for entries in self._symbols.values():
            for e in entries:
                if domain is not None and e.domain != domain:
                    continue
                if scope is not None and e.scope != scope:
                    continue
                results.append(e)
        return results

    def get_domain_default_assumptions(
        self,
        domain: MathDomain | str,
    ) -> dict[str, str]:
        """Get domain default assumptions (for compatibility with existing DOMAIN_ASSUMPTION_HINTS)."""
        if isinstance(domain, str):
            domain = MathDomain.from_string(domain)
        return DOMAIN_ASSUMPTION_HINTS.get(domain, {})


# Global singleton (usually each DerivationSession holds its own, or uses the global one directly)
_global_registry = SymbolRegistry()


def get_global_symbol_registry() -> SymbolRegistry:
    """Get the global symbol registry."""
    return _global_registry

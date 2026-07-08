"""
MathDomain — Mathematics/physics domain labels

For classification only; does not affect computation. Lets the user tag the
domain to which a derivation belongs.
"""

from enum import Enum


class MathDomain(str, Enum):
    """Mathematics and physics domain labels."""

    GENERAL = "general"                    # General / uncategorized
    ALGEBRA = "algebra"                    # Algebra
    CALCULUS = "calculus"                  # Calculus
    LINEAR_ALGEBRA = "linear_algebra"      # Linear algebra
    DIFFERENTIAL_EQ = "differential_eq"    # Differential equations
    FLUID_DYNAMICS = "fluid_dynamics"      # Fluid dynamics (NS equations, turbulence)
    SOLID_MECHANICS = "solid_mechanics"    # Solid mechanics / structural mechanics
    QUANTUM_MECHANICS = "quantum_mechanics"  # Quantum mechanics
    ELECTROMAGNETISM = "electromagnetism"  # Electromagnetism
    THERMODYNAMICS = "thermodynamics"      # Thermodynamics
    STATISTICAL_MECHANICS = "statistical_mechanics"  # Statistical mechanics
    OPTICS = "optics"                      # Optics
    ACOUSTICS = "acoustics"                # Acoustics
    CHEMICAL_KINETICS = "chemical_kinetics"  # Chemical kinetics
    PHARMACOKINETICS = "pharmacokinetics"  # Pharmacokinetics (kept but not default)
    BIOLOGY = "biology"                    # Biology models
    GEOMETRY = "geometry"                  # Geometry / differential geometry
    OPTIMIZATION = "optimization"          # Optimization
    PROBABILITY = "probability"            # Probability theory
    CUSTOM = "custom"                      # Custom

    @classmethod
    def from_string(cls, value: str) -> "MathDomain":
        """Parse domain from string; fallback to GENERAL if not matched."""
        try:
            return cls(value.lower().replace(" ", "_"))
        except ValueError:
            return cls.GENERAL


# ── Common symbol assumption hints per domain ──────────────────────────

DOMAIN_ASSUMPTION_HINTS: dict[MathDomain, dict[str, str]] = {
    MathDomain.FLUID_DYNAMICS: {
        "rho": "positive",    # density
        "mu": "positive",     # viscosity
        "nu": "positive",     # kinematic viscosity
        "Re": "positive",     # Reynolds number
        "p": "real",         # pressure (can be positive or negative, gauge pressure)
    },
    MathDomain.QUANTUM_MECHANICS: {
        "hbar": "positive",
        "m": "positive",      # mass
        "E": "real",          # energy
    },
    MathDomain.THERMODYNAMICS: {
        "T": "positive",      # absolute temperature
        "P": "positive",      # pressure
        "V": "positive",      # volume
        "n": "positive",      # amount of substance (moles)
        "R": "positive",      # gas constant
    },
    MathDomain.ELECTROMAGNETISM: {
        "epsilon_0": "positive",
        "mu_0": "positive",
        "c": "positive",      # speed of light
    },
    MathDomain.PHARMACOKINETICS: {
        "k": "positive",      # rate constant
        "V": "positive",      # volume of distribution
        "CL": "positive",     # clearance
        "C": "real",          # concentration
        "t": "positive",      # time
        "dose": "positive",
    },
}

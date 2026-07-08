"""
Adapter for SciPy's physical constants (CODATA).

scipy.constants provides:
- Fundamental physical constants (c, h, G, etc.)
- Physical constants database (CODATA 2018)
- Unit conversion utilities

This adapter provides a unified interface to access these constants.
"""

from dataclasses import dataclass

from sympy import Float, Symbol

from .base import BaseAdapter, FormulaInfo


@dataclass
class PhysicalConstant:
    """A physical constant with value, unit, and uncertainty."""

    name: str
    symbol: str
    value: float
    unit: str
    uncertainty: float
    category: str
    description: str = ""

    @property
    def relative_uncertainty(self) -> float:
        """Relative standard uncertainty."""
        if self.value == 0:
            return 0.0
        return self.uncertainty / abs(self.value)


class ScipyConstantsAdapter(BaseAdapter):
    """Adapter for SciPy's physical constants."""

    def __init__(self) -> None:
        self._constants: dict[str, PhysicalConstant] = {}
        self._load_fundamental_constants()
        self._load_electromagnetic_constants()
        self._load_atomic_constants()
        self._load_conversion_factors()

    @property
    def source_name(self) -> str:
        return "scipy.constants"

    def list_categories(self) -> list[str]:
        categories = set()
        for const in self._constants.values():
            categories.add(const.category)
        return sorted(categories)

    def list_formulas(self, category: str | None = None) -> list[str]:
        """List constants (treated as formulas with no variables)."""
        if category is None:
            return list(self._constants.keys())
        return [cid for cid, c in self._constants.items() if c.category == category]

    def get_formula(self, formula_id: str) -> FormulaInfo | None:
        """Get constant as FormulaInfo."""
        const = self._constants.get(formula_id)
        if const is None:
            return None

        # Create a symbol for the constant
        sym = Symbol(const.symbol)

        return FormulaInfo(
            id=formula_id,
            name=const.name,
            expression=sym,  # Just the symbol
            variables={
                const.symbol: {
                    "description": const.description or const.name,
                    "unit": const.unit,
                    "value": const.value,
                    "uncertainty": const.uncertainty,
                    "type": "constant",
                }
            },
            source="scipy.constants (CODATA 2018)",
            category=f"constants/{const.category}",
            description=const.description,
            tags=["constant", const.category],
        )

    def get_constant(self, name: str) -> PhysicalConstant | None:
        """Get a physical constant by name."""
        return self._constants.get(name)

    def get_value(self, name: str) -> float | None:
        """Get just the numerical value of a constant."""
        const = self._constants.get(name)
        return const.value if const else None

    def get_sympy_value(self, name: str) -> Float | None:
        """Get the constant as a SymPy Float for exact computation."""
        const = self._constants.get(name)
        return Float(const.value) if const else None

    # =========================================================================
    # Fundamental Constants
    # =========================================================================
    def _load_fundamental_constants(self) -> None:
        """Load fundamental physical constants."""
        # Speed of light
        self._constants["speed_of_light"] = PhysicalConstant(
            name="Speed of Light in Vacuum",
            symbol="c",
            value=299792458.0,
            unit="m/s",
            uncertainty=0.0,  # Exact by definition
            category="fundamental",
            description="Speed of light in vacuum (exact)",
        )

        # Planck constant
        self._constants["planck"] = PhysicalConstant(
            name="Planck Constant",
            symbol="h",
            value=6.62607015e-34,
            unit="J·s",
            uncertainty=0.0,  # Exact by definition (2019)
            category="fundamental",
            description="Planck constant (exact since 2019)",
        )

        # Reduced Planck constant
        self._constants["hbar"] = PhysicalConstant(
            name="Reduced Planck Constant",
            symbol="ℏ",
            value=1.054571817e-34,
            unit="J·s",
            uncertainty=0.0,
            category="fundamental",
            description="h/(2π), Dirac constant",
        )

        # Gravitational constant
        self._constants["gravitational_constant"] = PhysicalConstant(
            name="Newtonian Constant of Gravitation",
            symbol="G",
            value=6.67430e-11,
            unit="m³/(kg·s²)",
            uncertainty=1.5e-15,
            category="fundamental",
            description="Newton's gravitational constant",
        )

        # Boltzmann constant
        self._constants["boltzmann"] = PhysicalConstant(
            name="Boltzmann Constant",
            symbol="k_B",
            value=1.380649e-23,
            unit="J/K",
            uncertainty=0.0,  # Exact by definition
            category="fundamental",
            description="Boltzmann constant (exact since 2019)",
        )

        # Avogadro constant
        self._constants["avogadro"] = PhysicalConstant(
            name="Avogadro Constant",
            symbol="N_A",
            value=6.02214076e23,
            unit="1/mol",
            uncertainty=0.0,  # Exact by definition
            category="fundamental",
            description="Avogadro constant (exact since 2019)",
        )

        # Gas constant
        self._constants["gas_constant"] = PhysicalConstant(
            name="Molar Gas Constant",
            symbol="R",
            value=8.314462618,
            unit="J/(mol·K)",
            uncertainty=0.0,  # Exact (N_A × k_B)
            category="fundamental",
            description="Ideal gas constant R = N_A × k_B",
        )

        # Standard gravity
        self._constants["standard_gravity"] = PhysicalConstant(
            name="Standard Acceleration of Gravity",
            symbol="g_n",
            value=9.80665,
            unit="m/s²",
            uncertainty=0.0,  # Exact by definition
            category="fundamental",
            description="Standard gravitational acceleration",
        )

    # =========================================================================
    # Electromagnetic Constants
    # =========================================================================
    def _load_electromagnetic_constants(self) -> None:
        """Load electromagnetic constants."""
        # Elementary charge
        self._constants["elementary_charge"] = PhysicalConstant(
            name="Elementary Charge",
            symbol="e",
            value=1.602176634e-19,
            unit="C",
            uncertainty=0.0,  # Exact by definition
            category="electromagnetic",
            description="Charge of electron (magnitude)",
        )

        # Vacuum permittivity
        self._constants["epsilon_0"] = PhysicalConstant(
            name="Vacuum Electric Permittivity",
            symbol="ε_0",
            value=8.8541878128e-12,
            unit="F/m",
            uncertainty=1.3e-21,
            category="electromagnetic",
            description="Electric constant, permittivity of free space",
        )

        # Vacuum permeability
        self._constants["mu_0"] = PhysicalConstant(
            name="Vacuum Magnetic Permeability",
            symbol="μ_0",
            value=1.25663706212e-6,
            unit="H/m",
            uncertainty=1.9e-16,
            category="electromagnetic",
            description="Magnetic constant, permeability of free space",
        )

        # Coulomb constant
        self._constants["coulomb_constant"] = PhysicalConstant(
            name="Coulomb Constant",
            symbol="k_e",
            value=8.9875517923e9,
            unit="N·m²/C²",
            uncertainty=0.0,  # Derived exactly
            category="electromagnetic",
            description="k = 1/(4πε₀)",
        )

    # =========================================================================
    # Atomic Constants
    # =========================================================================
    def _load_atomic_constants(self) -> None:
        """Load atomic and nuclear constants."""
        # Electron mass
        self._constants["electron_mass"] = PhysicalConstant(
            name="Electron Mass",
            symbol="m_e",
            value=9.1093837015e-31,
            unit="kg",
            uncertainty=2.8e-40,
            category="atomic",
            description="Rest mass of electron",
        )

        # Proton mass
        self._constants["proton_mass"] = PhysicalConstant(
            name="Proton Mass",
            symbol="m_p",
            value=1.67262192369e-27,
            unit="kg",
            uncertainty=5.1e-37,
            category="atomic",
            description="Rest mass of proton",
        )

        # Neutron mass
        self._constants["neutron_mass"] = PhysicalConstant(
            name="Neutron Mass",
            symbol="m_n",
            value=1.67492749804e-27,
            unit="kg",
            uncertainty=9.5e-37,
            category="atomic",
            description="Rest mass of neutron",
        )

        # Atomic mass unit
        self._constants["atomic_mass"] = PhysicalConstant(
            name="Atomic Mass Constant",
            symbol="m_u",
            value=1.66053906660e-27,
            unit="kg",
            uncertainty=5.0e-37,
            category="atomic",
            description="1/12 of carbon-12 mass",
        )

        # Bohr radius
        self._constants["bohr_radius"] = PhysicalConstant(
            name="Bohr Radius",
            symbol="a_0",
            value=5.29177210903e-11,
            unit="m",
            uncertainty=8.0e-21,
            category="atomic",
            description="Radius of first Bohr orbit",
        )

        # Fine structure constant
        self._constants["fine_structure"] = PhysicalConstant(
            name="Fine-Structure Constant",
            symbol="α",
            value=7.2973525693e-3,
            unit="dimensionless",
            uncertainty=1.1e-12,
            category="atomic",
            description="Electromagnetic coupling constant ≈ 1/137",
        )

        # Rydberg constant
        self._constants["rydberg"] = PhysicalConstant(
            name="Rydberg Constant",
            symbol="R_∞",
            value=10973731.568160,
            unit="1/m",
            uncertainty=2.1e-5,
            category="atomic",
            description="Rydberg constant for infinite nuclear mass",
        )

    # =========================================================================
    # Conversion Factors
    # =========================================================================
    def _load_conversion_factors(self) -> None:
        """Load common conversion factors."""
        # Electronvolt
        self._constants["electron_volt"] = PhysicalConstant(
            name="Electron Volt",
            symbol="eV",
            value=1.602176634e-19,
            unit="J",
            uncertainty=0.0,
            category="conversion",
            description="Energy of 1 eV in joules",
        )

        # Calorie
        self._constants["calorie"] = PhysicalConstant(
            name="Thermochemical Calorie",
            symbol="cal",
            value=4.184,
            unit="J",
            uncertainty=0.0,  # Exact by definition
            category="conversion",
            description="1 calorie = 4.184 J (exact)",
        )

        # Atmosphere
        self._constants["atmosphere"] = PhysicalConstant(
            name="Standard Atmosphere",
            symbol="atm",
            value=101325.0,
            unit="Pa",
            uncertainty=0.0,  # Exact by definition
            category="conversion",
            description="1 atm = 101325 Pa (exact)",
        )

        # Angstrom
        self._constants["angstrom"] = PhysicalConstant(
            name="Angstrom",
            symbol="Å",
            value=1e-10,
            unit="m",
            uncertainty=0.0,
            category="conversion",
            description="1 Å = 10⁻¹⁰ m",
        )

    # =========================================================================
    # Search
    # =========================================================================
    def search(self, query: str, limit: int = 10) -> list[FormulaInfo]:  # noqa: ARG002
        """Search constants by keyword.

        Supports both exact substring match and token-based match, so natural
        language queries like "Planck energy using speed of light" can find
        relevant constants.
        """
        results = []
        query_lower = query.lower()
        tokens = [t for t in query_lower.split() if len(t) >= 2]
        for cid, const in self._constants.items():
            haystack = " ".join(
                f for f in (
                    const.name,
                    const.symbol,
                    const.description,
                    const.category,
                )
                if f
            ).lower()
            if query_lower in haystack or any(
                token in haystack for token in tokens
            ):
                formula_info = self.get_formula(cid)
                if formula_info:
                    results.append(formula_info)
            if len(results) >= limit:
                break
        return results

---
# SymKit Local Formula Library
#
# This directory contains user-editable, YAML-based formula entries.
# Each file is one formula. You can add, remove, or edit these files directly,
# or use the MCP `formula_add` tool.
#
# Required fields:
#   id          - Unique identifier (used with formula_get)
#   name        - Human-readable name
#   sympy_str   - SymPy-compatible string representation
#   latex       - LaTeX representation
#
# Optional fields:
#   aliases     - List of alternative names for search
#   domain      - Physics/math domain tag
#   category    - Sub-category inside the domain
#   description - Short description
#   tags        - Search keywords
#   variables   - Variable definitions {name: {description, unit}}
#   references  - Reference URLs or citations
#
# Example:
#
# id: "reynolds_number"
# name: "Reynolds number"
# aliases: ["Re", "Reynolds"]
# domain: "fluid_dynamics"
# category: "fluid"
# description: "Ratio of inertial to viscous forces"
# sympy_str: "Re = rho * v * L / mu"
# latex: "Re = \\frac{\\rho v L}{\\mu}"
# tags: ["dimensionless", "fluid", "turbulence"]
# variables:
#   rho: {description: "density", unit: "kg/m^3"}
#   v:   {description: "velocity", unit: "m/s"}
#   L:   {description: "characteristic length", unit: "m"}
#   mu:  {description: "dynamic viscosity", unit: "Pa·s"}
# references: ["https://en.wikipedia.org/wiki/Reynolds_number"]

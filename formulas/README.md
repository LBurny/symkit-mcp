# SymKit Formula Store

Two distinct collections live under `formulas/`, each with a different
purpose and file format.

🌐 [English](README.md) | [简体中文](README.zh-CN.md)

## 📁 Directory Structure

```text
formulas/
├── library/               ← Base formula library (hand-edited YAML)
│   ├── README.md          ← Field reference for library entries
│   ├── fluid_dynamics/    ← e.g. reynolds_number, ns_incompressible
│   ├── mechanics/         ← e.g. newtons_second_law
│   └── thermodynamics/    ← e.g. ideal_gas_law
└── derived/               ← Derivation results (auto-saved by session_complete)
    ├── fluid_dynamics/    ← Verified derivations in the fluid domain
    ├── general/
    └── mechanics/
```

## 📚 `library/` — Base Formula Library

User-editable YAML entries searched by the `formula_search` / `formula_get`
MCP tools. Each file is one formula with a stable, human-readable id
(`reynolds_number`, `ideal_gas_law`, …).

Add formulas here by:

1. Writing a YAML file directly, or
2. Calling the `formula_add` MCP tool.

See [`library/README.md`](library/README.md) for the full field reference.

## 🔨 `derived/` — Derivation Results

Output of `session_complete`: new formulas created through SymKit's
verified symbolic-derivation workflow. Files are named by session id
(a short hash) and organised into domain sub-folders.

Each YAML file is a `DerivationResult` record containing:

| Field | Purpose |
| ----- | ------- |
| `id` | Session id (hash) |
| `name` | Derivation name |
| `expression` | Final SymPy expression string |
| `derived_from` | Ids of base formulas used |
| `derivation_steps` | Step descriptions |
| `verified` / `verification_method` | Verification status |
| `assumptions` / `limitations` | Scope constraints |
| `domain` / `category` | Classification tags |

These files are loaded by `DerivationRepository` and feed the
`FormulaRecommender` so that past derivations can be suggested in
future sessions.

## ✅ What Belongs Where

| Content | Location |
| ------- | -------- |
| Textbook / base formulas (F=ma, Arrhenius…) | `library/` |
| Physical constants | SciPy constants (via `formula_search source="scipy"`) |
| Verified derivation outputs | `derived/` |

## ❌ What Does NOT Belong Here

| Type | Where it goes instead |
| ---- | -------------------- |
| Basic physics already in SymPy | Use SymPy directly |
| Standard constants (G, c, h…) | Use `formula_search(source="scipy")` |
| Temporary / unverified work | Stays in the session JSON, not persisted here |

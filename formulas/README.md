# SymKit Formula Store

[English](README.md) | [简体中文](README.zh-CN.md)

`formulas/` in this repository is the source tree for the bundled seed
formulas. At runtime, search goes through a per-user data directory
(`SYMKIT_DATA_DIR` or the platformdirs default): seeds ship read-only inside
the package, user formulas from `formula_add` go to a writable overlay that
overrides seeds by id, and session output goes to `derived/` there.

## Directory structure

```text
formulas/
├── library/            ← Base formulas (hand-edited YAML, one file per formula)
│   ├── README.md       ← Field reference for library entries
│   ├── fluid_dynamics/ ← e.g. reynolds_number, ns_incompressible
│   ├── mechanics/      ← e.g. newtons_second_law
│   └── thermodynamics/ ← e.g. ideal_gas_law
└── derived/            ← Session output (auto-saved by session_complete)
```

## `library/` — base formulas

YAML entries searched by `formula_search` / `formula_get`, each with a
stable, readable id (`reynolds_number`, `ideal_gas_law`, …). Add a formula by
writing a YAML file directly or by calling `formula_add`. See
[`library/README.md`](library/README.md) for the field reference.

## `derived/` — derivation results

Output of `session_complete(auto_save=True)`: formulas created through the
verified derivation workflow, named by a deterministic staging id and grouped
into domain sub-folders. Each file is a `DerivationResult` record:

| Field | Purpose |
| ----- | ------- |
| `id` / `name` | Session id (hash) and derivation name |
| `expression` | Final SymPy expression string |
| `derived_from` | Ids of the base formulas used |
| `derivation_steps` | Step descriptions |
| `verified` / `verification_method` | Verification status |
| `assumptions` / `limitations` | Scope constraints |
| `domain` / `category` | Classification tags |

Loaded by `DerivationRepository` and fed to `FormulaRecommender`, so past
derivations can be suggested in future sessions.

## What belongs where

| Content | Location |
| ------- | -------- |
| Textbook / base formulas (F=ma, Arrhenius, …) | `library/` |
| Verified derivation outputs | `derived/` |
| Standard physical constants (G, c, h, …) | Not here — `formula_search(source="scipy")` |
| Basic physics already in SymPy | Not here — use SymPy directly |
| Temporary / unverified work | Not persisted — stays in the session JSON |
# Roadmap

SymKit project roadmap and feature planning.

---

## Current

**v1.8.0** (2026-09-14) — 45 MCP tools, 33 `math()` operations, 1055 tests.
See [CHANGELOG.md](CHANGELOG.md) for the release-by-release history.

---

## Completed

### 1.8.0 — Lean lane hardening (2026-09-14)

- Lean certification is robust to cancelled runs and misconfigured toolchains:
  a timeout kills the whole `lake` process tree (no orphan holding the elan
  lock), `find_lake()` prefers `ELAN_HOME` over `PATH`, and a `lake` whose elan
  home lacks the pinned toolchain is refused with a directing reason instead of
  triggering a fresh download.
- Honest certification reporting: steps whose input and output are identical
  are reported as `trivial` and excluded from `proven` (the reported session
  had 11 of 20 theorems vacuous), skipped steps state their reason, and
  `session_certify(assumptions=...)` binds missing denominator facts at
  certify time.
- The verifier no longer reads a leading negated term (`-x**2 + x*(x + 1)`) as
  an asserted difference, which had flagged a correct simplification with a
  false `suspect_identity: unreduced` warning.
- Adds the `sandbox-experiment` agent skill (black-box round playbook).

### 1.7.0 — Lean certification and write-path governance (2026-09-14)

- Optional Lean 4 kernel certification: `session_certify` re-proves
  algebraic-equality steps with Lean 4 + Mathlib (`ring` / `field_simp`),
  attaches outcomes under `details.lean`, and surfaces verifier disagreements
  as `discrepancies` (44 → 45 tools). One-time setup via `symkit-lean-setup`.
- Dimensional analysis: `math("dimension", ...)` (32 → 33 operations) reports
  consistency and the net dimension of an expression; `session_verify_step` /
  `session_verify_session` run the check automatically when the session has
  unit information.
- Formula write-path governance: `formula_add` requires a unit per variable,
  write-time similarity detection (`similar_to`) surfaces duplicates at save
  time, and `formula_promote` / `formula_get` / `formula_stats` expose the
  `curated` flag and structural duplicate groups.

### 1.6.x — Formula index and curation

- Persistent SQLite FTS5 formula index (trigram tokenizer) over the unchanged YAML layers;
  search matches Chinese aliases and expression content, deterministically and offline.
- Three-tier curation (`seed` / `staging` / `curated`) with `formula_promote`,
  `formula_reindex`, and `formula_stats`.
- Content-hash dedup, deterministic staging ids, and idempotent re-saves.
- Path traversal rejected on every formula write path.
- Engineering baseline: CI quality gate (ruff / mypy / pytest over the
  3.10/3.12 matrix) and the bylaw §5.1 modularity ratchet
  (`scripts/check_modularity.py`), wired as a precondition of the release
  pipeline.

### 1.5.x — Verification and assumptions

- Assumption subsystem generalized around invariants I1/I2/I3; session assumptions route
  into the `math()` path.
- The verifier replays archived expressions instead of re-parsing display strings.
- Actionable diagnostics for sign decisions, one-sided limits, and `dsolve` mismatches.

### 1.1.0

- Session verification hardening: assumption-aware substitution checks and numeric-zero
  tolerance (no more false FAILED verdicts on substitute steps or machine-epsilon
  float residuals).
- Parser normalization: unevaluated numeric divisions fold to `Rational`, fractional
  exponents evaluate numerically; new `evalf` operation and float-coefficient warning on
  `solve`.
- Derived formulas included in the searchable corpus; report generation renders step
  formulas, verification counts, and real LaTeX.
- Goal progress counts variables across all steps; sessions stay ACTIVE when persisted.

### 1.0.1

- Unified math entry `math()` covering calculus, linear algebra, ODE, Laplace/Fourier
  transforms, and ~25 other operations.
- Step-by-step derivation sessions with start, continue, rollback, complete, record step,
  and verify step.
- Symbol assumption management: register, query, conflict detection, and per-step isolation.
- External formula search: Wikidata, SciPy constants, BioModels.
- Symbol registry: domain-specific notation, conflict detection, and per-domain listing.
- Code/report generation: Python functions, LaTeX derivation, Markdown reports, SymPy
  scripts.
- High-level derivation orchestration: `derive`, `intent_execute`, pattern listing, tool
  recommendations.
- **41 MCP tools** with DDD-layered architecture; the core library can be used
  independently.
- Python requirement lowered to 3.10+ for broader installation compatibility.

---

## In Progress

- Documentation cleanup and clearer project positioning (general-purpose formula
  derivation, not domain-specific).
- Derivation example library expansion: cross-domain cases in physics, engineering,
  chemistry, biology, etc.
- Tool usage examples and best-practice additions.

---

## Planned

### Near term

- **Multi-session routing.** Session tools take an explicit `session_id`, defaulting to the
  current session. Today `tools/_state.py` holds one process-global session, so a second
  client or agent silently takes over the first one's derivation. This is the prerequisite
  for the multi-agent goal below.
- **Decompose `DerivationSession`.** At ~1800 lines it is the largest module and sits in the
  modularity baseline. Split step storage, verification orchestration, and report rendering
  into collaborators, then lower the baseline.
- **Shrink the modularity baseline.** 10 files and 44 functions are currently frozen. Work
  them down by subdomain (bylaw §5.3) rather than raising limits.

### Later

- More external formula-source adapters (e.g., Wolfram Alpha, MathWorld).
- Extended export formats for derivation results (Julia, R, MATLAB).
- Formula version control and diff comparison.
- Richer cross-domain example library.
- More complete API documentation and interactive tutorials.

---

## Long-term Goals

- Become the standard derivation layer between the SymPy ecosystem and the MCP protocol.
- Support multi-agent collaborative derivation (multi-user / multi-agent sessions).
- Contribute general capabilities upstream to SymPy.
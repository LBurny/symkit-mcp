# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-09-10

Assumption-scope reform motivated by run-013 (per-call assumptions leaked permanently into the shared context even for `session=false` probe calls) and the design discussion that followed.

### Added

- 🧹 **`unassume(variables)`** — remove assumptions for named symbols from the shared context and the session engine (domain defaults preserved). `assume()` was previously irreversible short of a server restart.
- 🧹 **`clear_assumptions()`** — reset the whole scope (context + session engine layers), domain defaults preserved.
- 📣 **`assumptions_applied` echo** — `math()` responses list which assumptions took effect for the call.

### Changed

- ⚖️ **Per-call assumptions respect the `session` flag** — with `session=true` they persist into the shared context AND the session's assumption engine (visible to the step verifier, so identities recorded under session assumptions verify instead of staying inconclusive); with `session=false` they apply to that call only via a call-local context and the shared context is untouched — stateless calls are now truly side-effect free. Cross-session globals remain the explicit `assume()` tool's job. **Migration note:** code that seeded the context with `math(..., assumptions=[...], session=false)` must call `assume()` (or pass `session=true`) instead.

### Fixed

- ✅ **Parse-collapsed boolean steps verify** — when session assumptions make the parser resolve `Eq(...)` to a boolean before recording, a same-value boolean step verifies instead of landing in an unverifiable inconclusive limbo.

## [1.2.2] - 2026-09-10

Nine defects found by black-box rounds run-011/run-012 (Maxwell-Boltzmann and RC/RLC circuit tasks driven by subagents) and accepted by run-013/014/015 re-runs.

### Added

- 🧮 **dsolve understands Leibniz notation** — `dV/dt` and `d^2x/dt^2` parse into real `Derivative` terms alongside `diff(V,t)`.
- 🎯 **dsolve accepts `ics`** — initial conditions like `{"V(0)": "V_0"}` are forwarded to `sympy.dsolve`, eliminating the 3-call manual constant-solving workaround.
- 🔀 **`list_assumptions` accepts `"merged"`** as an alias for the default merged view.

### Fixed

- 🚨 **dsolve rejects non-ODE input loudly** — `R*C*dV/dt + V` used to parse `dV`/`dt` as plain symbols and return an algebraic rearrangement disguised as an ODE solution; input without any derivative of the dependent variable now fails with a notation hint.
- 💾 **Save selection is goal- and lineage-aware** — `session_complete(auto_save=true)` picks the last symbolic step involving a goal target variable (including hand-recorded binding steps like `Eq(v_rms, ...)`), else the last output in the derivation's symbol lineage; tangential probes (`exp(x)` limit probes, `omega` side-quests) no longer get saved under the derivation's name.
- 🔍 **Definite integrals verify by numeric quadrature** — the reverse-differentiation check false-FAILED correct definite results (d/dx of a constant is 0); bounds are read from the recorded command, parameters are prime-valued, and quadrature disagreement yields INCONCLUSIVE rather than a false FAILED.
- ➕ **solve promotes the positive root** — the `solution` field prefers a provably positive root under active assumptions instead of blindly taking `solutions[0]`; `all_solutions` keeps the full set.
- 📈 **series keeps the `O(x**n)` term** instead of silently reporting a bare polynomial as if exact.
- 🧾 **Scalar strings coerce to lists** — `limitations="..."`, `tags="..."`, `assumptions="..."`, `target_variables="..."`, `related_variables="..."` no longer fail schema validation or splat into characters.

## [1.2.1] - 2026-09-10

Four defects found by black-box round run-008 (damped-oscillator task) and accepted by run-010 probe: all four fixes verified from the black box.

### Fixed

- 🔢 **`evalf` substitution works under context assumptions** — substitution keys are rebound by name to the assumption-bearing symbols actually present in the parsed expression, instead of silently no-opping when earlier calls installed positive assumptions.
- 💾 **Derived-formula saver stores the representative symbolic output** — `session_complete(auto_save=true)` no longer saves a trailing numeric check (evalf float or residual `0`); the last symbolic step output is saved, `variables` metadata is backfilled, and the response reports `saved_expression`.
- ✅ **Boolean `simplify` outputs record cleanly** — `simplify(Eq(...))` resolving to a plain Python `True` no longer crashes step verification (`Add - bool` TypeError silently dropped the step); identities are verified when the verifier can confirm them, otherwise INCONCLUSIVE.
- 🎯 **Goal extraction ignores apostrophes** — prose primes like `x''(t)` are no longer mistaken for single-quoted expressions (junk targets such as `(t) + c x` no longer poison progress matching); double-quoted targets still extract.

## [1.2.0] - 2026-09-10

Structural fixes from the framework-design review of black-box regression rounds run-005/006/007: unknown function calls can no longer degrade to implicit multiplication, recorded steps are the same SymPy objects returned to the client, the derived-formula read/write schema is pinned by contract tests, ignored parameters warn instead of disappearing, and session verification grades outcomes instead of all-or-nothing.

### Added

- 🧩 **solve returns a bare solution** — `solution` / `solution_latex` fields carry the isolated right-hand side alongside the `Eq(v, ...)` expression, so agents no longer hand-strip the wrapper (and corrupt parentheses doing so).
- 🎯 **`session_start` / `session_set_goal` accept `target_variables`** — explicit override for the heuristic goal-text variable extraction.
- 🔢 **`evalf` accepts `substitution`** — substitute symbols and numerically evaluate in one call.
- ✅ **dsolve / limit / evalf steps are auto-verified** — via `checkodesol`, numeric probe points, and numeric re-evaluation respectively.

### Fixed

- 🚨 **Parser red line: `v(t)` stays a function call** — unknown `name(...)` call sites parse as undefined SymPy Functions (Mathematica convention) instead of silently degrading to implicit multiplication (`v*t`); `Integer * Integer**-1` factor pairs fold into exact rationals inside any product, so `1/2*rho*...` round-trips stably through the parser.
- 📼 **Recorded steps are the returned objects** — zero-reparse recording: the session archive is built from the live SymPy object, so archive and response can no longer diverge on function notation, assumptions, or unevaluated forms.
- 📖 **Derived formulas are readable by the library** — writer (`DerivationResult`) and reader (`FormulaEntry`) agree on `sympy_str` / `expression` / `latex` keys, pinned by contract tests; legacy expression-only YAML still loads.
- ⚠️ **Ignored parameters warn** — a per-operation parameter audit table flags caller-set params the operation does not consume (e.g. `point` on `simplify`); two-word assumptions (`"x positive"`) are accepted alongside `"x is positive"`, and malformed clauses warn instead of being silently dropped.
- 🔥 **Engine errors propagate** — 14 previously-silent `except` sites now surface `{ExceptionType}: {message}` in the tool's failure message.
- 📊 **Verification is graded** — a chain is `verified` when nothing failed and at least one substantive step verified; inconclusive steps (notes, ops without an automatic checker) lower confidence but no longer poison the chain; `generate_derivation_report` always renders the failed/inconclusive counts and LaTeX-renders `given` symbol keys.
- 🧭 **Goal tracking sees the whole history** — "solve for X" is satisfied when ANY step output isolates X, so a later `evalf` no longer false-reports "Not yet solved".

### Changed

- 🧱 **`math()` internals split into `tools/_math_dispatch.py`** (operation dispatch, parsing, parameter audit); `tools/math.py` is now a thin recording wrapper.

## [1.1.0] - 2026-09-10

Validated end-to-end by a black-box regression harness (headless MCP client, byte-identical task inputs, artifacts isolated via `SYMKIT_DATA_DIR`): verification false-failures dropped from 15 to 0, generated reports retain all step formulas, fractional exponents parse as exact rationals, and no cross-run formula contamination was observed.

### Fixed

- 🧭 **Session verification no longer false-fails substitute steps** — the verifier now builds assumption-aware target symbols, so substitution actually matches the input symbols; purely numeric residuals are compared with a 1e-9 tolerance instead of exact equality (machine-epsilon differences no longer flip correct steps to FAILED).
- ➗ **Numeric divisions are normalized during parsing** — `x**(1/6)` no longer keeps an unevaluated `Mul(1, 1/6)` exponent, so float bases like `65.0**(1/6)` evaluate numerically; unevaluated `Derivative` semantics are preserved.
- 🧮 **`substitute` folds evaluable unevaluated derivatives** — substituting into a deferred derivative no longer leaves `Derivative(0, x)` behind.
- 🔎 **Derived formulas are searchable** — `formula_search` now includes session-derived formulas (`formulas/derived/`) in its corpus; previously they were only visible to the recommender.
- 📄 **`generate_derivation_report` renders what it is given** — step `latex` is rendered as display math; `verification` accepts int counts (total/verified/failed/inconclusive) plus a text `note` (legacy bools still render as ✅/❌); the Results section emits proper LaTeX instead of raw SymPy source text.
- 🎯 **Goal progress counts variables from all steps** — target variables appearing only in intermediate steps are no longer reported missing; `progress_score` reflects coverage when no explicit target expression is set; multi-letter underscored symbols (e.g. `nu_tilde`) are extracted from goal text.
- 💤 **Persisting no longer flips an ACTIVE session to PAUSED** — `session_start` no longer returns the confusing `status: "paused"` right after creation; `session_complete`'s `auto_save` is documented as gating only the formula-library write (the session JSON is always persisted).
- 🧷 **Pinned `mcp>=1.0.0,<2.0`** — fresh installs no longer crash at startup (mcp 2.x removed `mcp.server.fastmcp`); `serverInfo.version` now reports the symkit package version instead of the MCP SDK version.

### Added

- 🔢 **New `evalf` math operation** — numeric floating-point evaluation, so agents no longer need decimal-exponent workarounds.
- ⚠️ **solve() warns on float coefficients** — solutions from equations containing float coefficients (e.g. `0.5`) carry an explanatory warning pointing to exact fractions (`1/2`) for exact symbolic results.

## [1.0.1] - 2026-07-08

### Changed

- 🐍 **Lowered Python requirement from 3.12+ to 3.10+** to make `pip install symkit-mcp` available on more environments.

### Fixed

- 🔢 **Corrected MCP tool count from 43 to 41** across `README.md`, `README.zh-CN.md`, `ARCHITECTURE.md`, `docs/symkit-design.md`, and `docs/symkit-design.zh-CN.md`.

## [1.0.0] - 2026-07-08

### Changed

- 🏷️ **Project rebranded to SymKit** — a general-purpose symbolic formula derivation engine
  - Renamed packages from `nsforge` / `nsforge_mcp` to `symkit` / `symkit_mcp`
  - Updated `pyproject.toml`, README, and documentation to reflect the new name
  - Project positioning is now domain-agnostic (physics, engineering, chemistry, biology, economics, etc.)
- 🧹 **Repository cleanup for public release**
  - Removed generated cache files (`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`)
  - Removed runtime artifacts (`derivation_sessions/`, `formulas/derived/`)
  - Removed development-only workspace files (`.claude/`, `memory-bank/`, `.vscode/`)
  - Rewrote `.gitignore` in English with broader coverage
- 📝 **Documentation refreshed**
  - Rewrote `README.md` and `README.zh-CN.md` with general-purpose examples and the correct **41-tool** count
  - Updated `ARCHITECTURE.md`, `CLAUDE.md`, and `ROADMAP.md` to match the current tool set
  - Removed outdated references to non-existent tools, skills, and Memory Bank
- 🌐 **Source comments internationalized**
  - All Chinese comments and docstrings in `src/` translated to English
- 📦 **Version bumped to 1.0.0** across `pyproject.toml`, `src/symkit/__init__.py`, and `src/symkit_mcp/__init__.py`; updated `Development Status` classifier to `5 - Production/Stable`.
- 🚀 **Initial PyPI release automation** via `.github/workflows/release.yml` using Trusted Publishing (OIDC): pushes to `main` publish to TestPyPI, and `v*` tags publish to PyPI.

## [0.2.5] - 2026-07-07

### Fixed

- 🐛 **CWD-relative data paths broke after `pip install`** — seed formulas,
  derived formulas, and session JSONs were resolved relative to the current
  working directory, so they vanished or leaked across runs when the server
  was launched from anywhere other than the repo root.
  - Seed formulas now ship read-only inside the wheel under
    `symkit/resources/seed_formulas/` and load via `importlib.resources`.
  - Derived formulas and session JSONs persist in a per-user data directory
    resolved with `platformdirs` (e.g. `~/.local/share/symkit/`,
    `%LOCALAPPDATA%\symkit`). Override with the `SYMKIT_DATA_DIR` env var.
  - Added `src/symkit/domain/paths.py` as the single source of truth for data
    directory resolution.
- 🐛 **Derived-formula data isolation bug** — `DerivationSession.__post_init__`
  instantiated a fresh `DerivationRepository(Path("formulas/derived"))` that
  bypassed the global singleton and the test fixture's temp dir, causing real
  persisted formulas to outscore test candidates. This was the root cause of
  two pre-existing test failures (`test_derive_with_scipy_external_source`,
  `test_derive_includes_external_recommendations`), now fixed. The
  `fresh_session_manager` fixture now resets the repository singleton too.

### Changed

- 🧹 **Removed three unused heavy dependencies** — `matplotlib`, `pint`, and
  `scipy` were declared but never imported at runtime. `scipy_constants.py`
  hardcodes CODATA values as float literals; the "scipy" string remains only as
  a textual source label. `pip install symkit-mcp` is now significantly lighter
  (no more numpy/scipy/matplotlib transitive pull).
- 📦 **Seed formula library moved into the package** — the six seed YAMLs
  (Reynolds number, Navier-Stokes, Euler, continuity, Newton's 2nd law, ideal
  gas law) now live under `src/symkit/resources/seed_formulas/` and ship in the
  wheel. User-added formulas via `formula_add` write to a writable per-user
  overlay that overrides seeds by id; deleting a seed-id removes only the
  override, leaving the read-only seed intact.
- 📝 **Version bumped to 0.2.5** across `pyproject.toml`,
  `src/symkit/__init__.py`, and `src/symkit_mcp/__init__.py`.

## [0.2.4] - 2026-01-21

### Added

- Unified `math()` tool supporting ~25 symbolic operations
- Step-by-step derivation sessions with full CRUD control
- Symbol assumption management
- External formula search (Wikidata, SciPy constants, BioModels)
- Symbol registry for domain-specific notation
- Code/report generation (Python, LaTeX, Markdown, SymPy)
- 43 MCP tools total across math, derivation, assumptions, verification, and orchestration

### Changed

- `pyproject.toml` version synchronized to `0.2.4`
- `src/symkit/__init__.py` and `src/symkit_mcp/__init__.py` versions synchronized to `0.2.4`

### Fixed

- MyPy type errors in `sympy_engine.py` and `services.py`
- Ruff linting issues across the codebase

## [0.2.0] - 2025-12-15

### Added

- Initial derivation framework
- Formula repository with provenance tracking
- Basic MCP server integration

## [0.1.0] - 2025-12-01

### Added

- Initial project structure
- SymPy engine integration
- Core domain entities and value objects

# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  - Rewrote `README.md` and `README.zh-CN.md` with general-purpose examples and the correct **43-tool** count
  - Updated `ARCHITECTURE.md`, `CLAUDE.md`, and `ROADMAP.md` to match the current tool set
  - Removed outdated references to non-existent tools, skills, and Memory Bank
- 🌐 **Source comments internationalized**
  - All Chinese comments and docstrings in `src/` translated to English

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

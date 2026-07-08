# AGENTS.md

Workspace instructions for ZCode agents working in `nsforge-mcp-sigma`.

## Repository Purpose

**SymKit MCP** (`symkit-mcp`) — a FastMCP server exposing ~43 MCP tools for symbolic formula derivation over SymPy. Domain-agnostic: physics, engineering, chemistry, biology, economics. The server runs over MCP stdio; AI agents (Claude, etc.) are the clients.

Entry point: `src/symkit_mcp/server.py` → `symkit-mcp` console script. The single `math()` tool covers ~25 symbolic operations; `session_*` tools manage step-by-step derivations with full provenance persisted to `derivation_sessions/`.

## Major Directories

- `src/symkit/` — Core domain library (DDD-layered, **no MCP dependency**)
  - `domain/` — Pure business logic, entities, value objects, services. Must not import external/infra modules.
  - `application/` — Use cases coordinating Domain ↔ Infrastructure.
  - `infrastructure/` — SymPy engine, file persistence, external adapters (Wikidata, SciPy, BioModels).
  - `resources/` — Static resources.
- `src/symkit_mcp/` — MCP presentation layer
  - `server.py` — FastMCP entry; eagerly initializes `SessionManager` in a worker thread on startup (see Gotchas).
  - `tools/` — Tool implementations grouped by concern: `math.py`, `session.py`, `formula.py`, `codegen.py`, `symbols.py`, `assumptions.py`, `orchestration.py`. All register via `register_all_tools(mcp)` in `__init__.py`.
  - `tools/_state.py` — **Process-global shared state**: single `_current_session` and `_current_context`. All tool modules read/write through `get_session()`/`set_session()`/`get_context()`/`set_context()`.
- `formulas/` — YAML formula library (`library/<category>/*.yaml`) and `derived/` outputs (gitignored).
- `derivation_sessions/` — Persisted session JSON (gitignored runtime artifacts).
- `tests/` — pytest suite, phase-organized (`test_phase1_*` … `test_phase5_*`) plus domain/engine/parser suites. E2E MCP smoke tests (`test_mcp_e2e.py`, `test_mcp_minimal.py`) spawn the server in stdio mode via the MCP client SDK.
- `docs/` — Design docs (`symkit-design.md`, `composable-formula-modification-engine.md`, etc.).
- `.github/bylaws/` — Binding sub-laws: `ddd-architecture.md`, `git-workflow.md`, `python-environment.md`.

## Build / Test / Lint Commands

Package manager is **uv** (preferred over pip). Python 3.12+ required (`.python-version` pins 3.12).

```bash
uv venv && uv sync --all-extras          # setup
uv run pytest                            # run tests (asyncio_mode=auto, --cov=src)
uv run pytest tests/test_session_verify_tools.py # focused test file
uv run ruff check src/ tests/            # lint (line-length 100, py312 target)
uv run mypy src/                         # typecheck (strict)
uv run python -m symkit_mcp.server       # run the MCP server (stdio)
uv run pytest tests/test_mcp_e2e.py      # end-to-end MCP smoke test
```

Pre-commit checklist (from `.github/bylaws/git-workflow.md`): pytest → ruff → mypy are **non-skippable**; update README/CHANGELOG/ROADMAP if user-visible behavior changed.

## Architecture Boundaries (DDD)

Enforced by convention; respect them on every edit:

1. **Domain Layer has zero external dependencies.** No imports from `infrastructure/`, `symkit_mcp`, sympy networking, or storage. Domain defines Repository *interfaces*; Infrastructure implements them.
2. Dependency direction: `symkit_mcp (Presentation) → application → domain ← infrastructure`.
3. The MCP layer (`symkit_mcp/`) is the only place that knows about FastMCP / MCP protocol. `symkit/` core must remain reusable without MCP.
4. Tool modules must not hold business logic — delegate to domain services / use cases.

Modularity limits (bylaw §5): files ≤200 lines soft / 400 hard; functions ≤30 / 50; classes ≤150 / 300. Cyclomatic complexity ≤10 soft / 15 hard. Propose refactor when exceeded.

## Coding Conventions

- **Language for docs/comments**: the constitution, bylaws, and ARCHITECTURE.md are written in Traditional/Mandarin Chinese; match the surrounding language when editing those files. Code identifiers and docstrings are English. Per `CLAUDE.md`: respond in Simplified Chinese when the user writes in Chinese.
- **Commits**: Conventional Commits — `<type>(<scope>): <subject>` with `feat|fix|docs|refactor|test|chore`. Branch model: `main` (protected, stable), `develop`, `feature/*`, `hotfix/*`.
- **Imports**: isort with `known-first-party = ["symkit", "symkit_mcp"]` (configured in `pyproject.toml`). Ruff selects E/W/F/I/B/C4/UP/ARG/SIM; E501 ignored.
- **Typing**: mypy strict, `warn_return_any`, `warn_unused_ignores`. `disallow_untyped_decorators = false` (MCP decorators lack annotations). Missing stubs ignored for `sympy`, `mcp`, `yaml`.
- **Per-file lint overrides**: `UP042` is suppressed in several `domain/` modules (ClassVar-style typing); `ARG002` suppressed in `infrastructure/sympy_engine.py`. Don't "fix" these without checking.
- **Tests**: any new logic gets a test in `tests/`. Scattered/ad-hoc tests belong in `tests/` files, never dropped in REPLs (constitution §6).

## Gotchas

- **Global session state is process-wide.** `tools/_state.py` keeps one `_current_session` / `_current_context`. The MCP server is single-process; do not assume per-request isolation. Always go through the `get_*/set_*` accessors, never mutate the module globals directly.
- **Blocking init on startup.** `server.main()` eagerly constructs the `SessionManager` in a `ThreadPoolExecutor` so the first `session_start()` doesn't stall FastMCP's asyncio loop (synchronous tool handlers run on the loop). Preserve this if you touch startup.
- **antlr4 runtime is pinned**: `antlr4-python3-runtime>=4.11,<4.12` — required by `sympy.parsing.latex`. Don't let a newer antlr4 sneak in via uv.
- **Gitignored runtime dirs** (do not commit): `derivation_sessions/`, `formulas/derived/`, `.coverage`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`.
- **External adapters are network-optional**: Wikidata/SciPy/BioModels searches should degrade gracefully when offline; legacy search paths must not hard-fail the server.
- **Windows platform**: repo lives under `I:\Formulation\...`; use forward-slash paths in tooling and `uv run` rather than relying on shell activation. `.venv\Scripts\` layout on Windows.

## Docs to Read Before Sensitive Edits

- `CONSTITUTION.md` + `.github/bylaws/*.md` — binding rules before any architectural change.
- `ARCHITECTURE.md` — layer/tool inventory (Chinese); update it after refactors (bylaw §6.2).
- `docs/symkit-design.md` — core design before touching `symkit/domain/`.
- `docs/composable-formula-modification-engine.md` — before editing `formula.py` / formula library logic.
- `CLAUDE.md` — tool usage patterns and the pre-commit checklist summary.

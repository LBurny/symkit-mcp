# SymKit

Step-by-step symbolic math for AI agents: derive, verify, and certify formulas over SymPy, with full provenance.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-1187%20passed-brightgreen.svg)]()

**English** | [简体中文](README.zh-CN.md)

## What is SymKit?

An [MCP](https://modelcontextprotocol.io/) server that lets AI agents do exact symbolic math through conversation. Built on SymPy, it combines known formulas into new ones, records every derivation step, and verifies each result symbolically and dimensionally — instead of leaving calculations as uncheckable LLM prose.

| LLM alone | With SymKit |
|---|---|
| ❌ "The answer is approximately..." | ✅ "The exact expression is ..." |
| ❌ Recalculating from scratch to double-check | ✅ Every step is recorded and independently verifiable |
| ❌ "I think the units work out" | ✅ Dimensional analysis checks every result |
| ❌ "Where did this formula come from?" | ✅ Full provenance: base formulas + derivation steps |

Works for physics, engineering, chemistry, biology, economics — any domain where formulas are combined and transformed.

## Core capabilities

| Capability | What it means | Main tools |
|---|---|---|
| Derive | Combine base formulas into new ones | `derive`, `intent_execute`, `math` |
| Control | Inspect, annotate, and roll back every step | `session_*` |
| Verify | Symbolic equivalence + dimensional analysis | `session_verify_*`, `assume` |
| Ship | Export to Python, LaTeX, Markdown, or SymPy script | `generate_output` |

Example — deriving the angular frequency of a simple harmonic oscillator from `F = -kx` and `F = m·a`:

```text
1. Load the two base formulas and substitute → m·d²x/dt² = -kx
2. Solve the ODE → x(t) = A·cos(ωt + φ),  ω = √(k/m)
3. Verify by substitution: d²x/dt² = -ω²x  ✓
4. Store the result with its full derivation history
```

## Tools

46 MCP tools across 9 categories. Most work flows through a few high-level tools; power users can drive each step individually.

| Category | Count | Highlights |
|---|---|---|
| Unified Math | 1 | `math` — 33 symbolic operations: calculus, ODEs, matrices, vector analysis, integral transforms, dimensional analysis |
| Session Management | 15 | `session_start`, `session_record_step`, `session_rollback`, `session_complete` |
| Verification | 5 | `session_verify_step`, `session_verify_session`, `session_certify`, `lean_status` |
| Assumptions | 7 | `assume`, `unassume`, `check_assumption_conflicts` |
| Formula Library | 8 | `formula_search`, `formula_get`, `formula_add`, `formula_promote` |
| Symbol Semantics | 4 | `register_symbol`, `lookup_symbol`, `check_symbol_conflicts` |
| Output | 1 | `generate_output` (`markdown_report` / `latex` / `python` / `sympy_script`) |
| Orchestration | 3 | `derive`, `intent_execute`, `list_patterns` |
| Meta | 2 | `tool_categories`, `tool_recommend` |

## Derivation sessions

A derivation is a chain of immutable, verifiable steps. Expressions are never edited in place — if something goes wrong, `session_rollback` to the last good state and continue, keeping the whole derivation reproducible. Every step stores its inputs, outputs, notes, assumptions, and SymPy command, persisted as JSON under the data directory.

## Formula library

Formulas live in YAML files backed by a persistent SQLite FTS5 index — deterministic, offline, instant. Entries are ranked by tier:

| Tier | Source | Boost |
|---|---|---|
| `seed` | Bundled read-only formulas (Reynolds number, Navier–Stokes, …) | +0.10 |
| `curated` | `formula_add`, or promoted via `formula_promote` | +0.15 |
| `staging` | Session output from `session_complete(auto_save=True)` | +0.00 |

```text
formula_search("Navier-Stokes", domain="fluid_dynamics")
formula_get("ns_incompressible", load_into_session=True)
math("simplify", "...", session=True)
session_complete(description="Incompressible NS momentum equation")
```

Search covers names, aliases (Chinese works: `雷诺数` → Reynolds number), tags, domains, descriptions, and expression text. Session output lands in `staging` with a deterministic id and is deduplicated; promote keepers with `formula_promote`, inspect tiers with `formula_stats`, rebuild after hand-editing YAML with `formula_reindex`. The index (`<data dir>/formulas/index.sqlite3`) is a cache — deleting it is always safe. Optional external sources (`source="wikidata" | "scipy" | "biomodels"`) degrade gracefully offline.

## Lean 4 kernel certification (optional)

`session_certify()` re-proves eligible algebraic-equality steps of the current session (`simplify` / `expand` / `factor` / `combine` in the rational fragment) with the Lean 4 + Mathlib kernel, using `ring` / `field_simp`. Results are attached under each step's `details.lean`; existing verification verdicts are never modified, and `unproven` only means the automation could not close the goal — not that the step is wrong. A step whose input and output are identical (`x = x`, `0 = 0`) is reported as `trivial` and excluded from the `proven` count: the kernel discharges it instantly but validates no algebra. No extra Python packages are required.

Call `lean_status()` first if you are unsure whether the backend is installed — it is read-only (never runs Lean, never downloads) and reports the resolved toolchain, Mathlib, and workspace paths, where each was resolved from, which layer is missing, and the exact next command. Do not probe the filesystem or run `lake --version` yourself: a missing directory is not evidence, and Mathlib lives under `<data dir>/lean-workspace/.lake/packages/mathlib`.

### Setup

```bash
# One-time: install elan + Lean 4 + prebuilt Mathlib (~1–2 GB download, needs network)
symkit-lean-setup --yes

# Optionally pin a Lean version instead of stable
symkit-lean-setup --yes --toolchain v4.24.0
```

Configuration knobs:

- **Data directory**: the Lean workspace is installed to `<data dir>/lean-workspace`. Set `SYMKIT_DATA_DIR` before running the setup (and the server) to relocate it.
- **Toolchain location**: `lake` is discovered from `ELAN_HOME/bin`, then `PATH`, then `~/.elan/bin`. Point `ELAN_HOME` at an existing elan install to reuse it — it takes precedence, so a default `~/.elan/bin/lake` on `PATH` cannot shadow it. Certification also checks that the selected `lake` already owns the Lean version pinned in the workspace; otherwise it reports `lean_available: false` with a directing reason instead of starting a fresh toolchain download.
- **Proxies**: if the download stalls or fails behind a corporate proxy, export `HTTP_PROXY` / `HTTPS_PROXY` before running the setup — the elan installer does not read the Windows system proxy settings.
- **Readiness check**: re-running `session_certify()` reports `lean_available: true` once the toolchain and the `.symkit-lean-ready` stamp are in place.

Usage notes: `session_certify()` requires an active session, and steps that divide by a variable need an explicit assertion that the denominator is nonzero. Supply it at certify time with `session_certify(assumptions={"x": {"nonzero": True}})` (or `assumptions="x nonzero"`), or register it beforehand with `assume({"x": "nonzero"})`. Without a toolchain, everything else in SymKit is unchanged.

## Installation

Requirements: Python 3.10+, an MCP-compatible client (Claude Desktop, Claude Code, Cherry Studio, …), and uv or pip.

### Option A — uv (recommended)

```bash
uv tool install symkit-mcp
symkit-mcp --version
```

`uvx symkit-mcp` runs the latest release on the fly without installing.

### Option B — pip

```bash
pip install symkit-mcp
```

(`pipx install symkit-mcp` for an isolated environment.)

### Option C — from source

```bash
git clone https://github.com/LBurny/symkit-mcp.git
cd symkit-mcp
uv sync --all-extras
uv run symkit-mcp
```

### Data directory

Runtime data lives per-user (via `platformdirs`): `~/.local/share/symkit/` on Linux, `%LOCALAPPDATA%\symkit` on Windows, `~/Library/Application Support/symkit` on macOS. Set `SYMKIT_DATA_DIR` to override — e.g. per project via the MCP server `env` block, to isolate sessions and formula libraries. Seed formulas ship read-only inside the package; user formulas from `formula_add` go to a writable overlay that overrides seeds by id; session-derived formulas go to `<data dir>/formulas/derived/`.

### Connect your client

Add an `mcpServers` entry (Claude Desktop: `claude_desktop_config.json`; Cherry Studio: settings panel).

Installed on PATH (uv tool / pip / pipx):

```json
{ "mcpServers": { "symkit": { "command": "symkit-mcp", "args": [] } } }
```

Without installing (uvx pulls and caches the latest release):

```json
{ "mcpServers": { "symkit": { "command": "uvx", "args": ["symkit-mcp"] } } }
```

From a source checkout:

```json
{
  "mcpServers": {
    "symkit": {
      "command": "uv",
      "args": ["run", "--no-sync", "--directory", "<local-path>",
               "python", "-m", "symkit_mcp.server"]
    }
  }
}
```

> Windows: if the client reports "command not found", use an absolute path, e.g. `"C:/Users/you/AppData/Local/uv/tools/symkit-mcp/Scripts/symkit-mcp.exe"`.

## Architecture

```text
src/
├── symkit/               # Core domain library (no MCP dependency)
│   ├── domain/           # Entities, derivation engine, verifier contracts
│   ├── application/      # Use cases
│   └── infrastructure/   # SymPy engine, Lean checker, persistence, adapters
└── symkit_mcp/           # MCP server layer (FastMCP) + 46 tools
formulas/                 # Seed formula library (source tree)
tests/                    # 1187 tests
```

Domain-driven design: the core is independent of MCP and SymPy, engines are pluggable via protocols, and formulas/sessions persist as readable YAML/JSON.

## Development

```bash
uv run pytest          # full test suite
uv run ruff check src/ tests/
uv run mypy src/
uv run symkit-mcp      # dev server
```

## Learn more

- [Architecture](ARCHITECTURE.md) — DDD layering and tool inventory
- [SymKit Design](docs/symkit-design.md) ([中文](docs/symkit-design.zh-CN.md)) — in-depth technical design
- [Recommended system prompt](docs/recommended-system-prompt.md) — agent-side prompt for tool-driven derivations
- [Roadmap](ROADMAP.md) — what's coming next
- [Formula library fields](formulas/README.md) — YAML entry format

## Acknowledgments

SymKit builds on [nsforge-mcp](https://github.com/u9401066/nsforge-mcp), which pioneered the neurosymbolic formula-derivation approach, and can be used alongside [sympy-mcp](https://github.com/sdiehl/sympy-mcp), a general-purpose SymPy MCP service.

## License

[Apache 2.0](LICENSE).
# SymKit

> **Mathematica-style symbolic computation, powered by LLMs.**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-266%20passed-brightgreen.svg)]()
[![Lint](https://img.shields.io/badge/ruff-passing-brightgreen.svg)]()

🌐 **English** | [简体中文](README.zh-CN.md)

## What if you had Mathematica's symbolic engine, driven by natural language?

Mathematica gave us precise symbolic math. LLMs gave us natural-language reasoning. **SymKit combines both.**

It is an MCP server that lets AI agents perform step-by-step symbolic derivations: calculate, transform, verify, and store formulas with full provenance — all through conversation.

```text
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  You describe the math in plain English                              │
│        ↓                                                           │
│  SymKit executes, verifies, and records every step                 │
│        ↓                                                           │
│  You get an exact, reusable formula with an audit trail            │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Why SymKit?

| Traditional LLM | SymKit |
|---|---|
| ❌ "The answer is approximately..." | ✅ "The exact expression is..." |
| ❌ "Let me calculate that again" | ✅ Every step is recorded and verifiable |
| ❌ "I think these units work out" | ✅ Dimensional analysis checks every result |
| ❌ "Where did this formula come from?" | ✅ Full provenance: base formulas + derivation steps |
| ❌ Calculation is lost in chat history | ✅ Stored as reusable Markdown + YAML |

## What it does

SymKit is **not a formula database**. It is a **symbolic derivation engine** that creates new formulas from existing ones.

```text
Known formulas                      New formula
┌─────────────────┐                 ┌────────────────────────────┐
│ F = -kx         │                 │                            │
│ F = ma          │  ──compose──▶   │  ω = √(k/m)                │
│ d²x/dt² = a     │                 │  (simple harmonic oscillator) │
└─────────────────┘                 └────────────────────────────┘
```

Use it for physics, engineering, chemistry, biology, economics — any domain where you need to combine and transform mathematical relationships.

## ⚡ Four superpowers

| Capability | What it means | Tools |
|---|---|---|
| **Derive** | Combine base formulas into new ones | `derive`, `intent_execute`, `math` |
| **Control** | Review, annotate, and rollback every step | `session_*`, `*_step` |
| **Verify** | Check correctness symbolically and dimensionally | `session_verify_*`, `assume*` |
| **Ship** | Turn results into Python, LaTeX, Markdown, or SymPy | `generate_*` |

## 🚀 See it in action

**Derive a physical law from first principles:**

```text
User: Derive the angular frequency of a simple harmonic oscillator.

SymKit:
  1. Load F = -kx  and  F = m·d²x/dt²
  2. Substitute → m·d²x/dt² = -kx
  3. Solve ODE → x(t) = A·cos(ωt + φ),  ω = √(k/m)
  4. Verify by substitution: d²x/dt² = -ω²x  ✓
  5. Store result with full derivation history
```

**Build a custom engineering model:**

```text
User: Find the cutoff frequency of an RC high-pass filter.

SymKit:
  1. Load Q = CV and V = IR
  2. Derive capacitive reactance X_c = 1/(2πfC)
  3. Set X_c = R at cutoff
  4. Solve for f → f_c = 1 / (2πRC)  ✓
```

**Verify a calculus result:**

```text
User: Calculate and verify ∫(x² + 3x) dx.

→ Result: x³/3 + 3x²/2 + C
→ Verify: d/dx(x³/3 + 3x²/2) = x² + 3x  ✓
```

## 🛠️ 41 MCP tools, one coherent workflow

SymKit exposes **41 MCP tools** across 8 categories. Everything routes through a few high-level tools while power users can drop down to individual steps.

| Category | Tools | Count |
|---|---|---|
| **Unified Math** | `math` | 1 |
| **Session Management** | `session_start`, `session_show`, `session_rollback`, `session_complete`, ... | 17 |
| **Assumptions** | `assume`, `show_assumptions`, `assume_for_step`, `list_assumptions`, `check_assumption_conflicts`, `clear_step_assumptions` | 6 |
| **Formula Search** | `formula_search`, `formula_get`, `formula_add`, `formula_categories` | 4 |
| **Symbol Registry** | `register_symbol`, `lookup_symbol`, `list_domain_symbols`, `check_symbol_conflicts` | 4 |
| **Code Generation** | `generate_python_function`, `generate_latex_derivation`, `generate_derivation_report`, `generate_sympy_script` | 4 |
| **Derivation & Orchestration** | `derive`, `intent_execute`, `list_patterns` | 3 |
| **Tool Discovery** | `tool_categories`, `tool_recommend` | 2 |

The `math()` tool alone covers ~25 symbolic operations — calculus, ODEs, matrices, vector analysis, integral transforms — and can write its result directly into a derivation session.

## 🔍 Formula search workflow

SymKit can pull authoritative formulas from Wikidata and physical constants from SciPy, normalize LLM queries automatically, and load the chosen formula straight into a derivation session.

**Recommended workflow:**

```text
1. Search
   formula_search("Navier-Stokes equations", domain="fluid_dynamics")

2. Get and load
   formula_get("Q201321", source="wikidata", load_into_session=True)

3. Derive
   math("simplify", "...", session=True)

4. Complete
   session_complete(description="Incompressible NS momentum equation")
```

**Query normalization:** you can write queries naturally — `fluid_dynamics`, `fluid mechanics`, and `cfd` all resolve to the same domain; `Navier–Stokes` (en dash) and `Navier-Stokes` (hyphen) match the same Wikidata item.

**MathML handling:** Wikidata sometimes returns rendered MathML for search previews. Call `formula_get` on the result ID to retrieve the original LaTeX and a SymPy-ready string.

## 🎛️ You own every step

A derivation in SymKit is a chain of immutable, verifiable steps. You can:

- **Create** — `session_record_step`
- **Read** — `session_get_steps`, `session_show`
- **Annotate** — `session_add_note`
- **Rollback** — `session_rollback`
- **Verify** — `session_verify_step`, `session_verify_session`

Expressions are never edited in place. If something goes wrong, roll back to the last good state and continue. This keeps the entire derivation reproducible.

## 🌍 Works with the MCP ecosystem

SymKit is designed to extend, not replace, your scientific computing stack. It handles derivation, verification, and provenance; raw symbolic computation and base formulas are delegated to SymPy-MCP.

**When to use SymKit:**

- ✅ Deriving new formulas from existing ones
- ✅ Building temperature/pressure/parameter-corrected models
- ✅ Creating custom models for any quantitative domain
- ✅ Producing verified, citable derivation results

**When to use something else:**

- ❌ Looking up basic physics formulas → use `sympy-mcp`
- ❌ Fetching physical constants → use `sympy-mcp` or `SciPy`
- ❌ Clinical scoring → use `medical-calc-mcp`
- ❌ Reading textbook formulas → use the reference directly

## 📦 Get started in 60 seconds

### Requirements

- **Python 3.10+**
- An MCP-compatible client: Claude Desktop, Claude Code, Cherry Studio, …
- **uv** (recommended) **or** pip

### Step 1 — Install SymKit

Pick **one** of the three install paths below. Each produces a runnable
`symkit-mcp` command you point your MCP client at in Step 3.

#### Option A — `uv` (recommended)

[`uv`](https://docs.astral.sh/uv/) is a fast Python package manager. Install
SymKit as an isolated global CLI tool — no virtualenv to manage, no clashes
with your system Python:

```bash
# 1. Install uv itself (if you don't have it yet)
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Install SymKit as a global CLI tool
uv tool install symkit-mcp

# 3. Verify it's on your PATH
symkit-mcp --version
```

`uv tool install` places a `symkit-mcp` entry point on your PATH. Upgrade later
with `uv tool upgrade symkit-mcp`, and uninstall with `uv tool uninstall symkit-mcp`.

> **No-install alternative:** `uvx symkit-mcp` runs the latest published
> release on the fly, caching it behind the scenes. Useful for one-off runs
> or for the MCP client config in Step 3 — no `uv tool install` required.

#### Option B — `pip`

```bash
# Install
pip install symkit-mcp

# Verify
symkit-mcp --version
```

Prefer [`pipx`](https://pypa.github.io/pipx/) (`pipx install symkit-mcp`) if
you want each CLI tool in its own isolated environment.

#### Option C — From source (development or unreleased changes)

```bash
git clone https://github.com/LBurny/symkit-mcp.git
cd symkit-mcp

# Install the project + dev/test extras into a local .venv
uv sync --all-extras

# Run the server straight from the checkout — no install step needed
uv run symkit-mcp
```

`uv run` executes against the local source tree, so you can edit and re-run
immediately. Pull the latest deps after changing `pyproject.toml` with
`uv sync`.

### Step 2 — Where data lives

After install, SymKit stores runtime data in a per-user directory (resolved via
`platformdirs`): derived formulas and session JSONs persist under
`~/.local/share/symkit/` (Linux), `%LOCALAPPDATA%\symkit` (Windows), or
`~/Library/Application Support/symkit` (macOS). Set the `SYMKIT_DATA_DIR`
environment variable to override this location. Seed formulas (Reynolds number,
Navier-Stokes, …) ship read-only inside the package; user-added formulas via
`formula_add` are written to the writable overlay and override seeds by id.

### Step 3 — Connect to your client

SymKit speaks MCP over stdio, so the same server works with every
MCP-compatible client. Below is the JSON config for Claude Desktop and Cherry
Studio.

#### Claude Desktop / Cherry Studio (JSON config)

Add an `mcpServers` entry to your client's config file (`claude_desktop_config.json`
for Claude Desktop; the equivalent settings panel for Cherry Studio).

**Installed via `uv tool` / `pip` / `pipx`** (the `symkit-mcp` command is on PATH):

```json
{
  "mcpServers": {
    "symkit": {
      "command": "symkit-mcp",
      "args": []
    }
  }
}
```

**Run on the fly without installing** (uvx pulls and caches the latest release):

```json
{
  "mcpServers": {
    "symkit": {
      "command": "uvx",
      "args": ["symkit-mcp"]
    }
  }
}
```

**Running from a local source checkout** (no install needed):

```json
{
  "mcpServers": {
    "symkit": {
      "command": "uv",
      "args": [
        "run",
        "--no-sync",
        "--directory",
        "<your-local-symkit-mcp-path>",
        "python",
        "-m",
        "symkit_mcp.server"
      ]
    }
  }
}
```

Replace `<your-local-symkit-mcp-path>` with the absolute path to your local
`symkit-mcp` clone. `--no-sync` skips dependency resolution on every launch;
run `uv sync` manually when dependencies change.

> **Windows PATH gotcha:** if Claude Desktop fails to launch the server with a
> "command not found" error, the app's process PATH may not include your
> `Scripts/` or uv tool directory. Switch the `command` to an absolute path,
> e.g. `"C:/Users/you/AppData/Local/uv/tools/symkit-mcp/Scripts/symkit-mcp.exe"`.

## 🏗️ Clean architecture, built to extend

```text
symkit-mcp/
├── src/
│   ├── symkit/               # Pure domain logic (no MCP dependency)
│   │   ├── domain/          # Entities, value objects, derivation engine
│   │   ├── application/     # Use cases
│   │   └── infrastructure/  # SymPy engine, adapters, persistence
│   └── symkit_mcp/          # MCP server layer
│       ├── server.py
│       └── tools/           # 41 MCP tools
├── formulas/                # Seed formula library (source tree)
├── tests/                   # 295 tests
└── pyproject.toml
```

- **Domain-driven design** — core logic is independent of MCP and SymPy.
- **Pluggable engines** — swap the symbolic engine or verifier via protocols.
- **File-based persistence** — formulas and sessions live in readable Markdown/YAML/JSON.

## 🧪 Development

```bash
# Run the full test suite
uv run pytest

# Lint and type check
uv run ruff check src/ tests/
uv run mypy src/

# Start the dev server
uv run symkit-mcp
```

## 📖 Learn more

- [Architecture](ARCHITECTURE.md) — DDD layering and responsibilities
- [SymKit Design](docs/symkit-design.md) — In-depth technical design (English)
- [SymKit Design (中文)](docs/symkit-design.zh-CN.md) — 中文设计文档
- [SymKit vs SymPy-MCP](docs/symkit-vs-sympy-mcp.md) — Capability comparison
- [Roadmap](ROADMAP.md) — What's coming next

## 🙏 Acknowledgments

SymKit is built on the foundation of [nsforge-mcp](https://github.com/u9401066/nsforge-mcp), which pioneered the neurosymbolic formula-derivation approach. The original Chinese README of nsforge-mcp can be found [here](https://github.com/u9401066/nsforge-mcp/blob/master/README.zh-TW.md).

SymKit works alongside [sympy-mcp](https://github.com/sdiehl/sympy-mcp), which provides the underlying SymPy-based symbolic computation and base formula lookup that SymKit builds upon.

## 📄 License

Apache 2.0 — see [LICENSE](LICENSE).

---

<p align="center">
  <strong>Stop answering math questions. Start deriving new knowledge.</strong>
</p>

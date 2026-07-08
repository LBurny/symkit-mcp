# CLAUDE.md - Claude Code Project Guide

This document provides project context for Claude Code (Anthropic's AI coding assistant).

---

## Project Overview

**SymKit MCP** — A general-purpose symbolic formula derivation engine for AI agents.

Built on SymPy + FastMCP. Provides **43 MCP tools** covering:

- A unified `math()` tool for ~25 symbolic operations (calculus, linear algebra, ODE, transforms)
- Step-by-step derivation sessions with CRUD control
- Symbol assumption management
- External formula search (Wikidata, SciPy constants, BioModels)
- Result verification (symbolic equality, reverse operations, dimension analysis)
- Code/report generation (Python, LaTeX, Markdown, SymPy scripts)

SymKit is **domain-agnostic**: it supports physics, engineering, chemistry, biology, economics, and any field that uses mathematical formulas.

### Core Tools

| Tool | Purpose |
|------|---------|
| `math()` | Unified math tool — diff, integrate, solve, dsolve, gradient, laplace, matrix ops... |
| `session_start/show/complete/rollback` | Step-by-step derivation session management |
| `assume/show_assumptions` | Symbolic assumption management |
| `formula_search` | Wikidata + SciPy + BioModels formula search |
| `derive` / `intent_execute` | High-level derivation orchestration |
| `generate_*` | Code/report generation |

### Usage Patterns

```python
# Stateless quick calculation
math("diff", "x**3", variable="x")  # → 3*x**2

# Stateful derivation
session_start("sho_oscillator", domain="mechanics")
math("dsolve", "m*diff(x(t),t,2) + k*x(t)", func="x", var="t", session=True)
session_show()
session_complete(description="Simple harmonic oscillator angular frequency")
```

## Governance Hierarchy

```
CONSTITUTION.md          ← Top-level principles (must not be violated)
  │
  ├── .github/bylaws/    ← Sub-laws (detailed rules)
  │     ├── ddd-architecture.md
  │     ├── git-workflow.md
  │     └── python-environment.md
  │
  └── docs/              ← Design documentation
```

## Core Principles

### 0. Development Philosophy
- Write or update design docs before changing behavior.
- Add tests to `tests/` for any new logic.
- Keep the Domain Layer free of external dependencies.

### 1. DDD Architecture
- Domain Layer has no external dependencies.
- Infrastructure implements Repository interfaces defined by Domain.
- See `.github/bylaws/ddd-architecture.md` for details.

### 2. Python Environment (uv preferred)

```bash
# Initialize
uv venv && uv sync --all-extras

# Add dependencies
uv add package-name
uv add --dev pytest ruff mypy
```

See `.github/bylaws/python-environment.md` for details.

### 3. Git Workflow

Before committing, run the checklist:
1. Update README if user-facing behavior changed.
2. Update CHANGELOG if applicable.
3. Update ROADMAP if progress was made.
4. Run `uv run pytest`, `uv run ruff check src/ tests/`, and `uv run mypy src/`.

## Directory Structure

```
src/
├── symkit/              # Core domain library (no MCP dependency)
│   ├── domain/          # Domain logic, entities, value objects
│   ├── application/     # Use cases
│   └── infrastructure/  # SymPy engine, adapters, persistence
│
└── symkit_mcp/          # MCP server layer
    ├── server.py        # FastMCP entry point
    └── tools/           # 43 MCP tool implementations
```

## Notes

- Update specs before changing code.
- Code is a "compiled artifact" of design docs.
- Follow Conventional Commits.
- Respond in Simplified Chinese when the user writes in Chinese.

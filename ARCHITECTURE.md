# Architecture

SymKit MCP Architecture Document (v1.5.0)

---

## System Overview

SymKit is a **general-purpose symbolic derivation engine** that provides AI agents with precise symbolic reasoning capabilities through the Model Context Protocol (MCP).

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI Agent (Claude, etc.)                     │
├─────────────────────────────────────────────────────────────────┤
│                     MCP Protocol Layer                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              symkit_mcp (44 Tools)                          ││
│  │  ┌───────────┐ ┌───────────┐ ┌───────────────┐ ┌─────────┐ ││
│  │  │  Session  │ │   Math    │ │ Tool Discovery│ │ Formula │ ││
│  │  │ 17 tools  │ │  1 tool   │ │  2 tools      │ │ 5 tools │ ││
│  │  └─────┬─────┘ └─────┬─────┘ └───────┬───────┘ └────┬────┘ ││
│  │        │             │             │              │         ││
│  │  ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌──────┴──────┐ ││
│  │  │  Symbol   │ │Assumption │ │  Codegen  │ │Derivation/  │ ││
│  │  │  4 tools  │ │  8 tools  │ │  4 tools  │ │Orchestration│ ││
│  │  └───────────┘ └───────────┘ └───────────┘ │  3 tools    │ ││
│  │                                            └─────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│                     symkit (Core Library)                       │
│  ┌───────────────┐  ┌─────────────────┐  ┌───────────────────┐  │
│  │    Domain     │  │   Application   │  │  Infrastructure   │  │
│  │  Pure Logic   │◄─│   Use Cases     │──►│   Persistence    │  │
│  └───────────────┘  └─────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## DDD Layered Architecture

### 1. Domain Layer (`src/symkit/domain/`)

Pure business logic with no external dependencies.

| Module | Description |
|--------|-------------|
| `entities/` | Formula, DerivationStep, DerivationSession |
| `value_objects/` | Expression, Assumption, Metadata |
| `services/` | SymPyEngine, DerivationEngine |
| `repositories/` | FormulaRepository (abstract interface) |
| `assumption_binding.py` | Sole implementation of assumption → Symbol binding (`resolve_assumed_symbol`, `apply_assumptions`); owns the property whitelist and conflict table. Assumptions are applied *after* parsing, onto free symbols only (invariant I1/I3) |
| `expr_io.py` | srepr-first reconstruction of archived expressions (`safe_load_expression`); verification replays the archived object instead of re-parsing a display string (invariant I2) |

### 2. Application Layer (`src/symkit/application/`)

Coordinates Domain and Infrastructure.

| Module | Description |
|--------|-------------|
| `use_cases/` | Derivation, verification, and formula management use cases |
| `dto/` | Data transfer objects |

### 3. Infrastructure Layer (`src/symkit/infrastructure/`)

Interfaces to external systems.

| Module | Description |
|--------|-------------|
| `persistence/` | YAML/JSON file storage |
| `formula_repository_impl.py` | FormulaRepository implementation |

### 4. MCP Layer (`src/symkit_mcp/`)

MCP protocol interface, independent of the core library.

| Module | Description |
|--------|-------------|
| `server.py` | MCP Server entry point |
| `tools/` | 44 MCP tool implementations |
| `tools/_math_dispatch.py` | `math()` internals: operation dispatch, expression parsing, per-operation parameter audit |
| `tools/_state.py` | Process-global current session/context shared by all tool modules |

---

## Tool Categories (44 Tools)

| Category | Count | Description |
|----------|-------|-------------|
| **Session** | 17 | Derivation session management and step operations; graded overall verification (a chain is verified when nothing failed and at least one substantive step verified) |
| **Math** | 1 | Unified math entry point (32 operations: calculus, matrices, ODE, transforms, numeric `evalf`, etc.) |
| **Assumption** | 8 | Symbolic assumption management |
| **Formula** | 5 | Formula search and management; searchable corpus = bundled seeds (read-only) + session-derived formulas + writable user overlay; non-seed entries are removable via `formula_remove` |
| **Symbol** | 4 | Symbol registration, lookup, and conflict detection |
| **Codegen** | 4 | Python / LaTeX / Markdown / SymPy generation |
| **Derivation / Orchestration** | 3 | High-level derivation orchestration |
| **Tool Discovery** | 2 | Tool discovery and recommendations |

---

## Data Flow

```
User Request → MCP Tool → Use Case → Domain Service → SymPy Engine
                                           │
                                           ▼
                              Infrastructure (YAML/JSON)
```

### Derivation Workflow Example

1. `session_start()` - Start a session.
2. `session_record_step()` - Record each step.
3. `math()` - Perform symbolic operations (differentiation, integration, solving, etc.).
4. `session_show()` - Display the current state.
5. `session_complete()` - Persist the session.

---

## Directory Structure

```
symkit-mcp/
├── src/
│   ├── symkit/              # Core Library (DDD)
│   │   ├── domain/          # Pure business logic
│   │   ├── application/     # Use-case coordination
│   │   └── infrastructure/  # Persistence, external adapters
│   └── symkit_mcp/          # MCP Server
│       ├── server.py        # Entry point
│       └── tools/           # 44 tools
├── formulas/                # Formula library
│   ├── library/             # Seed formulas (YAML, by category)
│   └── derived/             # Session-derived formulas (runtime output)
├── examples/                # Python examples
├── tests/                   # Tests
└── pyproject.toml
```

---

## Tech Stack

- **Python**: 3.10+
- **SymPy**: Symbolic computation engine
- **MCP SDK**: Model Context Protocol
- **uv**: Package manager
- **Ruff**: Linter
- **pytest**: Testing framework

---

## Related Documents

- [README.md](README.md) - Project overview
- [CONSTITUTION.md](CONSTITUTION.md) - Development principles
- [docs/symkit-vs-sympy-mcp.md](docs/symkit-vs-sympy-mcp.md) - Skill guide

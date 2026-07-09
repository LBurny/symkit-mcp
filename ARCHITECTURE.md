# Architecture

SymKit MCP Architecture Document (v1.0.1)

---

## System Overview

SymKit is a **general-purpose symbolic derivation engine** that provides AI agents with precise symbolic reasoning capabilities through the Model Context Protocol (MCP).

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI Agent (Claude, etc.)                     │
├─────────────────────────────────────────────────────────────────┤
│                     MCP Protocol Layer                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              symkit_mcp (41 Tools)                          ││
│  │  ┌───────────┐ ┌───────────┐ ┌───────────────┐ ┌─────────┐ ││
│  │  │  Session  │ │   Math    │ │ Tool Discovery│ │ Formula │ ││
│  │  │ 17 tools  │ │  1 tool   │ │  2 tools      │ │ 4 tools │ ││
│  │  └─────┬─────┘ └─────┬─────┘ └───────┬───────┘ └────┬────┘ ││
│  │        │             │             │              │         ││
│  │  ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌──────┴──────┐ ││
│  │  │  Symbol   │ │Assumption │ │  Codegen  │ │Derivation/  │ ││
│  │  │  4 tools  │ │  6 tools  │ │  4 tools  │ │Orchestration│ ││
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
| `tools/` | 41 MCP tool implementations |

---

## Tool Categories (41 Tools)

| Category | Count | Description |
|----------|-------|-------------|
| **Session** | 17 | Derivation session management and step operations |
| **Math** | 1 | Unified math entry point (calculus, matrices, ODE, transforms, etc.) |
| **Assumption** | 6 | Symbolic assumption management |
| **Formula** | 4 | External formula search and classification |
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
│       └── tools/           # 41 tools
├── formulas/                # Formula repository
│   ├── derivations/         # Derivation examples (Markdown)
│   └── fluid_dynamics/      # Saved formula examples
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

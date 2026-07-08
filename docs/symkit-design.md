# SymKit MCP Design Document

> Document Version: 0.2  
> Last Updated: 2026-07-03  
> Applicable Code Version: `symkit-mcp` 0.2.4 (`src/symkit/` and `src/symkit_mcp/`)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Design Goals](#2-design-goals)
3. [Architecture Overview](#3-architecture-overview)
4. [Layered Design](#4-layered-design)
   - 4.1 Domain Layer
   - 4.2 Application Layer
   - 4.3 Infrastructure Layer
   - 4.4 MCP Tool Layer
5. [Core Domain Models](#5-core-domain-models)
   - 5.1 DerivationSession
   - 5.2 DerivationStep
   - 5.3 Formula / FormulaInfo
   - 5.4 DerivationGoal / DerivationPattern
   - 5.5 AssumptionEngine / MathContext
   - 5.6 SymbolRegistry
6. [Expression Parsing Pipeline](#6-expression-parsing-pipeline)
7. [Derivation Lifecycle](#7-derivation-lifecycle)
8. [MCP Tool Design](#8-mcp-tool-design)
   - 8.1 Tool Categories
   - 8.2 math() Unified Math Tool
   - 8.3 Derivation Session Tools
   - 8.4 Formula Search Tools
   - 8.5 Assumption Tools
   - 8.6 Orchestration Tools
9. [External Adapters](#9-external-adapters)
10. [Step Verification](#10-step-verification)
11. [Assumptions and Conflict Detection](#11-assumptions-and-conflict-detection)
12. [Persistence and Round-Trip Loading](#12-persistence-and-round-trip-loading)
13. [State Management](#13-state-management)
14. [Testing Strategy](#14-testing-strategy)
15. [Design Principles](#15-design-principles)
16. [Appendix](#16-appendix)
    - A. Glossary
    - B. Key File Index
    - C. Quick Entry
    - D. Known Limitations

---

## 1. Project Overview

**SymKit MCP** is an MCP (Model Context Protocol) server for symbolic reasoning aimed at AI agents. Built on SymPy, it provides precise symbolic computation, formula derivation, step verification, and external formula search, while recording the entire derivation process in an auditable, traceable, and reusable manner.

SymKit is a **domain-agnostic** general-purpose formula derivation engine suitable for physics, engineering, chemistry, biology, economics, or any other domain that uses mathematical formulas. It emphasizes:

- **Verifiability**: Every derivation step is automatically or semi-automatically reverse-verified.
- **Traceability**: Each step records inputs, outputs, SymPy commands, assumptions, limitations, and human notes.
- **Reusability**: Local repositories and external authoritative sources (Wikidata, BioModels, SciPy CODATA) together provide referenceable formulas for derivations.
- **Human-AI Collaboration**: Supports inserting assumptions, limitations, observations, and correction suggestions into the derivation.
- **LaTeX Friendly**: Natively supports LaTeX input, subscript symbols, Greek letters, and physical star superscripts (e.g., `\beta^*`).

The external contract is a set of 43 MCP tools, where `math()` handles fast stateless/stateful computation, `session_start()` / `session_show()` / `session_complete()` provide interactive derivation sessions, and `derive()` provides a high-level automation entry point.

---

## 2. Design Goals

| Goal | Description |
|---|---|
| **Precise Computation** | Use SymPy rather than natural-language approximation to ensure mathematical correctness. |
| **Step Audit** | Every derivation step is an immutable record containing full context. |
| **Assumption Management** | Support four levels of assumptions (global/domain/session/step) and detect conflicts. |
| **Formula Recommendation** | Recommend available formulas based on goal text, domain, variables, and external sources. |
| **Pluggable Engine** | Abstract symbol engine, verifier, and repository via protocols for easy replacement. |
| **Tool Layering** | Provide fast tools like `math()`, session tools like `session_*`, and orchestration tools like `derive()`. |
| **LaTeX Robustness** | Compound LaTeX equations, star superscripts, subscript symbols, and `\max`/`\min` are parsed stably. |
| **Expression Round-Trip** | Store `srepr` in addition to string representations so expressions can be safely reloaded. |
| **Domain-Agnostic** | Core tools do not hard-code domain semantics; domain meaning comes from user context. |

---

## 3. Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────┐
│                        MCP Client / AI Agent                       │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ MCP Protocol
┌────────────────────────────────▼───────────────────────────────────┐
│                     MCP Tool Layer (src/symkit_mcp/tools/)          │
│  math / session / formula / assumptions / orchestration / symbols │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ Invocation
┌────────────────────────────────▼───────────────────────────────────┐
│                  Application Layer (src/symkit/application/)      │
│         CalculateUseCase / DeriveUseCase / VerifyUseCase          │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ Domain Interfaces
┌────────────────────────────────▼───────────────────────────────────┐
│                     Domain Layer (src/symkit/domain/)               │
│  DerivationSession, DerivationStep, AssumptionEngine,             │
│  StepVerifier, SymbolRegistry, FormulaRecommender, ...            │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ Adapter Interfaces
┌────────────────────────────────▼───────────────────────────────────┐
│                  Infrastructure Layer (src/symkit/infrastructure/) │
│  SymPyEngine, DerivationRepository, ScipyConstantsAdapter,        │
│  WikidataFormulaAdapter, BioModelsAdapter, ...                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Layered Design

### 4.1 Domain Layer

Responsible for business rules, entities, and domain services. Key files:

| File | Responsibility |
|---|---|
| `src/symkit/domain/derivation_session.py` | `DerivationSession`, `SessionManager`, and operations. Includes `output_srepr` and `_safe_load_expression`. |
| `src/symkit/domain/step_verifier.py` | Assumption-aware step verification engine. |
| `src/symkit/domain/assumption_engine.py` | Multi-level assumption storage and conflict detection. |
| `src/symkit/domain/formula.py` | `Formula` value object, parser, and source enum. Supports compound LaTeX equation splitting, `\max`/`\min` mapping, and `^*` superscript handling. |
| `src/symkit/domain/formula_recommender.py` | Local + external formula recommendation and `FormulaSourceAdapter` protocol. |
| `src/symkit/domain/derivation_goal.py` | Natural-language goal parsing. |
| `src/symkit/domain/derivation_pattern.py` | Derivation patterns and templates. |
| `src/symkit/domain/derivation_planner.py` | Goal-aware next-step suggestions. |
| `src/symkit/domain/symbol_registry.py` | Domain symbol semantics registry. |
| `src/symkit/domain/value_objects.py` | `MathContext`, `VerificationResult`, `StepStatus`, etc. |
| `src/symkit/domain/entities.py` | `Expression` and other data classes. |
| `src/symkit/domain/services.py` | `SymbolicEngine`, `Verifier`, `FormulaRepository` protocols. |

### 4.2 Application Layer

Coarse-grained use cases that coordinate Domain and Infrastructure without containing SymPy details:

| File | Responsibility |
|---|---|
| `src/symkit/application/use_cases.py` | `CalculateUseCase`, `SimplifyUseCase`, `DeriveUseCase`, `VerifyUseCase`. |

### 4.3 Infrastructure Layer

Technical implementation details:

| File | Responsibility |
|---|---|
| `src/symkit/infrastructure/sympy_engine.py` | SymPy-based `SymbolicEngine` implementation. |
| `src/symkit/infrastructure/derivation_repository.py` | YAML-persisted `DerivationRepository`. |
| `src/symkit/infrastructure/adapters/scipy_constants.py` | SciPy CODATA physical constants adapter. |
| `src/symkit/infrastructure/adapters/wikidata_formulas.py` | Wikidata SPARQL formula search adapter. |
| `src/symkit/infrastructure/adapters/biomodels.py` | BioModels SBML model adapter. |
| `src/symkit/infrastructure/adapters/base.py` | `BaseAdapter` and `FormulaInfo` unified format. |
| `src/symkit/infrastructure/verifier.py` | Basic `Verifier` implementation. |

### 4.4 MCP Tool Layer

Exposes 43 MCP tools; each module focuses on one capability area:

| File | Responsibility |
|---|---|
| `src/symkit_mcp/server.py` | FastMCP server entry point. |
| `src/symkit_mcp/tools/__init__.py` | Registers all tools uniformly. |
| `src/symkit_mcp/tools/math.py` | `math()` unified math tool, `assume()`, `show_assumptions()`. |
| `src/symkit_mcp/tools/session.py` | Unified derivation session workflow tools. |
| `src/symkit_mcp/tools/formula.py` | External formula search tools. |
| `src/symkit_mcp/tools/assumptions.py` | Assumption tools. |
| `src/symkit_mcp/tools/orchestration.py` | High-level orchestration tools `derive()`, `intent_execute()`, etc. |
| `src/symkit_mcp/tools/symbols.py` | Symbol registration tools. |
| `src/symkit_mcp/tools/codegen.py` | Code/LaTeX/report generation. |
| `src/symkit_mcp/tools/_state.py` | Global state (`SessionManager`, current session, `MathContext`). |
| `src/symkit_mcp/tools/_expression_parser.py` | Unified parser compatibility shim. |

---

## 5. Core Domain Models

### 5.1 DerivationSession

`DerivationSession` is SymKit's core stateful container, located in `src/symkit/domain/derivation_session.py`. It maintains:

- `current_expression`: the current expression (`sp.Basic`).
- `steps`: list of derivation steps (`list[DerivationStep]`).
- `formulas`: loaded formula mapping (`formula_id -> Formula`).
- `goal`: current derivation goal (`DerivationGoal`).
- `pattern`: derivation pattern (`DerivationPattern`).
- `assumption_engine`: `AssumptionEngine` instance.
- `symbol_registry`: `SymbolRegistry` instance.
- `verifier`: `StepVerifier` instance.
- `recommender`: `FormulaRecommender` instance.
- `planner`: `DerivationPlanner` instance.

Key methods:

- `load_formula`: load and parse a formula.
- `substitute / simplify / solve_for / differentiate / integrate`: perform derivation operations.
- `verify_step / verify_derivation`: verify a step or the entire chain.
- `set_goal / recommend_formulas / plan_next_steps`: goal-driven recommendations.
- `rollback_to_step / insert_note_after_step`: step management.
- `complete / save / load`: completion and persistence.
- `_safe_load_expression`: reload stored expressions using `srepr` first.

### 5.2 DerivationStep

`DerivationStep` records the complete context of each derivation step:

```python
step_number: int
operation: OperationType
description: str
input_expressions: dict[str, str]    # e.g., {"original": "x**3"}
output_expression: str               # human-readable str(expr)
output_latex: str
output_srepr: str                    # machine-readable sp.srepr(expr)
sympy_command: str
assumptions: list[str]
notes: str
limitations: list[str]
verification_result: str
status: StepStatus
timestamp: str
```

Each step is an immutable record for audit and academic traceability. `output_srepr` is critical: LaTeX subscripts like `\mu_t` become `Symbol('mu_{t}')`, whose `str()` is not valid Python input, so `srepr` is the only reliable way to reload.

### 5.3 Formula / FormulaInfo

- `Formula` (`src/symkit/domain/formula.py`) is an internal value object supporting parsing from SymPy strings, LaTeX, Python expressions, or dictionaries.
- `FormulaInfo` (`src/symkit/infrastructure/adapters/base.py`) is the unified output format for external adapters, with fields including `id`, `name`, `expression`, `latex`, `variables`, `source`, `category`, `description`, and `tags`.
- `Formula` includes a `parse_warnings` field to indicate when only the first equation of a compound input was recorded.

### 5.4 DerivationGoal / DerivationPattern

- `DerivationGoal` parses natural-language goals (e.g., "derive Navier-Stokes from conservation laws"), extracting domain, target form, target variables, and assumptions.
- `DerivationPattern` provides high-level derivation strategy templates, such as:
  - `CONSERVATION_CONSTITUTIVE`: conservation + constitutive relation
  - `VARIATIONAL`: variational principle
  - `OPERATOR_CORRESPONDENCE`: operator correspondence
  - `SERIES_APPROXIMATION`: series approximation
  - `EIGENMODE_ANALYSIS`: eigenmode analysis
  - `DIRECT_MANIPULATION`: direct algebraic manipulation

### 5.5 AssumptionEngine / MathContext

- `MathContext` (`src/symkit/domain/value_objects.py`) carries assumptions, coordinate system, simplification level, and domain.
- `AssumptionEngine` (`src/symkit/domain/assumption_engine.py`) supports four assumption levels, from lowest to highest priority:
  1. `GLOBAL`
  2. `DOMAIN`
  3. `SESSION`
  4. `STEP`

It handles merging, overriding, and conflict detection.

### 5.6 SymbolRegistry

`SymbolRegistry` (`src/symkit/domain/symbol_registry.py`) gives symbols domain semantics:

- Records symbol meaning, default units, applicable domain, and scope.
- Provides default symbols for fluid dynamics, quantum mechanics, electromagnetism, thermodynamics, etc.
- Detects conflicts where the same symbol is assigned different meanings in different contexts.

---

## 6. Expression Parsing Pipeline

`parse_user_expression` (`src/symkit/domain/expression_parser.py`) and `FormulaParser` (`src/symkit/domain/formula.py`) form the unified expression parsing layer. The pipeline is:

```text
User input (LaTeX / SymPy / Unicode / natural equation)
        │
        ▼
  LaTeX detection (FormulaParser._is_latex)
        │
        ├─ is LaTeX ──▶ FormulaParser._parse_latex
        │                  │
        │                  ▼
        │            1. Preprocess ^* superscript: \beta^* → \beta_{\star}
        │            2. Check bracket balance
        │            3. Split compound equations (\quad, ,, ;)
        │            4. Parse the first equation
        │            5. parse_latex
        │            6. Rename placeholder: beta_{star} → beta_star
        │            7. Map \max / \min → Max / Min
        │            8. Extract variables and return Formula
        │
        └─ not LaTeX ──▶ parse_expression_string
                          │
                          ▼
                    1. Unicode/Greek replacement
                    2. Leibniz derivative notation dX/dY → Derivative(X, Y)
                    3. Single equation conversion A = B → Eq(A, B)
                    4. Reserved name protection (beta, gamma, S, N, etc.)
                    5. parse_expr
```

Key design points:

- **Compound equations**: In LaTeX, `"A = B, \quad C = D"` only records `A = B`; the rest generate `parse_warnings`.
- **Star superscript**: `\beta^*` is converted to a single symbol `beta_star`.
- **`\max` mapping**: `parse_latex` support for `\max` is incomplete, so post-processing maps to SymPy `Max`.
- **Reserved name protection**: `beta * x` treats `beta` as a symbol, not a function; `sin(x)` remains a function.

---

## 7. Derivation Lifecycle

```text
Start (session_start)
    │
    ▼
Load formula (session_load_formula) ──► Parse as Formula and set current_expression
    │
    ▼
Execute operation (math() operations such as substitute / simplify / diff / integrate / solve)
    │
    ▼
Automatic verification (session_verify_step) ──► StepVerifier checks input/output relationship
    │
    ▼
Iterate or add human notes (session_add_note / session_rollback / insert_note_after_step)
    │
    ▼
Complete (session_complete)
    │
    ▼
Persist (save / DerivationRepository)
```

When rolling back, deleting, or inserting notes, `DerivationSession` no longer directly calls `sp.sympify(step.output_expression)`; it uses `step.output_srepr` first, so sessions containing LaTeX subscripts can safely recover the current expression.

---

## 8. MCP Tool Design

### 8.1 Tool Categories

SymKit exposes 43 MCP tools organized into 8 categories:

| Tool Module | Representative Tools | Count | Purpose |
|---|---|---|---|
| `math` | `math()`, `assume()` | 2 | Unified computation entry and global assumptions |
| `session` | `session_start`, `session_show`, `session_complete` | 17 | Unified derivation session workflow |
| `formula` | `formula_search`, `formula_constants`, `formula_get` | 6 | External formula search |
| `assumptions` | `assume_for_step`, `list_assumptions` | 5 | Step-level assumption management |
| `symbols` | `register_symbol`, `lookup_symbol` | 4 | Symbol semantics management |
| `codegen` | `generate_python_function`, `generate_latex_derivation` | 4 | Code/report generation |
| `orchestration` | `derive()`, `intent_execute()` | 3 | High-level automation orchestration |
| `meta` | `tool_categories()`, `tool_recommend()` | 2 | Tool discovery and recommendation |

`math()` consolidates functionality previously scattered across many tools into a single entry point, preventing LLMs from getting lost among many similar tools.

### 8.2 math() Unified Math Tool

`math(operation, expression, ...)` is the primary tool for LLMs. The `operation` parameter determines the behavior:

| Category | Operations |
|---|---|
| Parse/Simplify | `parse`, `simplify`, `expand`, `factor`, `collect`, `cancel`, `apart`, `together`, `trigsimp`, `powsimp`, `radsimp`, `combsimp` |
| Solve | `solve`, `substitute` |
| Calculus | `diff`, `integrate`, `limit`, `series` |
| ODE | `dsolve` |
| Vector | `gradient`, `divergence`, `curl`, `laplacian` |
| Matrix | `det`, `inv`, `eigenvals`, `eigenvects` |
| Integral Transforms | `laplace`, `ilaplace`, `fourier`, `ifourier` |

Important parameters:

- `variable`: primary variable (differentiation/integration/solving variable, or coordinate list for vector operations).
- `with_respect_to`: secondary variable (ODE independent variable, transform target variable).
- `substitution`: dictionary-style substitution mapping.
- `lower` / `upper`: definite integral bounds.
- `assumptions`: symbol assumptions for the current computation, e.g., `["x is positive"]`.
- `session`: when `True`, records to the current derivation session.
- `description` / `notes`: human knowledge recorded into the step.

### 8.3 Derivation Session Tools

`session.py` is the unified entry point for derivation session workflows. All state-related operations are `session_*` tools. They reuse `DerivationSession` internally, so they provide full step traceability, automatic verification, and persistence.

Unified session tools include:

- `session_start(name, domain=..., goal=...)`: create a new session, optionally with a goal.
- `session_resume(session_id)`: resume a saved session.
- `session_status()` / `session_show(show_steps=True)`: view current state, progress, next-step suggestions, and verification summary.
- `session_explain(...)`: summarize the current derivation in natural language.
- `session_complete(...)`: complete and save the derivation result.
- `session_rollback(to_step)` / `session_abort()`: roll back or abort the session.
- `session_add_note(...)`: record human insights. Now safely supports LaTeX subscripts.
- `session_load_formula(expression, formula_id=...)`: load a formula into the current session. Supports compound LaTeX equations.
- `session_set_goal(goal)`: set or update the derivation goal.
- `session_suggest_formulas(top_k=...)`: recommend available formulas based on the goal.
- `session_record_step(...)`: record a manually or externally computed step.
- `session_get_steps()`: get all steps.
- `session_verify_step(step_number)` / `session_verify_session()`: manually trigger single-step or full-chain verification.
- `session_list()`: list all saved sessions.

### 8.4 Formula Search Tools

- `formula_search(query, source="wikidata+scipy", domain=None, limit=10)`: cross-source search.
- `formula_get(id, source="wikidata")`: get a single formula by ID.
- `formula_constants(category=None, query="")`: list SciPy physical constants.
- `formula_categories()` / `formula_pk_models()` / `formula_kinetic_laws()`: domain-specific retrieval.

### 8.5 Assumption Tools

- `assume(variables)`: set global/session-level assumptions (affects `MathContext`).
- `show_assumptions()`: show current assumptions.
- `assume_for_step(symbol, property)`: set a temporary assumption for the current step.
- `list_assumptions(level)`: list assumptions at a given level.
- `check_assumption_conflicts()`: detect conflicts.

### 8.6 Orchestration Tools

- `derive(goal, given=None, domain=None, external_sources=None)`: automatically select a pattern, recommend formulas, and return a complete plan based on the goal.
- `intent_execute(intent)`: execute a tool chain based on intent.
- `tool_categories()` / `tool_recommend(...)`: tool discovery and recommendation.
- `list_patterns()`: list available derivation patterns.

> **Note**: `derive()` is a high-level orchestration entry point. If the goal chain is long or network adapters (e.g., `wikidata`) are enabled, it may trigger MCP client timeouts. For complex tasks, it is recommended to split into `session_start` + `math(..., session=True)` multi-step execution, or avoid using external network sources.

---

## 9. External Adapters

External adapters are located in `src/symkit/infrastructure/adapters/` and implement the unified `FormulaSourceAdapter` protocol:

| Adapter | Data Source | Use Case |
|---|---|---|
| `ScipyConstantsAdapter` | SciPy CODATA | Physical constants (c, h, G, etc.) |
| `WikidataFormulaAdapter` | Wikidata SPARQL | Cross-domain physics/chemistry/engineering formulas |
| `BioModelsAdapter` | BioModels SBML | Pharmacokinetic/enzyme kinetic models |

`FormulaRecommender` (`src/symkit/domain/formula_recommender.py`) aggregates the local `DerivationRepository` and external adapters, ranking by:

- Keyword/tag overlap
- Domain match
- Variable overlap
- Source credibility

By default, only the offline SciPy adapter is enabled (`create_default_external_adapters`) to avoid default network dependencies. Wikidata and BioModels can be enabled via `create_all_external_adapters()` when network is needed.

---

## 10. Step Verification

`StepVerifier` (`src/symkit/domain/step_verifier.py`) verifies each `DerivationStep`:

1. **Rebuild inputs/outputs**: prefer `output_srepr` for parsing SymPy objects; fall back to `str()` or the unified parser if `srepr` is unavailable.
2. **Assumption conflict detection**: if current assumptions are contradictory, the verification conclusion is downgraded to failure.
3. **Operation-specific checks**:
   - **Simplify / Expand / Factor**: `simplify(output - input) == 0`.
   - **Differentiate**: reverse integration `integrate(output) == input` (allowing constant differences).
   - **Integrate**: reverse differentiation `diff(output) == input`.
   - **Substitute**: apply the substitution to the original expression and check equality with output.
   - **Solve**: substitute the solution back into the original equation and check validity (handling `BooleanTrue`/`BooleanFalse`).
4. **Warning collection**: check `exp`/`log` arguments, division-by-zero risks, etc.

Verification results are encapsulated as `VerificationResult` (`src/symkit/domain/value_objects.py`), containing:

- `status`: `VERIFIED`, `FAILED`, or `INCONCLUSIVE`
- `message`: human-readable verification conclusion
- `details`: residuals, reverse checks, boundary checks, assumption conflicts, etc.

---

## 11. Assumptions and Conflict Detection

`AssumptionEngine` supports four assumption levels, from lowest to highest priority:

1. **GLOBAL** (global defaults)
2. **DOMAIN** (domain defaults, e.g., `rho > 0` in fluid dynamics)
3. **SESSION** (session-level, set by `assume()` or `assume_for_step`)
4. **STEP** (step-level, set by `assume_for_step()`)

Merge rule: higher priority overrides lower priority. Conflict detection identifies mutually exclusive assumptions, such as the same symbol being declared both `positive` and `negative`, or `real` and `imaginary`.

`MathContext` passes assumptions to the symbol parser and SymPy engine, so `sqrt(x**2)` simplifies to `x` under the assumption `x positive`.

---

## 12. Persistence and Round-Trip Loading

### 12.1 Expression Storage Strategy

`DerivationStep` stores three expression representations simultaneously:

- `output_expression`: `str(expr)`, human-readable but not always reloadable (e.g., `mu_{t}` is not a valid Python identifier).
- `output_latex`: `sp.latex(expr)`, for display.
- `output_srepr`: `sp.srepr(expr)`, machine-readable and the reliable source for reloading.

`DerivationSession._safe_load_expression(expr_str, srepr_str)` reload priority:

1. `srepr_str` → `sp.sympify`
2. `expr_str` → `sp.sympify`
3. `expr_str` → `parse_user_expression`
4. On failure, return `None`

### 12.2 Session Persistence

- `SessionManager.create()` creates a session under the configured `derivation_sessions` directory.
- `DerivationSession.save()` serializes the session to JSON, including `current_expression_srepr`.
- `SessionManager.load(session_id)` restores the session, using `output_srepr` to rebuild the current expression.

### 12.3 Derivation Result Repository

- `DerivationRepository` (`src/symkit/infrastructure/derivation_repository.py`) stores `DerivationResult` in YAML format.
- Supports register, query, search, list, update, and delete.
- `session_complete()` automatically saves verified derivation results through this repository.

### 12.4 Formula Sources

- Local derivation results can be loaded as formulas in subsequent derivations.
- External adapter results enter the recommendation list as `FormulaInfo` and can be loaded via `session_load_formula()`.

---

## 13. State Management

Global state is centralized in `src/symkit_mcp/tools/_state.py`:

```python
_manager: SessionManager | None = None          # Session manager
_current_session: DerivationSession | None = None  # Current active session
_current_context: MathContext = MathContext()   # Current math context (assumptions, etc.)
```

Utilities:

- `get_manager()` / `set_manager(...)`
- `get_session()` / `set_session(...)`
- `get_context()` / `set_context(...)`

This design allows all MCP tools to share the same session and assumption context while keeping the domain layer stateless.

---

## 14. Testing Strategy

Tests are organized by functional layer in `tests/`, with shared fixtures
(`MockMCP`, `fresh_session_manager`) centralized in `tests/conftest.py`:

| Test File | Coverage |
|---|---|
| `test_domain.py` | Basic domain entities |
| `test_domain_services.py` | Derivation patterns, symbols, assumptions |
| `test_sympy_engine.py` | SymPy engine implementation |
| `test_expression_parser.py` | Expression parsing, including LaTeX compound equations, subscripts, `\max`, and star superscripts |
| `test_derivation_engine.py` | Derivation engine logic |
| `test_derivation_examples.py` | End-to-end examples |
| `test_derivation_examples_extended.py` | Extended end-to-end examples and edge cases |
| `test_session_tools.py` | Modern session tools |
| `test_session_verification.py` | Session-level automatic verification |
| `test_session_verify_tools.py` | Session verification and completion tools |
| `test_session_goal_tools.py` | Goal-aware derivation and recommendation tools |
| `test_step_verifier.py` | Step verification |
| `test_step_crud.py` | Step CRUD, including LaTeX subscript/Max round-trip |
| `test_orchestration_tools.py` | Orchestration tools |
| `test_orchestration_external.py` | External source integration in orchestration |
| `test_derivation_goal.py` | Goal parsing |
| `test_derivation_planner.py` | Planner |
| `test_formula_recommender.py` | Formula recommender ranking and external-adapter merging |
| `test_external_adapters.py` | External formula adapter integration |
| `test_formula_search.py` | Formula search framework |
| `test_math_transforms.py` | Integral transforms via `math()` |
| `test_unified_math_coverage.py` | `math()` unified tool coverage |

Current status: 293 tests pass; Ruff and MyPy report no errors.

---

## 15. Design Principles

1. **Ports and Adapters**  
   Isolate SymPy and external network sources in the infrastructure layer through protocols such as `SymbolicEngine`, `Verifier`, `FormulaRepository`, and `FormulaSourceAdapter`.

2. **Domain-Driven Design (DDD)**  
   Concentrate business rules in rich domain objects like `DerivationSession`, `AssumptionEngine`, and `StepVerifier`. The MCP layer only handles parameter conversion and result presentation.

3. **Immutable Audit Records**  
   Each `DerivationStep` records complete context, ensuring the derivation process is reproducible and academically citable.

4. **Result Pattern Over Exceptions**  
   `VerificationResult` and tool-returned `dict` use `success`/`error` patterns, making it easy for LLMs to understand and retry.

5. **OperationType Classification**  
   Enumerate derivation operations so the verifier can automatically select the correct verification strategy.

6. **Unified Parsing Layer**  
   `expression_parser.py` and `FormulaParser` uniformly handle Unicode/Greek, LaTeX, equation conversion, reserved-name protection, compound equation splitting, and `\max`/`^*` mapping, avoiding duplicate implementation across tools.

7. **Expression Round-Trip Safety**  
   Store expressions in canonical `srepr` form so that LaTeX subscripts, special function names, etc., are correctly restored after persistence and rollback.

8. **Pluggable External Sources**  
   Unify Wikidata, BioModels, and SciPy through `FormulaInfo` and `FormulaSourceAdapter` into the recommender.

9. **Domain-Agnostic Core**  
   Core tools do not hard-code domain semantics; tool names and interfaces remain generic, with domain meaning provided by user context.

---

## 16. Appendix

### A. Glossary

| Term | Description |
|---|---|
| MCP | Model Context Protocol |
| Derivation | The process of deriving a new formula from known formulas/assumptions |
| Step | An immutable record of a derivation operation |
| Formula | A reusable mathematical formula or constant |
| Assumption | A declaration about a symbol's properties (e.g., positive, real) |
| Verification | Automatic or semi-automatic correctness checking of a derivation result |
| MathContext | A computation context carrying assumptions, coordinate system, simplification level, and domain |
| Adapter | A component that converts external sources into the project's internal unified format |
| srepr | SymPy's canonical expression string, safely reloadable |
| LaTeX round-trip | LaTeX input remains semantically consistent after parsing, storage, and reloading |

### B. Key File Index

| File | Description |
|---|---|
| `src/symkit/domain/derivation_session.py` | Derivation session and session manager |
| `src/symkit/domain/step_verifier.py` | Step verification |
| `src/symkit/domain/assumption_engine.py` | Assumption engine |
| `src/symkit/domain/formula.py` | Formula parsing and LaTeX handling |
| `src/symkit/domain/formula_recommender.py` | Formula recommendation |
| `src/symkit/infrastructure/sympy_engine.py` | SymPy engine |
| `src/symkit/infrastructure/derivation_repository.py` | YAML derivation repository |
| `src/symkit_mcp/tools/math.py` | Unified math tool |
| `src/symkit_mcp/tools/session.py` | Unified derivation session tools |
| `src/symkit_mcp/tools/formula.py` | Formula search |
| `src/symkit_mcp/tools/orchestration.py` | Orchestration tools |
| `src/symkit_mcp/tools/_state.py` | Global state |
| `src/symkit_mcp/tools/_expression_parser.py` | Unified parser compatibility shim |
| `tests/test_expression_parser.py` | Expression parser tests |
| `tests/test_step_crud.py` | Step CRUD tests |

### C. Quick Entry

- Start server: `python -m symkit_mcp.server`
- Quick calculation: `math("diff", "x**3", variable="x")`
- Start derivation: `session_start("k-omega derivation", domain="fluid_dynamics")`
- Load formula: `session_load_formula("\\mu_t = \\frac{k}{\\omega}", formula_id="eddy_viscosity")`
- Record step: `session_record_step("\\omega = \\frac{\\varepsilon}{\\beta^* k}", "Wilcox definition of omega")`
- Auto derive: `derive("derive k-omega turbulence model", domain="fluid_dynamics", external_sources=[])`

### D. Known Limitations and Recommendations

- `derive()` may trigger MCP client timeouts during long derivations or when network adapters are enabled; for complex tasks, use `session_start` + `math(..., session=True)` step by step.
- Compound LaTeX equations `"A = B, \\quad C = D"` only record the first equation; the rest generate `parse_warnings`. Record them separately.
- Network-dependent external adapters are disabled by default to avoid default network dependencies.
- The current version has 43 MCP tools; `formula_pk_models` and `formula_kinetic_laws` are legacy domain-specific category tools and may be renamed to more general names in future versions.


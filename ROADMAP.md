# Roadmap

SymKit project roadmap and feature planning.

---

## ✅ Completed

### v1.0.1 (Current)

- Unified math entry `math()` covering calculus, linear algebra, ODE, Laplace/Fourier transforms, and ~25 other operations.
- Step-by-step derivation sessions with start, continue, rollback, complete, record step, and verify step.
- Symbol assumption management: register, query, conflict detection, and per-step isolation.
- External formula search: Wikidata, SciPy constants, BioModels.
- Symbol registry: domain-specific notation, conflict detection, and per-domain listing.
- Code/report generation: Python functions, LaTeX derivation, Markdown reports, SymPy scripts.
- High-level derivation orchestration: `derive`, `intent_execute`, pattern listing, tool recommendations.
- **41 MCP tools** with DDD-layered architecture; the core library can be used independently.
- Python requirement lowered to 3.10+ for broader installation compatibility.

---

## 🚧 In Progress

- Documentation cleanup and clearer project positioning (general-purpose formula derivation, not domain-specific).
- Derivation example library expansion: cross-domain cases in physics, engineering, chemistry, biology, etc.
- Tool usage examples and best-practice additions.

---

## 📋 Planned

### v0.3.0 - Derivation Experience Enhancement

- **Auto-verification**: automatically run dimensional checks and boundary-condition validation after each step.
- **Derivation suggestions**: proactively suggest next steps or related formulas based on the current state.
- **Symbol semantic tracking**: distinguish the meaning of symbols with the same name in different contexts.
- **Error-pattern detection**: warnings for dimensional errors, undefined symbols, and assumption conflicts.

### v0.4.0 - Ecosystem & Extensions

- More external formula-source adapters (e.g., Wolfram Alpha, MathWorld).
- Extended export formats for derivation results (Julia, R, MATLAB).
- Formula version control and diff comparison.
- Richer cross-domain example library.

### Infrastructure

- GitHub Actions CI/CD (tests, lint, type checks).
- Automated PyPI release.
- More complete API documentation and interactive tutorials.

---

## Long-term Goals

- Become the standard derivation layer between the SymPy ecosystem and the MCP protocol.
- Support multi-agent collaborative derivation (multi-user / multi-agent sessions).
- Contribute general capabilities upstream to SymPy.

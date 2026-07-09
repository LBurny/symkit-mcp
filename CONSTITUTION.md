# Project Constitution

This document defines the highest-level principles of the project. All contributors and automated tools must follow it.

---

## Chapter 1: Architecture Principles

### Article 1: Domain-Driven Design (DDD)

1. The project adopts Domain-Driven Design architecture.
2. Core domain logic is separated from infrastructure.
3. Use Ubiquitous Language to describe business concepts.

### Article 2: Independent Data Access Layer

1. The Data Access Layer must be independent of business logic.
2. The Repository Pattern is the recommended data access approach.
3. The Domain Layer must not directly manipulate external storage or networks.

### Article 3: Layered Architecture

```
├── Domain/          # Core domain (pure business logic, no external dependencies)
├── Application/     # Application layer (use cases, service orchestration)
├── Infrastructure/  # Infrastructure layer (DAL, external services)
└── Presentation/    # Presentation layer (API, MCP tools)
```

---

## Chapter 2: Documentation Principles

### Article 4: Documentation First

1. Code is the "compiled output" of documentation.
2. Update specification documents before modifying code.
3. README is the project's "front door" and must be kept up to date.

### Article 5: Changelog Convention

1. Follow the Keep a Changelog format.
2. Use Semantic Versioning.
3. Check whether the changelog needs updating before every commit.

---

## Chapter 3: Development Philosophy

### Article 6: Tests as Documentation

1. Test code is the best usage example.
2. Ad-hoc tests are still tests; put them in the `tests/` folder.
3. Do not discard tests run in a REPL or notebook.

> 💡 **Tip: "When you want to write an ad-hoc test, write it into a file in tests/!"**
>
> Today's ad-hoc test is tomorrow's regression test.

### Article 7: Environment as Code

1. Virtual environment configuration must be reproducible.
2. Dependencies must be explicitly pinned.
3. Environment setup is part of version control.

### Article 8: Proactive Refactoring

1. **Continuous refactoring**: code should always be kept refactorable.
2. **Single responsibility**: one module/class/function should do one thing.
3. **Timely splitting**: split files and functions when they become too long.
4. **Architecture guard**: maintain the DDD layered architecture during refactoring.

> 💡 **Tip: "Refactoring is not a big rewrite; it is continuous small steps."**
>
> Every commit should be cleaner than the last.

---

## Chapter 4: Sub-law Delegation

### Article 9: Sub-law Hierarchy

```
Constitution (CONSTITUTION.md)
  └── Bylaws (.github/bylaws/*.md)
```

### Article 10: Sub-law Priority

1. Bylaws must not violate the Constitution.
2. In case of conflict, the higher-level document takes precedence.

---

## Supplementary Provisions

### Article 11: Amendment Process

1. Amendments to the Constitution must record the reason.
2. Major amendments require a version bump.
3. Constitution version: v1.0.0

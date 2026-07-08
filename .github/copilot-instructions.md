# Copilot Custom Instructions

This document provides project context for VS Code GitHub Copilot Agent Mode.

---

## Development Philosophy

- Write or update design docs before changing behavior.
- Add tests to `tests/` for any new logic.
- Keep the Domain Layer free of external dependencies.

---

## Governance

You must follow this hierarchy:

1. **Constitution**: `CONSTITUTION.md` — top-level principles, must not be violated
2. **Bylaws**: `.github/bylaws/*.md` — detailed rules

---

## Architecture Principles

- **Domain-Driven Design (DDD)**
- **Data Access Layer (DAL) must be independent**
- Dependency direction: `Presentation → Application → Domain ← Infrastructure`

See `.github/bylaws/ddd-architecture.md` for details.

---

## Python Environment (uv preferred)

- Prefer **uv** for package and virtual environment management.
- New projects must create `pyproject.toml` + `uv.lock`.
- Do not install packages globally.

```bash
# Initialize environment
uv venv
uv sync --all-extras

# Install dependencies
uv add package-name
uv add --dev pytest ruff
```

See `.github/bylaws/python-environment.md` for details.

---

## Git Workflow

Before committing, run this checklist:

1. ✅ Run tests: `uv run pytest`
2. ✅ Run lint: `uv run ruff check src/ tests/`
3. ✅ Run type check: `uv run mypy src/`
4. 📖 Update README if user-facing behavior changed
5. 📋 Update CHANGELOG if applicable
6. 🗺️ Update ROADMAP if progress was made

See `.github/bylaws/git-workflow.md` for details.

---

## Project Notes

- SymKit is a **domain-agnostic** symbolic formula derivation engine.
- It exposes **43 MCP tools** for math, derivation sessions, assumptions, verification, and orchestration.
- Respond in Simplified Chinese when the user writes in Chinese.

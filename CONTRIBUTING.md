# Contributing Guide

Thank you for your interest in contributing to this project!

## How to Contribute

### Bug Report

1. Search existing Issues to make sure the bug has not already been reported.
2. Submit the issue using the issue template.
3. Provide clear reproduction steps.

### Feature Request

1. Search existing Issues first.
2. Describe the use case for the feature.
3. Explain the expected behavior.

### Pull Request

#### Development Workflow

1. Fork this project.
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Follow the project architecture (see `CONSTITUTION.md`).
4. Commit your changes: `git commit -m 'feat: add your feature'`
5. Push the branch: `git push origin feature/your-feature`
6. Create a Pull Request.

#### Commit Message Format

Follow Conventional Commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Refactoring
- `test`: Tests
- `chore`: Miscellaneous

#### Code Standards

- Follow the DDD architecture (see `.github/bylaws/ddd-architecture.md`).
- The Data Access Layer must be independent.
- Update relevant documentation before submitting.

### Review Process

1. Automated checks must pass.
2. At least one maintainer must review.
3. All discussions must be resolved.
4. Documentation must be updated.

## Code of Conduct

Please see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Questions?

Feel free to open an Issue for discussion!

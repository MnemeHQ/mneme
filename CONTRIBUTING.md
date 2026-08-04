# Contributing to Mneme HQ

Thank you for contributing to Mneme! This document covers contributions to the **core package** (`MnemeHQ/mneme`). Website contributions and publishing governance belong in [MnemeHQ/mnemehq-site](https://github.com/MnemeHQ/mnemehq-site).

## Development Environment

Mneme requires Python 3.11+.

1. Fork and clone the repository.
2. Install the package in editable mode with development dependencies:

```bash
pip install -e .[dev]
```

## Running Tests

All tests must pass before a pull request can be merged:

```bash
pytest tests/ -v
```

## Running the Benchmark Suite

The benchmark suite verifies that enforcement behaviour has not changed unexpectedly. If you modify any core enforcement logic, you must run the benchmarks:

```bash
mneme benchmark examples/benchmarks/ --memory examples/project_memory.json
```

## Charter-Sensitive Components

Certain files implement the frozen retrieval, enforcement, and benchmark semantics defined by the Layer 1 freeze. See:

- [`docs/architecture/current-phase.md`](docs/architecture/current-phase.md) — current development phase and frozen scope
- [`docs/architecture/layer1-freeze-e73ff7d.md`](docs/architecture/layer1-freeze-e73ff7d.md) — Layer 1 freeze record

Behavioural changes to frozen retrieval, enforcement, or benchmark semantics require the charter-amendment procedure described in those documents. Documenting a change in the PR description alone is not sufficient.

## Pull Request Scope

- Keep PRs narrowly scoped. Do not mix unrelated refactoring with new features.
- Ensure your changes do not unexpectedly alter the retrieval scoring algorithm or violation checking logic.

## Modifying Project Memory

If you need to change `.mneme/project_memory.json` (the repository's own governance memory), prepend `[memory]` to your commit message and PR title.

## Documentation Expectations

- If you add a new command or modify an existing one, update `README.md` or the relevant `docs/` file.
- Changes to API boundaries should be documented.

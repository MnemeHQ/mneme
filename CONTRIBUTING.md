# Contributing to Mneme HQ

Thank you for contributing to Mneme! This document outlines the process for contributing to the core package and integrations.

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

If the results change, your PR description must explicitly document why the change is expected or desired.

## Charter-Sensitive Components

The following files contain the core enforcement and retrieval semantics. They are subject to the Layer 1 freeze and require charter-level discussion before behavioural changes are made:

- `mneme/decision_retriever.py`
- `mneme/enforcer.py`
- `mneme/benchmark.py`
- `examples/benchmarks/` fixtures

## Pull Request Scope

- Keep PRs narrowly scoped. Do not mix unrelated refactoring with new features.
- Ensure your changes do not unexpectedly alter the retrieval scoring algorithm or violation checking logic.

## Modifying Project Memory

If you need to change `.mneme/project_memory.json` (the repository's own governance memory), prepend `[memory]` to your commit message and PR title.

## Documentation Expectations

- If you add a new command or modify an existing one, update `README.md` or the relevant `docs/` file.
- Changes to API boundaries should be documented.

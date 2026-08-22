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
- State observations, scope, configuration, and evidence before interpretation. Distinguish benchmark fixtures, experimental candidates, live repo memory, and shipped production behavior when the distinction affects a claim.
- Prefer measured descriptions over evaluative labels. Do not use phrases such as "headline finding", "important implication", "meaningfully improves", "strong signal", "promising", "worthwhile", "largest", "deepest", or "winning" as substitutes for a metric, observed mechanism, or explicit comparison criterion.
- When one result matters more than another, state the concrete reason (for example, "affects rank 1 rather than ranks 2–3") instead of labeling it "more significant" or "more consequential".
- Separate observation from inference. If causality is not isolated, say so; do not attribute an observed change to one mechanism when multiple variables changed.
- Do not rewrite frozen locks, run artifacts, or preserved experiment outputs for editorial style. Record corrections or changed interpretation in a separate reconciliation or diagnosis document so the original evidence remains byte-stable.
- Accepted ADRs are architecture records, not copy-edit targets. Change them through the ADR/amendment process when their substance needs revision; do not reopen them solely to normalize wording.

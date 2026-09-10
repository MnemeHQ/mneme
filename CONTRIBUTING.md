# Contributing to Mneme HQ

Thank you for contributing to Mneme! This document covers contributions to the **core package** (`MnemeHQ/mneme`). Website contributions and publishing governance belong in [MnemeHQ/mnemehq-site](https://github.com/MnemeHQ/mnemehq-site).

## Development Environment

Mneme requires Python 3.11+.

1. Fork and clone the repository.
2. Install the package in editable mode with development dependencies:

```bash
pip install -e .[dev]
```

## Test Batteries

Mneme's test policy defines six batteries. The single source of truth is
[`scripts/run_test_battery.py`](scripts/run_test_battery.py) — CI runs the
same script a contributor runs locally.

| Battery         | Purpose                                                 | Typical trigger                        | How |
| --------------- | ------------------------------------------------------- | -------------------------------------- | --- |
| `targeted`      | Developer feedback                                      | Local development                      | Run the relevant test files/directories yourself |
| `gate`          | Critical regression protection                          | Pull request CI                        | `python scripts/run_test_battery.py gate` |
| `main`          | Broader confidence (complete canonical suite)           | Push/merge to `main`                   | `python scripts/run_test_battery.py main` |
| `release`       | Complete source validation                              | Exact release-candidate SHA, once      | `python scripts/run_test_battery.py release` |
| `artifact-smoke`| Validate the published package bytes                    | After PyPI publication                 | `.github/workflows/release-smoke.yml` |
| `benchmark`     | Validate charter-sensitive behavioural semantics        | Only when charter-sensitive files change | `mneme benchmark examples/benchmarks/ --memory examples/project_memory.json` |

### What should I run while developing?

Only the tests relevant to your change. For example:

```bash
python -m pytest tests/test_decision_retriever.py -v
python -m pytest tests/integrations/claude_code -v
```

### What runs on my PR?

The deterministic `gate` battery (`python scripts/run_test_battery.py gate`) —
the curated critical paths (retrieval, enforcement, typed rules and path
applicability, ADR parsing/compilation/lifecycle, Architecture Audit,
setup/pairing, protect activation, packaging contracts, benchmark-semantics
unit tests, and the shipped integrations). PR CI does **not** run the complete
suite.

### What runs after merge?

The `main` battery: the complete canonical suite plus the langchain-extra
integration suite.

### When is the full suite mandatory?

Once per release candidate, on the exact SHA intended for release — see
[Releasing](docs/releases/RELEASING.md). A successful full release-suite
result belongs to that exact Git SHA.

### When does a changed SHA invalidate a release validation?

- Runtime/application code changed → full release battery again.
- Tests changed → full release battery again.
- Dependencies or package metadata capable of affecting runtime/install changed → full release battery again.
- Docs or release notes only → no rerun required.
- Release-workflow-only changes → validate the workflow appropriately; the ~source test suite is not rerun unless the shipped package source changed.

See [`docs/releases/RELEASING.md`](docs/releases/RELEASING.md) for the full
SHA-invalidation policy.

## Running the Benchmark Suite

The benchmark suite verifies that enforcement behaviour has not changed unexpectedly. It is a separate charter instrument and is **never** part of the `gate`, `main`, or `release` pytest batteries. If you modify `decision_retriever.py`, `enforcer.py`, `benchmark.py`, or any benchmark fixture, you must run the benchmarks:

```bash
mneme benchmark examples/benchmarks/ --memory examples/project_memory.json
```

The enforcement-quality regression suite (charter 2026-08-24) runs as ordinary
pytest (`tests/test_enforcement_quality_benchmark.py`) and is part of the
canonical suite; the benchmark instrument above remains separate.

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

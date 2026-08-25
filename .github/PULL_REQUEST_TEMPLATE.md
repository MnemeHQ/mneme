## What changed and why

<!-- Describe the change and the problem it solves. Keep the PR narrowly scoped. -->

## Core behavior classification

<!-- Retrieval, enforcement, applicability/conflict handling, and benchmark semantics are distinct surfaces. -->
<!-- Behavioural changes to frozen retrieval, enforcement, or benchmark semantics may require the charter-amendment procedure. -->

Affected surface(s):

- [ ] No core behavioral change (docs/tooling/integration-only)
- [ ] Retrieval / decision ranking or context selection
- [ ] Enforcement / verdict semantics
- [ ] Rule applicability or conflict handling
- [ ] Benchmark harness or benchmark semantics
- [ ] Other core behavior (explain below)

Relevant ADR / architecture document(s):

<!-- Link the governing source. Do not infer architecture from adjacent integrations. -->

Charter amendment required?

- [ ] Yes
- [ ] No
- [ ] Unsure / needs maintainer classification

## Tests

<!-- Describe the tests run for this change. -->

- [ ] `pytest tests/ -v` passes locally

## Benchmark verification

<!-- Run the benchmark when core enforcement behavior changes; follow the freeze procedure for benchmark-semantic or fixture changes. -->

- [ ] Run; results unchanged or explained below
- [ ] N/A

## Documentation

- [ ] Relevant documentation updated
- [ ] N/A

## Project memory

<!-- Changes to `.mneme/project_memory.json` require `[memory]` in the PR title. An ADR amendment may reconcile the matching memory decision in the same reviewed PR under the repository's memory rule. -->

- [ ] This PR modifies `.mneme/project_memory.json` and the title includes `[memory]`
- [ ] This PR does not modify `.mneme/project_memory.json`

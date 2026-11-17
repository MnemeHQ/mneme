# ADR-033 C4 CI adapter fixtures

Deterministic regression data for `scripts/ci/adr033_c4_gate.py`, the trusted
CI availability adapter authorized by the C4 Gate 0 charter (#676, A1-A5), the
Gate 1 charter (#677, R1-R3) and the Layer 1 freeze amendment (#678). Tests:
`tests/test_adr033_c4_ci_gate.py`.

Every `vN/` directory is immutable: a changed expectation means a new version
next to it. The CI1 contract corpora under `tests/fixtures/ci1_contract/` are
reused read-only and are not modified.

## `v1/payload_cases.json`

Raw `mneme check --json` observations (a payload object, or raw `stdout` for
unparseable output) with the requested mode, the exit code and the adapter's
expected classification: `VERIFIED_PASS`, `WARN`, `VIOLATION` or
`UNEVALUATED`.

`assess` states the relation to the shipped `assess_verdict` (#484):

- `agree`: both trust the payload as a complete result with the same verdict.
- `untrusted`: `assess_verdict` rejects it, and the adapter must too.
- `stricter`: `assess_verdict` accepts it, and the adapter deliberately does
  not. These are incomplete evaluations, payloads without
  `evaluation_complete` (ADR-033 §2: absence is never proof of completeness)
  and `subject` records outside the adapter's contract.

## `v1/matrix.json`

The Gate 0 offline matrix as data. Each row builds a base commit (with trusted
memory at `.mneme/project_memory.json` unless `base_memory` says otherwise) and
a head commit from `changes`, then runs the adapter in each listed violation
mode under both availability postures. `expect` gives the aggregate
classification and the required-check disposition for `closed` and `open`.

File content `c4-case:<id>` tells the test's stub evaluator to replay that
payload case; `c4-sleep` makes it outlive the test timeout. Rows with
`launch_fail` point the adapter at an interpreter that does not exist; `head:
missing` names a head commit that is not in the object store.

Unnormalizable paths (O9p) cannot be stored by git on every platform, so they
are unit tests on the path classifier rather than matrix rows. O12 (missing or
invalid posture) is covered by unit and end-to-end tests.

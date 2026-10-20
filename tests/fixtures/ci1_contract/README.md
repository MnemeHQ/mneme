# CI1 contract fixtures

CI-platform-independent fixtures for the CI1 Enforcement Assurance workstream
(see the
[CI1.1 record](../../../docs/validation/ci1-1-enforcement-assurance-contract-validation-2026-10-16.md)).
Any CI adapter (GitHub Actions, GitLab CI, Jenkins or another) must reproduce
these results by calling the existing `mneme check --json` CLI, with one
enforcement engine and one machine contract (`mneme.check/v1`). Each corpus
README is the contract for that corpus. Every `vN/` directory is immutable:
a changed expectation means a new version next to it.

| Corpus | Step | Covers | Tests |
|---|---|---|---|
| [`path_scoped_forbid_literal/`](path_scoped_forbid_literal/README.md) | CI1.2.1 | ADR-020 path applicability: APPLIED, EXCLUDED, UNKNOWN | `tests/test_ci1_contract_fixtures.py` |
| [`warn_verdict/`](warn_verdict/README.md) | CI1.2.2 | WARN in strict (exit 1) and warn mode (exit 0) | `tests/test_ci1_contract_matrix.py` |
| [`incomplete_evaluation/`](incomplete_evaluation/README.md) | CI1.2.2 | `evaluation_complete: false` beyond the out-of-root case | `tests/test_ci1_contract_matrix.py` |
| [`memory_errors/`](memory_errors/README.md) | CI1.2.2 | Missing or malformed memory: no payload | `tests/test_ci1_contract_matrix.py` |

`tests/test_ci1_contract_matrix.py` also holds two checks with no committed
corpus:

- **ADR-005 cross-check.** The repository's own global `FORBID_LITERAL`
  (`ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333`) is checked
  read-only against the canonical `.mneme/project_memory.json`. The violating
  input is generated in a temporary directory at test time, so no committed
  file carries the forbidden install command. The rule must be APPLIED and
  FAIL on every target path and query, and must not fire on `mneme-hq`.
- **Classification of stubbed output.** Contradictory or unparseable CLI
  results (a PASS payload with a non-zero exit, non-JSON or mixed stdout, a
  non-boolean `evaluation_complete`, an unknown schema and so on) must never
  classify as VERIFIED_PASS.

## Classification

Descriptive (CI1.1 A3), not a blocking policy. Whether UNEVALUATED blocks a
merge is ADR-033's question (proposed, #483).

- **VERIFIED_PASS**: exactly one payload on stdout under the `mneme.check/v1`
  schema, `evaluation_complete` is exactly `true`, the verdict is PASS, there
  are no violations, and the exit code is the one the contract assigns to
  PASS in that mode.
- **VIOLATION**: the same consistency checks hold, and the verdict is WARN or
  FAIL with at least one violation record. Severity stays in the payload.
- **UNEVALUATED**: anything else. That includes `evaluation_complete` false,
  no payload, an unparseable payload, or a payload whose verdict, mode,
  violations and exit code disagree.

Contract exit codes for a complete evaluation:

| Mode | PASS | WARN | FAIL |
|---|---|---|---|
| `strict` | 0 | 1 | 2 |
| `warn` | 0 | 0 | 0 |

An incomplete evaluation exits 2 in both modes. A missing memory file exits 2
and a malformed one exits 1 (see `memory_errors/`). Neither emits a payload,
so the exit code alone never identifies a result.

## Record order

`applicability` and `violations` follow retrieval ranking when a memory has
more than one rule, so their order can change with the query. Order is not
part of the contract. Goldens are stored sorted by `rule_id`, then
`decision_id`, and compared after the same sort.

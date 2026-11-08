# CI1.2.2 fixture: WARN verdict

Pins the one verdict whose exit code depends on mode. Shared rules
(classification, contract exit codes, record order) are in the
[index README](../README.md).

The fixture is synthetic and does not touch the repository's canonical
`.mneme/project_memory.json`.

## Layout (`v1/`)

| Path | Role |
|---|---|
| `project_memory.json` | Hand-written legacy memory: one decision with constraint `no postgres` and anti-pattern `introduce ORM`, the supported WARN path from `tests/test_check_modes.py`. Typed rules have no WARN severity, so there is no `decision_index` and no ADR source |
| `inputs/*.md` | One input per verdict |
| `cases.json` | Case manifest |
| `expected/*.json` | Golden `mneme.check/v1` payloads |

## Invocation contract

Every case runs from `v1/` as:

```bash
python -m mneme.cli check --memory project_memory.json --input <input> --query storage --top 3 --mode <mode> --json
```

Legacy constraint and anti-pattern checks are retrieval-gated (ADR-017), so
the query is part of the case. Do not expect these results with a query that
does not retrieve the decision.

## Cases

| Case | Mode | Verdict | Exit | Classification |
|---|---|---|---|---|
| `pass_strict` | strict | PASS | 0 | VERIFIED_PASS |
| `warn_strict` | strict | WARN | **1** | VIOLATION |
| `warn_warn_mode` | warn | WARN | **0** | VIOLATION |
| `fail_warn_mode` | warn | FAIL | **0** | VIOLATION |

Exit 0 in warn mode is not a pass. An adapter that reads only the exit code
classifies `warn_warn_mode` and `fail_warn_mode` as passing. Exit 1 in strict
mode is also the code Python uses for an uncaught exception, including a
malformed memory file (`memory_errors/`). Read the payload.

## Versioning

`v1` is immutable. A change to legacy WARN semantics, payload shape or any
expected result means adding `v2/`, not editing `v1/`.

# Evidence

## What is committed

- `summary.json`: deterministic summary of one full run. No timestamps,
  absolute paths, tool-message text or environment data, so a rerun on the
  pinned build must reproduce it byte for byte.
- `summary.csv`: the same rows, flattened.

Raw run output (`runs/<UTC stamp>/`: `report.json` with environment and full
`pip freeze`, CLI stdout/stderr, audit JSON, transcript, `MANIFEST.sha256`
written last) stays local and is git-ignored.

## Labels

| Label | Meaning |
|---|---|
| `BLOCKED` | Trusted `FAIL` in strict mode. At the middleware the handler was not called. |
| `ALLOWED` | Trusted `PASS` with `evaluation_complete: true`. |
| `WARNED` | Trusted `WARN`. Not observed in this run. |
| `NOT_EVALUATED` | No Mneme evaluation happened: unguided control or a raw graph path. |
| `ERROR_DEGRADED` | Unparseable output, `evaluation_complete` not true, or a middleware fail-open (`[mneme] UNEVALUATED`). |

An error, an incomplete evaluation or a missing observation is never
`ALLOWED` or `BLOCKED`.

## Fields

- `oracle` / `oracle_accept`: the architectural expectation (from the case
  table) and the functional oracle's verdict on the end-state router.
- `classification_observed`: `TRUE_POSITIVE`, `TRUE_NEGATIVE`,
  `COVERAGE_GAP` (C2), `MODELLING_GAP` (C3), `FALSE_BLOCK` or
  `SCOPE_EXCLUDED`, derived from oracle and label.
- `handler_calls`: how many times the file tool body ran for that attempt.
- `sha256_before` / `sha256_after`: target file digest at the model turn
  before and after the attempt (`null` means the file did not exist).
- `model_feedback`: which markers the tool result returned to the model
  carried (`denied_tag`, `unevaluated_tag`, `names_decision`, `names_literal`).
- `task_success`: the scripted run finished and the final router passes the
  oracle. For a single denied attempt this only means the file was left
  compliant.
- `metrics.audit_tier_only`: the `mneme audit` classification, recorded next
  to, never instead of, `constraint_coverage`.

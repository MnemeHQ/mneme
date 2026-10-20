# Evidence

## What is committed

- `post-fix/summary.json` and `post-fix/summary.csv`: the current-runtime
  measurement (`main` including MnemeHQ/mneme#573). Deterministic: no
  timestamps, absolute paths, tool-message text or environment data, so a
  rerun on the pinned build must reproduce it byte for byte.
- `pre-fix/`: historical evidence from the runtime before #573: the summary,
  CSV and original `RESULTS.md`, moved unchanged, plus `PROVENANCE.json` with
  their SHA-256 digests and source commits. Immutable: never regenerate or
  edit; `test_pre_fix_evidence_is_unchanged` enforces the digests. Relative
  links inside `pre-fix/RESULTS.md` refer to its original location.

Raw run output (`runs/<UTC stamp>/`: `report.json` with environment and full
`pip freeze`, CLI stdout/stderr, audit JSON, transcript, `MANIFEST.sha256`
written last) stays local and is git-ignored.

## Labels

| Label | Meaning |
|---|---|
| `BLOCKED` | Trusted `FAIL` in strict mode. At the middleware the handler was not called. |
| `ALLOWED` | Trusted `PASS` with `evaluation_complete: true`. |
| `WARNED` | Trusted `WARN`. Not observed in this run. |
| `NOT_EVALUATED` | No Mneme evaluation happened: unguided control, a raw graph path, an unmapped tool, or a gate `skip`. |
| `ERROR_DEGRADED` | Unparseable output, `evaluation_complete` not true, mode not strict, exit code inconsistent with the verdict, a missing gate event, or a middleware fail-open (`[mneme] UNEVALUATED`). |

An error, an incomplete evaluation or a missing observation is never
`ALLOWED` or `BLOCKED`.

## Fields

- `oracle` / `oracle_accept`: the architectural expectation (from the case
  table) and the functional oracle's verdict on the end-state router.
- `classification_observed`: `TRUE_POSITIVE`, `TRUE_NEGATIVE`,
  `COVERAGE_GAP` (C2), `MODELLING_GAP` (C3), `FALSE_BLOCK` or
  `SCOPE_EXCLUDED`, derived from oracle and label.
- `handler_calls`: how many times the tool body ran for that attempt. Not
  applicable to CLI rows (`mneme check` never writes; the target digest is
  compared instead).
- `process_cwd`: `empty` or `decoy` (a temp dir holding a same-named
  `src/router.py`), pinned by the runner; it matters only for relative paths.
- `trace[].evaluated`: true only for `allow`, `deny` or `warn`; `skip` and
  `fail_open` were not evaluated.
- `sha256_before` / `sha256_after`: target file digest at the model turn
  before and after the attempt (`null` means the file did not exist).
- `model_feedback`: which markers the tool result returned to the model
  carried (`denied_tag`, `unevaluated_tag`, `names_decision`, `names_literal`).
- `task_success`: the scripted run finished and the final router passes the
  oracle. For a single denied attempt this only means the file was left
  compliant.
- `metrics.audit_tier_only`: the `mneme audit` classification, recorded next
  to, never instead of, `constraint_coverage`.

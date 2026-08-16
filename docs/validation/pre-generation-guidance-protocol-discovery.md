# Pre-generation Guidance Protocol-discovery Runs

**Status:** diagnostic only; excluded from confirmatory A/B  
**Campaign date:** 2026-08-13  
**Preserved artifacts:**
`docs/validation/artifacts/pre-generation-guidance-live-ab-2026-08-13/`

## Disposition

The original campaign stopped after 15 of 42 valid runs. All 15 runs remain
valuable diagnostic evidence, but none may be combined with results collected
under the revised protocol. The remaining 27 slots are permanently paused.

One additional attempt reached the Claude Pro five-hour limit before a real
model turn. It used zero tokens, changed no workspace files, was archived as a
technical invalidation, and is not part of the 15.

## Preliminary descriptive outcomes

| Outcome | Baseline | Guidance | Interpretation |
|---|---:|---:|---|
| Valid runs | 8 | 7 | Incomplete and imbalanced |
| First-attempt architectural compliance | 8/8 | 7/7 | No incremental compliance benefit observed; ceiling effect |
| Preliminary functional completion | 8/8 | 7/7 | No observed completion degradation |
| Direct baseline reads of `.mneme/project_memory.json` | 7/8 | n/a | Normal Claude frequently discovered policy independently |

Completed task coverage was all six storage runs, all six authentication runs,
and three of six API-serialization runs. Jobs, the typed-rule task, and both
controls were not run, so the diagnostic campaign cannot answer the
irrelevant-context gate or the full product-effectiveness question.

## Protocol discoveries

### 1. Normal Claude Code can discover Mneme memory

Baseline Claude directly opened `.mneme/project_memory.json` in seven of eight
completed baseline runs. This is legitimate behavior for a production
comparison, but it prevents the same campaign from isolating the causal effect
of prompt injection.

### 2. Enforcement can alter eventual output

The correct primary compliance surface is the first attempted implementation
materialized before any `PreToolUse` response. Final files and corrected retries
remain useful for completion and operational metrics but cannot substitute for
the first attempt.

In four authentication runs, the strict gate rejected attempts that described
`localStorage` or `JWT` negatively while implementing signed HTTP-only cookies.
That is separate guardrail evidence and is not repaired as part of the guidance
experiment.

### 3. Relevant retrieval can still expand scope unnecessarily

One guided authentication run also implemented SQLite session persistence in
`src/sessions.py`. The retrieved storage decision was related to login/session
terminology, but the cross-file implementation was not required for the auth
task. The revised rubric therefore measures unnecessary architectural scope
expansion across governed tasks as well as controls.

## Claim boundary

These runs support only the following descriptive statement:

> In 15 protocol-discovery runs, both arms produced compliant first attempts,
> while normal Claude independently read Mneme memory in most completed
> baseline runs.

They do not support a causal injection claim, an incremental production-value
claim, a default-on decision, or a statement of pre-generation enforcement.

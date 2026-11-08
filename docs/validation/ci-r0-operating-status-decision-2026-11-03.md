# CI rollout R0: operating-status decision (2026-11-03)

**Status: OWNER DECISION, PROPOSED.** Takes effect when this record merges with
the owner's acceptance. It records the decision that the R0 closure
([ci-r0-s7-closure-2026-11-03.md](ci-r0-s7-closure-2026-11-03.md), #742,
`aa126393`) left open. It changes no ruleset, workflow, variable or code, and
does not reopen R0.

## Decision

**Keep the Mneme trusted gate required on `main` as bounded dogfooding.**
Unrestricted production readiness is **not** declared.

| Item | State |
|---|---|
| `mneme-ci-gate` (26391853) | stays active and required on `main` |
| `main-pr-only` (22196895) | unchanged |
| `MNEME_CI_AVAILABILITY` | stays `closed` |
| R0 execution | closed (#742) |
| Operational status | bounded dogfooding |
| Unrestricted production readiness | not established |

## Why not "promote"

R0 shows real GitHub enforcement on Core, but three limitations stay material
and constrain what can be claimed:

- **R6.** Administrator-capable agents keep access to the enforcement
  controls (rulesets, posture variable, workflow) and to the bypass actor's
  login.
- **Coverage.** One literal-tier architectural rule (ADR-005) is protected.
  The pinned evaluator classes ADR-034 numeric/`subject` payloads as
  UNEVALUATED, so an evaluator change first needs new parity evidence.
- **Unvalidated paths.** Fork and first-time-contributor PRs, and enforcement
  by the tracked hooks in interactive sessions, are not independently shown.

## Why not "roll back"

The S3-S6 evidence shows the gate behaves as specified, ordinary merges pass,
and protected changes merge only through the recorded human bypass.

## What would change the status

A separate owner decision, on new evidence, for example: agents moved off
administrator-capable credentials (closing R6); more decisions made
enforceable as typed rules; observed fork-PR behavior; observed interactive
hook enforcement. Each needs its own scope; none is authorized here.

## Unchanged

All limitations in the R0 closure record §5, the recovery controls in its §6,
the §5.2 bypass procedure, and the C4 and R0 evidence. No ADR-029 "relevant
enforcement observed" claim.

## Authorization

Owner, 2026-11-03 (to be recorded on merge). Basis: the forwarded R0 final
review: "I recommend keeping the gate required as bounded dogfooding, rather
than declaring unrestricted production readiness or rolling it back."

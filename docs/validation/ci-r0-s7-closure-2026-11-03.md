# CI rollout R0 S7: results record and closure (2026-11-03)

**Status: PROPOSED FOR CLOSURE.** Records the S7 cleanup and the complete R0
results. On merge with the owner's acceptance, the R0 rollout stages S1-S7 are
closed. **The production promotion decision is not made here.** It is a
separate owner decision, taken on this evidence (§7).
**Governing documents:** [R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
(#684, R1-R6; R6 #718); [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)
R0 amendments #685, #721, #730.

## 1. Current state on `MnemeHQ/mneme` (verified 2026-11-03)

| Control | State |
|---|---|
| `mneme-ci-gate` (26391853) | **active** on `refs/heads/main`; required `mneme trusted gate` (GitHub Actions app 15368), strict up-to-date; one bypass actor `User` `TheoV823`, `pull_request` mode |
| `main-pr-only` (22196895) | active; required: PR battery, mojibake/BOM, provenance, install command; squash only; deletion and non-fast-forward rules; **no bypass actors** |
| Gate workflow `.github/workflows/mneme-trusted-gate.yml` | active; adapter `c51729f7` / `afe1d69c…`, evaluator `0b74d410` / `e3fcc769…`, strict mode; trigger `pull_request_target` on `main` only |
| `MNEME_CI_AVAILABILITY` | `closed` |
| Tracked Claude Code hooks (#598) | active for repository sessions |

## 2. S7 cleanup (#741)

Reverted the temporary S4 trigger filters (#731). Each of the four workflow
files is byte-identical to its blob before #731 (`6d58f472`); `.github/` and
`scripts/ci/` as a whole are identical to that state; no `recovery-staging`
reference remains.

| Step | Result |
|---|---|
| Gate on #741 | run 41645368526, check run 125949181549: **REFUSED** (`trusted_surface`, all four files), posture `closed`, base = main tip `e97aff3d` |
| §5.2 record | in the PR body before merge, with the owner's approval of head `840830d022ce3e37b6bb990cb4ad295468d46686` |
| Pre-merge reconfirmation | head unchanged, 0 behind, six other required checks pass, posture `closed`, both rulesets unchanged since S5 |
| Bypass merge by `TheoV823` | **200**, 13:43:04Z, request `EEEF:1C362C:12E68E9:3E43C46:6AE9E4E5`; squash `141a29e8` |
| GitHub rule suite 4880161681 | `bypass`; every `main-pr-only` rule `pass`; `mneme-ci-gate` required check `fail` (the bypassed part) |

Evidence: [`ci-r0-s7-closure-2026-11-03/`](ci-r0-s7-closure-2026-11-03/)
(gate report, merge response, rule suite, `EVIDENCE-SHA256SUMS`).

## 3. Stage results

| Stage | Outcome | Record |
|---|---|---|
| R0 charter | accepted, R1-R5; R6 dogfooding risk acceptance | #684, #718 |
| S1 freeze amendment (+ #721 S5 activation, #730 S4 triggers) | accepted | #685, #721, #730 |
| S2 dedicated gate ruleset, disabled; credential inventory (private) | done | #719 |
| S3 gate installed, shadow; 4 probes as specified | done | #720, #726 |
| S4 recovery validation on staging, all five cases as specified (attempt 1 stopped by its own rule) | done | #731, #735 |
| S4→S5 equivalence; D1 accepted | done | #736 |
| S5 required gate on `main` | done | #737 |
| S6 ordinary merge (`pass`) and first `.mneme/` change via recorded bypass (#598) | done | #740 |
| S7 trigger cleanup via recorded bypass; this record | done | #741, this PR |

## 4. What the evidence shows

- On Core, the pinned C4 adapter runs on GitHub runners as a required check
  and yields PASS, REFUSED (policy, trusted surface), strict VIOLATION and
  UNEVALUATED as specified, with the expected check conclusions.
- Changes to `.mneme/` and `.github/` merge only through the designated human
  authority; GitHub's rule-suite log records each as `bypass`, with the
  `main-pr-only` protections still enforced. A non-authority account was
  refused (S4 case (e)).
- Availability rollback lets UNEVALUATED pass visibly labelled while REFUSED
  still blocks; required-check removal is effective and reversible (S4).
- Ordinary compliant changes merge without bypass (#737, #740).

**Supplementary operational observation (not an acceptance criterion).**
After #598 merged, a live Claude Code session in this repository received
the Mneme `Stop` hook's message "no session baseline was found; captured one
now". This confirms the tracked hook was invoked in a real session. It does
not show that the hook enforced an architectural decision in that session.

## 5. Limitations that remain

- **R6.** The owner's administrator-capable login, reachable by agents in the
  dogfooding environment, can change the rulesets, the posture variable or the
  workflow, and is the bypass actor. No administrator-resistance claim.
- **Procedure, not enforcement.** GitHub enforces who may bypass, not the §5.2
  record; each bypass's justification is documentation.
- **D1.** A missing or failed advisory warn workflow no longer blocks merge on
  its own.
- **Default-branch semantics.** `pull_request_target` evaluates every PR
  against `main`'s tip; the gate is meaningful only for PRs into `main`.
- **Not observed:** fork and first-time-contributor PRs; posture `open` on
  `main`; interactive sessions under the tracked hooks enforcing a decision.
- **Coverage.** One literal-tier rule (ADR-005); the evaluator pin
  `0b74d410` classes ADR-034 numeric/`subject` payloads as UNEVALUATED, so an
  evaluator change needs new parity evidence first (C4 closure §7).
- **Evidence binding.** No ADR-029 "relevant enforcement observed" claim;
  attribution relies on joined records (check runs, rule suites, reports).
- **Operational.** Open PRs into `main` must be updated and pass the gate;
  documents quoting the ADR-005 forbidden literal are VIOLATIONs; #485 changes
  `.github/` and needs a recorded bypass if it is ever merged.

## 6. Recovery reference

Emergency controls (charter §5.4), each recorded on #540 the same day: posture
`open` for evaluation unavailability (VIOLATION and REFUSED still block); for a
gate defect, remove the required check from `mneme-ci-gate` or disable it.
Restore only through a reviewed change.

## 7. Production promotion decision

Not made by this record. Options for the owner:

- **Promote:** declare the required gate the standing configuration for Mneme
  Core, bounded by §5.
- **Keep as dogfooding:** leave the gate required but keep the "bounded
  dogfooding" status until a named limitation (for example fork PRs or R6) is
  addressed.
- **Roll back:** disable `mneme-ci-gate` and restore the warn check.

Production promotion stays **DEFERRED** until that decision is recorded.

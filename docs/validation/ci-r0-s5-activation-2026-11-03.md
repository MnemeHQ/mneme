# CI rollout R0 S5: Mneme trusted gate activated as a required check on `main` (2026-11-03)

**Status: RECORD.** On 2026-11-03 at 12:32:57Z / 12:33:11Z the R0 S5 change set
was applied to `MnemeHQ/mneme`. **The `mneme trusted gate` check is now
required for merges to `main`.** This is a bounded dogfooding enforcement on
Mneme Core under R0 and R6, not a general production-readiness or
administrator-resistance claim. S6 (post-switch checks) and S7 (closure and
the production promotion decision) remain; promotion stays **DEFERRED** until S7.
**Governing documents:** [R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
§5 and §7 (#684, R6 #718); [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)
R0 amendment S5 row (#685) and its S5 activation clarification (#721);
[S4 record](ci-r0-s4-recovery-2026-11-03.md) (#735);
[S4→S5 equivalence](ci-r0-s4-s5-equivalence-2026-11-03.md) (#736, D1 accepted).

## 1. Authorization

Owner (2026-11-03, Mneme Core conversation): "Authorize S5". Scope as
recorded in #736 §3: activate `mneme-ci-gate` with its required check and
strict freshness, then remove the advisory warn check from `main-pr-only`,
then verify.

## 2. Pre-checks (read-only, immediately before)

- `main` at `95e4daba`; commits since S4's base **M** `e6fa32d4` are only the
  #735 and #736 docs commits; no change to `.github/`, `scripts/ci/`, `.mneme/`,
  `.gitattributes` or `.gitmodules`.
- Both rulesets byte-identical to the #736 snapshots; posture `closed`;
  Actions permissions, token permissions and collaborators unchanged.
- The two update bodies are byte-identical to the merged #736 evidence
  (`s5-intended-mneme-ci-gate-update.json` `06200425…`,
  `s5-intended-main-pr-only-update.json` `49c64597…`).
- Administrator recovery route available: `TheoV823` (repo admin, `repo` and
  `workflow` scopes) can edit both rulesets and the variable.

## 3. Change set (in order, so protection never dropped)

| Step | Call | Response | Result |
|---|---|---|---|
| 1 | `PUT /rulesets/26391853` (`mneme-ci-gate`) | 200, 12:32:57Z, request `F4A7:60781:1ADF9AC:583AE51:6AE9D477` | `enforcement: active`; rule `required_status_checks`: `mneme trusted gate` (app 15368), strict `true`; bypass unchanged: one `User` 54006786 `pull_request`; ref `refs/heads/main` |
| 2 | `PUT /rulesets/22196895` (`main-pr-only`) | 200, 12:33:11Z, request `F270:9ED07:191F6E4:52C1474:6AE9D486` | required contexts: PR battery, mojibake/BOM, provenance, install command (D1: `mneme check --mode warn` removed); strict `false`; no bypass actors; other rules unchanged |

## 4. After-state (read-only)

Effective rules on `main`: `pull_request`, `deletion`, `non_fast_forward`,
`required_status_checks` from `main-pr-only` (22196895), and
`required_status_checks` from `mneme-ci-gate` (26391853, strict up-to-date).
Posture `MNEME_CI_AVAILABILITY=closed`. Both rulesets active. Evidence:
[`ci-r0-s5-activation-2026-11-03/`](ci-r0-s5-activation-2026-11-03/) (pre and
post snapshots, response headers, `EVIDENCE-SHA256SUMS`).

## 5. What now applies

- Every PR into `main` needs a passing `mneme trusted gate` (strict mode,
  posture `closed`) and must be up to date with `main`.
- PRs changing `.mneme/`, `.github/`, `.gitattributes` or `.gitmodules` are
  REFUSED; they merge only through the designated human bypass with the
  charter §5.2 record. Currently open: #485 (`.github/`), #598 (`.mneme/`).
- Documents quoting the ADR-005 forbidden install literal are VIOLATIONs.
- Unavailable evaluation blocks under `closed`; the charter §5.4 controls are
  the emergency rollback (posture `open`, or remove the gate rule / disable
  `mneme-ci-gate`), each recorded on #540 the same day.

## 6. Limits and non-claims

- R6: the owner's administrator-capable login (also used by agents in the
  dogfooding environment) can change or bypass these controls. No
  administrator-resistance or ADR-029 "relevant enforcement observed" claim.
- D1 residual: a missing or failed advisory warn workflow no longer blocks
  merge on its own.
- Fork and first-time-contributor PRs are unobserved.
- The four `r0/recovery-staging` trigger lines from #731 remain on `main`;
  their removal is a recorded cleanup in S7.
- This record PR is the first ordinary PR merged under the required gate; its
  own gate result is part of S6.

## 7. Next

S6 (post-switch checks: ordinary compliant merges, the first real refused
change through a recorded bypass) and S7 (closure, trigger-line cleanup and
the production promotion decision), each with owner authorization.

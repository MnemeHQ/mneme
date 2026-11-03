# CI rollout R0: S4→S5 configuration equivalence (2026-11-03)

**Status: RECORD (read-only comparison).** Compares the configuration S4
validated on staging with the exact configuration S5 would put on `main`.
**Nothing was changed.** S5 is not authorized by this record. Production
promotion stays **DEFERRED**.
**Governing documents:** R0 charter §7 (S4→S5 row: "Any difference that
affects merge authorization blocks S5 until reviewed and accepted by the
owner"); Layer 1 freeze R0 amendment S5 row (#685) as clarified by #721; S4
record [ci-r0-s4-recovery-2026-11-03.md](ci-r0-s4-recovery-2026-11-03.md) (#735).
**Authorization:** owner, 2026-11-03, via the forwarded S4 review: "Authorize
the read-only S4→S5 configuration-equivalence comparison ... it must not
silently claim identical branch tips."

## 1. Points compared

| Point | S4 tested | S5 intended / current production | Verdict |
|---|---|---|---|
| Gate ruleset target and ref | branch, `refs/heads/r0/recovery-staging` | branch, `refs/heads/main` (`mneme-ci-gate` 26391853) | differs **by design** (the ref under protection) |
| Gate ruleset enforcement | `active` | `active` after S5 (now `disabled`) | identical after S5 |
| Gate bypass actors | one `User` 54006786 (`TheoV823`), `pull_request` | same | **identical** |
| Gate rules | `required_status_checks`: `mneme trusted gate` app 15368, strict up-to-date `true`, `do_not_enforce_on_create` `false` | same (`s5-intended-mneme-ci-gate-update.json`) | **identical** |
| Second ruleset (layering) | `r0-staging-main-pr-only`: rules = production `main-pr-only`, no bypass, active | `main-pr-only` 22196895, no bypass, active | identical **except D1** |
| Required contexts in that ruleset | 5: PR battery, mojibake/BOM, provenance, install command, `mneme check --mode warn` (all app 15368), strict `false` | 4: the same minus `mneme check --mode warn` (`s5-intended-main-pr-only-update.json`) | **D1** (ruling R5) |
| Workflow files | at **M** `e6fa32d4` | at `main` tip `c27dc56a` | **byte-identical blobs** for `mneme-trusted-gate.yml` (`14764367`), `tests.yml` (`5bd14457`), `encoding-check.yml` (`e3a264e0`), `mneme-check.yml` (`60417677`), `provenance-check.yml` (`b1cea779`), `install-command-check.yml` (`f862cf05`) |
| Gate pins | adapter `c51729f7` / `afe1d69c…`, evaluator `0b74d410` / `e3fcc769…` | same (same workflow blob) | **identical** |
| Decision memory | `.mneme/project_memory.json` blob `5002a6c0` | same at `c27dc56a` | **identical** |
| Availability posture | `closed` (cases a, b, d, e; c flipped and restored) | `closed` (R3); variable updated 2026-11-02T23:14:53Z | **identical** |
| Actions permissions | enabled, `allowed_actions: all`, SHA pinning not required | same | **identical** |
| Workflow `GITHUB_TOKEN` | read, cannot approve reviews | same | **identical** |
| Merge settings | squash only (rule) | repo: squash only, auto-merge off, delete branch on merge | **identical** |
| Collaborators | `TheoV823` admin, `mneme-agent` write | same | **identical** |

**Branch tips are not identical, and are not claimed to be.** S4 ran with
staging = `main` = **M** `e6fa32d4`. `main` is now `c27dc56a`: **M** plus the #735
docs commit (`docs/validation/` only). No workflow, adapter, `.mneme/` or
`scripts/ci/` file differs between the two (`git diff M..c27dc56a` over those
paths is empty). In production the gate evaluates every PR against `main`'s
tip at run time (`pull_request_target`), which is the same relation S4 had by
construction.

## 2. Differences affecting merge authorization

**D1 (planned, ruling R5).** S5 removes `mneme check --mode warn` from
`main-pr-only`'s required checks; S4 kept it required on staging. Effect:
that workflow runs with `|| true` and always succeeds when it runs, so its only
blocking effect today is when it **fails to run or report** (for example an
install error). After S5 such a failure no longer blocks merge; the gate, the
PR battery, mojibake/BOM, provenance and install-command checks still do.
The owner ruled this in R5 ("drop warn check from required when the gate
becomes required"). **It needs the owner's explicit acceptance here before
S5**, per the charter's S4→S5 rule.

No other difference affects merge authorization.

## 3. Proposed S5 change set (not applied)

One recorded change set, in this order, so protection never drops:

1. `PUT /repos/MnemeHQ/mneme/rulesets/26391853` with
   `s5-intended-mneme-ci-gate-update.json` (enforcement `active` + the gate
   rule). Allowed by the S5 row and the #721 clarification.
2. `PUT /repos/MnemeHQ/mneme/rulesets/22196895` with
   `s5-intended-main-pr-only-update.json` (rules unchanged except D1).
3. Read-only after-snapshots: both rulesets, effective rules on `main`,
   variable `closed`.

Rollback: the charter §5.4 controls (posture `open`; or remove the gate rule /
disable `mneme-ci-gate`), plus restoring the warn context from
`current-main-pr-only.json`.

## 4. Operational impact to expect at S5 (not a configuration difference)

- 28 PRs are open into `main`. With strict up-to-date and the gate required,
  each needs an update to the current `main` and a passing gate before merge.
- Two of them change gate-protected paths and will be **REFUSED** until merged
  through the recorded bypass (charter §5.2) or changed: #485
  (`.github/workflows/release.yml`) and #598 (`.mneme/README.md`). Documents quoting the ADR-005 forbidden literal will be
  VIOLATIONs (S3 P4).
- Fork and first-time-contributor PRs remain unobserved (S3, S4).
- R6 residual unchanged.

## 5. Verdict

**Equivalent for S5, subject to the owner accepting D1.** The gate ruleset,
bypass actor, check identity, strict freshness, workflow blobs, pins, memory,
posture, Actions and merge settings that S5 would use are the ones S4
validated. Evidence: [`ci-r0-s4-s5-equivalence-2026-11-03/`](ci-r0-s4-s5-equivalence-2026-11-03/)
with `EVIDENCE-SHA256SUMS` (S4-tested staging rulesets, current production
snapshots, and the two intended S5 update bodies).

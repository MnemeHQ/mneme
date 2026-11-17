# CI rollout R0 S4: recovery validation on staging (2026-11-02/03)

**Status: RECORD (metadata only).** Records the R0 S4 run on a staging branch
of `MnemeHQ/mneme`. **All five charter §7 S4 cases came out as expected with
real gate verdicts.** Production was not changed by the cases: `main-pr-only`,
`mneme-ci-gate` (disabled, no rules) and the effective rules on `main` are
byte-identical before and after, and `MNEME_CI_AVAILABILITY` is `closed`. This
record authorizes no later stage; S5 needs its own authorization and the
S4→S5 configuration equivalence check. Production promotion stays **DEFERRED**.
**Governing documents:** [R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
§5 and §7 S4 (#684, R6 #718); [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)
R0 amendment S4 rows (#685) and the S4 trigger-filter amendment (#730).

## 1. Authorization and history

- Owner go-ahead for S4 via the forwarded S3 review (2026-11-02): "I approve
  the proposed S4 scope for execution preparation, consistent with R0 §7".
- **Attempt 1 stopped** under its own stop rule: the gate did not start on
  PRs into `r0/recovery-staging` (#727-#729). Cause: `pull_request_target` runs
  the default branch's workflow with `GITHUB_SHA` = `main`'s tip, so `main`'s
  `branches: [main]` filter applied, and the gate's trusted base is always
  `main`. Attempt 1 is not evidence for any case. Its staging-only filter commit
  was first written with CRLF line endings and replaced byte-exact before any
  ruleset or PR existed.
- Fix: `[layer1-freeze]` #730 (`6d58f472`) made one change eligible; #731
  (squash `e6fa32d4` = **M**) added `r0/recovery-staging` to the PR trigger
  filter of four workflows, nothing else. Reviewed and approved by the owner's
  forwarded reviews.
- Attempt 2 ran with the #730 conditions: staging created at exactly **M**,
  `main` frozen at **M** for the whole run (verified before case (d) and at
  teardown), every gate report `base_sha` = `merge_base` = **M**, the staging
  merge last.

## 2. Staging configuration

| Item | Identity | Check |
|---|---|---|
| Branch `r0/recovery-staging` | created at **M** `e6fa32d48b56640e7e196e238eb54195d2ea4fc6` | tip = **M** until case (a) |
| `r0-staging-main-pr-only` | ruleset 26406439, active, **no bypass** | rules identical to production `main-pr-only` (22196895); only `id`, `name`, `node_id`, `conditions`, timestamps, `_links` differ |
| `r0-staging-gate` | ruleset 26406441, active, bypass one `User` 54006786 (`TheoV823`) `pull_request`; required `mneme trusted gate` (app 15368), strict up-to-date | as specified |

Probes (plumbing-built commits on **M**, PRs into staging): A #732
`.mneme/r0-s4-a.txt`; C #733 `.mneme/r0-s4-c.txt`; D #734 `docs/r0-s4/link`
(symlink, mode 120000).

## 3. Cases

| Case | What was done | Result | Evidence |
|---|---|---|---|
| (b) bypass isolation | A with no provenance block: gate REFUSED, provenance failing; merge by `TheoV823` (the bypass actor) | **405**: "Required status check \"Validate PR execution provenance\" is failing." The gate failure is not listed: the bypass covered `r0-staging-gate` but not `r0-staging-main-pr-only` | request `F013:132D3:C5DA4D:28703F3:6AE9190A`; `case-b-merge-A-response.txt` |
| (e) non-authority | `mneme-agent`, from the `MnemeAgent` Windows account, merge of C (gate REFUSED, all other checks pass) | **405**: "Required status check \"mneme trusted gate\" is failing." No merge | owner-reported, request `FD00:110A32:619B29:142E7B3:6AE9CD9A`, 2026-11-03 12:03:44Z; independently confirmed by GitHub rule suite 4878291084 (`mneme-agent`, result `fail`) |
| (c) availability rollback | posture `open` 23:13:34Z to 23:14:53Z (2026-11-02), gate re-runs on D and C | `closed`: D UNEVALUATED, failure. `open`: D success with `::warning::` "UNEVALUATED, not PASS (availability open)", merge state CLEAN; C REFUSED, failure, BLOCKED. `closed` again: D UNEVALUATED, failure, BLOCKED. Re-runs read the current variable | gate reports D0, D1, C1, D2 |
| (d) required-check removal | removed the rule from `r0-staging-gate` 12:05:36Z, restored 12:05:40Z (2026-11-03) | effective rules lose then regain the `r0-staging-gate` `required_status_checks`; D BLOCKED → UNSTABLE (mergeable) → BLOCKED; restored rules equal the original | requests `D044:339E7D:14FF08A:451A3E7:6AE9CE0F` / `D04A:181D55:16206FA:49199A8:6AE9CE13`; `case-d-effective-*.json` |
| (a) refusal + recorded bypass | A with provenance and the charter §5.2 record in its body (approval, protected path, reason, check-run 125611337939 / head / REFUSED); merge by `TheoV823` | **200**, squash `22a7853e` on staging only; `main` still **M**. GitHub rule suite 4878345773: actor `TheoV823`, result **`bypass`**; every `r0-staging-main-pr-only` rule `pass`, `r0-staging-gate` `required_status_checks` `fail` | request `E416:2451C:15AB004:47A7D22:6AE9CE4F`; `rule-suite-bypass-owner.json` |

Gate runs (all `pull_request_target`, check `mneme trusted gate`, app 15368):

| Report | Run / job | Posture | Result |
|---|---|---|---|
| A0 | 41542937047 / 125611337939 | closed | REFUSED (`policy`) |
| C0 | 41542946448 / 125611369955 | closed | REFUSED (`policy`) |
| D0 | 41542953999 / 125611397378 | closed | UNEVALUATED, failure |
| D1 (attempt 2) | 41542953999 / 125614064858 | open | UNEVALUATED, success + warning |
| C1 (attempt 2) | 41542946448 / 125614089663 | open | REFUSED, failure |
| D2 (attempt 3) | 41542953999 / 125614661620 | closed | UNEVALUATED, failure |

## 4. Teardown and production check

Posture `closed` (verified); C and D closed unmerged; probe branches, both
staging rulesets and `r0/recovery-staging` deleted. Production `main-pr-only`
JSON (`fadc3443…`) and effective rules on `main` (`a4d21f9f…`) are identical to
the pre-run snapshots, as is `mneme-ci-gate`. The four #731 filter lines
**stay** on `main` through the S4→S5 equivalence check (#730 condition 5).

## 5. Findings

- **Recovery works with real verdicts.** A REFUSED change was merged only by
  the designated human through a recorded bypass; the same change from
  `mneme-agent` was refused.
- **Bypass is isolated to the gate ruleset.** With layered rulesets, the
  bypass actor still could not merge past the `main-pr-only` protections
  (case (b)), and GitHub's rule-suite log shows the bypass applied only to
  `r0-staging-gate` (case (a)).
- **Availability rollback behaves as specified.** `open` lets UNEVALUATED pass
  visibly labelled, never PASS, while REFUSED still blocks; returning to
  `closed` and re-running restores blocking. Re-runs read the current posture.
- **Required-check removal is effective and reversible** within seconds.
- **Gate base is always the default branch.** `pull_request_target` evaluates
  every PR against `main`'s tip. The gate is meaningful only for PRs into
  `main` (its production target), and S4 evidence holds only because staging
  was identical to `main`.

## 6. Limits and non-claims

- Case (e) execution was owner-reported; GitHub's rule-suite log independently
  shows the `mneme-agent` attempt with result `fail` at the same time.
- R6 applies: other actions used the owner's administrator-capable login in
  the dogfooding environment. No administrator-resistance or ADR-029
  "relevant enforcement observed" claim is made.
- Fork and first-time-contributor PRs remain unobserved.
- One literal-tier rule; the UNEVALUATED case used a symlink, as in C4 Gate 3.
- Per-bypass records are procedure, not GitHub-enforced (charter §5.2).

## 7. Evidence

[`ci-r0-s4-recovery-2026-11-03/`](ci-r0-s4-recovery-2026-11-03/) with
`EVIDENCE-SHA256SUMS`: the six gate reports (none contains the ADR-005
literal), the two rule-suite records, the case (b) and (a) merge responses,
the case (d) effective-rule snapshots, the owner-reported case (e) text, the
staging ruleset snapshots, and production pre/post snapshots.

## 8. S4 status

On merge of this record with the owner's acceptance, S4 closes as **passed**.
Next, the S4→S5 configuration equivalence check (read-only) and then S5, each
needing owner authorization.

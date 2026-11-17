# CI rollout R0 S3: trusted gate installed, first shadow runs (2026-11-02)

**Status: RECORD (metadata only).** Records the S3 install and four shadow
probe runs on `MnemeHQ/mneme`. **The gate is not required by any ruleset;**
`mneme-ci-gate` (26391853) stays `disabled` with no rules. This record
authorizes no later stage. Production promotion stays **DEFERRED**.
**Governing documents:** [R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
§7 S3 (#684, R6 #718) and the [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)
R0 amendment, S3 row (#685).

## 1. Authorization

Owner (2026-11-02, Mneme Core conversation, recorded on the owner's behalf):
go-ahead to "move on with the batches", with the independent review of
#720/#721 recommending to set `MNEME_CI_AVAILABILITY=closed`, merge both
reviewed PRs, and then gather real GitHub shadow-run evidence. That review
added: "S3 must establish that the gate actually executes correctly before
proceeding to S4."

## 2. What changed on Core

| Change | Identity |
|---|---|
| Repository variable `MNEME_CI_AVAILABILITY=closed` | created 2026-11-02T19:43:32Z |
| Workflow `.github/workflows/mneme-trusted-gate.yml`, job/check `mneme trusted gate` | #720, squash `0d34e018` (workflow id 404923975, active) |
| `[layer1-freeze]` S5 activation clarification | #721, squash `dc8ca76f` (docs only) |

Pins in the workflow, unchanged from C4: adapter `c51729f7`
`scripts/ci/adr033_c4_gate.py` blob `5feedf60`, sha256 `afe1d69c…`; evaluator
`0b74d410`, approved wheel `e3fcc769…`; `VIOLATION_MODE: strict`.
Not changed: rulesets (`main-pr-only` `updated_at` still `2026-09-12`;
`mneme-ci-gate` disabled, 0 rules), `mneme-check.yml`, required checks,
Actions permissions, adapter, evaluator, `.mneme/`.

## 3. Shadow probes

Four throwaway draft PRs from `main` at `dc8ca76f`, each one plumbing-built
commit, opened 19:44Z and closed unmerged afterwards with their branches
deleted. The gate ran on each with no approval prompt.

| Probe | PR | Change | Run / check run | Gate result | Check |
|---|---|---|---|---|---|
| P1 | #722 | `docs/validation/r0-s3-probe/p1.md`, neutral text | 41512778999 / 125508597242 | PASS (`VERIFIED_PASS`) | success |
| P2 | #723 | `.mneme/r0-s3-probe.txt` | 41512783652 / 125508610165 | REFUSED, kind `policy` | failure |
| P3 | #724 | `.github/r0-s3-probe.txt` | 41512789878 / 125508629763 | REFUSED, kind `trusted_surface` | failure |
| P4 | #725 | `docs/validation/r0-s3-probe/p4.md` quoting the ADR-005 forbidden install literal | 41512796052 / 125508649782 | VIOLATION: `ADR-005` `FORBID_LITERAL`, strict, evaluator exit 2 | failure |

Every run: event `pull_request_target`, attempt 1, ubuntu-24.04; check run
`mneme trusted gate`, GitHub Actions app 15368, on the PR head SHA; every
build, pin and evaluation step succeeded, and only the `Gate decision` step
failed on P2-P4. Each report shows posture `closed` from
`vars.MNEME_CI_AVAILABILITY` with no fallback, mode `strict`, adapter sha256
`afe1d69c…`, evaluator `0b74d410` / `e3fcc769…`. P1 and P4 read decision
memory from the base commit (`dc8ca76f`, `.mneme/project_memory.json` blob
`5002a6c0`, sha256 `db7ab995…`); P2 and P3 were refused before evaluation.

### Evidence handling

The gate reports of P1 and P4 contain the ADR-005 forbidden literal (the
evaluator echoes the applied rule), which the repository's own install-command
check refuses. So no report is committed here. They are held as GitHub
artifacts (expire 2027-01-31) and in owner-controlled private storage, with
these SHA-256 digests of `gate-report.json`:

| Probe | Artifact | `gate-report.json` SHA-256 |
|---|---|---|
| P1 | `mneme-gate-pr722-41512778999` (id 13173019711) | `3e556b7314199b63d5fa3892d63b705428c81bf91a821b05a90bbf57c6253512` |
| P2 | `mneme-gate-pr723-41512783652` | `df8d438b1ba83612ff53a37b7a3d69c8348aab13257cded12b1b0d7d30dbf686` |
| P3 | `mneme-gate-pr724-41512789878` | `157152ca1a352d479f4a35c87f911be17f05b87e00ceee4a9276ebac6731a8d4` |
| P4 | `mneme-gate-pr725-41512796052` | `66e0fea491fb6ce01a0a0fced835a508df2f0657dca9720dac7a4b9c7ad77fe7` |

## 4. Findings

- **The gate executes correctly on Core.** On GitHub runners it rebuilt the
  evaluator to the approved wheel hash, verified the adapter pins, read memory
  from the base, and produced PASS, both REFUSED kinds and a strict VIOLATION as
  specified, each reflected in the check conclusion.
- **CI1 condition 7, first evidence after 2026-11-02.** `pull_request_target`
  runs started and completed on 2026-11-02 for same-repository PR branches
  with no approval step and no Actions event policy change. **Not observed:**
  PRs from forks or first-time contributors, which GitHub's change targets
  most directly. No Actions event policy is created on this evidence.
- **Install PR got no gate run**, as designed: `pull_request_target` uses the
  base workflow, and #720's base did not have it.
- **ADR-005 quoting.** P4 confirms the earlier R0 observation: a document that
  quotes the forbidden literal is a VIOLATION under the gate. When the gate is
  required, such documents need the recorded bypass (charter §5.2).

## 5. Limits and non-claims

- Shadow only. Nothing here shows blocking at merge time, bypass, recovery,
  posture `open`, or unavailable evaluation; those are S4 (staging) questions.
- Probes were created by the owner's administrator login in the existing
  dogfooding environment (R6). No administrator-resistance or ADR-029
  "relevant enforcement observed" claim is made.
- Four synthetic probes, one literal-tier rule. Behavior on representative
  ordinary Core PRs accumulates from now on as PRs are opened; it is not
  summarized here.

## 6. S3 status and next stage

On merge of this record with the owner's acceptance, S3 is recorded as
**installed and executing correctly in shadow**. Open within S3: observing
ordinary Core PRs over time (no further action needed to collect it). Next,
S4 (recovery validation on a staging branch, gate required there) needs its
own owner authorization.

# Trusted CI gate: reproducible installation in a fresh repository (2026-11-03)

**Status: RECORD (metadata only).** The trusted CI gate was installed in a
fresh GitHub repository using only the published guide, and its three
acceptance tests passed. **Supported claim:** the trusted CI gate can be
installed and validated in a fresh GitHub repository from the published
instructions, with the frozen pins. **Not claimed:** independent third-party
installation, universal fail-closed behavior, or general production readiness.
No Core configuration changed.

## 1. What was followed

- Guide: [`docs/integrations/github-actions-c4-gate.md`](../integrations/github-actions-c4-gate.md)
  as published at `f8a780cd` (#744; blob `ef9e6b21`).
- Repository: `MnemeHQ/mneme-gate-repro`, created empty for this run, synthetic
  content only. Operated by the same owner and machine as R0.
- Authorization (owner, 2026-11-03): the reproducibility plan as reviewed, then
  "Publish and test" after a recorded pre-publication inspection.

## 2. Installation, step by step

| Guide step | What was done | Deviation |
|---|---|---|
| 1 Prerequisites | Actions enabled, `allowed_actions: all`, hosted `ubuntu-24.04` | none |
| 2 Decision memory | published example copied verbatim to `.mneme/project_memory.json` (blob `4c669436`, identical) | none (the guide does not prescribe how the file reaches the default branch; it was the initial commit) |
| 3 Posture | `MNEME_CI_AVAILABILITY=closed` with the guide's command | none |
| 4 Workflow | Core's workflow copied verbatim (blob `3fb1e0ba`, as the guide states) via ordinary PR #1; no gate run on it, as the guide says | none |
| 5 Rulesets | the guide's block run with only `REPO` and `BYPASS_LOGIN` set; created `main-pr-only` (26459082, no bypass) and `mneme-ci-gate` (26459083, required `mneme trusted gate` app 15368, strict, one `User` bypass in `pull_request` mode) | none |
| 6 Actions policy | none needed; `pull_request_target` runs started with no approval step | none |
| 7 Verify | three PRs; merge attempts by `mneme-agent`, a write collaborator that is not a bypass actor | **environmental:** see §4 |

## 3. Acceptance tests

Rulesets unchanged through the tests (rules, bypass, conditions, enforcement
and `updated_at` identical before and after); posture `closed`; base = `main`
`bc564411` for every run; every report shows adapter `afe1d69c…`, evaluator
`0b74d410`, wheel `e3fcc769…`, posture `closed` with no fallback.

| Test | PR | Gate run / check run | Gate result | Merge attempt by `mneme-agent` | Rule suite |
|---|---|---|---|---|---|
| T1 prohibited (`docs/t1.md` with the forbidden literal) | #2 | 41660425665 / 126001844631 | **VIOLATION**, failure | **405**, required `mneme trusted gate` failing | 4886949684 `fail` (only `mneme-ci-gate` fails; every `main-pr-only` rule passes) |
| T2 compliant (`docs/t2.md` neutral) | #3 | 41660437835 / 126001888160 | **PASS**, success | **200**, merged as `5335c722` | 4886951160 `pass` |
| T3 unavailable (`docs/t3-link`, symlink) under `closed` | #4 | 41660447456 / 126001921424 | **UNEVALUATED**, failure | **405**, required `mneme trusted gate` failing | 4886950408 `fail` (same) |

The merge attempts were run by the owner from the `MnemeAgent` Windows account
signed in as `mneme-agent` (permission `write`, not a bypass actor); the HTTP
results were reported in the owner's review and are independently corroborated
by GitHub's rule-suite records above and by the PR states (#2 and #4 never
merged and later closed; #3 merged by `mneme-agent`).

Evidence: [`c4-gate-reproducibility-2026-11-03/`](c4-gate-reproducibility-2026-11-03/)
(three gate reports, three rule suites, the two generated ruleset files, the
repository's rulesets and effective rules after the tests,
`EVIDENCE-SHA256SUMS`). No file contains the ADR-005 literal.

## 4. Environmental prerequisite found

Step 7 needs an account without bypass authority. Adding `mneme-agent` to the
repository while it was **private** failed: HTTP 422, "You must purchase at
least one more seat to add this user as a collaborator" (outside collaborators
on private repositories of a paid organization consume seats). After a
recorded pre-publication inspection (only synthetic or already-public
material) the repository was made public, where outside collaborators need no
seat. This is a property of the GitHub plan, not a Mneme enforcement defect;
this PR adds a one-line note on it to the guide's step 7.

## 5. Limits

- Same operator, machine and organization as R0: reproducible installation,
  not independent third-party validation.
- One synthetic literal-tier rule; fork and first-time-contributor PRs not
  exercised; posture `open` not exercised here (validated in R0 S4).
- CI boundary only; agent-host hooks are a separate boundary and are not
  fail-closed when the host does not invoke them.
- R6 and the other limits in the guide and the R0 closure record still apply.

## 6. Next

The repository `MnemeHQ/mneme-gate-repro` is archived after this record is
reviewed and merged.

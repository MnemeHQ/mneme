# CI1.3: Isolated merge-blocking experiment charter (proposal)

**Status:** **PROPOSED.** This is a design-only proposal. **Nothing here is
executed or authorized.** It does not create a repository, configure a
ruleset, change any workflow, change the runtime, enable strict mode in
`MnemeHQ/mneme`, decide ADR-033 availability policy, or amend Layer 1. §9 lists
the separate approvals the experiment needs before it can run.
**Anchor:** `main` @ `28df1442` (#538). CI1.2 is complete: #536 (`50b58c32`)
and #539 (`c5a7c896`).
**Tracker:** #540 (CI1 Enforcement Assurance).
**Builds on:** the
[CI1.1 record](../validation/ci1-1-enforcement-assurance-contract-validation-2026-10-16.md)
(F1–F7, S1–S7, A1–A7), the
[CI1 contract fixtures](../../tests/fixtures/ci1_contract/README.md), and the
[C1 verdict-consistency charter](2026-10-14-reliable-enforcement-c1-verdict-consistency-charter.md)
(#260, `assess_verdict`).

## 1. The proof

> **An agent cannot make a prohibited change pass by modifying the policies or
> mechanisms that evaluate that same change.**

CI1.1 found that today the opposite is true. The PR under evaluation supplies
its own decision memory (S1, S2), its own evaluator (S3, through
`pip install -e .`) and its own gate definition (S4, through `pull_request`).
A required check with that design can be switched off by the change it judges.

CI1.3 is proven only when **all** of the following hold in one isolated,
protected repository:

1. A PR containing a real violation of the trusted rule **cannot be merged**.
   The evidence is the repository host refusing the merge, not a red job.
2. The same violation stays unmergeable when the PR **also** edits, deletes or
   replaces the decision memory, the evaluator, the gate workflow, or adds a
   look-alike check (§6, rows V2–V7).
3. A compliant PR **can** be merged, so the gate is not simply always red.
4. A result computed for an earlier head commit cannot authorize a newer,
   unevaluated head (V10).

Anything less is recorded as a partial result, with the failing row named.

## 2. Scope

**In scope.** One new, isolated, **public** test repository, with one protected
branch and one trusted decision (the CI1.2.1 path-scoped `FORBID_LITERAL`
corpus). GitHub Actions is the CI executor. Compliant, violating and
adversarial PRs are opened by the experimenter.

**Out of scope.** Any change to `MnemeHQ/mneme`'s `mneme-check.yml` or
`main-pr-only` ruleset (CI1.1 A6). Production rollout. Jenkins, GitLab and
other hosts (CI1.1 §9: later parity targets). A reusable Action (#278).
Waivers and DG1 semantics (#497). ADR-033 availability policy (#483). Any
change to Mneme Core, its payload, or exit codes.

The repository must be public. `MnemeHQ` is on GitHub's **Free** plan
(`gh api orgs/MnemeHQ` reports `plan: free`). On Free, rulesets and branch
protection are enforced only on public repositories. A private lab repository
would silently not block, and the experiment would measure nothing.

## 3. Trusted-source options

A trustworthy gate needs three inputs the PR cannot substitute: **policy**
(decision memory), **evaluator** (the Mneme build), and **gate definition**
(the workflow or check that runs it).

| # | Option | Policy source | Evaluator | Gate definition | Self-modification resistance | Available on Free | Main risk |
|---|---|---|---|---|---|---|---|
| **T1** | **`pull_request_target` trusted workflow** | Base-branch commit, recorded SHA | `mneme-hq` pinned by version and hash from PyPI, or a pinned `MnemeHQ/mneme` commit | Workflow file from the **base** branch. PR edits to it do not run for that PR | By mechanism: the PR's workflow, memory and code are read as **data only** | Yes | `pull_request_target` runs with a base-repo token. It must never execute PR code (no `pip install` of the PR, no PR scripts, `persist-credentials: false`, `permissions: contents: read`, plus `checks`/`statuses` write only if needed) |
| T2 | Ruleset "required workflows" from a separate policy repository | Policy repository | Policy repository | Policy repository | By mechanism | Believed to need a paid plan (org-level rulesets). **To confirm. Treated as unavailable on Free** | Plan dependency. Not testable here without upgrading |
| T3 | Keep `pull_request` and add CODEOWNERS plus required code-owner review on `.mneme/**`, `.github/workflows/**` and evaluator paths | PR tree | PR tree | PR tree | **By human review only.** The PR's own workflow still runs on that PR | Yes | Depends on reviewer diligence. Needs `required_approving_review_count > 0`, a ruleset change. Does **not** meet §1 by mechanism |
| T4 | External evaluator (GitHub App or external CI) posting a check under its own app identity, with the required check pinned to that `integration_id` | Evaluator-owned store | Evaluator-owned build | Outside the repository | By mechanism, and also defeats same-app look-alikes (V7) | Yes, but needs an app or service | Build and operations cost. Closest to a product, so not an experiment default |

**Recommendation: T1 for the experiment.** T3 can be measured separately as
defense in depth. It must not count toward the §1 proof, because it relies on
people rather than mechanism. T4 is recorded as the productization candidate
if V7 shows that same-app look-alike checks defeat T1. It is not built here.

### T1 design details the experiment must validate

- **Two checkouts.** Check out `base/` at the base SHA (trusted: memory and
  workflow). Check out `pr/` at `github.event.pull_request.head.sha` as data
  only, with `persist-credentials: false`.
- **Policy root alignment.** ADR-020 derives the policy root from the memory
  file's parent, so memory in `base/` and inputs in `pr/` would put every input
  outside the root and yield UNKNOWN. The gate copies the trusted memory over
  `pr/.mneme/project_memory.json` before checking, so the root is `pr/` and
  any PR-supplied memory there is **overwritten**, never merged. V2 and V3
  test this.
- **Changed-file list.** Computed by trusted code from the recorded base and
  head SHAs. Not taken from PR-controlled scripts.
- **Verdict rule.** This is lab-local experiment policy, not product policy.
  The check succeeds only for VERIFIED_PASS on every in-scope file, as defined
  by the CI1.2 classification. Payload coherence follows the C1 charter's
  `assess_verdict` rules (#260), including **requested-mode equality**: the
  adapter passes the mode it requested, and a reported `mode` that differs is
  UNEVALUATED. Exit codes are never read alone (CI1.1 F1; #540 carry-forward:
  malformed memory exits 1, the strict WARN code). Failing UNEVALUATED in the
  lab is a measurement choice and does **not** settle ADR-033.
- **Check-run association.** Whether a `pull_request_target` check run
  attaches to the PR **head** SHA (so the required check can be satisfied or
  blocked per head) is a known subtlety. It is measured, not assumed (V10,
  V11).

## 4. Preconditions (all before any live run)

| # | Precondition |
|---|---|
| P1 | This charter is accepted by PR review |
| P2 | The pinned evaluator passes the full CI1.2 corpus (`tests/test_ci1_contract_fixtures.py`, `tests/test_ci1_contract_matrix.py`) in a clean venv. `v0.10.0` carries `evaluation_complete`, `rule_id` and `decision_version_id`, but the corpus was validated against `main`, not that release. If it fails, pin a `MnemeHQ/mneme` commit instead and record why |
| P3 | Lab repository name, owner and visibility are approved (§9) |
| P4 | The lab ruleset is written down **before** it is applied: target branch, required check context and `integration_id`, `bypass_actors: []`, required approvals, `strict_required_status_checks_policy` |
| P5 | The experimenter's merge attempts use the API (`PUT /repos/{o}/{r}/pulls/{n}/merge` with `sha`), so the refusal is a recorded HTTP response and not a screenshot |

## 5. Lab fixture

The trusted memory is the CI1.2.1 corpus memory
(`tests/fixtures/ci1_contract/path_scoped_forbid_literal/v1/project_memory.json`):
`rule_id` `ADR-901:FORBID_LITERAL:1eff1b82c5be57bd80379f967b799f7b`,
`decision_version_id` `dver-d3d431ff6d5edba8b555a040a7b85f9b`,
`include_paths: [docs/**]` and `exclude_paths: [docs/history/**]`. It is a
literal-tier rule, so query steering (CI1.1 S7) cannot change the verdict. Lab
`main` is seeded with that memory and a trusted gate workflow. The seed commit
SHA is recorded.

## 6. Substitution test matrix

Every row is a separate PR against the lab's protected branch. "Blocked"
means the host refused the merge **and** the refusal is captured.

| # | Scenario | PR contents | Expected gate classification | Expected host outcome | Maps to |
|---|---|---|---|---|---|
| V0 | Compliant change | `docs/` edit without the literal | VERIFIED_PASS | **Merge succeeds** | §1.3 |
| V1 | Plain violation | `docs/` edit with the literal | VIOLATION | Blocked | §1.1 |
| V2 | Violation plus policy removal | V1, and the PR deletes ADR-901's rule or decision from `.mneme/project_memory.json` | VIOLATION (trusted memory used) | Blocked | S1 |
| V3 | Violation plus memory deletion | V1, and the PR deletes `.mneme/project_memory.json` | VIOLATION | Blocked | S2 |
| V4 | Violation plus evaluator substitution | V1, and the PR adds or edits Python files or packaging that would change verdicts if installed | VIOLATION (PR code never executed) | Blocked | S3 |
| V5 | Violation plus gate edit | V1, and the PR edits the trusted workflow (for example `exit 0`, warn mode, or deleting the job) | VIOLATION (base workflow runs) | Blocked | S4 |
| V6 | Violation plus new `pull_request` workflow | V1, and the PR adds a second workflow that runs its own permissive check | VIOLATION from the trusted gate | Blocked | S4 |
| V7 | Violation plus look-alike check | V1, and the PR adds a `pull_request` job whose display name equals the required context | Trusted gate VIOLATION, look-alike green | **Measured.** Blocked means T1 holds against same-app look-alikes. Merged means V7 fails and T4 is required | S5, CI1.1 F3b |
| V8 | Out-of-scope file | Literal in `src/notes.md` (no include match) | VERIFIED_PASS with EXCLUDED applicability | Merge succeeds. Recorded as a **coverage limit**, not as assurance | S6 |
| V9 | Unevaluable input | Trusted gate deliberately given an out-of-root target, or a corrupted trusted-memory variant on a lab branch | UNEVALUATED | Lab policy: blocked. Recorded as lab policy, not ADR-033 | F1, #540 |
| V10 | Stale head | V0 goes green, then a commit adding the literal is pushed | VIOLATION on the new head | Blocked. The earlier green must not satisfy the new head | CI1.1 F5 |
| V11 | Base advanced | V0 goes green, then lab `main` gains a rule-relevant change (for example a second scoped literal that V0's content trips) | Measured. With `strict_required_status_checks_policy: false`, the stale green may still allow merge | **Measured.** Records whether base freshness is enforced. Not assumed | CI1.1 F5, #488 |
| V12 | Requested-mode mismatch | Lab variant whose evaluator reports a `mode` other than the requested one (a stubbed wrapper on a lab branch, never PR code) | UNEVALUATED | Lab policy: blocked | #540 carry-forward |

V9 and V12 exercise the gate's own robustness. They are configured by the
experimenter on lab branches, never supplied by an untrusted PR, so they test
classification rather than substitution.

## 7. Evidence per row (CI1.4 input)

For every row, record:

- PR number, head SHA, base SHA, and the SHA actually checked out as `pr/`
- trusted-memory blob SHA and its source commit, plus the evaluator version and hash
- raw `mneme.check/v1` payload for each in-scope file, requested mode, exit code and classification
- check-run id, name, `app.id`, `head_sha` and conclusion, for every check run on the head commit (V7)
- a ruleset snapshot (before the run and after the matrix)
- the merge API request and response (status code and message)

Missing ADR-029 bindings are listed as gaps, not inferred (CI1.1 F2 as
amended).

## 8. Outcomes

- **Proven:** V0–V6 and V10 behave as expected, V7 is blocked, and the
  evidence is complete.
- **Proven with T4 dependency:** everything as above except V7 merges. That
  means a same-app look-alike defeats name-pinned required checks, so T1 alone
  is insufficient and T4 is required for assurance.
- **Not proven:** any of V1–V6 or V10 merges. Record the row and stop.
- V8 and V11 never decide the outcome. They are recorded as coverage and
  freshness limits.

The CI1.4 recommendation (promote or defer) follows from the outcome. It does
not follow from this charter.

## 9. Approvals required before execution

1. Acceptance of this charter (PR review).
2. The lab repository: name, owner (the `MnemeHQ` org or a personal account),
   **public** visibility, and its lifetime (archived after CI1.4).
3. The lab ruleset contents (P4), applied only to the lab repository.
4. Confirmation that `MnemeHQ/mneme` stays unchanged. Any later adoption needs
   the G2 C1 charter and a `[layer1-freeze]` amendment (ADR-031 §7).

## 10. Explicitly not authorized

- Any edit to `MnemeHQ/mneme` workflows, rulesets, `.mneme/`, Core code or the frozen benchmark.
- Running PR-supplied code in any privileged context, including in the lab.
- Treating the lab's "UNEVALUATED blocks" choice as product policy (ADR-033 #483).
- Treating a red job, or a CLI exit code, as merge-blocking evidence.
- Relaxing required human review anywhere.

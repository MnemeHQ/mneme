# CI portability: Gate 0 read-only assessment

**Status: ASSESSMENT AND PROPOSAL.** Read-only. It authorizes no
implementation, configuration change, lab, experiment or platform-support
claim. The experiment in §7 is a proposal for separate owner approval.
**Date:** 2026-11-03.
**Repository state assessed:** `MnemeHQ/mneme` `main` at `790c98b5` (#745).
**Scope:** the revised Gate 0 scope, "approved for read-only assessment"
(owner, 2026-11-03, Mneme Core conversation, recorded on the owner's behalf):
architecture review (A), portability inventory (B), platform assessment (C),
second-platform experiment proposal (D), deliverables E1-E5.

## 1. Question and conclusion

Can the ADR-033 §5 CI merge gate, proven on GitHub by C4 (#676-#682) and
running as bounded dogfooding on Core (R0, #684-#745), be carried to another
CI platform without redefining its enforcement or availability semantics?

**Conclusion.**

1. **The evaluation and policy logic is portable as is.** The pinned adapter
   (`scripts/ci/adr033_c4_gate.py`, `c51729f7`) takes base and head SHAs as
   arguments, reads everything else from git objects, and depends on the
   platform only for reporting. Under posture `closed` it runs unmodified on
   any platform that can give it a trusted base checkout, the head as git
   objects, and an environment variable (§4).
2. **The trust boundary is not portable; it is rebuilt per platform.** On
   GitHub it rests on `pull_request_target` (pipeline definition from the
   base), a ruleset-required check, and an administrator-only variable.
   GitLab, Jenkins and Azure DevOps all run the pipeline definition from the
   change's source by default (§5). Each has a different, partly
   tier-dependent mechanism to pin the definition elsewhere, and none was
   verified live.
3. **Posture `open` is not portable without an adapter change.** ADR-033 §5
   requires `open` UNEVALUATED to be visible. The adapter makes it visible
   with GitHub `::warning::` workflow commands, and `verify-report` requires
   that string (§4, G-2). Elsewhere it would be written but not displayed.
4. **Recommended next step:** one isolated GitLab lab, `closed` posture,
   unchanged pins, the pipeline definition held in a separate trusted project
   (§7). Fork behavior (case 5) is the highest-risk unknown and may fail.

No ADR, Layer 1 freeze text, `mneme.check/v1` field or availability state
needs to be redefined for this proposal. Section 6 lists what is unproven.

## 2. Sources

| Source | Identity |
|---|---|
| ADRs | 017, 020, 021, 022, 029, 030, 031, 033, 034 (`docs/adr/`), all accepted |
| C4 adapter | `scripts/ci/adr033_c4_gate.py`, commit `c51729f7`, blob `5feedf60`, SHA-256 `afe1d69c…` |
| Evaluator pin | `0b74d410`, wheel SHA-256 `e3fcc769…` (CI1 P2) |
| Core workflow | `.github/workflows/mneme-trusted-gate.yml` (R0 S3, required since S5) |
| C4 records | Gate 0 charter #676, Gate 1 #677, freeze #678, Gate 2 #680, Gate 3 #681, closure #682 |
| CI1 | contract fixtures `tests/fixtures/ci1_contract/` (CI1.2), gate-weakening threat model (`docs/plans/2026-10-19-ci1-gate-weakening-threat-model.md`), CI1.4 #564 |
| C4 fixtures | `tests/fixtures/adr033_c4_ci/v1/` |
| R0 | S7 closure §5 (#742), operating-status decision (#743), install guide (#744), reproducibility record (#745) |
| Layer 1 freeze | `docs/architecture/layer1-freeze-e73ff7d.md`, C4 amendment and R0 amendments |
| Platform behavior | official documentation only: docs.gitlab.com, jenkins.io / plugins.jenkins.io, learn.microsoft.com (URLs in §5) |

Platform claims were checked against the documentation on 2026-11-03.
Anything the documentation did not state is marked **not documented** and
treated as unverified.

## 3. E1: architecture-to-implementation traceability matrix

| # | Requirement | Source | Implementation | Evidence | Portability |
|---|---|---|---|---|---|
| T1 | One engine, one machine contract: `mneme check --json`, `mneme.check/v1` | CI1 fixtures README; ADR-033 §2 | `evaluator_command` (l.363), `classify_payload` (l.272) | CI1 contract 123 passed; Gate 2 | **Shared.** The fixtures README already requires any adapter (GitHub, GitLab, Jenkins) to reproduce the corpora |
| T2 | Trust a result only if payload, exit code and mode cohere; absent `evaluation_complete` is never complete | ADR-033 §2; C4 A2/A4 | `classify_payload`; `EXIT_CODES_BY_MODE` | 53 payload cases (Gate 2) | **Shared** |
| T3 | Literal-tier, query-independent rules; fixed query keeps PR text out | ADR-017; CI1.1 S7 | `QUERY` (l.71) | CI1 replay; R0 (ADR-005 rule) | **Shared** |
| T4 | ADR-020 applicability APPLIED / EXCLUDED / UNKNOWN; UNKNOWN is operational | ADR-020; ADR-029 §2 | evaluator; `applicability_outcomes` (evidence only); UNKNOWN → UNEVALUATED | CI1 `path_scoped_forbid_literal/v1` | **Shared** |
| T5 | ADR-034 numeric / `subject` records are outside the adapter contract | ADR-034; C4 closure §7 | `classify_payload` → UNEVALUATED | `payload_cases.json` | **Shared**; coverage limit carried forward |
| T6 | Decision memory read from the trusted base revision only | ADR-033 §5; ADR-031 (canonical authority); ADR-030 (version identity) | `read_memory` from base blob (l.255) | Gate 3; R0 S3-S6 | **Git-based.** Needs a platform that yields a trusted base SHA |
| T7 | PR content read as git blobs, never checked out or executed | ADR-033 §5; CI1 threat model P5 | `changed_entries`, `write_exclusive`; workflow "fetch head as objects" | Gate 3; V5 | **Git-based** in the adapter; **platform-specific** in the wrapper (who checks out what) |
| T8 | Refuse `.mneme/` and the gate's trusted surface under every posture | ADR-033 §5; C4 A1 | `path_refusal` (l.181); `BASE_SURFACE_*` (l.78-79); `--trusted-surface` | L4 (405); O8/O9 | **Shared logic, platform-specific surface list** (§4, G-3) |
| T9 | Aggregate REFUSED > strict VIOLATION > UNEVALUATED > WARN > PASS; SKIP-only is SKIP | C4 A2, R1 | `aggregate` (l.392) | Gate 2 matrix | **Shared** |
| T10 | Strict/warn violation mode is a trusted constant, not PR-controlled | ADR-033 §1; C4 R2 | `VIOLATION_MODE` workflow constant | AC5 | **Platform-specific** (where the constant lives) |
| T11 | Posture `open`/`closed` set by administrators; missing or invalid means `closed` | ADR-033 §5; C4 A3 | `resolve_posture` (l.102) reads env `MNEME_CI_AVAILABILITY` | L2/L3; AC2 | **Logic shared; source platform-specific** (GitHub `vars`) |
| T12 | `open` UNEVALUATED must be visible and never a verified PASS | ADR-033 §5 | `annotations_for` (l.432) `::warning::`; `summary_markdown`; `verify_report` check (l.612-616) | L3 | **GitHub-specific** (G-2) |
| T13 | Trusted decision step never trusts the adapter's exit code alone | C4 Gate 1 §4 | `verify_report` (l.572) | AC8 | **Shared** (apart from T12's string check) |
| T14 | Evaluator and adapter pins checked before execution | C4 A5; CI1 P2 | workflow steps "Rebuild the evaluator wheel…", "Verify the adapter pins…" | AC5; #745 3/3 | **Platform-specific wrapper; values shared** |
| T15 | Revision and subject identity in the report | ADR-029 §2 dims 1-2 | report `base_sha`, `head_sha`, `merge_base`, per-file SHA-256, adapter and evaluator identity | C4 closure §5 | **Shared fields; values come from the platform** (§6, G-5) |
| T16 | Required check blocks the merge; host actually refuses | ADR-033 §5; ADR-022 | GitHub ruleset `mneme-ci-gate` + `main-pr-only` | L2/L4/L5 405; R0 S5/S6 | **Platform-specific** |
| T17 | Main reached only through a reviewed PR / squash | ADR-022 | GitHub ruleset; local pre-push hook | R0 | **Platform-specific.** ADR-022 names the GitHub ruleset as authority; a lab on another host needs its own equivalent, not an ADR change |
| T18 | Administrative trust is the root (P7/P8) | ADR-033 §5; R0 R6 | out of band | R0 §5 | **Platform-specific**; R6 not closed anywhere |
| T19 | CI is a merge boundary, not pre-write prevention | ADR-021; ADR-033 §5-6 | n/a | n/a | **Shared** statement |
| T20 | Evidence: ADR-029 "relevant enforcement observed" is not claimed | ADR-029; C4 closure §5 | adapter-recorded provenance joined to host records | C4 closure §5 | **Shared limit**; the joins (check run → artifact) are platform-specific |

## 4. E2: shared versus platform-specific inventory

### 4.1 Platform-independent evaluation and policy logic (reusable unmodified)

`classify_payload`, `applicability_outcomes`, `evaluator_command`,
`evaluate_file`, `clean_env`, `aggregate`, `disposition`, `summarize`,
`_reason`, `resolve_posture` (logic), `verify_report` (all checks except the
`open` annotation check), the `mneme.c4.gate-report/v1` schema, the
`mneme.check/v1` contract, the six file classes and six aggregates, and the
CI1 and C4 fixture corpora. Nothing here reads a GitHub variable or API.

### 4.2 Git-based revision and trusted-input handling (reusable, needs trusted inputs)

`git`, `parse_raw_diff`, `changed_entries` (merge-base..head, `--no-renames`),
`path_problem`, `path_refusal`, `classify_entries`, `_ensure_dirs`,
`write_exclusive`, `read_memory`, `run_gate`, `_evaluate_pending`. They need
exactly three things from the platform:

1. a local repository whose checked-out commit is the trusted base;
2. the change's head commit present as objects;
3. a base SHA and head SHA the change author cannot choose.

How each platform supplies them is §5's question.

### 4.3 GitHub-specific reporting, configuration and merge controls

| Item | Where | Effect off GitHub |
|---|---|---|
| `::error` / `::warning` workflow commands | `annotations_for`, `_cmd_*` | printed to the log as plain text; no annotation |
| `verify_report` requires a `::warning` line with `UNEVALUATED` for `open` success | l.612-614 | still satisfiable (the string is in the report), but it no longer proves visibility (G-2) |
| `--summary` help text names `$GITHUB_STEP_SUMMARY` | l.703 | optional; any file path works |
| Report `posture.source` is the literal `vars.MNEME_CI_AVAILABILITY` | `resolve_posture` | provenance label is wrong off GitHub even when the value is right (G-4) |
| `BASE_SURFACE_DIRS = (".github/",)` always refused | l.79 | harmless over-refusal elsewhere; the platform's own definition file is **not** protected unless passed with `--trusted-surface` (G-3) |
| `_escape_command` | l.423 | GitHub command escaping; harmless elsewhere |
| Whole workflow wrapper | `mneme-trusted-gate.yml` | must be rewritten per platform: trigger, base checkout and `GITHUB_SHA` check, `refs/pull/N/head` fetch and race check, evaluator rebuild, adapter pin check, artifact upload, decision step |
| Check identity, required check, bypass actor, `main-pr-only` | rulesets `mneme-ci-gate`, `main-pr-only` | no equivalent object; per-platform merge controls |

### 4.4 Components needing a new architectural decision

- **Visible `open` UNEVALUATED on a non-GitHub host** (G-2). Either a
  platform-neutral visibility contract for ADR-033 §5 or a per-platform
  rendering rule. Avoided by limiting the experiment to `closed`.
- **Check identity.** GitHub pins the required check by integration ID. Other
  platforms bind "a pipeline must succeed" to the pipeline, not to a named
  check (§5). Whether that is equivalent for the same-name look-alike risk
  (CI1 threat model §1.4, last row) needs a ruling per platform.
- **Merged-result revisions** (G-5). Some platforms test a synthetic merge
  commit. The adapter's `head_sha` must be the change's own head; which SHA
  feeds which argument is a design decision, not a configuration detail.

None of these changes `mneme.check/v1`, the decision schema, retrieval or
conflict detection, or the canonical decision authority.

## 5. E3: platform trust and capability comparison

GitHub (Core, R0) is the baseline. "Not documented" means the official
documentation did not state it; it is a question for a lab, not an answer.

### 5.1 Comparison

| Dimension | GitHub (baseline, evidenced) | GitLab CI/CD | Jenkins | Azure DevOps |
|---|---|---|---|---|
| **Default definition source** | `pull_request_target`: base branch | MR pipelines run the **source branch** configuration | Same-repo PR: the **PR's** Jenkinsfile, always trusted. Fork PR: per Trust setting | Build validation runs the **merge commit's** YAML; the PR can override target behavior |
| **Trusted-definition mechanism** | built in | Free+: CI/CD configuration file in another project (`file@group/project`, optional ref). Ultimate: pipeline execution policies (policy jobs, non-overridable variables). Compliance pipelines deprecated | Remote Jenkinsfile Provider; Pipeline from SCM in a separate repo; Templating Engine (up for adoption, past sandbox advisory); trusted global libraries. Fork Trust "Nobody" protects the Jenkinsfile only, not files it calls | Validation pipeline whose YAML is in another repository, or a classic pipeline; `extends` + Required-template check on a protected resource the gate stage uses (check does not cover runs that use no protected resource) |
| **Merge blocking** | ruleset required check, pinned to integration 15368 | "Pipelines must succeed" (all tiers; Maintainer/Owner setting; needs a successful pipeline to exist; skipped counts only if ticked). External status checks: Ultimate | **Not a repository host.** Blocking is done by the SCM host consuming a Jenkins status or check (e.g. a GitHub ruleset) | Branch policy: Required build validation (with expiration), or Required status check with an Authorized identity |
| **Check identity / spoofing** | integration pin; any Actions workflow shares it (CI1 V6/V7), mitigated by refusing `.github/` | pipeline-level, no named-check pin | any Jenkinsfile that runs can `publishChecks` with any name and `SUCCESS` through Jenkins's own App | Authorized identity on status policy; build validation bound to a pipeline definition |
| **Same-repo vs fork** | same-repo observed; fork unobserved after 2026-11-02 | fork MR pipelines run **in the fork with the fork's config** by default; running in the parent uses the fork's config with parent resources after a member confirms (no warning via API or `/rebase`); Owners can disable | same-repo always trusted; fork trust configurable | Azure Repos forks: same organization, built like same-repo PRs. GitHub-hosted: fork builds and secrets settings |
| **First-time contributors** | GitHub approval setting; unobserved on Core | **not documented** | none; nearest is comment-triggered builds or fork trust "Nobody" | GitHub-hosted only: "Require a team member's comment before building" |
| **Admin / R6 exposure** | admins and admin-token agents can change rulesets, variable, workflow; owner is bypass actor | Maintainer/Owner set config path, merge checks, protected branches, variables; can unprotect `main`; whether they can merge past a failed pipeline is **not documented** | Overall/Administer (Script Console); Job/Configure and Run/Replay can rewrite the gate for a run | Project Administrators and Edit policies; bypass permissions explicit, no default holder; bypass audit event (Services, preview, Entra-backed) |
| **Admin-only posture** | repository variable, admin-only | project variable (Maintainer to edit); pipeline-variable override limited by minimum role (default `no_one_allowed` on new GitLab.com namespaces); protected variables do not reach unprotected MR pipelines | any running Jenkinsfile can read and override environment for its run | **PR YAML overrides UI variables**; the posture must live in a definition the PR cannot edit |
| **Revision binding** | `GITHUB_SHA` base; `pull_request.head.sha` head | detached MR pipeline tests source contents; source and target SHAs populated **only** in merged-results pipelines; `CI_MERGE_REQUEST_DIFF_BASE_SHA` available | merge or head strategy; no documented base-SHA variable | `Build.SourceVersion` is the merge commit; `System.PullRequest.SourceCommitId` is the head; **no target-SHA variable** |
| **Visible warning (for `open`)** | `::warning::` annotation + job summary | `allow_failure` warning state (orange) | Checks annotations / NEUTRAL; UNSTABLE mapping not documented | `task.logissue` warning; SucceededWithIssues; whether partial success satisfies a Required build is not documented |
| **Typed-rule coverage** | literal-tier only (pinned evaluator) | same: coverage is set by the evaluator pin, not the platform | same | same |
| **Tier / hosting** | GitHub.com, rulesets | Free sufficient for external config; Ultimate for policies; GitLab.com, Self-Managed, Dedicated | self-hosted controller (CloudBees commercial) plus an SCM host | Services: 5 Basic users free, 1 free parallel job (hosted needs billing link). Server: no free tier |
| **Can an ordinary contributor weaken the gate?** | no, by trusted surface refusal + base definition (evidenced, same-repo) | Free external config: **plausibly no** for same-project MRs (override behavior not documented); forks **unknown** | **yes** for same-repo branches unless the definition is moved out of the repo and Replay/Configure are restricted | **yes** by default; plausibly no with an out-of-repo definition plus the template-check chain |

### 5.2 GitLab notes

- Default MR pipelines "run on the contents of the source branch only and
  ignore the content of the target branch":
  <https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/>.
- External CI configuration file (all tiers), read from the other project's
  default branch unless a ref is given; the docs advise hosting it where only
  trusted users can write: <https://docs.gitlab.com/ci/pipelines/settings/>.
  **Not documented:** whether the source branch can still influence the
  pipeline, and which role can change the setting.
- Pipeline execution policies (Ultimate):
  <https://docs.gitlab.com/user/application_security/policies/pipeline_execution_policies/>.
  The merge check requiring the policy pipeline is marked Experiment.
- Compliance pipelines (deprecated):
  <https://docs.gitlab.com/user/compliance/compliance_pipelines/>.
- "Pipelines must succeed" and the older-successful-pipeline caveat:
  <https://docs.gitlab.com/user/project/merge_requests/auto_merge/>.
- External status checks (Ultimate):
  <https://docs.gitlab.com/user/project/merge_requests/status_checks/>.
- Protected branches and "Allowed to push and merge":
  <https://docs.gitlab.com/user/project/repository/branches/protected/>.
- Variables, protected variables and the pipeline-variable minimum role:
  <https://docs.gitlab.com/ci/variables/>.
- Merged-results pipelines and predefined variables:
  <https://docs.gitlab.com/ci/pipelines/merged_results_pipelines/>,
  <https://docs.gitlab.com/ci/variables/predefined_variables/>.
- `allow_failure` warning state: <https://docs.gitlab.com/ci/yaml/>.

### 5.3 Jenkins notes

- Same-repository PRs are always trusted and run their own Jenkinsfile; fork
  trust ("Nobody" … "Everyone") falls back to the base Jenkinsfile only:
  <https://plugins.jenkins.io/github-branch-source/>. Detail is from the
  plugin source (`ForkPullRequestDiscoveryTrait`, `getTrustedRevision`),
  not from jenkins.io prose; scripts the Jenkinsfile calls still come from
  the PR (Jenkins issue JENKINS-53753, supporting only).
- Remote Jenkinsfile Provider: <https://plugins.jenkins.io/remote-file/>.
  Templating Engine: <https://plugins.jenkins.io/templating-engine/>.
- Shared-library trust and the sandbox:
  <https://www.jenkins.io/doc/book/pipeline/shared-libraries/>,
  <https://www.jenkins.io/doc/book/managing/script-approval/>.
- Checks publishing and arbitrary check names:
  <https://plugins.jenkins.io/github-checks/>,
  <https://www.jenkins.io/doc/pipeline/steps/checks-api/>.
- Permissions including Run/Replay:
  <https://www.jenkins.io/doc/book/security/access-control/permissions/>,
  <https://www.jenkins.io/doc/book/pipeline/development/>.
- Merge blocking stays with the host, for example GitHub's required check
  bound to an app:
  <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets>.

### 5.4 Azure DevOps notes

- PR builds use the merged YAML; source-branch YAML can override target
  behavior: <https://learn.microsoft.com/azure/devops/pipelines/repos/azure-repos-git>,
  <https://learn.microsoft.com/azure/devops/pipelines/repos/github>,
  <https://learn.microsoft.com/azure/devops/pipelines/security/misc>.
- Checks and required templates:
  <https://learn.microsoft.com/azure/devops/pipelines/process/approvals>,
  <https://learn.microsoft.com/azure/devops/pipelines/security/templates>.
  Server support for these checks is unclear in the docs.
- Pipeline in another repository:
  <https://learn.microsoft.com/azure/devops/pipelines/repos/multi-repo-checkout>.
  **Not verified:** which YAML version runs for a PR-triggered cross-repo run.
- Branch policies, status policies, bypass permissions and audit:
  <https://learn.microsoft.com/azure/devops/repos/git/branch-policies>,
  <https://learn.microsoft.com/azure/devops/repos/git/pr-status-policy>,
  <https://learn.microsoft.com/azure/devops/organizations/security/default-git-permissions>,
  <https://learn.microsoft.com/azure/devops/organizations/audit/auditing-events>.
- Variable precedence: <https://learn.microsoft.com/azure/devops/pipelines/process/variables>.
- PR variables: <https://learn.microsoft.com/azure/devops/pipelines/build/variables>.
- Logging commands: <https://learn.microsoft.com/azure/devops/pipelines/scripts/logging-commands>.
- Licensing: <https://learn.microsoft.com/azure/devops/pipelines/licensing/concurrent-jobs>.

## 6. E4: outstanding gaps and limitations

### 6.1 Contract gaps

| # | Gap | Severity | Disposition |
|---|---|---|---|
| G-1 | **The trusted definition is not the default anywhere else.** GitLab, Jenkins and Azure DevOps all run the change's own pipeline definition unless something pins it elsewhere (§5). The pinning mechanism must be part of the trust claim and tested, not assumed | Critical | §7 case 4 |
| G-2 | **`open` visibility is GitHub-rendered.** ADR-033 §5 needs `open` UNEVALUATED to be visible; the adapter's `::warning::` line is only rendered by GitHub, and `verify_report` checks for the string, not for visibility | High for `open`; none for `closed` | Experiment limited to `closed`. Any `open` support needs a separate decision (§4.4) |
| G-3 | **The platform's own definition file is not on the base surface.** `BASE_SURFACE_DIRS` is `.github/` only. `.gitlab-ci.yml`, `Jenkinsfile` or `azure-pipelines.yml` are refused only if passed with `--trusted-surface` | High | Configuration, no code: the charter passes them. Where the definition lives outside the repository, the refusal is defense in depth |
| G-4 | **Posture provenance label.** `posture.source` is always `vars.MNEME_CI_AVAILABILITY` | Low (evidence accuracy) | Record the real source in the evidence; no adapter change for the experiment |
| G-5 | **Revision binding differs.** GitHub gives base (`GITHUB_SHA`) and head explicitly. GitLab populates source and target SHAs only in merged-results pipelines; Azure tests a merge commit and exposes no target SHA. The wrapper must derive the base itself from the target branch, and must pass the change's own head, never a synthetic merge commit, as `--head-sha` | High | Charter fixes the derivation and records it per run |
| G-6 | **Default checkout of untrusted content.** GitHub's wrapper checks out the base; GitLab and Azure runners check out the change's tree by default | High | Charter disables the default checkout; the job clones the base itself |
| G-7 | **Merge-check semantics differ.** GitLab "Pipelines must succeed" needs a successful pipeline to exist, and the docs warn an older successful pipeline can allow a merge after a newer one fails. Azure's required build has expiration settings. Neither is a named check pinned to an app identity | High | Charter case 6 and race notes; check-identity ruling in §4.4 |
| G-8 | **Admin-held variables are not equally protected.** On Azure, pipeline YAML overrides UI variables, so the posture must come from a definition the change cannot edit. On GitLab, project variables need Maintainer, and pipeline-variable overrides are role-limited | Medium | Charter sets and evidences the override role |

### 6.2 Security risks and unproven guarantees

- **Forks (case 5).** GitLab fork MR pipelines run in the fork with the fork's
  configuration by default. Whether such a pipeline can satisfy the parent's
  "Pipelines must succeed" check, and whether the parent's external
  definition setting applies, is **not documented**. This is the
  highest-risk unknown and may be a bypass. Azure Repos forks behave like
  same-repository PRs (same organization only). Jenkins: §5.3.
- **First-time contributors.** No GitLab analogue of GitHub's first-time
  approval is documented. Azure has "Require a team member's comment" for
  GitHub-hosted repositories only. On GitHub itself this path is unobserved
  (R0 §5), so no platform can be shown equivalent to GitHub on it.
- **R6 / P7-P8 everywhere.** Every platform has roles (GitLab Maintainer and
  Owner, Azure Project Administrators, Jenkins Overall/Administer) that can
  move the definition, drop the merge check, change the posture or grant
  bypass. No platform closes R6; the experiment must use a non-admin
  contributor and must not claim administrator resistance.
- **Administrator merge override.** Whether a GitLab Maintainer can merge
  past a failed pipeline is not documented; Azure bypass permissions are
  explicit and default to no holder.
- **Tier dependence.** GitLab's strongest pinning (pipeline execution
  policies) and approval-policy bypass controls are Ultimate. The Free-tier
  mechanism (external CI configuration file) is documented but thin on
  override behavior.
- **Same-name look-alike.** CI1 threat model §1.4, last row: untested on
  GitHub; on GitLab and Azure the merge check binds to the whole pipeline or
  build, which changes but does not remove the question.
- **Unchanged limits.** Literal-tier coverage only; ADR-034 numeric and
  `subject` payloads are UNEVALUATED; ADR-029 relevant enforcement not
  claimed; merge races, runner outages and posture fallback not exercised
  live; decision step shares code with the evaluation step (C4 closure §7).

## 7. E5: recommended experiment charter (proposal)

### 7.1 Candidate and why

**GitLab.com, Free tier, one isolated lab group.** Of the three:

- **GitLab** is a repository host, so cases 4-6 are tested on one system. Its
  Free tier has a documented way to hold the definition outside the
  repository the change edits (the external CI configuration file), the
  closest match to `pull_request_target`.
- **Azure DevOps** can pin the definition only through a chain (a pipeline
  defined in another repository or the classic UI, `extends`, and a required
  template check on a protected resource), and a PR's YAML overrides UI
  variables. More moving parts, more to authorize.
- **Jenkins** is not a repository host: merge rejection would be done by a
  second system (for example GitHub) consuming a Jenkins status. That adds a
  trust boundary and makes case 6 a test of that host again, not of Jenkins.

If case 5 or the Free-tier pinning fails, the fallback is a separate charter
for GitLab pipeline execution policies (Ultimate), not a different platform.

### 7.2 Fixed inputs (unchanged pins)

- Adapter `c51729f7`, blob `5feedf60`, SHA-256 `afe1d69c…`, run unmodified.
- Evaluator `0b74d410`, wheel SHA-256 `e3fcc769…`, hash-locked dependencies
  as in Core's workflow.
- Violation mode `strict` as a constant of the trusted definition.
- Posture `closed` only.
- Decision memory and corpus: CI1 `path_scoped_forbid_literal/v1` (ADR-901,
  a forbidden literal scoped to `docs/**`), as in the CI1 and C4 labs.
- `--trusted-surface` adds `.gitlab-ci.yml` and any directory the trusted
  definition reads from the lab repository (none planned).

### 7.3 Lab design (to be authorized, not built)

- A new private group with two projects: `gate-config` (holds the trusted
  definition; only the owner can write) and `lab` (the target repository).
- `lab` settings: CI/CD configuration file set to the `gate-config` file at a
  pinned ref; "Pipelines must succeed" on; "Skipped pipelines are considered
  successful" off; `main` protected with push "No one" and merge
  "Developers + Maintainers"; project variable
  `MNEME_CI_AVAILABILITY=closed`; minimum role for pipeline variables
  `no_one_allowed`; no merged-results pipelines, no merge trains.
- Trusted job: default checkout disabled; the job clones `lab`, takes the
  target branch tip as the base SHA, fetches the MR source commit as objects
  only, checks that it equals the MR's source head, then runs the same
  evaluator-rebuild, adapter-pin, `evaluate` and `verify-report` steps as
  Core's workflow. Report kept as a job artifact.
- Accounts: the owner, and one contributor with Developer role and no other
  rights. Creating the contributor account is the owner's action. Every
  merge attempt is made by the contributor.
- Before and after snapshots of every setting above (API GET), restore at
  the end, then archive the group.

### 7.4 Validation cases

Each case is judged on its own. A case that is not run, or whose result is
ambiguous, stays **unverified**; no case's result is inferred from another.

| # | Case | Change (contributor MR) | Expected gate | Expected host | Pass criterion |
|---|---|---|---|---|---|
| V1 | Compliant change | `docs/` file without the literal | PASS → success | merge accepted | pipeline from the trusted definition succeeds; head-pinned merge by contributor accepted |
| V2 | Architectural violation | `docs/` file with the ADR-901 literal | VIOLATION → failure | merge refused | report names ADR-901 rule, APPLIED, FAIL; merge refused |
| V3 | Incomplete evaluation | symlink under `docs/` (as C4 L2) | UNEVALUATED → failure under `closed` | merge refused | report states UNEVALUATED and reason, never PASS; merge refused |
| V4 | Same-repository pipeline weakening | (a) add or edit `.gitlab-ci.yml` with an always-pass job; (b) contributor tries to change the CI config path, merge checks or posture; (c) contributor runs a pipeline overriding `MNEME_CI_AVAILABILITY` | (a) trusted definition runs and REFUSES the change; (b), (c) not permitted | merge refused for (a) | MR's own file never defines the gating pipeline; (b) and (c) refused by role; merge refused |
| V5 | Fork-based pipeline weakening | contributor forks `lab` into their namespace, edits `.gitlab-ci.yml` to always pass, opens MR to `lab` | not decided in advance | merge refused | no fork-controlled pipeline satisfies the merge check; record where every pipeline ran, with which configuration |
| V6 | Host-side merge rejection | the V2-V5 refusals, plus V1 acceptance | n/a | as above | raw merge API responses and `detailed_merge_status` for each attempt; the refusal comes from the host, not from the contributor declining to merge |

V6 is evidenced only by actual merge attempts. If any refusal depends on a
setting the contributor could change, V6 fails for that case.

### 7.5 Evidence requirements

Pins (adapter blob and SHA-256, evaluator commit and wheel SHA-256,
`gate-config` commit at the pinned ref); settings snapshots before, during and
after; contributor role proof; for each case the MR, pipeline and job IDs,
the project the pipeline ran in and the configuration source it used, the job
log, `gate-report.json`, the `verify-report` output, `detailed_merge_status`,
the raw merge request and response; an `EVIDENCE-SHA256SUMS` manifest; and an
offline replay of the CI1 corpora on the lab runner image, showing the same
results as Gate 2. An independent read-only audit, as in C4 Gate 4, before
any results record.

### 7.6 Acceptance and stop rules

- **Experiment PASS:** V1-V4 and V6 pass with the pins in §7.2 unchanged and
  no adapter code change. V5 is reported separately as PASS, FAIL or
  unverified and never folded into the overall result.
- **Stop and report** if any case needs an adapter change, a different
  evaluator, posture `open`, a paid tier, or an admin action during a case.
  The stop is a result, not a reason to change the protocol mid-run.
- **Claim limit:** even a full PASS supports only "the C4 adapter enforced
  these cases in one GitLab Free lab under `closed`". No platform-support,
  production or ADR-029 relevant-enforcement claim, and R6 stays open.

## 8. Not authorized by this assessment

No code, adapter or workflow change; no lab, project, repository, pipeline,
ruleset, branch protection, policy, variable or permission anywhere; no live
merge attempt; no ADR or Layer 1 freeze change; no change to Core's CI; no
claim that Mneme supports GitLab, Jenkins or Azure DevOps. The §7 charter
needs separate owner approval, and any adapter change it later reveals needs
its own authorization and a new parity proof (C4 A5).

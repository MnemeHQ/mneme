---
id: ADR-033
title: "Opt-In Fail-Closed Handling for Unavailable Enforcement Evaluations"
status: proposed
priority: foundational
date: 2026-10-13
scope: enforcement.availability_policy
---

# ADR-033: Opt-In Fail-Closed Handling for Unavailable Enforcement Evaluations

**Status:** Proposed (revision 2, 2026-10-20). Authorization architecture A
chosen; CI merge-gate semantics added. No implementation authority,
implementation charter or Layer 1 amendment is conferred.
**Date:** 2026-10-13 (revised 2026-10-20)
**Deciders:** Pending review
**Charter:** none. The earlier bundled C0 charter was removed from this
proposal as stale; a bounded implementation charter is written only after this
ADR is accepted, under the Layer 1 freeze procedure.
**Verdict-trust prerequisite:** [#260](https://github.com/MnemeHQ/mneme/issues/260),
resolved by merged PR #484 (`60b02af3`).

## Context and verified baseline

The current CLI returns `mneme.check/v1` with a `verdict` (`PASS|WARN|FAIL`),
`mode` (`strict|warn`), `evaluation_complete`, applicability traces and
violations. `mneme check --json` uses exit 0/1/2 for complete strict
PASS/WARN/FAIL, 0 for complete warn-mode results, and exit 2 for incomplete
applicability. Exit 2 also reports input errors such as missing files or bad
paths, with no payload (`mneme/cli.py`). An exit code alone therefore cannot
distinguish a violation from a failure.

PR #484 made the Claude Code hook validate process exit, requested mode,
verdict and payload together. **It did not introduce availability blocking:**
checker launch errors, timeouts, malformed output, incomplete applicability
and missing memory remain fail-open or skip at the shipped consumer
boundaries (DG1F blocking-semantics matrix). These conditions are **not
architectural violations**.

ADR-017 keeps retrieval separate from deterministic enforcement. ADR-018 limits
the direct edit gate to introduced content. ADR-020 owns typed-rule path
applicability (`APPLIED|EXCLUDED|UNKNOWN`). ADR-021 defines prevent → catch →
verify, with CI as the verify stage, and rejects guessing arbitrary shell
effects; Stop is post-mutation, not pre-write. ADR-023/030/031 preserve
canonical decision authority and lineage. ADR-029 distinguishes execution
observed from relevant enforcement observed. None of these allow inventing an
authoritative PASS or violation from an unavailable check.

The Layer 1 freeze forbids enforcement behavior changes without an explicit,
independent charter amendment.

Two consumers of the check already take opposite, undocumented availability
postures:

- Core's `mneme-check.yml` is a required check name but **advisory in
  effect**: `--mode warn`, `|| true` suppresses exit 2, and missing memory
  skips the step while the job passes (DG1F G2 audit).
- The CI1 lab gate fails closed: an incoherent payload, incomplete evaluation,
  refused path or gate error is UNEVALUATED and blocks. Its source states this
  is "lab policy, not product policy" pending this ADR (CI1.4 §6.5, §7
  condition 3).

## Proposed decision

### 1. Two independent policy dimensions (all surfaces)

- **Violation mode** remains `strict|warn`, with existing semantics for
  *trusted, complete* results.
- **Availability policy** is a separate `open|closed` policy. `closed` means a
  change within the protected boundary is refused when an applicable check
  could not be completed or its result cannot be trusted, where `closed` is
  verified as authorized (§4) or configured by administrators (§5). A failure to
  evaluate is reported as **UNEVALUATED**, never as a decision violation.
- A trusted `SKIP` or non-applicable boundary remains a skip, not an evaluation
  failure. Never manufacture a PASS for a skipped or unevaluated operation.
- No new deterministic rule, retriever, selector, conflict detection, decision
  authority or evidence engine is introduced.

How the policy is selected, and its default, is surface-specific (§3 for
PreToolUse, §5 for CI).

### 2. Check-result trust is established before applying either policy (all surfaces)

Every surface reuses the #484 observation (stdout payload, process return
code, requested mode) and may not create a competing verdict parser or
reclassify incoherent output as authoritative.

A coherent complete observation requires:

- `schema == mneme.check/v1`; `verdict` exactly PASS/WARN/FAIL; `mode` exactly
  strict/warn and equal to the requested mode;
- `violations` an array of valid records; optional `freshness` and
  `applicability` arrays, when present, structurally valid;
- each violation having nonempty `decision_id`, string `decision_text`,
  `severity` exactly WARN/FAIL, nonempty `rule`, nonempty `trigger`;
- PASS with no violations; WARN with one or more WARN-only violations; FAIL
  with at least one FAIL violation;
- for **complete** evaluations, process exit agrees with the requested mode and
  verdict (strict PASS=0, WARN=1, FAIL=2; warn PASS/WARN/FAIL=0).

An **incomplete** evaluation is not checked against the complete-result exit
matrix: the CLI uses exit 2 for `evaluation_complete == false`, independently
of mode. Incompleteness is an operational condition, even if the payload
carries partial match information. A malformed or inconsistent observation is
untrusted, not a policy denial. Unknown additive JSON keys remain permissible
within v1.

Historical payloads without `evaluation_complete` need an explicit
compatibility characterization before any default changes. Under `closed`,
absence of affirmative completeness is never proof of a complete evaluation.

Implementations may model `TRUSTED_COMPLETE`, `INCOMPLETE`, `UNTRUSTED`,
`NOT_RUN`, `SKIPPED` separately from the policy verdict. These labels are
conceptual and do **not** authorize a new public JSON schema.

This ADR decides how a caller **treats** an untrusted or crashed check. It does
not change the CLI. In particular, the malformed-memory path (exit 1 with a
traceback and empty stdout, which collides with strict WARN's exit code;
CI1.4 §6.4, V9-A) stays a separate CLI-contract decision: a structured
incomplete-evaluation result with a new fixture version, or explicit
acceptance of the crash path (CI1.4 §7 condition 4).

### 3. PreToolUse surface: failure-handling matrix

Applies to Claude Code `PreToolUse` for `Edit|Write|MultiEdit` only (§6).
Availability `open` is the default for all existing installations; `closed` is
opt-in and requires the authorization in §4.

| Condition | Default availability=open | Opt-in availability=closed |
|---|---|---|
| Complete trusted PASS | Proceed | Proceed |
| Complete trusted WARN/FAIL | Existing strict/warn policy | Same strict/warn policy |
| Typed rule applicability UNKNOWN / incomplete checker | Unevaluated; proceed | Unevaluated; refuse supported write |
| Checker timeout, crash, launch error | Unevaluated; proceed | Unevaluated; refuse supported write |
| Malformed/contradictory checker observation | Unevaluated; proceed | Unevaluated; refuse supported write |
| Target cannot be reconstructed in a supported direct-file event | Unevaluated; proceed | Unevaluated; refuse supported write, if within protected boundary |
| Out-of-scope/non-mutating event or proven empty introduced delta | Existing skip | Same skip |
| No project memory in an unprotected/ordinary repository | Existing behavior | No new global block |

For partial results with a genuine matched violation **and** an incomplete
evaluation, the adapter preserves both facts and does not report the result as
fully verified. Exact precedence for a mixed partial report is characterized
and specified in the implementation charter, not guessed from an exit code.

### 4. PreToolUse surface: authorization contract (Architecture A)

#### 4.0 Architecture and threat model

This ADR adopts **Architecture A: verified Git authorization with no persistent
trusted state** (DG1F `AUTHORIZATION_UNVERIFIABLE` spec, §2 and §5.2). No host
enrollment record or other durable state outside the repository is introduced.

Threat model, using the spec's levels:

- **In scope:** ADV-0 (no adversary: network outage, accidental loss, expired
  token, shallow clone) and the part of ADV-1 that edits canonical memory or
  source files, or alters (but does not delete) the local declaration, **while
  the local declaration is present and authorization is successfully
  verified**.
- **Not guaranteed:** deletion of the local declaration or of `.mneme/` as a
  whole (spec T-01 to T-03, BP-1); edits to project host settings, including
  removing the hook or setting proxy or `MNEME_MEMORY` values through the
  project settings `env` (ADV-1 via BP-6, BP-2, T-07); ADV-2 (arbitrary shell
  as the same OS user, able to make verification unavailable, redirect it
  through git configuration, or re-initialize the repository); ADV-3 (ADV-2
  plus the developer's forge credentials); and ADV-4.

**Verification trigger.** Under Architecture A the only trigger for
authorization verification is the **presence of the local declaration**.
Nothing else (memory contents, activation state, a configured remote) starts
verification, which preserves default-open parity (§4.3). Consequently a
repository whose declaration has been deleted is indistinguishable from one
that was never enrolled.

**The guarantee, stated plainly:** fail-closed applies while the local
declaration is present and verified as authorized, when canonical memory is
then missing or altered, or the declaration is altered, replaced or rolled
back. There is **no guarantee against deletion of the declaration, removal of
the hook, or an agent able to make verification unavailable, redirect it, or
re-initialize the repository.** When authorization cannot be verified, the
hook reports the problem and proceeds (§4.3).

Architecture B (a host-scoped enrollment record outside the agent's reach)
remains a possible later hardening decision. It is not a prerequisite, is not
adopted here, and would need its own ADR decision, charter and Layer 1
amendment.

#### 4.1 Declaration, scope and existing authority (G3-B R1, R3, R5, R6)

- The policy declaration is a **small, explicit, human-issued, review-gated
  artifact under `.mneme/`**, managed by an explicit Mneme-owned authority
  operation. Issuance and revocation need human approval and a **recorded
  review event** on the protected baseline (§4.5). No agent, inference, producer, hook, environment flag or
  decision retrieval can grant or withdraw authorization.
- It binds the **intended repository identity** and the **exact effective
  memory path** within that root, as recorded at the verified baseline.
- Authorization is a **separate policy switch**, not a second decision source.
  It contains no decisions, rules, lifecycle, precedence or rule evaluation.
  ADR-030's `.mneme/project_memory.json` / `decision_index` remains the **sole
  canonical decision authority**.
- Three conditions are independent: (1) decision memory exists, (2) protection
  was **explicitly activated** through the existing `setup → active` /
  `mneme protect activate` flow, and (3) fail-closed availability was
  **explicitly authorized**. Enrollment requires verified activation evidence
  and its protection-rule binding at the verified baseline, not merely a
  committed memory file. Issuing a declaration never activates protection.
- **Memory-path mismatch (pins SS-3).** When authorization is verified as
  AUTHORIZED and the effective memory (for example via `MNEME_MEMORY` or
  parent-directory discovery) differs from the bound path, the outcome is
  "tampered without approval" (§4.4). When authorization cannot be
  verified, the binding cannot be established; the mismatch is reported
  visibly and the repository is treated as **inactive** for availability
  purposes (G3 §4.3). The deterministic check may still run against the
  effective memory, but its result is reported as **not bound to the
  authorized memory** and never as verified enforcement.
- **Memory selection is a precondition.** The binding is meaningful only if the
  hook selects memory from the edited target's repository, not from the
  payload `cwd`. T-08 showed `cwd`-based selection producing a complete,
  trusted PASS against the wrong memory. Slice 1 (#517, `2a445142`; live
  re-probe #518) fixed the payload-`cwd` case for direct writes, the only
  surface this ADR covers. It did not change `MNEME_MEMORY`, which still takes
  precedence in `find_memory`; an override pointing at other memory (T-08 V5)
  is handled only by the mismatch rule above, and only when authorization is
  verified. Other hook seams (Bash, SessionStart, Stop) still select from
  `cwd` and stay outside this contract until their T-08 slices land.
- The concrete schema, enrollment command and verifier belong to a **future
  bounded charter**, which must preserve these invariants.

#### 4.2 Verified baseline and revision selection (G3-B R2, R4, R7)

- The declaration is authoritative **only through a live verification** of an
  M4-style baseline: a protected remote Git ref and its reviewed history. A
  committed file without that verification is insufficient.
- **Mneme selects the revision** by a fixed rule (the current tip of the
  configured protected ref, read live), not an agent-supplied `--ref`, local
  branch or tag, remote-tracking ref, older commit or arbitrarily old snapshot.
  The verifier does not use local remote-tracking refs and should not use
  ambient git configuration (`insteadOf`, proxies, credential helpers) or
  project-settings environment.
- **Disclosed limit of Architecture A:** the location of the baseline (remote
  URL and ref) is read from repository configuration, which an ADV-2 agent can
  change, and no verification result is cached in trusted storage. Revision
  selection is therefore protected against ADV-0/ADV-1 only.
- When a **verified AUTHORIZED** baseline governs, corrupting, replacing or
  rolling back the local declaration, or deleting or altering canonical
  memory, cannot turn protection off. A present but invalid or mismatching
  local declaration is "tampered without approval". **Deleting** the local
  declaration removes the verification trigger and does turn protection off
  without detection (§4.0).

#### 4.3 Revocation, positive absence and unavailable verification (G3-B R8–R10)

- **Revocation** is a separate, explicit, human-reviewed authority action,
  never deletion of the local declaration. The most recent reviewed
  authorization or revocation in the verified baseline history governs. A
  later reviewed revocation supersedes earlier authorization, and vice versa.
  Timestamps and agent-controlled refs do not decide precedence.
- **Baseline deletion without revocation (pins RR-7).** A reviewed change that
  deletes the declaration at the baseline without an explicit revocation record
  is neither REVOKED nor VERIFIED_ABSENT. It is
  `AUTHORIZATION_UNVERIFIABLE` with reason `EVIDENCE_INVALID`.
- **`VERIFIED_ABSENT`** is a positive verification outcome: independent evidence
  from the baseline history that no governing authorization exists. If older
  authorization cannot be ruled out (incomplete history, unavailable
  verification), the outcome is `AUTHORIZATION_UNVERIFIABLE`, not "never
  authorized".
- **`AUTHORIZATION_UNVERIFIABLE`** is a distinct operational outcome, not `PASS`,
  `FAIL`, a rule-level `UNEVALUATED`, `VERIFIED_ABSENT` or an implicit revocation.
  Under Architecture A it means:
  - **a visible proceed, with no availability-policy refusal** (a refusal could
    only be keyed on agent-controlled inputs, which §4 excludes as authority);
  - a reason code from a closed set: `NETWORK`, `DNS`,
    `TLS_IDENTITY_MISMATCH`, `AUTH`, `TIMEOUT`, `VERIFIER_CRASH`,
    `REF_MISSING`, `HISTORY_INCOMPLETE`, `EVIDENCE_INVALID`,
    `VERIFIER_CONFIG_MISSING`. `ROLLBACK_DETECTED` and `CLOCK_REGRESSION`
    are reserved: detecting them needs a trusted high-water mark, which only
    Architecture B keeps;
  - the existing deterministic check **still runs** when memory is present; a
    trusted complete strict `FAIL` still blocks with today's semantics;
  - the diagnostic reaches a host-visible channel, does not echo submitted
    content, and is never counted as relevant enforcement observed (ADR-029).
- While the local declaration is present, a repository whose verification
  becomes unavailable does **not revert silently**: each non-refusing proceed
  is reported. If the declaration is deleted there is no trigger and nothing
  is reported; Architecture A keeps no trusted record that the repository was
  ever enrolled (§4.0, BP-1).
- A repository with no configured verifiable baseline is **not eligible** for
  `closed`. Because this is read from repository configuration, it is a
  configuration fact, not an adversarial guarantee.
- **Default-open parity:** a repository with no declaration produces output
  identical to current behavior and makes no verifier network calls.

#### 4.4 Authorization-state and missing-memory matrix

`B` is the verification result at the Mneme-selected revision; `L` is the local
declaration; `M` is canonical memory. "Refuse" applies only to the supported
mutation seam in §6.

| Verified B | Local L / memory M | Availability consequence |
|---|---|---|
| **AUTHORIZED** | Valid matching local declaration; memory present at the bound path | Existing deterministic check and strict/warn for trusted complete results. Unavailability handled per §3 `closed` column |
| **AUTHORIZED** | Declaration present and valid; memory missing | **Refuse supported mutation**: authorized missing-memory failure, operational UNEVALUATED; never a skip or rule violation |
| **AUTHORIZED** | Declaration present but invalid, replaced, rolled back or identity-mismatched, or effective memory differs from the bound path | **Refuse supported mutation**: tampered without approval. No silent downgrade |
| *(not verified)* | Declaration absent | No verification trigger (§4.0). Existing behavior, identical to a never-enrolled repository. **Disclosed limit**, not protection |
| **REVOKED** | Any | No availability-policy refusal. Existing enforcement still applies when memory exists. Stale local declarations cannot reauthorize |
| **VERIFIED_ABSENT** | Any | No availability-policy refusal. Existing enforcement runs when valid memory exists; missing memory keeps ordinary unprotected behavior |
| **AUTHORIZATION_UNVERIFIABLE** | Declaration present; any memory state | **Visible proceed** with the reason code (§4.3). Deterministic check still runs when memory is present. No fabricated PASS, no "never authorized", no claim that protection was enforced |

**Precedence:** first establish `B` and identity/activation eligibility; then
apply the local-tamper/missing-memory row; only if AUTHORIZED with intact local
policy and memory does the §3 `closed` column decide an operational refusal. A
valid, complete decision violation keeps strict/warn semantics. A local
artifact never overrides `B`.

#### 4.5 Review event

Issuance and revocation require a **review event recorded on the protected
baseline** (G3-B R1, review-gated). Mneme records the event; it cannot
mechanically verify that the approver is independent of the agent, because it
cannot tell whether the approver's credentials are reachable from the agent's
environment (spec BP-4).

A protected ref alone is therefore not review independence: Mneme's own
ruleset requires zero approvals (ADR-022), and agent and human merges are
recorded under the same identity when credentials are shared (T-08
merge-attribution caveat; spec ADV-3). The declaration **does not resist
ADV-3**. Single-developer repositories may enroll, but diagnostics and
documentation must not present their declaration as independently reviewed.

### 5. CI merge-gate surface

Applies to a CI check configured as a **required status check** that runs the
gate against the trusted base revision. It reuses §§1, 2 and 7 and the state
vocabulary unchanged. It does **not** use §4: CI authorization sits on a
different trust boundary.

- **Trusted inputs.** The gate evaluates the PR's changes against decision
  memory read from the trusted base revision, and refuses changes to
  `.mneme/` and to the gate's own trusted surface. This is proven in an
  isolated lab only (CI1.3, C1, V11 Option A; #540). This ADR makes no claim
  about Core's production CI.
- **Trusted-surface refusals are not availability states.** A refused change
  to `.mneme/` or to the gate's own trusted surface is a **policy refusal**. It
  produces a non-success conclusion under **every** posture, including `open`,
  and is reported as a refusal, not as UNEVALUATED or a rule FAIL. Otherwise an
  `open` posture would let a PR replace the inputs that judge later PRs.
- **State → check conclusion under `closed`.** A trusted complete result keeps
  strict/warn semantics. UNEVALUATED (incoherent payload, incomplete
  evaluation, crash or launch error, missing or unreadable memory at the
  trusted base, a non-regular or unmaterializable path, a gate error) produces
  a **non-success** conclusion, reported as an operational failure, never as a
  rule FAIL or as relevant enforcement observed.
- **State → check conclusion under `open`.** The conclusion may satisfy the
  required check, but the report must state UNEVALUATED and its reason and must
  never record a verified PASS. Because the host treats several non-failure
  conclusions as satisfying a required check, `open` must be an explicit,
  visible configuration, not a side effect of suppressing exit codes.
- **Authorization.** The CI posture is set by whoever controls the workflow,
  the required checks and the ruleset: **administrative trust (P7/P8)**, not a
  `.mneme/` declaration. The trusted base and ruleset take the place of §4's
  verified baseline. **This holds only where the gate's own trusted surface is
  protected from ordinary PRs** (as the C1 refusal does in the lab). Without
  that protection, CI configuration is agent-editable and is not an authority
  (G3-B M3). Where it holds, the authority to require the check sits with
  administrators rather than with repository content the agent controls, so a
  non-success on unavailability is not a refusal grounded in unverified
  authority. The Architecture A limits in §4 do not apply to CI; P7/P8 limits
  do. Administrators can change the ruleset, policy or workflow, and in a
  setup where the agent's token has administrator rights, the agent can too.
  That is outside what this ADR can constrain.
- **Existing advisory CI.** A check that suppresses exit codes or passes when
  memory is missing (Core's current `mneme-check.yml`) is an **implicit,
  undeclared `open`**: its success conclusion carries no visible UNEVALUATED,
  contrary to the `open` rule above. It is recorded as a known gap until
  reconfigured under a separate, approved change.
- **CI is not pre-write prevention.** It verifies a proposed merge; it does not
  stop an agent from writing (ADR-021).

### 6. Host boundary and supported surfaces

- **PreToolUse:** first proof is Claude Code `PreToolUse` for
  `Edit|Write|MultiEdit`, using the existing introduced-delta gate and T-08
  slice 1 target-based memory selection. Class-A reconstructable Bash
  handling may be a separately enumerated follow-up; arbitrary class-B Bash
  mutations must not be blocked on a guessed future write. No claim of
  universal interception.
- **Relationship to ADR-021.** ADR-021 makes checker transport failures fail
  open with visible diagnostics. Opt-in `closed` narrows that rule **for the
  PreToolUse direct-write surface only**, and only for authorized repositories
  (§4). ADR-021's Stop and session-delta behavior is unchanged.
- For a running hook, an operational refusal uses the documented host blocking
  transport with actionable UNEVALUATED feedback. If the hook never runs, Python
  cannot enforce anything. Host-level handling of a hook that fails to launch,
  crashes or times out (including any `onFailure`-style host setting) must be
  established by pinned live tests before any support claim. Stop cannot undo
  writes and needs a separate follow-up to ADR-021.
- A disabled or misconfigured hook, unsupported mutation surface, missing
  provider hook or unprotected checkout cannot be claimed protected.
- **CI:** §5. CI is a separate, configured verification boundary, not proof of
  pre-write interception.

### 7. Evidence, diagnostics and regression discipline (all surfaces)

- Use the existing `RuleEvaluation`, `Violation`, `EnforcementResult` and ADR-029
  trace concepts. No second enforcement or evidence engine and no model-based
  adjudication.
- Keep evaluation status and failure reason separate from the policy verdict;
  never label an operational refusal as a rule FAIL or count it as relevant
  enforcement observed.
- Diagnostics identify the failure category, boundary and remediation without
  dumping submitted source content.
- Preserve the frozen canonical benchmark fixtures and
  DecisionRetriever/ConflictDetector semantics. Add a separate deterministic
  availability-regression fixture matrix with default-open parity and opt-in
  closed cases.
- No new persistence, cloud service, telemetry or organizational policy
  management.

## Explicit non-goals

- Redefining `strict` or `warn`, changing enforcement ranking, or adding rule
  types.
- Changing the CLI's malformed-memory behavior (§2; CI1.4 §7 condition 4).
- Automatically enabling protection, upgrading canonical memory, or creating a
  parallel decision authority.
- A host enrollment record or any other trusted state outside the repository
  (Architecture B).
- Interpreting arbitrary Bash/shell commands.
- Making `Stop` a pre-write barrier, guaranteeing hooks always run, or silently
  blocking all unknown agent actions.
- Reconfiguring any CI workflow, ruleset or Actions policy.
- Broad rollout to Codex, Kiro, Cursor, Hermes, managed agents or other
  providers.
- Data Engine work, hosted services, organizational governance, or a redesigned
  public evidence schema.

## Implementation gates (not authorized by proposed or accepted status)

1. **ADR review and acceptance** as a design decision. Acceptance does not
   authorize implementation.
2. **Bounded implementation charter** and matching **`[layer1-freeze]`
   amendment**, written after acceptance. Pin baseline verification,
   enrollment and revocation design before any behavior change.
3. **Verdict consistency (done):** #484 resolved #260. Reuse its coherence
   validation; characterize historical v1 payloads and mixed-partial reporting.
4. **C2:** opt-in policy routing and verified project eligibility for
   PreToolUse, only after gates 1–3.
5. **C3 live proof (PreToolUse):** Claude Code `PreToolUse` non-mutation on
   missing memory, local declaration tamper, unverifiable baseline, crash,
   timeout, invalid or incomplete result and host-level failure. The evidence
   bar is the DG1F `AUTHORIZATION_UNVERIFIABLE` spec's U, T, RV, S and P groups
   with E1–E10, including verifier denial (T-06, T-07), substitution (T-05),
   the reverse bypass (U-10) and host-boundary probes (S-02 to S-04). Under
   Architecture A, scenarios the spec marks as bypasses are expected to show a
   **visible** proceed, or, where the declaration is deleted (T-01 to T-03), no
   trigger at all. Either result confirms a disclosed limit; neither is
   reclassified as protection. The prior G1 violation proof alone does not
   suffice.
6. **C4:** adversarial regressions, canonical benchmark parity, CI
   implementation under §5 (with its own approval under P7/P8 and the CI1
   rollout gate, CI1.4 §7 condition 9), installation and release documentation.

Every behavioral slice requires its own reviewed PR and tests; no direct writes
to `main` (ADR-022).

## Related

- Core #260 / merged PR #484: verdict coherence
- DG1F G3 missing-memory assessment and G3-B eligibility/authorization design
  (R1–R10), merged PR #512
- DG1F `AUTHORIZATION_UNVERIFIABLE` architecture comparison and adversarial spec,
  merged PR #513 (`docs/plans/2026-10-15-dg1f-authorization-unverifiable-adversarial-spec.md`)
- T-08 memory selection: evidence #513, slice 1 #517 (`2a445142`), live re-probe
  #518
- DG1F G2 CI-consumer coverage audit
- CI1 (#540): CI1.4 record, C1 and V11 Option A lab results, production-readiness
  reconciliation (#569)
- G1 pinned live Claude Code direct-write violation proof (not an
  availability-error proof)
- ADR-017/018/019/020: retrieval, introduced delta, typed-rule enforcement,
  applicability
- ADR-021: prevent/catch/verify, shell preflight and Stop claim boundaries
- ADR-022: PR/squash-only `main`
- ADR-023/029/030/031: decision identity, evidence binding, canonical
  persistence, governance
- M1.3/M1.4: setup and explicit activation
- [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)

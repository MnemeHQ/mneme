---
id: ADR-033
title: "Opt-In Fail-Closed Handling for Unavailable Enforcement Evaluations"
status: proposed
priority: foundational
date: 2026-10-13
scope: enforcement.availability_policy
---

# ADR-033: Opt-In Fail-Closed Handling for Unavailable Enforcement Evaluations

**Status:** Proposed — G3-B authorization contract reconciled for review; no implementation authority, implementation-charter acceptance, or Layer 1 amendment is conferred.
**Date:** 2026-10-13
**Deciders:** Pending review
**Charter:** [Reliable Enforcement C0](../plans/2026-10-13-reliable-enforcement-charter.md)
**Verdict-trust prerequisite:** [#260 — inconsistent checker verdicts](https://github.com/MnemeHQ/mneme/issues/260), resolved by merged PR #484 (`60b02af3`); availability-policy authorization remains separate.

## Context and verified baseline

The current CLI returns `mneme.check/v1` with a `verdict` (`PASS|WARN|FAIL`), `mode` (`strict|warn`), `evaluation_complete`, applicability traces and violations. `mneme check --json` uses exit 0/1/2 for complete strict PASS/WARN/FAIL, 0 for complete warn-mode results, and exit 2 for incomplete applicability. An exit code alone cannot distinguish violation from failure.

Before PR #484, the Claude Code hook could trust a parseable PASS despite a contradictory process exit (#260). The merged C1 verdict-consistency fix now validates the process exit, requested mode, verdict, and payload together. **It did not introduce availability blocking:** checker launch errors, timeouts, malformed output, incomplete applicability, and missing memory remain fail-open/skip at the shipped consumer boundaries (see DG1F blocking-semantics matrix). These conditions are **not architectural violations**.

ADR-017 keeps retrieval separate from deterministic enforcement. ADR-018 limits the direct edit gate to introduced content. ADR-020 owns typed-rule path applicability (`APPLIED|EXCLUDED|UNKNOWN`). ADR-021 defines prevent/catch/verify and explicitly rejects guessing arbitrary shell effects; Stop is post-mutation, not pre-write. ADR-023/030/031 preserve canonical decision authority and lineage. ADR-029 distinguishes execution observed from relevant enforcement observed. None of these allow inventing an authoritative PASS or violation from an unavailable check.

The Layer 1 charter forbids enforcement behavior changes without an explicit, independent charter amendment.

## Proposed decision

### 1. Two independent policy dimensions

- **Violation mode** remains `strict|warn`, with existing semantics for *trusted, complete* results.
- **Availability policy** is a separate, opt-in `open|closed` policy. Default is `open` for all existing installations. `closed` means an eligible protected-project mutation is refused when an applicable check could not be completed or its result cannot be trusted. A failure to evaluate is reported as **UNEVALUATED**, never as a decision violation.
- A trusted `SKIP`/non-applicable boundary remains a skip, not an evaluation failure. Never manufacture a PASS for a skipped operation.
- No new deterministic rule, retriever, selector, conflict-detection, decision authority, or evidence engine is introduced.

### 2. Check-result trust is established before applying either policy

The prerequisite verdict-trust correction was merged in PR #484 (`60b02af3`). Availability-policy work must reuse its full checker observation (stdout payload, process return code, requested mode) and may not create a competing verdict parser or reclassify incoherent outputs as authoritative.

A coherent complete observation requires:
- `schema == mneme.check/v1`; `verdict` exactly PASS/WARN/FAIL; `mode` exactly strict/warn and equal to the requested mode;
- `violations` an array of valid records; optional `freshness` and `applicability` arrays, when present, structurally valid;
- each violation having nonempty `decision_id`, string `decision_text`, `severity` exactly WARN/FAIL, nonempty `rule`, nonempty `trigger`;
- PASS with no violations; WARN with one or more WARN-only violations; FAIL with at least one FAIL violation;
- for **complete** evaluations, process exit agrees with the requested mode and verdict (strict PASS=0, WARN=1, FAIL=2; warn PASS/WARN/FAIL=0).

An **incomplete** evaluation must not be checked against the complete-result exit matrix: the current CLI uses exit 2 for `evaluation_complete == false`, independently of violation mode. Incompleteness is an operational condition, even if the payload carries partial match information. A malformed or inconsistent observation is untrusted, not a policy denial. Unknown additive JSON keys remain permissible within the v1 contract.

`evaluation_complete` is emitted by the current CLI. Historical payloads without it need an explicit compatibility characterization before changing default fail-open behavior. For opt-in `closed`, absence of affirmative completeness must not be treated as proof of a complete evaluation.

The internal implementation may model `TRUSTED_COMPLETE`, `INCOMPLETE`, `UNTRUSTED`, `NOT_RUN`, `SKIPPED` separately from the policy verdict; these labels are conceptual and do **not** authorize a new public JSON schema.

### 3. Failure-handling matrix for the initial PreToolUse slice

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

For partial results with a genuine matched violation **and** an incomplete evaluation, the adapter must preserve both facts. The complete-result verdict must not be reported as fully verified. Exact precedence for a mixed partial report must be characterized and specified in C1, not guessed from an exit code.

### 4. Project-scoped authorization contract (reconciled with G3-B)

**Architectural choice:** adopt the G3-B **M2 declaration with mandatory M4 (or an equivalent independently verified trusted baseline)**. M2 alone is not an authorization boundary. A local file, local Git index/ref/history, agent-provided revision, environment variable, activation record alone, or hook registration cannot authorize `availability=closed`. The governed agent must not solely control the authoritative baseline or its revision selection.

This section reconciles the reviewed [G3-B design](../plans/2026-10-14-dg1f-g3b-eligibility-authorization-design.md) (R1–R10). It is an **authorization decision**, not approval to ship a verifier, declaration format, hook change, or new public schema.

#### 4.1 Declaration, scope, and existing authority (R1, R3, R5, R6)

- The policy declaration is a **small, explicit, human-issued and review-gated artifact under `.mneme/`**, managed via an explicit Mneme-owned authority operation. Issuance and revocation need human approval and a verified review event. Neither an agent, inference, producer, hook, environment flag, nor decision retrieval can grant or withdraw authorization.
- It binds the **intended repository root / repository identity** and the **exact effective memory path** within that root, verified against the trusted baseline. Checkout relocation must not silently cause a different repo or a parent repo's memory to supply authority. A differing `MNEME_MEMORY`, missing expected file, or parent-directory discovery result cannot bypass the established binding; the mismatch is an operational problem, not a downgrade to “unprotected.”
- Authorization is a **separate policy switch**, not a second decision source. It contains no decision contents, authoritative rules, lifecycle, precedence, or rule evaluation. ADR-030's `.mneme/project_memory.json` / `decision_index` remains the **sole canonical decision authority** and retains its existing write discipline.
- Three conditions are independent: (1) decision memory exists, (2) protection was **explicitly activated** via the existing `setup → active` / `mneme protect activate` flow, and (3) fail-closed availability was **explicitly authorized**. Enrollment requires **verified activation evidence and its protection-rule binding at the trusted revision**, not merely a committed memory file or `activation` field. Issuing an availability declaration must not itself silently activate protection.
- The concrete schema, enrollment command, and verification adapter belong to a **future bounded charter**; they must preserve these invariants before any implementation is authorized.

#### 4.2 Independently verified baseline and revision selection (R2, R4, R7)

- The M2 declaration becomes authoritative **only through an independently verified M4-style baseline**, such as a suitably protected remote Git ref and its reviewed history (or a documented equivalent the agent cannot solely modify). A committed file **without** that independent verification is insufficient. Protection/review and verifier credentials must be outside the governed agent's unilateral control.
- **Mneme selects the trusted revision**, using an independently established ref and verifier configuration. An agent-supplied `--ref`, downgraded local branch/tag, changed remote URL, rewritten local Git history, stale checkout, or older commit cannot determine authorization or establish its absence. The selection rule must reflect the current reviewed baseline, not an arbitrarily old valid snapshot.
- The verifier binds the signed/protected provenance and reviewed event order, repository identity, expected memory path, declaration contents, and activation evidence. An invalid/unreachable baseline is **not** the same as an absent local declaration.
- When a **verified authorized baseline** governs, deleting, corrupting, replacing, or rolling back local `.mneme/` policy or canonical memory cannot turn protection off. An invalid, mismatching, or missing **local** declaration is “removed/tampered without approval”; the verified baseline still governs.

#### 4.3 Revocation, positive absence, and unavailable verification (R8–R10)

- **Revocation is a separate explicit, human-reviewed authority action**, never deletion of the local declaration. The **most recently reviewed authorization or revocation in independently verified baseline history** governs at the Mneme-selected revision. A later reviewed revocation supersedes earlier authorization; a later reviewed authorization supersedes revocation. Timestamps and agent-controlled refs do not decide precedence.
- **`VERIFIED_ABSENT` is a positive verification outcome**, not a default when a file is missing. It requires independent evidence from the trusted baseline/history that **no governing authorization** exists. If older authorization cannot be ruled out because history is incomplete or verification is unavailable, the outcome is **`AUTHORIZATION_UNVERIFIABLE`**, not “never authorized.”
- **`AUTHORIZATION_UNVERIFIABLE` is a distinct operational error**, not `PASS`, `FAIL`, `UNEVALUATED` as a rule violation, `VERIFIED_ABSENT`, or an implicit revocation. Its reason must be exposed to the caller; no adapter may quietly convert it to “never protected,” claim an authoritative PASS, or claim a verified fail-closed guarantee. It **cannot itself authorize a fail-closed policy block** based on unverified authority. Any host-level operational refusal on this state must be specified and proven separately from architectural violation blocking before a prevention claim.
- **Local-only repositories without an agent-independent baseline cannot enroll in verified `closed` protection.** This is **ineligible / no protection guarantee**, not evidence that a previously authorized repository was never authorized. A once-enrolled repository whose verifier later becomes unavailable reports `AUTHORIZATION_UNVERIFIABLE`; it does not silently revert to `open`.

#### 4.4 Authorization-state and missing-memory matrix

Here `B` is the independently verified result at the **Mneme-selected** revision; `L` is the local declaration; `M` is canonical memory. “Refuse” below applies only to an **in-scope, supported mutation seam**; it does not imply hooks always run, shell class-B pre-write coverage, Stop-time prevention, or CI coverage.

| Verified B | Local L / memory M | Availability consequence |
|---|---|---|
| **AUTHORIZED** | Valid matching local declaration; memory present | Existing deterministic check and `strict|warn` for trusted complete results. Opt-in `closed` handles unavailability separately per §3. |
| **AUTHORIZED** | Memory missing (whether local declaration present or absent) | **Refuse supported mutation — authorized missing-memory failure**, operational `UNEVALUATED`; never a skip or rule violation. |
| **AUTHORIZED** | Local declaration absent, invalid, replaced, rolled back or identity-mismatched (memory present or missing) | **Refuse supported mutation — removed/tampered without approval**, even if memory remains. No silent downgrade. |
| **REVOKED** | Any local declaration and either memory state | **No availability-policy refusal**. Reviewed revocation governs; existing trustworthy enforcement still applies when memory exists. Stale local declarations cannot reauthorize. |
| **VERIFIED_ABSENT** | No authenticated authorization; any local declaration and either memory state | **No availability-policy refusal**. Existing enforcement can run when valid memory exists; missing memory keeps the ordinary unprotected behavior. An untrusted local declaration never activates `closed`. |
| **AUTHORIZATION_UNVERIFIABLE** | Any local or memory state; trusted baseline invalid, incomplete or unreachable | **Explicit authorization-verification operational error.** No fabricated PASS, no “never authorized,” no claim that protection was enforced, and no silent policy-based refusal from an unverifiable authorization. |

**Precedence:** first independently establish `B` and identity/activation eligibility; then apply the local-tamper/missing-memory outcome; only if **AUTHORIZED** with intact local policy and memory can the §3 checker-evaluation availability matrix decide an operational `closed` refusal. A valid, complete decision violation continues to use existing `strict|warn` semantics, not an authorization-error verdict. A local artifact may never override `B`.

#### 4.5 Guarantee boundary and downstream gates

This authorization contract resolves **who may authorize** a fail-closed posture and **what trusted evidence governs** it. It does **not** prove that a host prevents the write when an operational error occurs. G1 live evidence establishes a Claude Code 2.1.202 **decision-violation** block on one direct-write surface, not missing-memory/availability-error blocking or command-hook launch-failure handling. The latter requires distinct pinned live probes, including unchanged-file assertions and actionable diagnostics.

No `closed` opt-in may be enabled by default or inferred globally; the default remains `open`. Existing unprotected repos keep current behavior. No new canonical authority, standalone hosted service, retrieval/enforcer change, generalized shell interpreter, or widened host-support claim is authorized.

### 5. Host boundary and supported surfaces

First proof: Claude Code `PreToolUse` for `Edit|Write|MultiEdit`, using the existing introduced-delta gate. Existing class-A reconstructable Bash handling may be evaluated as a separately enumerated follow-up; arbitrary class-B Bash mutations **must not** be blocked on a guessed future write. No claim of universal interception is authorized.

For a running hook, a distinct operational refusal is translated through the documented host blocking transport with actionable `UNEVALUATED` feedback. If the hook never runs, Python cannot enforce anything. Claude Code command-hook `onFailure: "block"` is documented for versions >=2.1.295, but the pinned host version and actual not-launched/crash/timeout behavior require live capability tests before any support claim. `Stop` cannot undo existing writes; its behavior and retries require a separate, explicit follow-up to ADR-021.

A disabled/misconfigured hook, unsupported mutation surface, missing provider hook, or unprotected checkout cannot be claimed protected by this feature. CI is a separate, configured verification boundary, not proof of pre-write interception.

### 6. Evidence, diagnostics, and regression discipline

- Use the existing `RuleEvaluation`, `Violation`, `EnforcementResult`, and ADR-029 trace concepts. No second enforcement or evidence engine and no model-based adjudication.
- Separate `evaluation_status`/failure reason from a policy verdict internally; never tag an operational refusal as a rule FAIL or count it as relevant enforcement observed.
- Diagnostics identify failure category, boundary, and remediation without dumping submitted source content.
- Preserve the frozen canonical benchmark fixtures and DecisionRetriever/ConflictDetector semantics. Add a separate deterministic availability-regression fixture matrix with baseline default-open parity and opt-in closed cases.
- No new persistence, cloud service, telemetry, or organizational policy management.

## Explicit non-goals

- Redefining `strict` or `warn`, changing enforcement ranking, or adding rule types.
- Automatically enabling project protection, automatically upgrading canonical memory, or creating a parallel decision authority.
- Interpreting arbitrary Bash/shell commands.
- Making `Stop` into a pre-write barrier, guaranteeing hooks always run, or silently blocking all unknown agent actions.
- Broad rollout to Codex, Kiro, Cursor, Hermes, managed agents or other providers in this first slice.
- Data Engine work, hosted services, organizational governance, or a redesigned public evidence schema.

## Implementation gates (not authorized by proposed status)

1. **ADR reconciliation (this proposal):** Review the G3-B-based R1–R10 authorization contract, mandatory independently verified baseline, revocation and negative verification, identity/path binding, and authorization-error behavior. **Do not treat this ADR edit as acceptance.**
2. **Separate authorization gates:** Only after ADR review, consider a **bounded implementation charter** and its matching **[layer1-freeze] amendment**. Neither is accepted or authorized by this PR. Pin the exact baseline verification and enrollment/revocation design before any behavior change.
3. **Verdict consistency (done):** PR #484 resolved #260, preserving default fail-open. Reuse its coherence validation; characterize historical v1 payloads and mixed-partial reporting without guessing.
4. **C2 (not authorized):** Implement opt-in policy routing and verified project eligibility only if gates 1–3 are reviewed and accepted in the required order.
5. **C3 (not authorized):** Live-prove Claude Code PreToolUse non-mutation on missing-memory, local declaration tamper, unverifiable baseline, crash, timeout, invalid/incomplete result and host-level failure. The prior G1 violation proof alone does not suffice.
6. **C4 (not authorized):** Separate adversarial regressions, canonical benchmark parity, CI semantics, installation and release documentation.

Every behavioral slice requires its own reviewed PR and tests; no direct writes to `main` (ADR-022).

## Related

- Core #260 / merged PR #484 — trusted-verdict coherence defect resolved; availability policy still proposed
- G3 missing-memory assessment and G3-B eligibility / authorization design (R1–R10), merged PR #512
- G1 pinned live Claude Code direct-write violation proof (not an availability-error proof)
- ADR-017/018/019/020 — retrieval, introduced delta, typed-rule enforcement, applicability
- ADR-021 — shell preflight and Stop claim boundaries
- ADR-022 — PR/squash-only main
- ADR-023/029/030/031 — decision identity, evidence binding, canonical persistence, governance
- M1.3/M1.4 — setup and explicit activation
- [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)

---
id: ADR-033
title: "Opt-In Fail-Closed Handling for Unavailable Enforcement Evaluations"
status: proposed
priority: foundational
date: 2026-10-13
scope: enforcement.availability_policy
---

# ADR-033: Opt-In Fail-Closed Handling for Unavailable Enforcement Evaluations

**Status:** Proposed — no implementation authority until accepted with the linked Layer 1 charter.
**Date:** 2026-10-13
**Deciders:** Pending review
**Charter:** [Reliable Enforcement C0](../plans/2026-10-13-reliable-enforcement-charter.md)
**Prerequisite:** [#260 — inconsistent checker verdicts](https://github.com/MnemeHQ/mneme/issues/260)

## Context and verified baseline

The current CLI returns `mneme.check/v1` with a `verdict` (`PASS|WARN|FAIL`), `mode` (`strict|warn`), `evaluation_complete`, applicability traces and violations. `mneme check --json` uses exit 0/1/2 for complete strict PASS/WARN/FAIL, 0 for complete warn-mode results, and exit 2 for incomplete applicability. An exit code alone cannot distinguish violation from failure.

The Claude Code hook presently uses `parse_verdict(stdout)` to validate only the envelope's schema and verdict. As documented in #260 and deliberately pinned in `tests/integrations/claude_code/test_hook_verdict.py`, an apparent PASS may be accepted despite a contradictory nonzero child exit. Checker launch errors, timeouts, malformed output, incomplete applicability and an unavailable project memory currently fail open. These conditions are **not architectural violations**.

ADR-017 keeps retrieval separate from deterministic enforcement. ADR-018 limits the direct edit gate to introduced content. ADR-020 owns typed-rule path applicability (`APPLIED|EXCLUDED|UNKNOWN`). ADR-021 defines prevent/catch/verify and explicitly rejects guessing arbitrary shell effects; Stop is post-mutation, not pre-write. ADR-023/030/031 preserve canonical decision authority and lineage. ADR-029 distinguishes execution observed from relevant enforcement observed. None of these allow inventing an authoritative PASS or violation from an unavailable check.

The Layer 1 charter forbids enforcement behavior changes without an explicit, independent charter amendment.

## Proposed decision

### 1. Two independent policy dimensions

- **Violation mode** remains `strict|warn`, with existing semantics for *trusted, complete* results.
- **Availability policy** is a separate, opt-in `open|closed` policy. Default is `open` for all existing installations. `closed` means an eligible protected-project mutation is refused when an applicable check could not be completed or its result cannot be trusted. A failure to evaluate is reported as **UNEVALUATED**, never as a decision violation.
- A trusted `SKIP`/non-applicable boundary remains a skip, not an evaluation failure. Never manufacture a PASS for a skipped operation.
- No new deterministic rule, retriever, selector, conflict-detection, decision authority, or evidence engine is introduced.

### 2. Check-result trust is established before applying either policy

Resolve #260 first by validating a full checker observation (stdout payload, process return code, requested mode) instead of relying on `parse_verdict(stdout)` alone.

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

### 4. Protected-project eligibility is a precondition, not an inference

`closed` requires explicit opt-in, project scope and a checkable activation witness. The current activation record lives within `.mneme/project_memory.json` and cannot itself prove a protected-project opt-in when that entire file is missing. Therefore the missing-memory block is **not implementable safely** until a separate, reviewed method binds the opt-in to the intended project root without creating a competing decision authority.

Do not interpret a globally set environment variable or mere installation of the CLI as permission to block every repository. Do not rewrite or repair canonical memory automatically. C2 must resolve the configuration/witness contract against the existing M1.3/M1.4 setup/activation lifecycle and ADR-030.

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

1. **C0:** Accept this ADR together with an explicit Layer 1 charter; settle the activation-witness and incomplete-result compatibility questions.
2. **C1:** Close #260 with complete process/payload consistency tests, preserving default fail-open diagnostics.
3. **C2:** Add opt-in failure-policy routing through the existing adapter/checker boundary, with explicit protected-project eligibility.
4. **C3:** Live-prove supported Claude Code PreToolUse non-mutation on crash, timeout, invalid/incomplete result, and host-level failure.
5. **C4:** Run separate adversarial regressions, canonical benchmark parity, CI failure semantics, installation and release documentation.

Every behavioral slice requires its own reviewed PR and tests; no direct writes to `main` (ADR-022).

## Related

- Core #260 — trusted-verdict coherence defect
- ADR-017/018/019/020 — retrieval, introduced delta, typed-rule enforcement, applicability
- ADR-021 — shell preflight and Stop claim boundaries
- ADR-022 — PR/squash-only main
- ADR-023/029/030/031 — decision identity, evidence binding, canonical persistence, governance
- M1.3/M1.4 — setup and explicit activation
- [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md)

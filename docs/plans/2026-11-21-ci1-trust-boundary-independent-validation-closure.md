# CI1: trust-boundary correction and independent-validation closure plan

**Status:** PROPOSED for independent review and owner acceptance. **Scope:** Core CI1 assurance, not new enforcement semantics.
**Date:** 2026-11-21
**Source pin:** `MnemeHQ/mneme` `main` at `3c65915a2ff835b20bc1d6fff4dc2e2220564229`.
**Tracker:** [CI1 #540](https://github.com/MnemeHQ/mneme/issues/540); [DG1 #497](https://github.com/MnemeHQ/mneme/issues/497) remains separate.
**Companion read-only assessment:** [CI1 Gate 0 inventory](../validation/ci1-trust-boundary-gate0-assessment-2026-11-21.md).

## 0. Authority and non-authorization

The owner authorized writing the plan and doing available read-only analysis on 2026-11-21, with later execution intended for DeepSeek. This record authorizes its own documentation-only PR, not implementation, new tests, live experiments, ruleset/variable changes, release, or a retrospective PASS. Each later gate needs separate owner approval and independent review.

No changes to `mneme/`, `tests/`, `scripts/ci/`, `.github/`, `.mneme/`, accepted ADRs, Layer 1 freeze, benchmark, runtime evaluator, or rulesets are part of this PR. Do not change CI1 tracker #540's historical evidence or use this document as a substitute for owner approval.

## 1. Existing architecture and completed evidence

- **Canonical authority:** ADR-023/030/031. Decision and waiver authority is separate from retrieval ranking, enforcement evaluation and verification. DG1-S is closed by #838; full DG1/G1-G3 remain open.
- **Enforcement scope:** ADR-017/020 (retrieval does not reduce enforcement, typed rules have explicit path applicability), and ADR-033 (availability handling).
- **CI control:** The required `mneme trusted gate` on `main` is the C4 adapter from #679, deployed through R0 #742 with strict up-to-date and posture recorded as `closed`. Its deliberate operating classification is bounded dogfooding (#743), not unrestricted production readiness.
- **Evidence semantics:** ADR-029 has six mandatory binding dimensions for relevant enforcement. The literal-rule CI record does not yet satisfy all six; the Verification Step 4 independent review #778 says CI reports are execution observed and identifies R-1.
- **Closed historical work, do not reopen:** CI1 lab/C4 Gate 4 #682; Core CI R0 stages S1-S7 #742; frozen Verification Steps 2-4 #772/#776/#778; ADR-034 M4 #628 (different benchmark); T-08 P2-first #815/#818 and G3 reassessment #822 (G3 stays PARTIAL).

Use the accepted [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md), [ADR-031](../adr/ADR-031-decision-governance-semantics.md), [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md), [C4 adapter](../../scripts/ci/adr033_c4_gate.py), [trusted workflow](../../.github/workflows/mneme-trusted-gate.yml), [R0 record](../validation/ci-r0-s7-closure-2026-11-03.md), and [Step 4 independent review](../validation/verification-step4-independent-review-2026-11-09.md) as the baseline. Reconcile later `main` changes before execution; this plan is pinned to the stated commit, not an assertion about future tips.

## 2. The two deliverables

### CI-TB: bounded trust-boundary correction

Question: Can a PR supply or alter the decisions, evaluator, gate or evidence used to accept itself, within the configured GitHub trusted gate?

First classify each alleged gap by reachability from the untrusted PR. The gate currently executes from `pull_request_target`, reads policy from the trusted base, pins the evaluator and adapter, refuses `.mneme/` and `.github/` changes, and uses GitHub strict freshness. These controls must not be silently replaced.

The specific R-1 result in #778 is **not itself proof of an attacker-accessible bypass**: `verify-report` checks known pins and recomputes aggregate/disposition but does not independently attest memory/subject digests or re-evaluate the raw output; it accepts coherent rewrites in a test copy. Under the accepted C4 design, the report is an artifact of the same trusted job. Distinguish:
1. **representation/claim correction** (documentation currently overstates verification);
2. **a reproducible untrusted-to-trusted write route** (would be an actual CI trust-boundary defect);
3. **additional evidence binding/attestation** (separate ADR-029/CI1 scope, not automatically a gate defect).

R6 administrator-capable credentials reachable by agents are an operational authority limitation expressly accepted for bounded dogfooding, not something a report parser can fix. Do not claim R6 closed without independently verified isolation.

### CI-IV: independent validation and limited closure

Validate the specific corrected/accepted contract, not every historical milestone and not universal production readiness. Reuse frozen C4/R0 evidence with its original pins and ceilings; run only missing negative/positive checks for the changed surface. A new independent checker must derive its expected result from ADR/charter, trusted Git objects, raw evaluator output and host rule suites, not from the implementation harness's own PASS label.

Every outcome must be distinguished as one of: `VERIFIED_PASS`, `VIOLATION`, `REFUSED`, `UNEVALUATED`, `UNTESTED`, or `EVIDENCE_INCOMPLETE` as appropriate to the observed surface. These are validation labels, **not** a new public Mneme runtime schema or ADR-033 state model.

## 3. Sequential gates and exit conditions

### Gate 0: read-only baseline and gap disposition (this PR begins it)

- Pin live repo HEAD, current approved workflow/adapter blob and hash, evaluator build, decision memory revision, ruleset status/required context/freshness and approved human bypass; separately record what is available only as a historical attestation (notably variable posture and credential access).
- Reconcile CI1 #540, R0 #742/#743, C4 #682, Verification #761/#778, T-08 #822 and current ADRs.
- For each issue mark `CLOSED (evidence)`, `CORRECTION REQUIRED`, `ACCEPTED LIMITATION`, or `OUT OF SCOPE`; append exact source and contrary evidence. Where exploitability is unverified write `INVESTIGATION REQUIRED`, not a verdict.
- Independent reviewer checks the matrix. No new host probe or implementation is permitted by Gate 0.

**Exit:** reviewed, source-pinned matrix; one explicit recommendation: documentation correction only, bounded engineering charter, or no change with limitation. Companion Gate 0 assessment provides the initial source-inspected draft.

### Gate 1: decision and smallest correction charter (separate authorization)

Only if Gate 0 finds a reproducible defect or unsupported claim: define exact changed surface, threat actor/control, accepted behavior, unchanged contracts, independent test fixture, rollback, and permission/credential prerequisites. Specify whether this is documentation, adapter, workflow/host configuration, evidence consumer, or administration. Any freeze-sensitive change needs an accepted `[layer1-freeze]` amendment before implementation. Never broaden CI authority via a test-only change.

**Exit:** owner accepts an independently reviewed charter (or records no code correction required).

### Gate 2: implementation and author-side regression (separate authorization)

Use the existing C4 adapter and `mneme.check/v1` contract. Keep evaluator/adapter pins, `pull_request_target` safety, base/head/protected-memory selection and strict freshness unless the charter specifically changes them. Measure no false green or false block on the scoped fixtures; keep all `UNEVALUATED` and refusals distinct. Run applicable canonical/gate/test-policy suites and capture the exact commit/tree and outputs.

**Exit:** reviewed head and tests green, or FAIL with the unresolved case preserved. No release/re-pin/production change implied.

### Gate 3: preregistered independent validation (separate authorization)

- Freeze implementation commit/tree, evaluation build/wheel, adapter blob, workflow blob, protected decision-memory blob, host/runtime version, ruleset IDs, posture observation, fixtures and independent scorer/checker before results.
- Isolate validation author/reviewer from implementation. An independently authored checker must examine raw Git blobs, outputs, GitHub check run IDs/conclusions and host rule-suite responses; it must not import result assertions from the implementation harness.
- Validate positive and negative controls in section 4, mark unavailable host tests `UNTESTED`, preserve original frozen results, and separate offline replay from observed merge refusal.
- Retain a manifest of SHA-256 values, raw evidence in owner custody where needed, redacted publishable copies, test invocation, version pins and exceptions.

**Exit:** all mandatory applicable cases have independently verified expected outcome, no false-green, no unexplained false-block on compliant controls, and no missing mandatory provenance. A single unresolved mandatory case prevents PASS.

### Gate 4: review and bounded closeout (separate authorization)

Independently audit checks, evidence hashes, provenance, negative space and contradictory records. Write a closure artifact with: subject pin; explicit claimed boundary; statuses for each Gate 0 gap; table of expected/observed per case; false green/false block/unknown counts; ADR-029 six-dimension binding and ceilings; R6/admin and bypass caveats; outstanding host paths; preserved historical failures; rollback implications. Owner acceptance must identify reviewed head SHA. Only then update #540 and the roadmap through its separate review process.

**Exit:** a scoped `PASS`, `PARTIAL`, or `FAIL` supported by raw evidence; never automatically `CI1 COMPLETE`, `DG1G COMPLETE`, `PRODUCTION READY`, or a new release.

## 4. Minimal independent test matrix (conditional, not yet authorized)

| ID | Case | Required observation | Evidence |
|---|---|---|---|
| IV-01 | Compliant, in-scope, current head | Genuine check succeeds; ordinary non-bypass merge allowed | raw report + GitHub check and pinned merge response |
| IV-02 | Applicable prohibited edit | Genuine check VIOLATION; non-bypass merge refused | evaluator output + rule trace + GitHub response |
| IV-03 | Self-substitution of memory/workflow/evaluator or deletion | REFUSED where trusted surface; same-PR attack cannot change governing gate | base/head/tree and rule suite |
| IV-04 | Missing, malformed or incomplete evaluation | UNEVALUATED; under observed `closed` posture cannot satisfy required check | raw stdout/exit, report, check and host response |
| IV-05 | Coherent report rewrite and pin mismatch | Record exactly what `verify-report` does and does not reject; no claim of tamper-proof subject/config verification without new contract | independent tamper probes on copies; no mutation to trusted job |
| IV-06 | Stale PR head / advanced base | GitHub strict freshness blocks stale merge or a fresh evaluated head is required | exact base/head, check ID, rule suite, pinned merge response |
| IV-07 | Authorized human exception vs ordinary PR | Separate `bypass` record attributed to authorized actor; unprivileged merge refusal | rule suite, authority evidence |
| IV-08 | Reviewer-controlled independent reconstruction | Recompute expected classifications and compare with raw evaluator/adapter output | independent checker + provenance |
| IV-09 | R6 administrative exposure | Documentary/account-control assessment; do not run agent-credential or administrative attack without separate consent and safe lab | credential-boundary attestation with precise limit |

Use prior accepted host evidence for an unchanged case where possible; otherwise independently reproduce only after a charter. A 200/405 HTTP code or a green job name without associated SHA, context and ruleset is insufficient. For any new test, the mandatory status and expected outcome must be frozen *before* execution. State whether the test validates report truth, gate integrity, or GitHub merge authority.

## 5. Acceptance constraints and non-goals

- No alternate decision authority, retrieval rank-based enforcement, inferred waiver, new policy DSL, general event system or changed Audit tiers.
- Do not change `DecisionRetriever`, `ConflictDetector`, DG1 applicability, waiver consumers, or Layer 1 benchmark by side effect.
- No automatic CI evaluator re-pin to v0.11.0; `0b74d410` is the currently approved CI evaluator. New rule types need separate parity and pin approval.
- Do not transfer the T-08 P2-first fix or G3 PARTIAL result into a CI trust-boundary PASS. Host hook and CI are distinct checkpoints.
- No GitHub ruleset, Actions policy, bypass, repository variable, protected memory, production workflow or live merge experiment from this plan alone.
- No retrospective changes to C4, R0, Verification Step 4, ADR-034 M4 or G3 records.
- No unconditional CI1 full-programme closure: documented/unverified coverage, administrator authority and ADR-029 bindings remain limited.

## 6. DeepSeek executor handoff

1. Read this plan, the companion Gate 0 assessment, issue #540, all accepted ADRs above and the actual `main` tree. Verify that the recorded SHA still anchors the plan. Do not infer current operating conditions from a historical record.
2. Read any open work overlapping this path (including roadmap PR #839). Keep this PR docs-only and independent; do not edit another branch or replace concurrent roadmap work.
3. Complete Gate 0 as a **read-only** evidence review, checking exact code, current rulesets, expected behavior, published records and the independent review's R-1. Report discrepancies and a proposed disposition for each row. No live probes.
4. Stop at the Gate 0 approval boundary. Request the owner's explicit decision on a concrete Gate 1 correction or an evidence-only closure. If a source is unavailable, mark that line `UNVERIFIED`.
5. When authorized, work on one separate branch per behavioral correction, with charter/freeze/review/test gates before any trusted surface change. Use a fresh independent agent session for validation; DeepSeek implementation self-tests never count as independent review.

**Suggested validation commands when authorized and applicable** (do not execute as part of plan approval): `python -m pytest tests/test_adr033_c4_ci_gate.py`, `python -m pytest tests/test_ci1_contract_matrix.py`, `python -m pytest tests/test_test_policy.py`, the repository's documented `run_test_battery` gate, and a dedicated independent report replay in a detached pinned checkout. Confirm exact environment/commands in the current test-policy docs first.

## 7. Source list

- [CI1 tracker #540](https://github.com/MnemeHQ/mneme/issues/540)
- [CI1.4 historical lab evidence](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)
- [CI1 C1 separate-PR threat model](2026-10-19-ci1-gate-weakening-threat-model.md)
- [Core R0 closure](../validation/ci-r0-s7-closure-2026-11-03.md) and [operating-status owner decision](../validation/ci-r0-operating-status-decision-2026-11-03.md)
- [ADR-029 evidence audit](../validation/adr029-evidence-completeness-audit-2026-11-08.md), [Verification Step 4](../validation/verification-step4-independent-review-2026-11-09.md)
- [DG1-S closeout](../validation/dg1s-closeout-evidence-2026-11-18.md), [T-08 G3 reassessment](../validation/t08-g3-reassessment-p2-first-2026-11-17.md)

## 8. Execution provenance

- Change author: ChatGPT (read-only source inspection, documentation proposal)
- Execution agent for later authorized work: DeepSeek (not invoked in this PR)
- Task origin: owner instruction in Mneme Core, 2026-11-21
- Human owner: @TheoV823
- Architecture impact: none in this documentation PR

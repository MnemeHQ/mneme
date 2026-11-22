# CI1 Gate 0: read-only trust-boundary and closure-readiness assessment

**Status:** INITIAL SOURCE-INSPECTED DRAFT; independent review and owner acceptance pending. Not a new CI execution, not a completed Gate 0 PASS.
**Date:** 2026-11-21
**Pinned Core source:** `main` `3c65915a2ff835b20bc1d6fff4dc2e2220564229` (branch API inspected 2026-11-21).
**Plan:** [CI1 trust-boundary and independent-validation closure](../plans/2026-11-21-ci1-trust-boundary-independent-validation-closure.md).
**Tracker:** [#540](https://github.com/MnemeHQ/mneme/issues/540).

## 1. Method and limits

Read-only inspection through GitHub's repository file, branch and ruleset APIs, cross-checked against existing accepted evidence records and the independent Verification Step 4 #778. No checkout, test suite, new offline replay, live PR/merge attempt, credential inventory, Actions variable read, hash recomputation or new independent scorer was run by the author. Historical experimental PASS/FAIL labels below belong to their original records; this source inspection does **not** reclassify them.

A directly inspected source/ruleset state is `SOURCE-VERIFIED`, not a proof of end-to-end execution or a new host test. Historic records are `RECORDED`, not currently remeasured. `NOT VERIFIED` means no direct evidence in this assessment. Each finding must be independently reviewed before Gate 0 can close.

## 2. Read-only controls inspected on 2026-11-21

| Object | Directly observed | Verification ceiling |
|---|---|---|
| Core `main` | `3c65915a2ff835b20bc1d6fff4dc2e2220564229`; source tree available by immutable commit | Current tip when inspected only |
| Workflow `.github/workflows/mneme-trusted-gate.yml` | Blob `3fb1e0ba17ed0849649130b75447a22af18ac8f4`; `pull_request_target` to `main`, `contents: read`, fixed strict mode, fixed evaluator + adapter pins; PR head fetched as Git objects rather than checked out/executed | SOURCE-VERIFIED, not a new live execution |
| Adapter `scripts/ci/adr033_c4_gate.py` | Blob `5feedf60ce1a67b2bb85673354c8b8b367a87d06`; matches `ADAPTER_BLOB` named in workflow. `verify-report` checks base/head/mode/adapter and evaluator pins/posture, recomputes aggregate and disposition | SOURCE-VERIFIED, not full artifact authenticity |
| Pinned evaluator | Workflow names `0b74d410b45e7b3efcf08d00ce58e7bd7017b757`, approved wheel SHA-256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51` | Pinned by workflow; build parity is RECORDED by historical P2, not re-run |
| Gate ruleset | `mneme-ci-gate`, ID `26391853`, active on `refs/heads/main`, required status `mneme trusted gate` from GitHub Actions integration `15368`, strict freshness true | SOURCE-VERIFIED GitHub ruleset response; no new merge attempt |
| Gate bypass | Exactly one `User` actor `54006786` with `pull_request` bypass mode | SOURCE-VERIFIED ruleset structure; whether credentials are agent-reachable was not checked |
| Other branch protections | `main-pr-only`, ID `22196895`, active on `main`, no bypass; PR required, squash only; four other required named checks | SOURCE-VERIFIED ruleset response; no new host behavior |
| CI availability variable | `MNEME_CI_AVAILABILITY=closed` in [R0 S7](ci-r0-s7-closure-2026-11-03.md) (2026-11-03) | RECORDED only; **current repository variable not directly read** |

Sources: [workflow](../../.github/workflows/mneme-trusted-gate.yml), [adapter](../../scripts/ci/adr033_c4_gate.py), [R0 S7](ci-r0-s7-closure-2026-11-03.md), [operating decision](ci-r0-operating-status-decision-2026-11-03.md), and the GitHub [gate ruleset](https://github.com/MnemeHQ/mneme/rules/26391853) / [main ruleset](https://github.com/MnemeHQ/mneme/rules/22196895). API-observed ruleset update timestamps both remain 2026-11-03; this is not a guarantee that other admin settings or credential access are unchanged.

## 3. Gap / trust / closure matrix

Dispositions are a **proposal** for independent review, not a current grant of authority or a declaration of a security fix.

| ID | Boundary / question | Evidence reviewed | Proposed disposition | Work needed to close |
|---|---|---|---|---|
| TB-01 | Can same-PR memory substitution make its own policy permissive? | Base policy selection, `.mneme/` refusal, C4/R0 live evidence | **CLOSED (bounded evidence)** | Revalidate only if policy-source contract changes; preserve bypass distinction |
| TB-02 | Can same-PR evaluator/adapter/workflow change replace its own gate? | Trusted source pins and `.github/` refusal; C1 lab and R0 | **CLOSED (bounded evidence)** | Keep current pin/provenance and strict changed-surface refusal; no universal tamper-proof claim |
| TB-03 | Is stale check success sufficient for a changed head/base? | Gate report carries head; GitHub rule strict freshness true; CI1 V11 Option A | **CLOSED for measured GitHub Option A**, conditional | Independent reviewer must inspect exact evaluated head/base vs merge subject in any new run |
| TB-04 | Does `verify-report` cryptographically/internally bind subject + policy to raw evaluator output? | Source code and independent R-1 (#778) | **ACCEPTED CONTRACT LIMITATION; documentation correction candidate** | State explicitly what is rechecked; only charter hardening after reproducing an untrusted report-write route or owner choosing stronger provenance |
| TB-05 | Can arbitrary caller-supplied bytes be promoted to ADR-029 relevant enforcement? | ADR-029 + #761 + independent #778 | **ACCEPTED EVIDENCE LIMITATION** | No relevant claim for CI literal tier; any new evidence binding separately chartered |
| TB-06 | Can administrator-capable agent credentials modify controls or use human bypass? | R0 R6 owner-accepted dogfooding limit; live ruleset still has one human bypass | **ACCEPTED LIMITATION for dogfooding; BLOCKER to unrestricted readiness** | Verify current agent credential boundary independently; separate operational decision for isolation; no admin attack authorized |
| TB-07 | Does the gate evaluate all shipped typed-rule classes? | C4 classifier source refuses `subject`/ADR-034 numeric records as UNEVALUATED; #761 E-5 | **ACCEPTED COVERAGE LIMITATION** | Separate evaluator parity, replay and pin authorization before expanding scope |
| TB-08 | Are incomplete, missing or malformed `mneme.check/v1` payloads silently accepted? | Payload-first classifier + aggregate/posture implementation; CI1.2 memory-errors and C4 | **CLOSED at adapter classification level** | Do not mistake a CLI traceback for a complete PASS; keep structural CLI crash issue separately scoped |
| TB-09 | Are default-branch / fork / alternate host paths generally verified? | R0 S7 explicitly says forks and first-time contributors unobserved; workflow `main` filter | **ACCEPTED LIMITATION / UNTESTED** | New host test only if chartered; do not generalize beyond `main` and observed PR class |
| TB-10 | Is the evidence reviewer itself independent of the author? | Verification Step 4 independently checked earlier fixtures and exposed R-1/R-3 | **HISTORICAL REVIEW CLOSED; new correction NOT VALIDATED** | Preregister and independently reproduce any new change; do not reuse historical PASS as acceptance for new code |
| TB-11 | Is repo-local `MNEME_MEMORY` host precedence fully solved? | T-08 #815/#818, G3 #822 | **OUT OF CI1 SCOPE; G3 PARTIAL** | No CI1 closure inference; keep Phase 2 and host paths under their existing authorization |
| TB-12 | Are current availability posture and administrator credential exposure directly verified today? | 2026-11-03 posture record and R6; live rulesets only | **INVESTIGATION REQUIRED (read-only)** | Request current read-only variable/credential inventory or label `UNVERIFIED`; never infer from rulesets alone |

**Interpretation:** The accepted R-1 probe identifies a *verification claim boundary*, not a demonstrated PR-to-report attack. It may merit a precise correction to future documentation/claims without any behavioral modification. A code change to reparse raw evaluator output or cryptographically bind subject/configuration would alter the accepted C4 contract and requires a charter, freeze review if applicable, and fresh independent validation. No default change to the running gate is justified solely by R-1.

## 4. Evidence provenance and historical closures to preserve

| Prior record | Existing result | How Gate 0 uses it |
|---|---|---|
| [CI1.4 lab](ci1-4-trusted-merge-gate-validation-2026-10-19.md) | Head-revision merge blocking for one literal rule; historical V11 gap identified | Baseline, superseded operationally by later C1 + strict freshness; do not rerun/rewrite |
| [C4 closure](adr033-c4-closure-2026-10-26.md) | Bounded CI availability milestone closed | Reuse unchanged semantics; not evidence of broad rule coverage |
| [Core R0 S7](ci-r0-s7-closure-2026-11-03.md) + [owner decision](ci-r0-operating-status-decision-2026-11-03.md) | Real required gate, bounded dogfooding, R6 accepted limitation | Retain operating status until a separate owner change |
| [ADR-029 audit](adr029-evidence-completeness-audit-2026-11-08.md) | Literal CI records remain execution observed; `0b74d410` evaluator | Preserve binding ceiling |
| [Verification Step 4](verification-step4-independent-review-2026-11-09.md) | Independent PASS with conditions, including R-1 report-tamper limit, R-3 consumer obligations | Do not reopen; carry findings forward into claims and any new tests |
| [T-08 G3 reassessment](t08-g3-reassessment-p2-first-2026-11-17.md) | G3 PARTIAL | Host memory boundary remains independent |
| [DG1-S closeout](dg1s-closeout-evidence-2026-11-18.md) | DG1-S complete, DG1/G3 not complete | No semantic migration or authority change |
| [ADR-034 M4](adr-034-m4-heldout-scoring-2026-10-24.md) | Held-out benchmark 161/161 PASS, limited to its own G1 scope | Entirely separate from CI trust assurance |

Do not promote `execution observed` to `relevant enforcement observed` because a GitHub check succeeded. Do not claim independent attestation because an agent in another session replayed a fixture. No historical result is changed by this record.

## 5. Initial conclusions and recommended next independent checks

1. **No new CI implementation defect is established by this read-only assessment.** The current C4 trusted boundary appears consistent with its narrowly stated source contract and with the historical tests. This is a source-level conclusion, not a new live exploit test or production-readiness statement.
2. **The strongest actionable discrepancy is semantic:** some earlier wording suggests `verify-report` detects all report tampering. R-1 proves it does not; it checks trusted pins, posture and aggregate/disposition consistency, not the factual truth of every row. A forward-looking claim correction or append-only erratum is the smallest potential Gate 1 action, subject to owner review. Do not silently change the frozen Step 3 record.
3. **Broader CI assurance stays limited** by R6, literal-only evaluator scope, source/subject binding gaps and unobserved host cases. These cannot be truthfully closed by a documentation-only PR.
4. **Current posture and credential reachability need read-only confirmation.** If unavailable, publish that inability as an evidence gap; do not mark them closed.
5. **A new independent live validation is not automatically justified.** Reuse accepted C4/R0 host results. Only a demonstrably changed security boundary or a specific untested acceptance criterion should trigger a new, narrow, owner-authorized host experiment.

## 6. Reviewer checklist (DeepSeek handoff: read-only first)

- [ ] Re-read exact approved ADR-017/020/023/029/030/031/033 semantics, current CI1 #540, the source-pinned workflow/adapter and current independent review #778.
- [ ] Verify each recorded blob/commit/ruleset response against current immutable GitHub objects; compare with pinned baseline without modifying the repository.
- [ ] Confirm (or mark unverifiable) the current CI availability posture and R6 credential trust boundary.
- [ ] Examine `verify_report`, `classify_payload`, `run_gate`, `_evaluate_pending` and workflow `Gate decision` directly; reproduce R-1 from a detached pinned copy **only after an approved offline validation charter**, or cite its accepted historical result.
- [ ] Identify any fresh counterexample in which untrusted PR contents influence the trusted policy/evaluator/report; do not assume report-editability merely because tamper tests of a copy passed.
- [ ] Check that the test matrix is minimal and independent, and that every required negative result has a host- or source-supported expected outcome.
- [ ] Output a second-person independent review with `ACCEPT`, `ACCEPT WITH CHANGES`, or `REQUEST CHANGES`, findings and exact evidence paths. This assessment's author cannot self-approve it.
- [ ] Request owner Gate 1 choice; do not implement or run host experiments on the basis of the plan.

## 7. Read-only operational status

- **Completed here:** source/repo/ruleset inspection; architecture reconciliation; draft plan; this draft matrix.
- **Not completed here:** independent Gate 0 review, current variables/credential inventory, new test execution, controlled correction, preregistered validation, closure approval.
- **Next allowed action for DeepSeek:** independent review of this Gate 0 matrix and a recommendation only. Separate owner authorization is required to advance to Gate 1.

## 8. Provenance

- Record author: ChatGPT, 2026-11-21.
- Source pin: `3c65915a2ff835b20bc1d6fff4dc2e2220564229`.
- Type: read-only assessment based on published accepted records, source and read-only GitHub ruleset API; **not independently executed validation**.
- Execution planned: DeepSeek, not yet invoked.
- Owner: @TheoV823.

# ADR-033 C4 Gate 1: bounded CI adapter implementation charter

**Status:** **ACCEPTED — Gate 1 owner approval recorded 2026-10-26** in [PR #677](https://github.com/MnemeHQ/mneme/pull/677#issuecomment-6423873813), after R1–R3 at `3248ccd932e028e70c6203234b63f65722ff7a1a`. Acceptance fixes this bounded implementation charter, but **does not** amend the Layer 1 freeze or authorize implementation until a separately approved `[layer1-freeze]` amendment merges. It does not authorize lab unarchive, CI/ruleset/Actions-variable changes, or live PR or merge attempts. Gates 2–4 remain separate.

**Date:** 2026-10-26.
**Repository:** `MnemeHQ/mneme`.
**Approved Gate 0:** [C4 scope charter](2026-10-26-adr033-c4-ci-availability-charter.md), PR #676, squash `9a0c1ae18bc37797249ab776ad6ea2c87005417f`; amendments A1-A5 are binding.
**Proposal branch anchor:** Core `main` at `217189956f26b68c7e28e441df378c95d4ad1863`; C4 design authority is the earlier Gate 0 merge.
**Architecture:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md) §§1-2, 5-7; ADR-017/020/021/029/030/031; [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md), Amendment Procedure.
**Prior evidence:** CI1.2 [fixtures](../../tests/fixtures/ci1_contract/README.md), [CI1.4](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md), [CI1 readiness](../validation/ci1-production-readiness-reconciliation-2026-10-20.md), CI1 C1, V11 Option A, and [C3 closure](../validation/adr033-c3-closure-2026-10-26.md).

## 1. Accepted Gate 1 boundary (implementation contingent on freeze amendment)

Implement exactly one **CI adapter**, derived from the archived CI1 trusted gate, that deterministically translates `mneme.check/v1` observations and the approved `open|closed` availability policy into an attributable required-check outcome. CI remains **post-change merge verification**, never PreToolUse interception.

Once the separate freeze amendment is approved and merged, Gate 1 permits **only** a reviewed Core adapter, its isolated deterministic tests, its versioned C4 fixtures and adapter documentation. It would **not** activate a required merge-blocking check in Core, alter GitHub administration, run the live validation, or amend ADR-033.

**Proposed Core file placement (requires Gate 1 approval):**

- `scripts/ci/adr033_c4_gate.py`: single standard-library-only adaptation of the CI1 lab `gate/ci1_gate.py` at `MnemeHQ/mneme-ci1-lab` `3cd402fe`. This stays outside the `mneme-hq` wheel.
- `tests/test_adr033_c4_ci_gate.py` and, if tests require data files, `tests/fixtures/adr033_c4_ci/v1/`: regression coverage. No modification to existing frozen fixture versions.
- `docs/validation/` for an eventual offline execution record and `docs/integrations/` for the separately required installation and limitations documentation. This proposal itself is not an execution record.

No edits to `mneme/`, `.mneme/`, `.github/workflows/`, the Core ruleset, the archived lab, `DecisionRetriever`, `ConflictDetector`, or the canonical benchmark.

## 2. Frozen evaluator and adapter origin

**Evaluator:** preserve CI1 P2's commit `0b74d410b45e7b3efcf08d00ce58e7bd7017b757` and wheel SHA-256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51`. Existing hash-locked dependency installation and Python 3.12 lab assumptions remain. No upgrade under this charter. If changing the evaluator is necessary, **stop**: Gate 0 A5 requires a new parity proof and owner approval.

**Adapter:** after the reviewed implementation is pinned, its exact Git commit, path, Git blob object ID, content SHA-256 and review PR are recorded. Do not invent a hash before there is a reviewed artifact. The future lab's trusted base workflow must:

1. Obtain adapter bytes by exact approved Core commit and path, never from the evaluated PR tree, its title, its environment, or an unpinned branch.
2. Verify both expected Git blob identity and content SHA-256 **before execution**, and require a regular-file blob rather than a symlink or submodule.
3. Run the script from a trusted, fresh workspace with `python -I`; retain CI1's trusted-base memory, fetch-head-as-objects-only materialization, fixed query, pinned evaluator and no execution of PR-provided code.
4. Fail the required check on a missing or mismatched adapter/hash. No report or failed integrity preflight may be converted into an `open` success.

The exact adapter hash and the trusted-workflow bootstrap patch are **not** authorized or pinned by this proposal. They must be separately reviewed before any Gate 3 live experiment. The approved adapter's source must not be fetched from GitHub's mutable `main`.

## 3. Policy and result contract

**Policy source (A3):** propose the exact repository Actions variable `MNEME_CI_AVAILABILITY`, read by the trusted `pull_request_target` workflow through GitHub's `vars` context. Only the literal `open` or `closed` is valid. Missing, empty, malformed, or differently cased values resolve to **closed with an explicit configuration warning**. The effective posture and its administrative provenance are captured for each run. This is an **administrative trust** source (ADR-033 §5, P7/P8), not a `.mneme/` declaration. PR code may not supply or override it.

**Violation mode:** `strict` or `warn` is a separate trusted input with a fixed source: a literal constant in the trusted adapter invocation within the base-revision workflow, which the C1 trusted-surface refusal protects (as CI1's `REQUESTED_MODE = "strict"` was a gate-file constant). It is never read from the PR tree, title, branch, labels, environment or any PR-writable location, and it is not a second Actions variable. Each run records the requested mode in the report, and the decision step (section 4) checks it against the workflow constant. Live probes L1-L4 use `strict`; `warn` is covered offline. The test matrix covers both; neither setting is inferred from checker output. A complete strict PASS/WARN/FAIL requires exits 0/1/2; complete warn-mode PASS/WARN/FAIL requires exit 0. Incomplete observations follow ADR-033 §2's separate treatment, not that exit matrix.

**Classifier:** use the `mneme.check/v1` coherence semantics of ADR-033 §2 and the already shipped `assess_verdict` contract (#484), without introducing divergent trust semantics. Because A5 places the adapter outside the wheel and restricts it to standard-library-only code, any deterministic JSON validation inside this adapter is an **adapter translation**, not a new enforcement engine. The implementation must prove parity with the approved validator through a cross-checking test matrix. A mismatch is Gate 2 FAIL, not an invitation to relax A5 or the contract.

**A1 order:** normalize/check the path first (including absolute path, NUL, backslash, empty, `.`, `..` components); then classify any `.mneme/` or trusted-surface change as **REFUSED regardless of file type**; only then treat any other non-regular or unmaterializable path as operational UNEVALUATED. Refusals never turn into UNEVALUATED merely because the entry is a symlink, submodule or other unsupported mode.

**A2 aggregate precedence:** REFUSED > strict VIOLATION > UNEVALUATED > WARN > PASS. **Interpretation of A2 (not an amendment):** under `strict`, any trusted complete WARN or FAIL result is a "strict VIOLATION", because strict WARN exits 1 and is non-success today; the lower WARN rank applies only under `warn`. Otherwise a strict WARN combined with one unevaluable file would aggregate to UNEVALUATED and could pass under `open`, letting a PR unblock a WARN by adding an unevaluable file. Do not lose per-file detail: a strict violation plus an incomplete evaluation is still reported as **partly unevaluated**, even if the blocking reason is the violation. Untrusted/incomplete payloads (including missing `evaluation_complete: true`) never produce an authoritative PASS. SKIP-only remains SKIP, may satisfy the check, and never becomes PASS. A trusted complete EXCLUDED applicability result remains a PASS for the check but is **not** relevant enforcement observed under ADR-029.

**Disposition:**

| Condition | Strict/warn violation mode | Availability `closed` | Availability `open` |
|---|---|---|---|
| Complete trusted PASS | Both | Success, PASS | Success, PASS |
| Trusted complete WARN/FAIL | Strict | Non-success, actual rule outcome | Non-success, actual rule outcome |
| Trusted complete WARN/FAIL | Warn | Success with violation/warning report | Success with violation/warning report |
| Operational UNEVALUATED only | Both | Non-success, UNEVALUATED | Success only with explicit UNEVALUATED annotation, summary and report |
| REFUSED on trusted surface/policy | Both | Non-success, REFUSED | Non-success, REFUSED |
| SKIP only | Both | Success, SKIP not PASS | Success, SKIP not PASS |
| No trustworthy adapter/report | Both | Non-success, no verified result | Non-success, no verified result |

Under `open`, operational errors **inside a running trusted adapter** must still produce the required reason-labelled report; the runner must never suppress an error into a silent success. If the runner fails to start, no valid report exists, or the bootstrap integrity check fails, there is no authenticated evidence of UNEVALUATED delivery, so fail the required check. This is a **host/preflight limit**, not a new rule violation or a guarantee that all infrastructure failures can proceed under `open`.

## 4. Required-report / required-check integrity

CI1's existing `Gate decision` step accepts only a report stating `passed: true` with `verdict: PASS`. That condition cannot support `open` with an explicitly UNEVALUATED result. At **Gate 3 only**, a reviewed replacement of that **lab** decision step must instead:

- Validate the adapter's execution result *and* parse a schema-checked report whose effective posture equals the independently read trusted posture.
- Check its base SHA, head SHA, adapter identity, evaluator identity, requested mode (equal to the trusted workflow constant), classification, reason and required-check disposition; fail if any required field is missing/inconsistent.
- Permit a success conclusion for an `open` UNEVALUATED result **only** when the report still says UNEVALUATED, names the reason, and the same job emits `::warning::` and the job summary.
- Never permit `REFUSED`, a strict trusted violation, invalid report, missing report or adapter preflight failure to succeed.
- Emit only the existing genuine required check `CI1 trusted gate`; do not introduce a Checks API or same-name look-alike check.

This separation of the trusted decision step and the adapter is necessary to avoid an adapter's own successful process exit being taken as sufficient merge proof. Any mismatch fails the required check.

## 5. Offline acceptance and regression protocol (Gate 2, not yet authorized)

Implement and replay **all** Gate 0 rows: O1, O2, O2w, O3-O9, O8s, O9s, O9p, O9n, O10, O10x, O11 and O12, in `closed` and `open` as applicable.

Additional mandatory checks within those rows:

1. O7: cross-product of mode, JSON schema, verdict/violation coherence, missing fields, non-boolean completeness, return-code coherence, and legacy payloads. Require parity against the approved `assess_verdict` semantics; do not relabel a missing verdict as a real FAIL.
2. O8s/O9s/O9p: protected paths with symlink, submodule, deletion, rename into/out of the surface, mixed mode/path invalidity and unnormalizable paths remain REFUSED under `open`.
3. O9n: non-protected non-regular entries, materialization failures, and gate-level recoverable errors are operational UNEVALUATED with reasons; ensure no policy refusal is silently downgraded.
4. O11: PASS+UNEVALUATED; strict FAIL+UNEVALUATED; REFUSED+PASS; WARN+UNEVALUATED in **both** modes (under `strict` it is non-success in `open` and `closed`; under `warn` it follows the UNEVALUATED posture); SKIP-only; check both aggregate decision and preserved subordinate evidence.
5. O12: missing/invalid `MNEME_CI_AVAILABILITY` resolves to closed with a visible configuration warning.
6. Explicit negative tests: checker timeout, Python launch error, adapter/bootstrap failure, wrong blob/sha256, mismatched base/head, bad report, missing summary/annotation, and report posture different from trusted posture. None can create a silent required-check success.
7. Existing CI1.2 fixture replay, ADR-005 global-rule checks, contradictory-output controls, CI1 C1 trusted-surface regression, and CI1 V11 Option A invariants. Re-run the applicable canonical frozen benchmark and capture its exact results; do not alter its fixtures or interpret a historical passing score as new parity evidence.
8. Confirm unchanged evaluator wheel hash and no changes to core `mneme/`, decision IDs, rule IDs, retrieval ordering, or existing hook behavior.

Every row records a deterministic expected classification, outcome and diagnostic. Non-matching behavior is FAIL and stops the rollout. In a multi-file test, incomplete coverage is recorded as incomplete, not backfilled or reclassified.

## 6. Evidence and release ceiling

At Gate 2, record exact Core base/implementation SHA, adapter blob ID and SHA-256, evaluator commit and wheel SHA-256, fixture version, OS/Python version, command invocations, stdout/stderr/exit, report, expected and actual result, and artifact digests. Preserve CI1 source evidence by reference; do not rewrite any historical results.

At the separately approved Gate 3 live lab, require GitHub workflow/check/run ID, genuine app/check identity, head SHA, base SHA, ruleset and Actions-policy snapshot, repository-variable before/after snapshots, reason-labelled report, annotation and job summary, pinned merge request and host API response. Include rollback/re-archive and explicitly record whether an `open` green result remained attached to a test head after reverting posture. No test can leave an untrusted PR quietly mergeable.

ADR-029 relevant enforcement observed is withheld unless all six dimensions bind to the **same** evaluation. A green check, a successful process exit, an `EXCLUDED` result or a SKIP is insufficient.

Installation and release notes must state supported GitHub context, administrative trust, version pins, policy fallback, required check, posture change/recheck caveat, immutable adapter location, exclusions, and production rollout status. Documentation must not imply this is enabled on Core.

## 7. Approval sequence, stop conditions and separate freeze procedure

1. **This charter and the owner's Gate 1 ruling, in one PR:** the owner explicitly accepts or amends this exact charter, including A1-A5, the adapter path, variable name, mode source and bootstrap/report protocol, and the ruling is recorded in this PR (status set to ACCEPTED, as for the C2b and C3 charters). Merging with the ruling recorded is the acceptance; there is no separate post-merge ruling step. Without that ruling, no code.
2. *(Folded into step 1.)*
3. **Freeze amendment:** after this charter merges as accepted, open a **separate** PR titled `[layer1-freeze] authorize ADR-033 C4 CI adapter`, citing this accepted charter and freeze Amendment Procedure §3(b). Merge it before any implementing PR. Its change must be only the narrow authorization described below.
4. **Implementation PR:** only after both preceding approvals, implement Core adapter/tests/versioned fixtures in a reviewed PR. No deployment or lab administration.
5. **Gate 2:** separate authorization to execute and record offline parity/regressions against the pinned implementation.
6. **Gate 3:** separate authorization for lab unarchive, trusted workflow integration, repo variable changes, controlled PRs and actual GitHub merge attempts. Nothing touches Core production CI.
7. **Gate 4:** independent evidence review/closure decision, with all failures and limitations preserved. No production promotion.

**Stop conditions:** discovered mismatch with ADR-033 §2/§5 or A1-A5; attempted evaluator change; inability to pin adapter bytes; inability to preserve trusted refusal under open; a raw failure being classified PASS; unexpected host outcome; or any need to edit Core CI, schema or canonical fixtures. Stop and return to the owner for a new scoped decision.

## 8. Proposed text for the separate freeze amendment (NOT APPLIED)

This is **preview text**, not a modification to the freeze. If Gate 1 is accepted, the subsequent `[layer1-freeze]` PR should append an amendment under the frozen document's Amendment Procedure:

> **Amendment — bounded ADR-033 C4 CI adapter implementation (date of actual owner acceptance).**
>
> **Authority:** accepted ADR-033 §§1-2 and 5-7; C4 Gate 0 charter #676, `9a0c1ae` (A1-A5); accepted C4 Gate 1 charter and explicit owner approval [record links to be filled only when those events occur]. Rationale: Amendment Procedure §3(b), an already-accepted bounded behavioral charter.
>
> **Allowed:** one stdlib-only Core CI adapter outside the wheel; its deterministic tests, versioned availability regression fixtures, associated adapter documentation; approved CI1 evaluator build/hash unchanged. Behavior is restricted to CI required-check interpretation of trusted verdict vs UNEVALUATED vs policy refusal and administrative `open|closed`; it is not a mutation seam.
>
> **Locked:** no modifications to `mneme/`, `DecisionRetriever`, `ConflictDetector`, typed-rule applicability, ADR-030 decision authority, CLI `mneme.check/v1`, canonical benchmarks, frozen CI1 fixtures, `.mneme/`, Core production workflow/rulesets/Actions policy. No new evidence engine or check identity.
>
> **Unchanged claims and limitations:** C3 historical failure/non-guarantees, CI1 P7/P8 and evidence/freshness/decision-update limits, ADR-029 attribution standard, host-specific coverage. The adapter's offline tests do not authorize live GitHub experiments or release deployment.
>
> **Next gates:** Gate 2 offline execution, Gate 3 isolated live lab and Gate 4 closure require separate approvals. Core production merge blocking stays DEFERRED.

No freeze text is written now. It is not permissible to retroactively authorize any implementation from this preview.

## 9. Exclusions carried from Gate 0

No new rule, retriever, conflict-detection or canonical persistence semantics; no malformed-memory CLI redesign; no CI productization for other providers; no live test without Gate 3; no Core production required-check conversion, settings edit, release or installation rollout. The lab stays archived until a separate owner action. C3 R-1 Edit-2 FAIL, F-R2/F-R3-1, Architecture A verifier-unavailable proceed, local enrollment removal, H-2 timeout proceed, MultiEdit N/A, P-6 earlier runtime pin and operator-attested evidence remain untouched.

## 10. Gate 1 owner ruling

**APPROVED:** the human owner explicitly accepted this bounded adapter design, including Gate 0 A1–A5 and review fixes R1–R3, on 2026-10-26. The ruling is recorded in [PR #677](https://github.com/MnemeHQ/mneme/pull/677#issuecomment-6423873813). This acceptance permits the next **freeze-amendment PR proposal**; implementation remains blocked until that separate amendment is approved and merged. Gates 2–4 and production rollout are not authorized.

**Execution provenance**
- Change author: agent
- Agent: ChatGPT
- Agent model: GPT-6
- Agent session: not-exposed
- Task origin: chat
- Human owner: @TheoV823

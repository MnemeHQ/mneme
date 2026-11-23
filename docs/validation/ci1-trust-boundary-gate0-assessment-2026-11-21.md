# CI1 Gate 0: read-only trust-boundary and closure-readiness assessment

**Status:** REVISED AFTER INDEPENDENT REVIEW (`ACCEPT WITH CHANGES` on PR #842 head `ba8cb4cf`); corrections recorded here, revised head not yet independently accepted; owner Gate 0 acceptance pending. No new CI execution or Gate 0 PASS.
**Date:** 2026-11-21
**Pinned Core source:** `main` `3c65915a2ff835b20bc1d6fff4dc2e2220564229` (branch API inspected 2026-11-21).
**Plan:** [CI1 trust-boundary and independent-validation closure](../plans/2026-11-21-ci1-trust-boundary-independent-validation-closure.md).
**Tracker:** [#540](https://github.com/MnemeHQ/mneme/issues/540).

## 1. Method and limits

Read-only inspection through GitHub's repository file, branch and ruleset APIs, cross-checked against existing accepted evidence records and the independent Verification Step 4 #778. No checkout, test suite, new offline replay, live PR/merge attempt, credential inventory, Actions variable read, hash recomputation or new independent scorer was run by the author. Historical experimental PASS/FAIL labels below belong to their original records; this source inspection does **not** reclassify them.

A directly inspected source/ruleset state is `SOURCE-VERIFIED`, not proof of end-to-end execution or a new host test. Historic records are `RECORDED`, not currently remeasured. `NOT VERIFIED` means no direct evidence in this assessment. Additional reviewer-specific observations are marked `REVIEWER-REPORTED`; the reviewer keeps the raw evidence in local custody, and the author of this revision has not independently inspected those files. An independent review of `ba8cb4cf` returned `ACCEPT WITH CHANGES`; approval of this corrected head and owner Gate 0 acceptance remain outstanding.

### 1.1 Independent reviewer relay (2026-11-22)

- **Reviewer:** Claude Opus 5.5 in Claude Code on Windows 11 `10.0.26300`, Git `2.47.1.windows.2`, GitHub CLI `2.88.1`, relayed by the owner; **not** DeepSeek. Target PR #842 at `ba8cb4cfdd373fa32243a490f299b1c02e079fb6`, base `3c65915a2ff835b20bc1d6fff4dc2e2220564229`.
- **Method (reviewer-reported):** source reading at the pin plus GitHub REST GETs (rulesets, Actions policy, availability variable, fork approval, collaborators). No writes, PRs, workflow runs or live probes. Raw API JSON and sources: 29 files under `SHA256SUMS`, digest `5978f0f7fcac918859da5ca572112931852e323b42a313fb17dd99f4c6051c9e`, 29/29 hash check reported OK. `REPORT.md` digest `0fae757b3940c648162af3664f59c6ad40483b4c6e1f8843221730a661434378`.
- **Custody:** `C:\\dev\\ci-tb-evidence\\gate0-review\\` (local reviewer/owner evidence; **not attached to the PR**, not independently byte-verified by this documentation author). Preserve the original files and hashes. To cite their contents as verified artifacts, a later independent reviewer must obtain and verify the bytes.
- **Verdict:** `ACCEPT WITH CHANGES`, documentation only, no newly identified CI implementation defect. Confirmed TB-01/03/04/05/08/09/10/11; TB-02 with a missing check-name caveat; TB-06 with a stronger current credential observation; TB-07 with citation/wording corrections; TB-12's original statement was incorrect. This revision incorporates the requested corrections but is **not** a second reviewer acceptance.

## 2. Read-only controls inspected on 2026-11-21

| Object | Directly observed | Verification ceiling |
|---|---|---|
| Core `main` | `3c65915a2ff835b20bc1d6fff4dc2e2220564229`; source tree available by immutable commit | Current tip when inspected only |
| Workflow `.github/workflows/mneme-trusted-gate.yml` | Blob `3fb1e0ba17ed0849649130b75447a22af18ac8f4`; `pull_request_target` to `main`, `contents: read`, fixed strict mode, fixed evaluator + adapter pins; PR head fetched as Git objects rather than checked out/executed | SOURCE-VERIFIED, not a new live execution |
| Adapter `scripts/ci/adr033_c4_gate.py` | Approved adapter commit `c51729f78199203fe12fcbc5c678b89a2c4f7d3e` (#679), blob `5feedf60ce1a67b2bb85673354c8b8b367a87d06`, SHA-256 `afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9` match workflow pins. `verify-report` checks trusted base/head/mode/pins/posture and recomputes aggregate/disposition | SOURCE-VERIFIED source/pins; **not** an independently attested report |
| Pinned evaluator | Workflow names `0b74d410b45e7b3efcf08d00ce58e7bd7017b757`, approved wheel SHA-256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51` | Pinned by workflow; build parity is RECORDED by historical P2, not re-run |
| Gate ruleset | `mneme-ci-gate`, ID `26391853`, active on `refs/heads/main`, required status `mneme trusted gate` from GitHub Actions integration `15368`, strict freshness true | SOURCE-VERIFIED GitHub ruleset response; no new merge attempt |
| Gate bypass / session reachability | One `User` actor `54006786` with `pull_request` bypass; GitHub GET returns `current_user_can_bypass=pull_requests_only`. Independent reviewer reports active Claude Code session `gh` login `TheoV823` with administrator and `repo`/`workflow` scopes | GitHub ruleset property SOURCE-VERIFIED; session login/scopes REVIEWER-REPORTED (live R6 exposure for **that session**, not every agent or credential) |
| Other branch protections | `main-pr-only`, ID `22196895`, active on `main`, no bypass; PR required, squash only; four other required named checks | SOURCE-VERIFIED ruleset response; no new host behavior |
| CI availability variable | Independent reviewer GET verified `MNEME_CI_AVAILABILITY=closed`, variable `updated_at=2026-11-02T23:14:53Z` | REVIEWER-REPORTED direct GET; source author has not obtained raw API JSON |
| Actions policy | Reviewer GET found repository Actions policy ID `12208`, created 2026-11-09, restricting `pull_request_target` to `.github/workflows/mneme-trusted-gate.yml`. This post-R0 change was absent from the repo's recorded baseline | REVIEWER-REPORTED; live behavior of the policy **not tested**, org Actions settings GET returned HTTP 403 |
| Credential inventory | Reviewer inspected current session login/scopes, but not every administrator-capable credential | TB-06 session exposure verified by reviewer; full inventory and org settings remain UNVERIFIED |

Sources: [workflow](../../.github/workflows/mneme-trusted-gate.yml), [adapter](../../scripts/ci/adr033_c4_gate.py), [R0 S7](ci-r0-s7-closure-2026-11-03.md), [operating decision](ci-r0-operating-status-decision-2026-11-03.md), and the GitHub [gate ruleset](https://github.com/MnemeHQ/mneme/rules/26391853) / [main ruleset](https://github.com/MnemeHQ/mneme/rules/22196895). Ruleset update timestamps remain 2026-11-03. **They do not establish administrative configuration stability:** the reviewer identified post-R0 Actions policy `12208` (2026-11-09). Its runtime effect was not tested. A rule timestamp cannot substitute for an Actions-policy/variable/credential inventory.

## 3. Gap / trust / closure matrix

Dispositions are a **proposal** for independent review, not a current grant of authority or a declaration of a security fix.

| ID | Boundary / question | Evidence reviewed | Proposed disposition | Work needed to close |
|---|---|---|---|---|
| TB-01 | Can same-PR memory substitution make its own policy permissive? | Base policy selection, `.mneme/` refusal, C4/R0 live evidence | **CLOSED (bounded evidence)** | Revalidate only if policy-source contract changes; preserve bypass distinction |
| TB-02 | Can same-PR evaluator/adapter/workflow change replace its own gate? | Trusted source pins and `.github/` refusal; C1 lab and R0; CI1.4 same-name look-alike check caveat | **CLOSED (bounded same-PR evidence)** | Retain caveat: look-alike required-check name with the same GitHub Actions app ID `15368` may be indistinguishable when the genuine check is absent; specific re-runs and absent-genuine-check behavior **UNTESTED**, not a proven bypass |
| TB-03 | Is stale check success sufficient for a changed head/base? | Gate report carries head; GitHub rule strict freshness true; CI1 V11 Option A | **CLOSED for measured GitHub Option A**, conditional | Independent reviewer must inspect exact evaluated head/base vs merge subject in any new run |
| TB-04 | Does `verify-report` independently bind subject/policy to raw evaluator output? | Source + #778 R-1; reviewer inspected single trusted `pull_request_target` job | **ACCEPTED CONTRACT / OFF-JOB EVIDENCE LIMITATION; not a demonstrated CI bypass** | Report and decision run in one trusted job; evaluator pinned, isolated `-I`, neutral cwd and scrubbed environment; PR_HEAD/PR_NUMBER from event and PR files read as data. No PR-author report-write route found by source review. Forgery requires trusted job code execution or R6 administrator control. Correct the C4 guide over-claim separately before alleging a gate defect |
| TB-05 | Can arbitrary caller-supplied bytes be promoted to ADR-029 relevant enforcement? | ADR-029 + #761 + independent #778 | **ACCEPTED EVIDENCE LIMITATION** | No relevant claim for CI literal tier; any new evidence binding separately chartered |
| TB-06 | Can administrator-capable agent credentials modify controls or use human bypass? | R0 R6; live ruleset `current_user_can_bypass=pull_requests_only`; reviewer reports Claude Code session `gh` authenticated as `TheoV823` with admin and `repo`/`workflow` scopes | **R6 LIVE EXPOSURE (reviewer-reported); ACCEPTED dogfooding limitation and unrestricted-readiness blocker** | Segregate agent session credentials from administration only through a separate approved operational decision; no bypass experiment authorized; session observation does not prove all agents have access |
| TB-07 | Does the gate evaluate all shipped typed-rule classes? | C4 classifier **classes** `subject`/ADR-034 numeric records as `UNEVALUATED`; [ADR-029 audit](adr029-evidence-completeness-audit-2026-11-08.md) §3.2 (around L63) and [C4 guide](../integrations/github-actions-c4-gate.md) limitations (around L365-366). Audit E-5 instead concerns the evaluator pin | **ACCEPTED COVERAGE LIMITATION** | Do not write `refuses`: `UNEVALUATED` disposition depends on availability posture; separate evaluator parity and approved re-pin before expansion |
| TB-08 | Are incomplete, missing or malformed `mneme.check/v1` payloads silently accepted? | Payload-first classifier + aggregate/posture implementation; CI1.2 memory-errors and C4 | **CLOSED at adapter classification level** | Do not mistake a CLI traceback for a complete PASS; keep structural CLI crash issue separately scoped |
| TB-09 | Are default-branch / fork / alternate host paths generally verified? | R0 S7 explicitly says forks and first-time contributors unobserved; workflow `main` filter | **ACCEPTED LIMITATION / UNTESTED** | New host test only if chartered; do not generalize beyond `main` and observed PR class |
| TB-10 | Is the evidence reviewer itself independent of the author? | Verification Step 4 independently checked earlier fixtures and exposed R-1/R-3 | **HISTORICAL REVIEW CLOSED; new correction NOT VALIDATED** | Preregister and independently reproduce any new change; do not reuse historical PASS as acceptance for new code |
| TB-11 | Is repo-local `MNEME_MEMORY` host precedence fully solved? | T-08 #815/#818, G3 #822 | **OUT OF CI1 SCOPE; G3 PARTIAL** | No CI1 closure inference; keep Phase 2 and host paths under their existing authorization |
| TB-12 | Are current availability posture and administrator credential exposure directly verified? | Reviewer GET: availability `closed` with timestamp; TB-06 session login + bypass observed | **ORIGINAL ROW CORRECTED: current variable and session exposure confirmed by reviewer; org settings/full inventory UNVERIFIED** | Do not repeat resolved requests. Only org Actions settings (GET 403) and credentials beyond the observed session remain unverified; policy runtime effect likewise untested |

**Interpretation:** R-1 identifies a *verification claim boundary*, not a demonstrated PR-to-report attack. The reviewed source shows evaluation and `verify-report` inside one trusted `pull_request_target` job: the PR cannot rewrite the report without access to trusted execution. The SHA-pinned `upload-artifact` step is between evaluation and decision but does not give an untrusted PR control over the local report. It may merit a precise correction to future documentation/claims without any behavioral modification. A code change to reparse raw evaluator output or cryptographically bind subject/configuration would alter the accepted C4 contract and requires a charter, freeze review if applicable, and fresh independent validation. No default change to the running gate is justified solely by R-1.

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
2. **The smallest justified correction is documentation, not CI engineering:** the [C4 guide](../integrations/github-actions-c4-gate.md) limitation text around lines 369-370 says the decision step catches an inconsistent *or tampered* report. That overstates the coverage shown by #778 R-1: it checks trusted pins, posture and aggregate/disposition consistency, but does not validate a coherently rewritten content digest, memory blob or outcome against raw evaluator stdout. Propose a separately authorized **docs-only** guide correction; do not silently change frozen [Verification Step 3](verification-step3-e2e-fixture-2026-11-09.md) around L100 or [C4 closure](adr033-c4-closure-2026-10-26.md) around L139. No Gate 1 engineering charter is justified by the current evidence.
3. **Broader CI assurance stays limited** by R6, literal-only evaluator scope, source/subject binding gaps and unobserved host cases. These cannot be truthfully closed by a documentation-only PR.
4. **Current variable and session credentials were confirmed by the independent reviewer:** `closed` and live administrator-capable `gh` session, respectively; see TB-06/TB-12 and the custody caveat in §1.1. Org-level Actions settings (403), full credential inventory and actual behavior of Actions policy `12208` remain unverified; no further action may assume otherwise.
5. **A new independent live validation is not automatically justified.** Reuse accepted C4/R0 host results. The look-alike absent-genuine-check/re-run case, fork PRs and policy `12208` runtime effect remain untested. Any new IV-01/02/03/04/06/07 run involves live PR/merge authority; IV-05 is already available from #778; IV-08 can be offline and IV-09 documentary. Only a named new experiment with separate owner authorization may run.

## 6. Reviewer checklist (DeepSeek handoff: read-only first)

- [ ] Re-read exact approved ADR-017/020/023/029/030/031/033 semantics, current CI1 #540, the source-pinned workflow/adapter and current independent review #778.
- [ ] Verify each recorded blob/commit/ruleset response against current immutable GitHub objects; compare with pinned baseline without modifying the repository.
- [x] Independent reviewer confirmed `MNEME_CI_AVAILABILITY=closed` and live R6 session credentials (REVIEWER-REPORTED; raw local custody). Further org/inventory checks remain UNVERIFIED.
- [ ] Examine `verify_report`, `classify_payload`, `run_gate`, `_evaluate_pending` and workflow `Gate decision` directly; reproduce R-1 from a detached pinned copy **only after an approved offline validation charter**, or cite its accepted historical result.
- [ ] Identify any fresh counterexample in which untrusted PR contents influence the trusted policy/evaluator/report; do not assume report-editability merely because tamper tests of a copy passed.
- [ ] Check that the test matrix is minimal and independent, and that every required negative result has a host- or source-supported expected outcome.
- [x] Claude Opus 5.5 independently reviewed original head `ba8cb4cf`: `ACCEPT WITH CHANGES`. Raw report and manifest are locally held; this documentation revision is **not yet reviewed**. This assessment's author cannot self-approve it.
- [ ] Request owner Gate 1 choice; do not implement or run host experiments on the basis of the plan.

## 7. Read-only operational status

- **Completed here:** source/repo/ruleset inspection; architecture reconciliation; draft plan; this draft matrix.
- **Reviewer-reported completion:** one read-only independent review on original head (ACCEPT WITH CHANGES), variable inspection, observed live session credential exposure, and the Actions policy finding. These were relayed; raw evidence is retained locally outside this PR.
- **Still not completed:** review/acceptance of this *revised* head, current org settings/full credential inventory, any new live test or correction, and owner Gate 0 acceptance.
- **Next authorized action:** obtain independent disposition of the revised documentation and the owner's Gate 0 choice. DeepSeek is intended for later separately approved execution, **not** retrospectively the reviewer. No engineering charter justified by this evidence.

## 8. Provenance

- Record author: ChatGPT, 2026-11-21.
- Source pin: `3c65915a2ff835b20bc1d6fff4dc2e2220564229`.
- Type: read-only assessment based on published accepted records, source and read-only GitHub ruleset API; **not independently executed validation**.
- Execution planned: DeepSeek, not yet invoked.
- Owner: @TheoV823.

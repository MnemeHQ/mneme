# CI1 production-readiness reconciliation (2026-10-20)

**Status:** Reconciliation record. Read-only. **No experiment, runtime
change, workflow or ruleset change, `.mneme/` change or `[layer1-freeze]`
amendment is authorized by this document.** Production merge blocking stays
**DEFERRED** ([CI1.4 §7](ci1-4-trusted-merge-gate-validation-2026-10-19.md)).
**Tracker:** #540 (CI1 Enforcement Assurance). This record does not create a
separate approval ledger; approvals stay on #540 and the owning workstreams.
**Core anchor:** `main` @ `c443de87`.

## 1. Purpose

CI1.4 §7 lists nine conditions for any later promotion decision. Work since
CI1.4 was written (C1, lab archive, V11 Option A) changes the status of some
of them. This record maps each condition to its current status, evidence and
owning workstream, names the first decision to take, and dates the one
time-boxed check. It does not rewrite CI1.4; superseded findings are listed in
section 4.

## 2. The nine conditions

| # | CI1.4 §7 condition | Status (2026-10-20) | Evidence | Owner |
|---|---|---|---|---|
| 1 | Separate-PR gate weakening: close or accept, with a designed and tested mitigation | **Mitigated in lab.** C1 trusted-surface refusal proven (B0, L1 to L6). Residual: administrative edits to the ruleset and Actions policy (P7/P8) and any exception route are outside what C1 can constrain | [threat model](../plans/2026-10-19-ci1-gate-weakening-threat-model.md); [C1 charter](../plans/2026-10-19-ci1-c1-lab-validation-charter.md); #540 comment 6270256696 | C1 / P7–P8 administrative trust |
| 2 | Base-revision conformance: evaluate the merge result or require up-to-date branches, then measure | **Validated for GitHub Option A** (squash-only, strict up-to-date, trusted head-diff gate). Conditional: memory on the protected branch; live decision-memory update not tested end to end | [V11 Option A charter](../plans/2026-10-19-ci1-v11-option-a-validation-charter.md); #540 comments 6272349261, 6272698989; CI1.4 §5 as corrected by #568 | CI1 (closed) |
| 3 | ADR-033 decision on UNEVALUATED handling, replacing the lab's fail-closed choice | **Open. Proposed, not accepted.** ADR-033 and a C0 charter exist in draft #483. The ADR's G3-B authorization contract is reconciled for review; the bundled C0 charter is marked unreconciled and must not be accepted as is. **Scope gap:** the draft's first proof is Claude Code `PreToolUse`; it states that CI is a separate verification boundary and defers CI semantics to its gate C4. Accepting the draft as written does not by itself settle UNEVALUATED handling in the CI gate | draft #483 (`docs/adr/ADR-033-opt-in-fail-closed-enforcement.md` §§4.5, 5, implementation gate 6); [G3](../plans/2026-10-14-dg1f-g3-missing-memory-eligibility-assessment.md); [G3-B](../plans/2026-10-14-dg1f-g3b-eligibility-authorization-design.md); #484 (`60b02af3`, verdict coherence, merged) | ADR-033 / DG1-F |
| 4 | Structured malformed-memory result in the CLI contract, or explicit acceptance of the crash path | **Open.** Distinct from 3: an availability policy decides what a caller does with an unavailable evaluation; it does not change the CLI's current behavior (exit 1, traceback, empty stdout; CI1.4 §6.4, V9-A). Needs its own choice: a structured incomplete-evaluation payload with a new fixture version, or recorded acceptance of the crash path | CI1.4 §6.4; V9-A | CI1.2 contract / ADR-033 |
| 5 | Runtime-carried control provenance and subject binding (ADR-029 dimensions 1 and 2), plus a durable evidence record | **Partial.** The lab gate binds base, head, merge-base, memory blob, decision version and rule identity in `gate-report.json`; control provenance and subject binding are still assembled from separate records (check runs, logs, snapshots). Durable copies exist for the lab archive and V11 Option A, held by the executor, not a reviewed evidence store | CI1.4 §4; [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md); #540 comments 6270862573, 6272698989 | ADR-029 / CI1 |
| 6 | A governed path for decision changes under a gate that refuses `.mneme/` edits | **Open.** No authorized route exists; V11 Option A deliberately avoided a live memory update. Requires DG1 decision-update semantics plus a trusted CI administration route that is not an agent-reachable path | CI1.4 §6.7; [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md); [ADR-031](../adr/ADR-031-decision-governance-semantics.md) | DG1 (#497) + P7–P8 |
| 7 | Confirmed `pull_request_target` behavior after 2026-11-02 on the target repository | **Not verified. Time-boxed** (section 3.2) | CI1.4 §6.8; Actions policy `7806` | CI1 / GitHub Actions policy |
| 8 | Coverage beyond one literal rule; production-shaped ruleset (approvals, bypass actors, merge queue) | **Open.** All live evidence uses one literal-tier `FORBID_LITERAL` rule, one protected branch, no approvals, no bypass actors, no merge queue | CI1.4 §6.9 | CI1 validation |
| 9 | A separate rollout charter and `[layer1-freeze]` amendment before any change to `MnemeHQ/mneme` workflows or rulesets | **Process gate, not started.** Required before any production change; not a blocker to the decisions above | CI1.4 §7; [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md) | CI1 / Layer 1 freeze |

**Separate trust boundaries.** Conditions 1, 3 and 6 each involve some form of
override, but they are different authorities and must stay separate:

- **Availability recovery** (3): what happens, and who may proceed, when an
  evaluation is unavailable. ADR-033 defines this contract and its
  authorization requirements.
- **Administrative change to CI controls** (1): who may change the gate,
  ruleset or Actions policy. P7/P8; not decided by ADR-033.
- **Decision change or waiver** (6): who may change or waive the governing
  decisions. DG1 and ADR-030/031; not decided by ADR-033.

## 3. Priority

### 3.1 First architectural decision: condition 3 (ADR-033)

ADR-033 is the first decision to settle. It is a decision rather than
infrastructure, it builds on existing research (G3, G3-B, the
authorization-unverifiable specification) and a merged prerequisite (#484),
and its state model (`UNEVALUATED`, `AUTHORIZATION_UNVERIFIABLE`, verified
absence) is what the CI gate's failure handling and later override routes
need to refer to.

The review should start from draft #483, not a new ADR, and should:

1. Review the ADR against ADR-021, ADR-029, ADR-030, ADR-031 and the G3/G3-B
   findings.
2. Settle policy behavior for unavailable checks, missing memory, opt-in
   authorization and operational recovery.
3. **Decide the CI scope explicitly:** either extend ADR-033 to cover the CI
   gate's UNEVALUATED handling, or record that the CI gate needs its own
   availability decision under ADR-033's state model. Until one of these
   happens, condition 3 stays open for CI even if ADR-033 is accepted.
4. **Record the condition 4 choice separately:** structured CLI failure
   result versus explicit acceptance of the current crash path.
5. Leave the bundled C0 charter unaccepted until it is reconciled with the
   reviewed ADR under the freeze procedure.

### 3.2 Time-boxed check: condition 7 (on or after 2026-11-02)

GitHub's default restriction on `pull_request_target` applies from
2026-11-02 to affected public repositories without an applicable Actions
event policy. The lab has a specific policy (`7806`), which removed the
evaluation-mode warning; that does not show behavior once enforcement
starts.

On or after 2026-11-02, record on #540:

- the applicable Actions policy state for the lab (read-only); and
- observed workflow behavior, **only if** a relevant workflow runs for another
  reason.

The lab stays archived. It is **not** reopened for this check. If no relevant
workflow runs, report host behavior after 2026-11-02 as **unverified**.

### 3.3 Not prioritized now

Conditions 5, 6 and 8 are substantive but depend on, or are better framed
after, the ADR-033 state model. Condition 9 is a gate before production
change, not a design task.

## 4. CI1.4 findings superseded since it was written

CI1.4 is a historical record and is not rewritten here (beyond the §5
correction already merged in #568). These of its statements are now
superseded:

| CI1.4 location | Original statement | Superseded by |
|---|---|---|
| §6.1 | Separate-PR gate weakening structurally identified, untested; no mechanism protects the gate's own definition | C1 lab result (#540 comment 6270256696); residual is P7/P8 |
| §6.3, §5 "Strict status policy" | Correctness against an advanced base depends on conflicts or freshness; strict effect not measured | V11 Option A (#540 comments 6272349261, 6272698989); §5 updated by #568 |
| §6.10 | Lab due to be archived; evidence held locally | Lab archived with digest-verified artifacts and a durable copy (#540 comments 6270380073, 6270862573); re-archived after V11 Option A |
| §7 "Next decision" | Whether the separate-PR weakening experiment must run before promote/defer; then archive the lab | Both done (C1; archive) |

## 5. What remains true

- Production merge blocking is **DEFERRED**.
- No CI1 experiment is pending. No further V11 testing is planned.
- The next substantive step is the ADR-033 review in section 3.1, followed by
  the dated check in section 3.2. Each needs its own approval on #540 or its
  owning workstream.

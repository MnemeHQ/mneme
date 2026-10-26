# ADR-033 C4: CI availability enforcement charter

**Status:** **Gate 0 APPROVED** by the owner on 2026-10-26 with amendments
A1-A5 (section 11) pinned. Documentation only. Approval fixes the scope,
criteria, environment and exclusions. It authorizes no implementation, no
`[layer1-freeze]` amendment, no lab unarchive, no settings change, no
controlled PR and no merge attempt. Gates 1-4 (section 6) each need the
owner's separate, explicit authorization.
**Repository:** `MnemeHQ/mneme`
**Core baseline:** `b7ac024b` (#673, C3 closure)
**Governing decision:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
§§1-2 and 5-7, implementation gate 6 (C4); ADR-017, ADR-020, ADR-021,
ADR-029 to ADR-031; Layer 1 freeze.
**Prior evidence:** CI1.2, CI1.3, CI1 C1, CI1 V11 Option A, CI1.4
([record](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)),
ADR-033 C3 closure
([record](../validation/adr033-c3-closure-2026-10-26.md)).

Amendments A1-A5 are folded into the sections below and listed with their
rationale in section 11. Where the original proposal and an amendment differ,
the amendment governs.

## 1. Objective

Establish whether a GitHub required CI check can apply ADR-033's explicit
availability policy while preserving deterministic decision enforcement and
the existing CI trust boundary.

C4 must distinguish:

- **Trusted decision results:** existing strict/warn semantics.
- **Operational UNEVALUATED:** evaluation unavailable, incomplete or
  untrusted.
- **Policy refusal:** an attempt to modify canonical decision memory or the
  trusted CI control surface, including any path that cannot be shown to lie
  outside it (A1).
- **SKIP:** deletion of a path outside `.mneme/` and the trusted surface.
  Never represented as a verified PASS (A5).

The required status check must reach the correct GitHub merge outcome under
the chosen policy.

## 2. Smallest implementation boundary

One GitHub Actions trusted merge-gate adapter, derived from the CI1 lab gate
(`MnemeHQ/mneme-ci1-lab` `gate/ci1_gate.py` at lab `main` `3cd402fe`).

The adapter must:

1. Read decision memory from the trusted base revision, not the PR.
2. Use the existing `mneme check --json` engine and `mneme.check/v1`
   contract.
3. Establish result coherence (ADR-033 §2) before applying either policy,
   including the warn-mode exit rule (A4).
4. Support an explicit administrator-controlled availability posture, `open`
   or `closed`, read as specified in A3.
5. Preserve the separate violation mode, `strict` or `warn`.
6. Preserve unconditional refusal of `.mneme/` and trusted-surface changes
   under both postures, with path classification before file-type
   classification (A1).
7. Aggregate per-file results with the fixed precedence in A2.
8. Bind the check to the evaluated PR head and the approved evaluator (A5).
9. Report operational failures without manufacturing a PASS or a rule
   violation.

The posture must reside within trusted, administrator-controlled CI
configuration. A PR must not be able to change its own availability posture.

**Placement (A5).** The adapter is a reviewed, standard-library-only script
whose source and tests live in Core, outside the `mneme-hq` wheel. The lab
uses it by exact blob hash. The evaluator stays the CI1-approved commit build
of `0b74d410` (wheel sha256
`e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51`), so the
CI1 P2 parity result remains applicable. A different evaluator pin needs its
own parity proof and the owner's approval at Gate 1.

No new decision model, rule engine, retriever, ConflictDetector, persistence
format or public CLI schema.

## 3. Acceptance criteria

| ID | Criterion | Required outcome |
|---|---|---|
| AC1 | Contract coherence | Invalid, incomplete or contradictory observations never become trusted PASS |
| AC2 | Availability policy | `closed` makes UNEVALUATED non-success; `open` may satisfy the required check but reports UNEVALUATED visibly (A3) |
| AC3 | Policy refusal | `.mneme/` and trusted-surface changes, whatever the file type, remain non-success under both postures (A1) |
| AC4 | Existing enforcement | Trusted complete violations retain their existing strict/warn semantics, both modes covered (A4) |
| AC5 | CI authority | Posture, evaluator and memory originate from the trusted base and administrative control, not PR content |
| AC6 | Host behavior | GitHub actually refuses or permits pinned merge attempts as specified; job exit alone is insufficient |
| AC7 | Regression parity | Canonical benchmark, CI1 contract fixture and relevant adversarial regressions remain intact |
| AC8 | Evidence | Pins, policy, classifications, reasons, GitHub check identity and host outcomes are reproducibly recorded |
| AC9 | Documentation | Installation, configuration, limitations and release implications are documented without claiming production readiness |

All applicable criteria must pass for C4 closure. A failed test remains FAIL;
unexecuted or unsupported coverage remains unverified.

## 4. Offline validation matrix

Run against pinned evaluator and adapter implementations in a disposable,
isolated workspace. "Non-success" means a failing required check; "success"
under `open` always carries the visible UNEVALUATED report from A3.

| Case | Input | `closed` | `open` |
|---|---|---|---|
| O1 | Trusted complete PASS | Success | Success |
| O2 | Trusted complete FAIL, `strict` | Non-success | Non-success |
| O2w | Trusted complete FAIL, `warn` (A4) | Success, violation reported | Success, violation reported |
| O3 | Incomplete applicability / evaluation | Non-success, UNEVALUATED | Success, UNEVALUATED |
| O4 | Missing trusted-base memory | Non-success, UNEVALUATED | Success, UNEVALUATED |
| O5 | Malformed memory / checker crash | Non-success, UNEVALUATED | Success, UNEVALUATED |
| O6 | Checker timeout or launch failure | Non-success, UNEVALUATED | Success, UNEVALUATED |
| O7 | Contradictory schema, mode, verdict or exit code, including warn-mode exit (A4) | Non-success, UNEVALUATED | Success, UNEVALUATED |
| O8 | `.mneme/` mutation (add, edit, delete) | Policy refusal | Policy refusal |
| O8s | Symlink, submodule or other non-regular entry at a `.mneme/` path (A1) | Policy refusal | Policy refusal |
| O9 | Trusted-surface mutation (add, edit, delete) | Policy refusal | Policy refusal |
| O9s | Symlink, submodule or other non-regular entry at a trusted-surface path (A1) | Policy refusal | Policy refusal |
| O9p | Path that cannot be normalized (backslash, NUL, absolute, empty, `.` or `..` component) (A1) | Policy refusal | Policy refusal |
| O9n | Non-regular entry or materialization failure at a normalized path outside `.mneme/` and the trusted surface (A1) | Non-success, UNEVALUATED | Success, UNEVALUATED |
| O10 | Deletion of a path outside `.mneme/` and the trusted surface (A5) | SKIP, never PASS | SKIP, never PASS |
| O10x | Out-of-scope file evaluated with applicability `EXCLUDED` (A5) | Success, trusted PASS | Success, trusted PASS |
| O11 | Mixed complete and incomplete evaluations (A2) | Aggregate per A2 | Aggregate per A2 |
| O12 | Posture variable missing or not exactly `open`/`closed` (A3) | Treated as `closed`, reported | Not applicable (no valid `open`) |

O11 must include at least: PASS + UNEVALUATED; strict FAIL + UNEVALUATED;
refusal + PASS; WARN + UNEVALUATED; SKIP-only.

Use the existing CI1 fixtures. New regression cases belong in separate,
versioned fixtures; historical expectations and the canonical corpus remain
untouched.

The two boundary questions in the original proposal are resolved here
(section 11, A1 and A2) without broadening ADR-033.

## 5. Live GitHub validation

A subsequent, separately approved live session must use an isolated lab, with
the exact gate, evaluator build, memory, workflow, ruleset and posture
variable pinned.

Minimum live probes:

| ID | Scenario | Required evidence |
|---|---|---|
| L1 | Compliant change, explicit `closed` | Genuine required check succeeds; pinned merge succeeds |
| L2 | Deliberately unavailable evaluation, `closed` | Operational UNEVALUATED reported; genuine required check fails; GitHub refuses pinned merge |
| L3 | Deliberately unavailable evaluation, explicit `open` | Report, annotation and job summary say UNEVALUATED, not PASS; check conclusion is `success`; GitHub merge outcome verified |
| L4 | Trusted-surface-only change under `open` | Policy refusal remains non-success; GitHub refuses pinned merge |

Existing CI1 violation, head freshness and same-PR tampering evidence may be
reused by reference, provided the changed adapter's offline regressions pass.
If the integration changes those mechanisms, their relevant live proofs must
be repeated. The A1 reordering changes refusal classification, so O8s and O9s
must pass offline before any live run; a live symlink-at-trusted-path probe
is optional and needs its own approval.

Changing the lab posture is a separately recorded trusted administrative
operation (a repository variable update with before/after snapshots), never
an ordinary PR-controlled configuration change.

## 6. Validation sequence and approval gates

**Gate 0: scope approval.** Done by this document (2026-10-26). No
implementation authority is implied.

**Gate 1: implementation authorization.** Approve the bounded behavior-change
charter and the applicable Layer 1 freeze amendment. Any Core behavior change
uses a reviewed PR.

**Gate 2: offline validation.** Run contract, adversarial and canonical
benchmark parity tests against the approved implementation pins. No live
experiment proceeds with unexplained failures.

**Gate 3: live-lab authorization.** Approve the selected lab, any
unarchiving, administrative settings changes (including the posture
variable), controlled PRs and merge attempts. Capture pre-test settings
before execution.

**Gate 4: evidence and closure.** Preserve raw and redacted evidence, exact
commits, hashes, workflow/check identifiers, GitHub merge responses,
deviations and failed attempts. Review the evidence in a separate closure
record.

Every gate requires explicit authorization. Unexpected outcomes stop the
current execution phase.

## 7. Evidence requirements

Each live probe records:

- Core, adapter, evaluator and fixture commit SHAs, with the adapter blob
  hash and the evaluator artifact SHA-256.
- Trusted base SHA, PR head SHA, merge-base and memory blob identity.
- Posture value, its source (repository variable name) and the variable
  snapshot taken before the run.
- Requested mode, raw checker observation, classification and reason.
- Applicable decision version, rule identity and applicability traces.
- GitHub workflow/run/check identifiers, check conclusion and head SHA.
- Required-check ruleset and applicable Actions policy snapshots.
- Pinned merge request and actual GitHub response.
- Evidence artifact digests and durable retention location.

Record the script hash and the owner's review/go-ahead citation in the
evidence record from the start (C3 lesson).

Separate hook or gate output, GitHub check conclusions and actual merge
authorization. Do not classify a result as *relevant enforcement observed*
under ADR-029 unless all six binding dimensions are established for the same
evaluation.

## 8. Explicit exclusions

C4 does not authorize:

- Changing Core's production `mneme-check.yml`, required checks, rulesets or
  Actions policy. Its implicit, undeclared `open` stays a known gap
  (ADR-033 §5).
- Reopening C3, altering C3 fixtures or reclassifying C3 failures.
- A CLI malformed-memory contract redesign.
- New decision semantics, waivers, exception authority or governed `.mneme/`
  update routes.
- New rule types, retrieval tuning, ConflictDetector changes or canonical
  benchmark modifications.
- Shipping the adapter inside the `mneme-hq` wheel or a new evaluator build
  (A5), unless approved at Gate 1 with its own parity proof.
- Use of the Checks API to create an additional check run (A3).
- Other CI providers, other agent hosts or a reusable multi-platform CI
  product.
- A general claim of reliable fail-closed enforcement, including host
  timeouts outside the tested CI boundary.

## 9. Preserved limitations

C3's original R-1 Edit-2 FAIL, Architecture A verifier-unavailable proceed,
F-R2 history, F-R3-1 classification limitation, removable local enrollment,
H-2 timeout proceed, MultiEdit N/A, P-6 earlier runtime pin and
operator-attestation limitations remain unchanged.

CI1's administrative P7/P8 exposure, governed decision-update gap, rule
coverage limits, partial ADR-029 evidence binding, incomplete merge-race
testing and production rollout restrictions remain separate. Under P7/P8, an
administrator, or an agent token with administrator rights, can change the
posture variable; that is outside what C4 can constrain (ADR-033 §5).

The archived lab's earlier evidence is not treated as fresh C4 proof. GitHub
`pull_request_target` behavior after 2026-11-02 remains unverified until
observed; lab Actions policy `7806` is expected to keep the gate workflow
allowed, and the first live run after that date is its first observation.

## 10. Closure rule

C4 can close only as a **bounded CI availability-policy implementation and
validation milestone** when AC1-AC9 are met and the evidence record is
accepted.

Closure does not authorize deployment to Core's production CI, eliminate CI1
promotion conditions or establish general enforcement safety.

Any production adoption requires its own subsequent rollout decision and
Layer 1 authorization.

## 11. Gate 0 amendments (pinned)

**A1: path classification before file-type classification.** The lab gate's
`refusal()` tests the file mode before the `.mneme/` and trusted-surface
paths. A symlink or submodule at a protected path is therefore classed as
"not a regular file". In CI1 that class blocked, which is why V13-B was
refused. ADR-033 §5 lists non-regular paths as UNEVALUATED, which `open` may
let through, so keeping the CI1 order would let a PR replace the trusted
memory or a workflow with a symlink under `open`, breaking AC3.

Pinned order:

1. A path that cannot be normalized (absolute, backslash, NUL, empty, `.` or
   `..` component) is a **policy refusal**. The gate cannot show such a path
   lies outside `.mneme/` and the trusted surface. This applies the existing
   trusted-surface refusal rule to paths whose target cannot be determined;
   it is not a new refusal class and does not broaden ADR-033.
2. A path under `.mneme/` or on the trusted surface is a **policy refusal**,
   for any change type and any file mode.
3. Otherwise, a non-regular entry or a materialization failure is
   **UNEVALUATED**, as ADR-033 §5 states.

**A2: aggregate precedence and legacy payloads.** Per-file results aggregate
as REFUSED > strict VIOLATION > UNEVALUATED > WARN > PASS. A run whose only
entries are SKIP aggregates to SKIP and never to PASS; under both postures a
SKIP-only run may satisfy the required check but is reported as SKIP. A
payload whose `evaluation_complete` is not exactly `true` is UNEVALUATED
under both postures, with no compatibility shim; only an unapproved evaluator
can emit one, and ADR-033 §2 forbids treating its absence as completeness.
The lab gate's split (file-level UNEVALUATED labelled BLOCK, aggregate
UNEVALUATED reserved for gate errors; V9-A) is replaced by this precedence.

**A3: posture source and `open` visibility.** The posture is a repository
Actions variable, read by the `pull_request_target` workflow in the base
context, so a PR cannot set it and every change is an administrative API
operation with before/after snapshots. A missing value, or any value other
than exactly `open` or `closed`, is treated as `closed` and reported (O12).
A constant in the trusted workflow was rejected because switching posture
between L2 and L3 would itself be a trusted-surface PR that the C1 rule
refuses. Under `open`, an UNEVALUATED aggregate gives job conclusion
`success` with a `::warning::` annotation, a job-summary entry and a report
label `UNEVALUATED` plus reason. The Checks API `neutral` conclusion is not
used: it would add a second check identity, and V7 showed same-app checks are
distinguished by name only.

**A4: warn-mode coverage.** The lab gate requests strict mode only and checks
exit coherence for strict only. The adapter adds the ADR-033 §2 warn rule
(every complete warn result exits 0), and the matrix adds O2w and warn cases
in O7.

**A5: adapter placement, evaluator pin and SKIP definition.** The adapter is a
standard-library-only script reviewed in Core, outside the wheel, and used by
blob hash in the lab; the evaluator stays the CI1-approved `0b74d410` build.
Packaging the adapter would force a new evaluator build and a fresh parity
proof for no engine change. SKIP means only the deletion of a path outside
`.mneme/` and the trusted surface (the lab gate's existing `deleted` skip).
An out-of-scope file evaluated with applicability `EXCLUDED` is a trusted
complete PASS (CI1 V8), recorded as O10x.

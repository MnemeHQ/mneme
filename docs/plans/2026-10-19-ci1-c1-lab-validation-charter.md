# CI1 C1: Trusted-surface refusal, lab implementation and validation charter (proposal)

**Status:** **PROPOSED.** This is a design-only charter. **Nothing here is
executed or authorized.** It does not change `MnemeHQ/mneme-ci1-lab` (its gate,
workflows, tests, ruleset `25313704`, Actions policy `7806` or baseline
`3a87809c`), does not open a lab PR or attempt a merge, does not add a bypass
actor, and changes nothing in `MnemeHQ/mneme`. Section 10 lists the separate
approvals the experiment needs. Production merge blocking stays **DEFERRED**
(CI1.4 §7).
**Tracker:** #540 (CI1 Enforcement Assurance).
**Implements, for review:** the next step named in the
[threat model](2026-10-19-ci1-gate-weakening-threat-model.md) §6: "a separate,
narrowly scoped C1 lab implementation and validation charter ... initially
with **no** bypass actor".
**Builds on:** [CI1.3 charter](2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md)
(structure, §7 evidence, §10 exclusions);
[CI1.4 record](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)
§6.1 and §7 condition 1;
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) §7.
**Lab source read (not modified):** `MnemeHQ/mneme-ci1-lab` @ `3a87809c`:
`.github/workflows/ci1-trusted-gate.yml`, `gate/ci1_gate.py`,
`gate/evaluator-requirements.txt`, `p2/build-constraints.txt`,
`.gitattributes`, `tests/test_ci1_gate.py`, `tests/test_gate_workflow.py`,
`GATE.md`, `README.md`.
**Core anchor:** `main` @ `4823f156`.

## 1. The proof

> **A PR cannot change the trusted surface that will judge later PRs.**

C1 is shown to hold in the lab only when **all** of the following are true:

1. A compliant PR that changes only a trusted-surface file (no `docs/**`, no
   `.mneme/**`) **cannot be merged**. The evidence is GitHub refusing the
   merge (HTTP 405 on the required check), not a red job.
2. That holds for an **addition, a modification, a deletion and a rename**
   on the trusted surface.
3. A compliant PR outside the trusted surface **can** be merged, so the gate
   is not simply always red.
4. A genuine ADR-901 violation is still refused for the same reason as before
   (VIOLATION), so C1 did not weaken the rule path it sits beside.

Anything less is recorded as a partial result, with the failing row named.

C1 is the mechanically enforced part only. It provides **no** route for
legitimate trusted-surface changes. Any such route is a separately trusted
human or administrative exception that C1 cannot constrain (threat model §4),
and is out of scope here.

## 2. Scope

**In scope.** One change to the lab gate (`gate/ci1_gate.py`) and its offline
tests, bootstrapped onto lab `main`, then one short live batch (section 6).

**Out of scope.**
- Any bypass actor, exception route or `GOVERNED_CHANGE` approval flow.
- Admin-controlled settings: ruleset `25313704` (P8) and Actions policy `7806`
  (P7). They stay unchanged and are only observed (section 7).
- C2 (code-owner review), C3 (external app), C4 (separate gate repository).
- Base-revision conformance (CI1.4 V11) and ADR-033.
- Anything in `MnemeHQ/mneme`.

## 3. Trusted surface

The trusted surface is everything a base-commit gate run reads, plus the files
that would let a PR add or replace a check. It is derived from the workflow
and gate at `3a87809c`, not from a general list.

| # | Path (pattern) | Read by a gate run? | Why it is on the surface |
|---|---|---|---|
| S1 | `.github/workflows/ci1-trusted-gate.yml` | Yes: GitHub runs the base copy for `pull_request_target` | Trigger, job name (the required context), steps, the `Gate decision` rule, `EVALUATOR_COMMIT`, `APPROVED_WHEEL_SHA256`, the evaluator `repository:`, `GATE_PYTHON`, pinned action SHAs (threat model P1, P9, P10) |
| S2 | `.github/**` (all other files) | Not by the gate | Any other workflow runs on its own trigger and can post a same-name check from app 15368 (V6, V7, V7b); `p2-evaluator-preflight.yml` is one today. Covers the two-step look-alike path (threat model §1.4) and future files such as `CODEOWNERS` (P4) |
| S3 | `gate/ci1_gate.py` | Yes: `python -I base/gate/ci1_gate.py` | Refusal rules, query, classification, verdict, and (under C1) the trusted-surface list itself (P2) |
| S4 | `gate/**` (all other files) | `gate/evaluator-requirements.txt` yes (copied into the hash-locked install) | P3. The rest of `gate/` is listed so a new file there cannot become a later import or input. `-I` already keeps the script directory off `sys.path` |
| S5 | `p2/**` | `p2/build-constraints.txt` yes (`PIP_CONSTRAINT` for the wheel rebuild) | P3. The wheel hash check fails closed on a changed build, but only while S1 keeps the hash |
| S6 | `.gitattributes` | Indirectly: `actions/checkout` of the base applies it (`* text=auto eol=lf`) | P5. Changes how S4 and S5 are written to disk. Not a known exploit; listed because it is read |
| S7 | `.mneme/**` | Yes, via `git cat-file` from the base | Already refused today (V2, V3, V3a, V13-B). Unchanged by C1, listed for completeness |
| S8 | `policy/**` | No | The recorded specs of ruleset `25313704` and policy `7806`. Not runtime input; protected so the in-repo record of P7/P8 cannot be rewritten through the gated path |

**Not on the surface, with reasons:**
- `tests/**`: not read by any gate run, and no workflow runs it. Weakening a
  test does not change a verdict. Leaving it open keeps C1's own tests
  editable through a later bootstrap-style change. **Open question Q2.**
- `GATE.md`, `README.md`, `docs/**`, `src/**`: not read by the gate. `docs/**`
  stays subject to ADR-901.

**Matching rule.** A changed path is on the surface if it equals a listed file
or starts with a listed directory prefix (`.github/`, `gate/`, `p2/`,
`.mneme/`, `policy/`). Matching is on the normalized repository path, after
the existing refusals for non-regular modes and unnormalized paths, which stay
unchanged.

## 4. Refusal semantics

| PR change touching the surface | Today (`3a87809c`) | Under C1 |
|---|---|---|
| Add a file | Materialized, evaluated as data, VERIFIED_PASS | **Refused** |
| Modify a file (content) | VERIFIED_PASS | **Refused** |
| Modify mode only (`100644` → `100755`) | VERIFIED_PASS | **Refused** |
| Delete a file | `skipped` ("deleted"), not evaluated, does not block | **Refused** (as `.mneme/` deletions already are) |
| Rename within, into or out of the surface | `--no-renames` gives a delete and an add | **Refused** if either side is on the surface |
| Type change to symlink or submodule | Refused (non-regular mode) | Refused, unchanged |

**Requirements on the implementation:**
- A surface refusal **blocks even when it is the PR's only change** (the V3a
  analogue).
- The refusal reason names the trusted surface explicitly (for example
  `trusted surface: PR changes never reach the gate's own inputs`). It must
  be distinguishable in `gate-report.json` from a rule VIOLATION and from the
  existing `.mneme/` and mode refusals. A short `kind` field (for example
  `trusted_surface`, `policy`, `mode`, `path`) is proposed. This is reporting
  only. It does not create an exception path (threat model §4).
- The surface list is a constant in `gate/ci1_gate.py` (on S3). It is not
  read from any file a PR could add.
- Aggregate verdict stays `BLOCK` for any refusal. `UNEVALUATED` stays reserved
  for gate-level errors.
- No other behavior changes: same evaluator, same memory handling, same
  classification, same `Gate decision` step. The workflow file is **not**
  edited.

## 5. Offline validation (before any live run)

Added to the lab's `tests/test_ci1_gate.py` and run locally against the
approved evaluator venv, as V9-A and V12 were.

| # | Test | Expected |
|---|---|---|
| O1 | For each of S1 to S6 and S8: add, modify, mode-change, delete | Refused with the trusted-surface reason; aggregate BLOCK |
| O2 | Rename into, out of, and within the surface | Refused (either side) |
| O3 | A surface change as the PR's only change | BLOCK, zero files evaluated |
| O4 | Nested paths (`gate/sub/x.py`, `.github/workflows/new.yml`) and near-miss names (`gate.md`, `docs/gate/x.md`, `.githubx/y`) | Nested refused; near misses not on the surface and handled as today |
| O5 | Compliant `docs/` change (control) | VERIFIED_PASS, PASS, exit 0 |
| O6 | ADR-901 violation in `docs/` (regression) | VIOLATION, BLOCK, exit 1 |
| O7 | Surface change plus a violation | Both reported; BLOCK |
| O8 | Existing tests (`.mneme/` refusals, modes, traversal, classification, workflow decision) | Unchanged and passing |
| O9 | Workflow coverage: every `base/...` path the workflow reads appears on the surface | Pass. Fails if a later workflow edit introduces an unlisted input |
| O10 | Report shape: refusal records carry the kind and reason; a VIOLATION record does not | Pass |

O1 to O10 must all pass on the implementation commit before the bootstrap PR
is opened.

## 6. Live validation

### 6.1 Bootstrap (B0)

Under today's base gate, the PR that introduces C1 changes only `gate/` and
`tests/`. That gate does not refuse gate paths, so the PR is expected to pass
and merge. This is the threat from the threat model §1, in a benign form.

| # | Scenario | PR contents | Expected gate result | Expected host outcome |
|---|---|---|---|---|
| B0 | Bootstrap C1 | `gate/ci1_gate.py` (C1) + `tests/test_ci1_gate.py` (O1 to O10); optional `GATE.md` note | VERIFIED_PASS for every file (evaluated as data by the **old** base gate) | **HTTP 200**, lab `main` moves |

B0 is also the **first observed instance** of the threat-model prediction "a
PR that changes only the gate's trusted surface merges" (threat model §1.3,
"predicted, never attempted"). It turns that prediction into an observation
without installing a weakened gate. The record must say so, and must not
present it as a bypass.

After B0, every further trusted-surface change, **including a revert of C1**,
is refused by design. Section 8 covers what that means.

### 6.2 Batch (after B0, no bypass actor)

Every row is its own PR from the post-B0 lab `main`, with one pinned squash
merge attempt (`PUT .../pulls/{n}/merge` with `sha=<head>`), run in order,
stopping at the first unexpected result.

| # | Scenario | PR contents | Expected gate result | Expected host outcome |
|---|---|---|---|---|
| L1 | Modify the gate script | Comment-only change to `gate/ci1_gate.py` | `gate/ci1_gate.py` REFUSED (trusted surface); BLOCK | **405** |
| L2 | Delete the gate workflow | Delete `.github/workflows/ci1-trusted-gate.yml` | REFUSED (trusted surface, deletion); BLOCK. The base workflow still runs (`pull_request_target`) | **405** |
| L3 | Rename the gate workflow | `git mv` to `.github/workflows/renamed.yml` | Both sides REFUSED; BLOCK | **405** |
| L4 | Add a workflow | New `.github/workflows/l4-extra.yml`, `pull_request`, job `L4 extra check`, `contents: read`, echo only | REFUSED (trusted surface); BLOCK. Its own job may run and succeed but is not required (V6) | **405** |
| L5 | Compliant control | `docs/` change without the literal | VERIFIED_PASS, PASS | **200** |
| L6 | Violation regression | `docs/` change with `install legacy-client` | VIOLATION (ADR-901 `1eff1b82…`), BLOCK | **405** |

L1 to L4 are the four refusal kinds from §1.2 on the files that matter most.
Evaluator-input files (S4, S5), `.gitattributes` (S6) and `policy/**` (S8) are
covered offline (O1). They reach the host through the same refusal path, so a
live row for each would add little.

L4 deliberately uses a **different** job name. Same-name look-alikes were
measured in V7 and V7b. Mixing them in here would not isolate the C1 refusal.

L5 merges and moves lab `main`. L6 and L1 to L4 stay open as evidence, as in
CI1.3.

## 7. Evidence per row

As CI1.3 charter §7 and as collected for V0 to V13, plus C1-specific items:

- PR number, base SHA, head SHA, merge-base
- `gate-report.json`: per changed path, its mode, whether it was materialized
  or refused, the refusal **kind** and reason; trusted memory blob and its
  source commit; per evaluated file, the raw `mneme.check/v1` payload and
  classification
- the gate run id and event, the `Gate decision` step result, and the
  evaluator wheel line from the job log
- every check run on the head: name, app id, `head_sha`, conclusion
- the artifact name and digest
- the merge API status line, request id and body
- after each row: lab `main` SHA, `main`'s memory blob, and ruleset `25313704`
  and policy `7806` as read back (id, enforcement, `updated_at`). Full ruleset
  and policy JSON once before B0 and once after the batch. CI1.4 §2 named the
  missing per-row snapshot as a gap, so this closes it
- for B0 only: the C1 commit's diff, the offline test run output (O1 to O10),
  and the gate script blob that lands on `main`

The local evidence collector (`ci1_evidence.py`) is executor tooling that has
not been reviewed. It reads; it never decides a row. The record states this.
Raw artifacts expire after about 90 days, so the record quotes the fields it
relies on.

## 8. Bootstrap, rollback and teardown

**Bootstrap.** B0 is the only trusted-surface change that can land through the
gated path, because it lands before C1 is active. Its content must be final
when it merges. Fixes found after B0 cannot use the gated path.

**Rollback after B0.** By design, no PR can revert C1. The options, each a
separately approved admin action outside C1 (P8):

1. **Archive the lab after the batch (preferred).** The lab is temporary. Its
   README plans archiving after CI1.4; this batch would extend its life by one
   step. Archiving needs no revert.
2. **Temporarily set ruleset `25313704` enforcement to `disabled`**, merge a
   revert PR, and re-enable it. This is the documented fallback for an
   unmergeable lab (#540). It is a P8 admin action and is recorded as such,
   not as evidence about C1.

The choice between 1 and 2 must be **made before B0**, because B0 removes the
in-repo way back.

**If the lab becomes unmergeable for other reasons** (for example GitHub
changes `pull_request_target` handling after 2026-11-02 and the required check
stops reporting): stop the batch, record the state, and use option 2 only with
approval. Do not add a bypass actor.

**Timing.** Policy `7806` removed GitHub's evaluate-mode warning, but
enforcement of the default restriction starts 2026-11-02 (CI1.4 §6.8). Running
B0 and the batch before then avoids mixing two unknowns. Running later is
allowed, but the record must say which side of that date each row ran on.

## 9. Outcomes and stop conditions

- **Proven (C1, lab):** B0 merges; L1 to L4 are refused (405) with the
  trusted-surface refusal on the exact head; L5 merges (200); L6 is refused
  as a VIOLATION (405); the evidence in section 7 is complete.
- **NOT PROVEN — C1:** any of L1 to L4 merges, or is refused for a reason
  other than the trusted-surface refusal. Record the row and stop.
- **NOT PROVEN — gate always red:** L5 cannot merge.
- **Regression:** L6 merges, or is no longer a VIOLATION. Stop: C1 weakened the
  rule path.
- **Bootstrap failure:** B0 does not merge under the old gate. That contradicts
  the threat model's prediction and is itself a result. Record it and stop
  before any batch row.

**Stop immediately** (before the next row) on any of: an unexpected gate
verdict or HTTP status; a check run on a different `head_sha`, or from an app
other than 15368; lab `main` moving except by B0 or L5; ruleset `25313704` or
policy `7806` changing (`updated_at`); the evaluator wheel line missing or
not the approved hash; an artifact missing.

A proven result establishes only that **the gated path** cannot change the
trusted surface. It says nothing about P7 or P8 (admin edits), base-revision
conformance (V11) or exception routes, and does not change the CI1.4
recommendation by itself.

## 10. Approvals required before execution

Each is separate:

1. Acceptance of this charter (PR review).
2. Review of the C1 implementation commit and its offline results (O1 to O10)
   **before** B0 is opened, including the surface list in section 3 and the
   open questions in section 12.
3. The post-batch disposition (section 8, option 1 or 2), decided before B0.
4. B0: opening the bootstrap PR and its one pinned merge.
5. The batch L1 to L6, run in order with stop-on-unexpected.

## 11. Explicitly not authorized

- Any change to `MnemeHQ/mneme` workflows, rulesets, `.mneme/`, Core code or
  the frozen benchmark.
- Adding a bypass actor, or any exception route, to any ruleset.
- Changing ruleset `25313704` or Actions policy `7806`, except the section 8
  option 2 fallback under its own approval.
- Editing the lab's gate workflow file as part of C1.
- Running PR-supplied code in any privileged context.
- Deliberately merging a weakened gate, or a violating PR after one (threat
  model §5: not recommended).
- Treating C1 as an approved production control, or as a reason to change the
  CI1.4 DEFER recommendation without a separate decision.

## 12. Open questions

- **Q1. Surface completeness.** Section 3 is derived from the workflow and gate
  at `3a87809c`. O9 checks the workflow's `base/` reads mechanically. Any
  input outside `base/` (for example a new action input) is not covered by O9
  and needs review.
- **Q2. `tests/**`.** Left off the surface because nothing runs it in CI.
  Should C1 protect it anyway, so the offline evidence cannot be edited after
  B0?
- **Q3. `.gitattributes` influence (S6).** Listed because the base checkout
  reads it. Whether a change could alter a verdict was not analyzed.
- **Q4. Reporting field.** The exact name and values of the refusal `kind`
  field, and whether the `Gate decision` step should surface it.
- **Q5. Post-2026-11-02 behavior.** Unknown. Section 8 handles timing, not the
  behavior itself.
- **Q6. Lab lifetime.** Whether the lab is still needed after the batch, for
  example for an exception-route charter. That decides between section 8's
  options.

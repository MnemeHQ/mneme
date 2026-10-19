# CI1 V11: Option A (strict up-to-date + head-diff gate) validation charter (proposal)

**Status:** **PROPOSED.** This is a design-only charter. **Nothing here is
executed or authorized.** It does not unarchive `MnemeHQ/mneme-ci1-lab`,
does not change ruleset `25313704` or Actions policy `7806`, does not edit
lab decision memory, does not open a lab PR or attempt a merge, and changes
nothing in `MnemeHQ/mneme` beyond adding this document. Section 11 lists the
separate approvals each step needs. Production merge blocking stays
**DEFERRED** (CI1.4 §7).
**Tracker:** #540 (CI1 Enforcement Assurance). Related: #488 (revision-bound
conformance).
**Implements, for review:** the next decision agreed in the V11 architecture
review on 2026-10-19: a narrowly scoped validation of **Option A** (require
up-to-date branches, keep the existing trusted head-diff gate) as the first
GitHub-specific conformance model, including the memory-snapshot-only base
advance that has not been tested. Option C (evaluate a constructed merge
result) stays the fallback for integration points that cannot establish the
freshness invariant in section 1.
**Builds on:** [CI1.3 charter](2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md)
(V11 row, §7 evidence);
[C1 charter](2026-10-19-ci1-c1-lab-validation-charter.md) (structure, §7
snapshots, §8 admin fallback);
[CI1.4 record](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)
§5 and §7 condition 2;
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md) (row E:
evidence bound to a different SHA is stale and fails closed);
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md);
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) §7;
[Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md).
**V11 evidence:** #540 comment 6263454460 (phases 1 to 4).
**Lab source read (not modified):** the archived lab bundle
`C:\dev\ci1-tools\evidence\lab-archive\final\mneme-ci1-lab.bundle` (#540
comments 6270380073, 6270862573). Lab `main` @ `3cd402fe`:
`.github/workflows/ci1-trusted-gate.yml` (`EVALUATOR_COMMIT` `0b74d410`),
`gate/ci1_gate.py` (C1), `.mneme/project_memory.json` (blob `dd760bf0`).
Archived `ruleset.json`: `allowed_merge_methods: ["squash"]`,
`strict_required_status_checks_policy: false`, `bypass_actors: []`.
**Core anchor:** `main` @ `c2b78199`.

## 1. The claim under test

> **On GitHub, with squash-only merges and required up-to-date branches, a
> PR can land only in a state the trusted gate has evaluated against the
> current base's decision memory.**

It rests on two invariants that V11 showed to be separate:

1. **Conformance.** The evaluated subject is the change that actually lands.
2. **Freshness.** The evaluation still applies when the host accepts the
   merge: same base, same head, same decision memory.

**Why Option A should deliver both on GitHub (analytic, to be tested):**

- With `strict_required_status_checks_policy: true`, GitHub refuses the
  merge unless the base tip is an ancestor of the PR head.
- When the base tip is an ancestor of the head, the squash result's tree is
  exactly the head's tree. The gate's merge-base..head diff is then the
  whole change that lands, judged against the memory at that base tip.
- If the base moves, including a memory-only change, the PR is behind again.
  Updating it pushes a new head, which triggers `synchronize`, which runs the
  gate afresh against the new base and its memory.

**What Option A does not certify** (stated in the review and kept here):

- **Unchanged repository content.** Only the PR's diff is evaluated. Files
  already on the base are the base's responsibility (baseline violations).
- **Externally managed decision snapshots.** Freshness holds only for memory
  stored on the protected branch. Memory held outside the repository does
  not make a PR "behind" when it changes.
- **Other merge methods or hosts.** The tree-equality argument is made for
  squash-only on GitHub. Portability is not claimed.
- **Throughput.** Every merge makes every open PR behind. The serialization
  cost (#488's merge-queue concern) is recorded as a limit, not measured.

## 2. Scope

**In scope.**
- An offline fixture rebuilt from the archived bundle (section 4), four cases
  (a) to (d), plus two mechanical properties.
- If separately approved: unarchiving the lab for this experiment only, one
  admin memory-only advance, one ruleset change (strict on), and a short live
  batch (section 6).

**Out of scope.**
- Option C (constructing and evaluating a merge result), Option B (a portable
  revision-freshness record) and Option D (merge queue).
- Any change to the gate script, workflow, evaluator pin or decision schema.
  The gate stays the C1 gate at lab `main` `3cd402fe`.
- Any change to `DecisionRetriever`, `ConflictDetector`, ADR-020 applicability,
  the CLI or the frozen benchmark in `MnemeHQ/mneme`.
- A governed route for legitimate decision changes (CI1.4 §6.7, DG1 #497).
  Section 7's admin route is an operator action used to set up a case, not a
  proposed design.
- Production adoption.

## 3. Cases

| Case | Base | Head | Invariant | What Option A must do |
|---|---|---|---|---|
| (a) | M1 `9f1d95a9` | H `e4d45bb8` (literal in `docs/history/v11-note.md`) | Control | Gate PASS (file EXCLUDED). Head is up to date, so it may land |
| (b) | M2 `1bb964dc` (rename to `docs/v11-note.md`) | H, unchanged | Conformance | H is **not** up to date (M2 is not an ancestor of H), so the host must refuse to merge. The gate's stale PASS must not count as evidence for M2 |
| (c) | M2 | H′ = H updated with M2 | Conformance | Gate evaluates `docs/v11-note.md` under `docs/**`: VIOLATION, BLOCK |
| (d) | M3 = memory-only advance (new) | H_d: adds the literal in a **new** file `docs/history/v11a-note.md` | Freshness | Before M3: PASS. After M3: H_d is behind and must not land on the old green. After update: VIOLATION, BLOCK |

**Case (d) in detail.** M3 changes only decision memory: ADR-901's
`FORBID_LITERAL` loses `exclude_paths: [docs/history/**]`. It touches no file
the PR touches, so there is no conflict to stop the merge incidentally. This
is the gap V11 left open ("a base change that alters applicability without
conflicting with the PR's files was not constructed or tested").

Offline, M3 is M2 plus the memory change and H_d branches from M2. Live, M3
is lab `main` (`3cd402fe`) plus the same memory change and H_d branches from
`3cd402fe`. The case is the same; only the parent differs.

(b) and (d) fail differently without Option A, which is why both are needed:

- In (b), a **fresh** gate run on M2 still PASSes, because the merge-base
  stays at M1 and the gate only sees `docs/history/v11-note.md`. The failure
  is evaluation scope.
- In (d), a **fresh** gate run on M3 already reports a VIOLATION, because the
  gate reads memory from the base tip. The failure is only that nothing forces
  a fresh run: the old green check stays valid. The failure is staleness.

## 4. Offline validation

Rebuilt from the archived bundle into a scratch clone. The gate script is the
C1 gate from lab `main` `3cd402fe`, run with `python -I` against the approved
evaluator (`EVALUATOR_COMMIT` `0b74d410`, approved wheel hash) as V9-A and V12
were run. C1 does not change how `docs/**` paths are evaluated; the record
states that the C1 gate, not the V11-era gate, was used.

M3, H_d and H′ are created locally and exist only in the scratch clone. H′ is
`git merge M2` into H with the default configuration; its exact resolution is
recorded.

| # | Check | Expected |
|---|---|---|
| OA1 | Gate, base M1, head H | `docs/history/v11-note.md` EXCLUDED, VERIFIED_PASS, PASS |
| OA2 | Gate, base M2, head H | merge-base M1, PASS (reproduces V11 4b offline) |
| OA3 | `git merge-base --is-ancestor M2 H` | false: H is ineligible under Option A |
| OA4 | Gate, base M2, head H′ | merge-base M2, `docs/v11-note.md` APPLIED, VIOLATION, BLOCK |
| OA5 | Gate, base M2, head H_d | PASS (excluded under memory `dd760bf0`) |
| OA6 | Gate, base M3, head H_d (no update) | merge-base M2, file APPLIED under the new memory, VIOLATION. Confirms (d) is staleness, not scope |
| OA7 | Gate, base M3, head H_d′ = H_d updated with M3 | VIOLATION, BLOCK |
| OA8 | M3 diff against M2 | Only memory (and, if Q2 requires it, the ADR-901 source file). No path overlaps H_d |
| P1 | Tree equality: for every up-to-date pair (M1/H, M2/H′, M3/H_d′), `git merge-tree --write-tree <base> <head>` equals `<head>^{tree}` | Equal for all three |
| P2 | Merge-algorithm record for (b): `git merge-tree --write-tree M2 H` with git version and config recorded | Recorded only. Not a pass/fail condition under Option A (see Q1) |
| OR | Existing lab tests and the Core frozen benchmark | Unchanged and passing; nothing in Core is edited |

Each gate report records base SHA, head SHA, merge-base, memory blob and its
source commit, `decision_version_id`, the rule identity, the per-file
classification and the evaluator wheel line. A PASS in OA2 or OA5 is recorded
as bound to that (base, head, memory) triple only, per ADR-029 row E.

OA1 to OA8 and P1 must all pass before any live step is requested.

## 5. What the offline run cannot show

The offline run shows that the gate gives the right answer **when it is run**
on an up-to-date head. It cannot show that GitHub refuses a behind PR, that
"update branch" triggers a fresh run, or what GitHub's merge machinery does.
Those are host behaviors and need the live steps in section 6.

## 6. Live validation (each step separately approved)

Lab `main` at start: `3cd402fe` (C1 gate, memory `dd760bf0`). Every merge
attempt is a pinned squash merge (`PUT .../pulls/{n}/merge`, `sha=<head>`).
Run in order; stop at the first unexpected result.

| # | Step | Ruleset strict | Action | Expected |
|---|---|---|---|---|
| S0 | Unarchive | off | Unarchive the lab (admin). Full snapshots of ruleset, policy, repo | Snapshots identical to the archived `final/` copies except archive state and `updated_at` |
| A1 | Open H_d | off | PR adding `docs/history/v11a-note.md` with `install legacy-client` | Gate PASS (EXCLUDED), check success. **No merge attempt** |
| A2 | Memory-only advance (admin route, section 7) | off | M3 lands on `main` | `main` moves by exactly one memory-only commit |
| A3 | Observe the stale green | off | Read H_d's check runs and merge state. **No merge attempt** | Check still success on the same head; GitHub reports it mergeable. This is the measured freshness gap. Merging here would land a violation, so it is not attempted |
| A4 | Enable strict | **on** | Ruleset change (P8 admin), section 8 | Snapshot shows only `strict_required_status_checks_policy: true` and `updated_at` changed |
| A5 | Behind refusal | on | Pinned merge of H_d's unchanged head | **405**, reason: branch not up to date. The old green does not satisfy the merge |
| A6 | Update and re-evaluate | on | Update H_d's branch with `main` (merge update) | New head, `synchronize` gate run on base M3: VIOLATION, BLOCK. Pinned merge → **405** (required check failed) |
| A7 | Compliant control, up to date | on | New PR from M3: `docs/` change without the literal | PASS, **200**. `main` moves to M4 |
| A8 | Compliant PR made behind | on | PR opened from M3 before A7 merged, compliant, different file | After A7: pinned merge **405** (behind). Update branch, fresh run PASS, pinned merge **200** |
| A9 | V11 PR #20 | on | Read state only. **No merge attempt** | Still not mergeable (dirty and behind). Recorded for completeness |

A5 is the only step that attempts to merge a head whose content violates the
current memory while its check is green. Its purpose is to show the host
refuses it. If it returns 200, the violating file lands on lab `main`: record
it, stop, and treat the lab as compromised for further rows. This risk is
named in approval item 6.

## 7. The memory-only admin route (A2)

In the lab, decision memory cannot change through a PR: the C1 gate refuses
every `.mneme/` change (`kind: policy`), and the ruleset requires a PR with no
bypass actor. A2 therefore needs an administrative action outside the gated
path. The proposed route is the one the C1 charter §8 option 2 already names
as the documented fallback:

1. Snapshot ruleset `25313704` and policy `7806`.
2. Set ruleset enforcement to `disabled`.
3. Push exactly one commit to `main`: the memory change from section 3,
   case (d), produced as Q2 decides. No other change.
4. Set enforcement back to `active`.
5. Snapshot again. Expected: identical to step 1 except `updated_at`.

Rules for the route:

- **No bypass actor** is added (C1 charter §11).
- No PR may be merged or opened while enforcement is disabled. The window is
  recorded with timestamps.
- The record labels A2 an **admin action used to construct a case**, not
  evidence about Option A and not a design for decision changes.
- The exact memory diff, old and new blob SHAs, and old and new
  `decision_version_id` and rule identity for ADR-901 are recorded (ADR-030).

## 8. Ruleset change (A4)

One field changes: `required_status_checks.parameters.strict_required_status_checks_policy`
from `false` to `true`. Required context `CI1 trusted gate`, `integration_id`
`15368`, `allowed_merge_methods: ["squash"]`, `bypass_actors: []` and all other
rules stay as archived. The change is made after A3 so the stale-green state
is observed first.

## 9. Evidence per step

As C1 charter §7 (PR, base, head, merge-base, `gate-report.json`, check runs
with app id and `head_sha`, artifact name and digest, merge API status line,
request id and body, full ruleset and policy snapshots before and after every
merge attempt and every admin action), plus:

- GitHub's reported `mergeable`, `mergeable_state` and `mergeStateStatus` for
  the PR at each observation, with timestamps
- lab `main` SHA and its `.mneme/project_memory.json` blob before and after
  each step
- for A6 and A8: the update commit SHA, its parents and the event that
  triggered the new gate run
- for A2: the enforcement-disabled window and the memory diff (section 7)
- for every up-to-date merge that lands (A7, A8): the squash commit's tree
  equals the evaluated head's tree (P1, live)

Raw artifacts expire in about 90 days; the record quotes what it relies on.

## 10. Outcomes and stop conditions

- **Proven (Option A, lab):** OA1 to OA8 and P1 pass; A3 shows the stale
  green; A5 and A8's first attempt are refused as behind; A6 is refused as a
  VIOLATION after a fresh run on M3; A7 and A8's second attempt merge with
  tree equality; evidence complete.
- **NOT PROVEN, freshness:** A5 or the behind attempt in A8 merges.
- **NOT PROVEN, conformance:** A6's fresh run does not report the VIOLATION,
  or a landed squash tree differs from the evaluated head tree.
- **NOT PROVEN, always red:** A7 cannot merge.
- **Gap not reproduced:** A3 shows the PR not mergeable for a reason other
  than strict mode. Record it; continue only with approval.

**Stop immediately** on any unexpected verdict or HTTP status; a check run on
a different `head_sha` or from an app other than 15368; lab `main` moving
other than by A2, A7 or A8; the ruleset or policy changing other than at A2 or
A4; the evaluator wheel line missing or not the approved hash; an artifact
missing.

A proven result covers only: GitHub, squash-only, one protected branch, memory
stored on that branch, one literal-tier rule. It does not change the CI1.4
DEFER recommendation by itself.

## 11. Approvals required before execution

Each is separate:

1. Acceptance of this charter (PR review), including the open questions.
2. The offline run (section 4). No GitHub change.
3. **Unarchiving the lab** and extending its lifetime for this experiment
   only, with the end condition (batch complete or stopped) and the teardown
   in item 7 fixed in advance.
4. The admin memory-only advance (A2), via the route in section 7.
5. The ruleset change (A4).
6. The live rows A1, A3, A5 to A9, in order, including A5's named risk.
7. Teardown: preserve evidence as the 2026-10-19 archive did (artifact digests
   against GitHub's, bundle, logs, snapshots, durable copy), decide whether to
   set strict back to `false` first, then re-archive.

No unarchive, admin action, ruleset change, PR or merge attempt happens
without the matching approval.

## 12. Explicitly not authorized

- Any change to `MnemeHQ/mneme` workflows, rulesets, `.mneme/`, Core code or
  the frozen benchmark, and any Layer 1 freeze amendment.
- Adding a bypass actor or exception route to any ruleset.
- Editing the lab gate, workflow, evaluator pin or tests.
- Implementing Option B, C or D.
- Merging any head while its check is green against stale memory (A3).
- Treating a proven result as a production control or as grounds to change
  the CI1.4 recommendation without a separate decision.

## 13. Open questions

- **Q1. Merge semantics record.** CI1.4 §5 says no conflict-free violating
  fixture was found under default git merge semantics. A check on 2026-10-19
  with git 2.47.1 and no merge config found that
  `git merge-tree --write-tree 1bb964dc e4d45bb8` exits 0 and places
  `install legacy-client` in `docs/v11-note.md` (rename/modify, not a
  directory rename). GitHub reported the same pair as DIRTY. The two
  statements should be reconciled in the record. Option A does not depend on
  the answer: a behind PR is refused whatever the merge algorithm would do.
- **Q2. How M3 is produced.** The memory change must keep ADR-030 identities
  meaningful: a new decision version and rule identity for ADR-901, produced
  by approved tooling at the pinned evaluator, not hand-edited. Whether the
  ADR-901 source file (`adr/ADR-901-...md`, bound by `source.sha256`) must
  change in the same commit is to be decided before item 4.
- **Q3. GitHub merge-state values.** The exact `mergeable_state` reported for a
  behind PR with strict off versus on is not documented as a contract.
  Expected values are written as observations to record, not as the pass
  criterion; the pass criterion is the merge API status.
- **Q4. Update method.** A6 and A8 use a merge update. A rebase update rewrites
  the head; the tree-equality argument holds for both, but only the merge
  update is in scope.
- **Q5. Post-2026-11-02 behavior.** As C1 charter §8: the record states which
  side of GitHub's `pull_request_target` default restriction each step ran
  on.
- **Q6. External memory.** Option A gives no freshness for decision memory
  stored outside the protected branch. Whether a later charter needs Option B
  for that case is open.

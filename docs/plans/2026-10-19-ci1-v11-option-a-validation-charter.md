# CI1 V11: Option A (strict up-to-date + head-diff gate) validation charter (proposal)

**Status:** **PROPOSED, revision 2.** This is a design-only charter. **Nothing
here is executed or authorized.** It does not unarchive
`MnemeHQ/mneme-ci1-lab`, does not change ruleset `25313704` or Actions policy
`7806`, does not edit lab decision memory, does not open a lab PR or attempt a
merge, and changes nothing in `MnemeHQ/mneme` beyond adding this document.
Section 11 lists the separate approvals each step needs. Production merge
blocking stays **DEFERRED** (CI1.4 §7).
**Revision 2** answers the first independent review of this PR: Q2 resolved
(section 4.1), the admin step restated as a new adaptation rather than C1 §8
option 2 (section 7), a harmless strict-refusal control placed ahead of the
stale-green attempt and that attempt split into its own approval (sections 6
and 11), A7/A8 sequencing repaired, teardown configuration fixed in advance
(section 8), and Q1 corrected to distinguish V11 from V11b.
**Tracker:** #540 (CI1 Enforcement Assurance). Related: #488 (revision-bound
conformance).
**Implements, for review:** the next decision agreed in the V11 architecture
review on 2026-10-19: a narrowly scoped validation of **Option A** (require
up-to-date branches, keep the existing trusted head-diff gate) as the first
GitHub-specific conformance model, including the decision-snapshot-only base
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
**V11 evidence:** #540 comments 6263454460 (V11 phases 1 to 4) and 6263559908
(V11b offline directory-rename follow-up).
**Lab source read (not modified):** the archived lab bundle
`C:\dev\ci1-tools\evidence\lab-archive\final\mneme-ci1-lab.bundle` (#540
comments 6270380073, 6270862573). Lab `main` @ `3cd402fe`:
`.github/workflows/ci1-trusted-gate.yml` (`EVALUATOR_COMMIT` `0b74d410`),
`gate/ci1_gate.py` (C1), `.mneme/project_memory.json` (blob `dd760bf0`).
Archived `ruleset.json`: `allowed_merge_methods: ["squash"]`,
`strict_required_status_checks_policy: false`, `bypass_actors: []`.
Read-only GitHub check on 2026-10-19: the lab's `main` has **no classic branch
protection** (`GET .../branches/main/protection` → 404 "Branch not
protected"); the rules applying to `main` are the ruleset's `deletion`,
`non_fast_forward`, `pull_request` and `required_status_checks`.
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
- If the base moves, including a decision-only change, the PR is behind
  again. Updating it pushes a new head, which triggers `synchronize`, which
  runs the gate afresh against the new base and its memory.

**What Option A does not certify:**

- **Unchanged repository content.** Only the PR's diff is evaluated. Files
  already on the base are the base's responsibility (baseline violations).
- **Externally managed decision snapshots.** Freshness holds only for memory
  stored on the protected branch. Memory held outside the repository does
  not make a PR "behind" when it changes.
- **Other merge methods or hosts.** The tree-equality argument is made for
  squash-only on GitHub. Portability is not claimed.
- **Throughput.** Every merge makes every open PR behind. The serialization
  cost (#488's merge-queue concern) is recorded as a limit, not measured.
- **Races.** Concurrent updates, in-flight checks and the post-push window
  (CI1.4 §6.6) are not exercised. This is a coverage limit of this first
  validation.

## 2. Scope

**In scope.**
- An offline fixture rebuilt from the archived bundle (section 4), four cases
  (a) to (d), plus two mechanical properties.
- If separately approved: unarchiving the lab for this experiment only, one
  administrative decision-snapshot advance, one ruleset change (strict on),
  and a short live batch (section 6).

**Out of scope.**
- Option C (constructing and evaluating a merge result), Option B (a portable
  revision-freshness record) and Option D (merge queue).
- Any change to the gate script, workflow, evaluator pin or decision schema.
  The gate stays the C1 gate at lab `main` `3cd402fe`.
- Any change to `DecisionRetriever`, `ConflictDetector`, ADR-020 applicability,
  the CLI, the frozen benchmark, or the frozen Core fixture
  `tests/fixtures/ci1_contract/path_scoped_forbid_literal/v1/` in
  `MnemeHQ/mneme`.
- A governed route for legitimate decision changes (CI1.4 §6.7, DG1 #497).
  Section 7's admin step is an operator action used to set up a case, not a
  proposed design.
- Correcting CI1.4 §5's wording (Q1). That is a separate docs change.
- Production adoption.

## 3. Cases

| Case | Base | Head | Invariant | What Option A must do |
|---|---|---|---|---|
| (a) | M1 `9f1d95a9` | H `e4d45bb8` (literal in `docs/history/v11-note.md`) | Control | Gate PASS (file EXCLUDED). Head is up to date, so it may land |
| (b) | M2 `1bb964dc` (rename to `docs/v11-note.md`) | H, unchanged | Conformance | H is **not** up to date (M2 is not an ancestor of H), so the host must refuse to merge. The gate's stale PASS must not count as evidence for M2 |
| (c) | M2 | H′ = H updated with M2 | Conformance | Gate evaluates `docs/v11-note.md` under `docs/**`: VIOLATION, BLOCK |
| (d) | M3 = decision-snapshot-only advance (new) | H_d: adds the literal in a **new** file `docs/history/v11a-note.md` | Freshness | Before M3: PASS. After M3: H_d is behind and must not land on the old green. After update: VIOLATION, BLOCK |

**Case (d) in detail.** M3 changes only the lab's decision memory: ADR-901
gets a new canonical version whose `FORBID_LITERAL` no longer has
`exclude_paths: [docs/history/**]` (section 4.1). The lab commit touches only
`.mneme/project_memory.json`, so nothing overlaps the PR's files and no
conflict can stop the merge incidentally. This is the gap V11 left open ("a
base change that alters applicability without conflicting with the PR's
files was not constructed or tested").

Offline, M3 is M2 plus the memory change and H_d branches from M2. Live, M3
is lab `main` (`3cd402fe`) plus the same memory change and H_d branches from
`3cd402fe`. The case is the same; only the parent differs.

**How (b) and (d) differ.** Without Option A, both can be accepted unsafely,
but for different reasons:

- In (b), unsafe acceptance needs **two** things at once: a scope-blind
  evaluation (a fresh run on M2 still PASSes, because the merge-base stays at
  M1 and the gate only sees `docs/history/v11-note.md`) **and** no base
  freshness requirement at merge time. Option A removes the second; the first
  remains a property of the head-diff gate and is why an update is required.
- In (d), a **fresh** gate run on M3 already reports a VIOLATION, because the
  gate reads memory from the base tip. The only failure is that nothing
  forces a fresh run: the old green check stays valid. This is pure
  staleness.

## 4. Offline validation

Rebuilt from the archived bundle into a scratch clone. The gate script is the
C1 gate from lab `main` `3cd402fe`, run with `python -I` against the approved
evaluator (`EVALUATOR_COMMIT` `0b74d410`, approved wheel hash) as V9-A and V12
were run. C1 does not change how `docs/**` paths are evaluated; the record
states that the C1 gate, not the V11-era gate, was used.

M3, H_d and H′ are created locally and exist only in the scratch clone. H′ is
`git merge M2` into H with the default configuration; its exact resolution is
recorded.

### 4.1 How M3's memory is produced (Q2, resolved)

ADR-030 requires immutable decision versions, content-derived rule identities
and truthful source provenance, so the exclusion is not edited in place.

1. **Derived source.** Copy ADR-901's source from the frozen Core fixture
   `tests/fixtures/ci1_contract/path_scoped_forbid_literal/v1/adr/ADR-901-ci1-fixture-scoped-installer.md`
   into a scratch ADR directory **outside** both repositories, and remove only
   the `exclude_paths` entry. The frozen fixture is not modified. ADR-902 is
   copied unchanged.
2. **Import at the pinned evaluator.** From a clean install of `MnemeHQ/mneme`
   at `0b74d410`, run against a copy of the lab memory (blob `dd760bf0`):
   `mneme adr import <scratch-adr-dir> --memory <copy> --dry-run`, then
   `--apply --update-existing --expected-predecessor ADR-901=dver-d3d431ff6d5edba8b555a040a7b85f9b`.
   The tool, not a hand edit, writes the new version.
3. **Provenance.** The derived ADR text, its sha256, the dry-run and apply
   output, and the old and new `decision_version_id` and rule identities are
   preserved as evidence. The new version's `source.sha256` must equal the
   derived file's sha256.
4. **Why the lab commit stays memory-only.** ADR sources have never been in
   the lab repository; every lab payload already reports the freshness
   channel as `ADR_MISSING` (CI1.4 §5). The lab change is therefore exactly
   one file, `.mneme/project_memory.json`. Its provenance is the preserved
   derived source, not a file in the lab.

If step 2 fails, or produces anything other than one new ADR-901 version with
ADR-902 unchanged, stop: case (d) is not constructed and no live step is
requested.

### 4.2 Checks

| # | Check | Expected |
|---|---|---|
| OA1 | Gate, base M1, head H | `docs/history/v11-note.md` EXCLUDED, VERIFIED_PASS, PASS |
| OA2 | Gate, base M2, head H | merge-base M1, PASS (reproduces V11 4b offline) |
| OA3 | `git merge-base --is-ancestor M2 H` | false: H is ineligible under Option A |
| OA4 | Gate, base M2, head H′ | merge-base M2, `docs/v11-note.md` APPLIED, VIOLATION, BLOCK |
| OA5 | Gate, base M2, head H_d | PASS (excluded under memory `dd760bf0`) |
| OA6 | Gate, base M3, head H_d (no update) | merge-base M2, file APPLIED under the new memory, VIOLATION. Confirms (d) is staleness, not scope |
| OA7 | Gate, base M3, head H_d′ = H_d updated with M3 | VIOLATION, BLOCK |
| OA8 | `git diff --name-only M2 M3` | exactly `.mneme/project_memory.json`; no path overlaps H_d |
| OA9 | Import result (section 4.1) | one new ADR-901 version whose predecessor is `dver-d3d431ff…`; ADR-902 version unchanged; `source.sha256` matches the derived source |
| P1 | Tree equality: for every up-to-date pair (M1/H, M2/H′, M3/H_d′), `git merge-tree --write-tree <base> <head>` equals `<head>^{tree}` | Equal for all three |
| P2 | Merge-algorithm record for (b): `git merge-tree --write-tree M2 H` with git version and config recorded | Recorded only. Not a pass/fail condition under Option A (see Q1) |
| OR | Existing lab tests and the Core frozen benchmark | Unchanged and passing; nothing in Core is edited |

Each gate report records base SHA, head SHA, merge-base, memory blob and its
source commit, `decision_version_id`, the rule identity, the per-file
classification and the evaluator wheel line. A PASS in OA2 or OA5 is recorded
as bound to that (base, head, memory) triple only, per ADR-029 row E.

OA1 to OA9 and P1 must all pass before any live step is requested.

## 5. What the offline run cannot show

The offline run shows that the gate gives the right answer **when it is run**
on an up-to-date head. It cannot show that GitHub refuses a behind PR, that
"update branch" triggers a fresh run, or what GitHub's merge machinery does.
Those are host behaviors and need the live steps in section 6.

## 6. Live validation (approvals per section 11)

Lab `main` at start: `3cd402fe` (C1 gate, memory `dd760bf0`). Every merge
attempt is a pinned squash merge (`PUT .../pulls/{n}/merge`, `sha=<head>`).
Run in order; stop at the first unexpected result.

| # | Step | Strict | Action | Expected |
|---|---|---|---|---|
| S0 | Unarchive | off | Unarchive the lab (admin). Full snapshots of ruleset, policy, repo, `main` rules | Identical to the archived `final/` copies except archive state and `updated_at` |
| A1 | Open H_d | off | PR from `3cd402fe` adding `docs/history/v11a-note.md` with `install legacy-client` | Gate PASS (EXCLUDED), check success. **No merge attempt** |
| A2 | Decision-snapshot advance (admin, section 7) | off | M3 lands on `main` | `main` moves by exactly one commit touching only `.mneme/project_memory.json` |
| A3 | Observe the stale green | off | Read H_d's check runs and merge state. **No merge attempt** | Check still success on the same head; GitHub reports it mergeable. This is the measured freshness gap |
| A4 | Enable strict | **on** | Ruleset change (section 8) | Snapshot shows only `strict_required_status_checks_policy: true` and `updated_at` changed |
| A5 | Harmless behind refusal | on | Open two compliant PRs from M3, **both before either merges**: PX (`docs/` file X) and PY (`docs/` file Y, no overlap). Both gate PASS. Pinned merge of PX → **200**; `main` moves to M4. PY is now behind. Pinned merge of PY's unchanged head → **405** | The 405 is attributable to freshness only: PY's required check is success on that head, no conflict, `mergeable_state` reports behind, and the response body names the out-of-date branch |
| A6 | Behind PR recovers | on | Update PY with `main` (merge update). Fresh `synchronize` gate run PASS on base M4. Pinned merge → **200** | Strict is not "always red"; tree equality holds on the landed commit |
| A7 | Stale-green adversarial attempt (**own approval, optional**) | on | Pinned merge of H_d's unchanged head (green on old memory, behind M3/M4) | **405**, freshness. See the risk and pre-attempt checks below |
| A8 | Update and re-evaluate H_d | on | Update H_d with `main`. Fresh gate run on the current base: VIOLATION, BLOCK. Pinned merge → **405** (required check failed) | The new memory applies once a fresh run is forced |
| A9 | V11 PR #20 | on | Read state only. **No merge attempt** | Still not mergeable (dirty and behind). Recorded for completeness |

**Minimal finding without A7.** A5, A6 and A8 together establish the central
claims: strict refuses a behind head for freshness reasons alone, a behind PR
recovers only through a fresh evaluation, and a fresh evaluation applies the
advanced decision snapshot. A7 adds direct adversarial evidence about the
stale-green case and is not a prerequisite.

**A7 risk.** A7 is the only step that attempts to merge a head whose content
violates the current memory while its check is green. If GitHub returns 200,
the violating file lands on lab `main`. The stop rule limits further damage
but cannot undo that first merge. A7 runs only if A5 and A6 matched
expectations, and only under its own approval.

**A7 pre-attempt checks**, read immediately before the `PUT` and recorded:
lab `main` SHA equals the expected M4; H_d's head SHA equals the A1 head; the
only success check on that head is `CI1 trusted gate` from app 15368; the
ruleset snapshot shows strict `true` and enforcement `active`; GitHub reports
no conflict for H_d; no other blocking cause (review, draft state) applies.
Any mismatch: do not attempt.

`mergeable_state` is supporting evidence throughout. The pass criterion for
every refusal is the merge API status and body.

## 7. The decision-snapshot admin step (A2)

**Why an admin step.** In the lab, decision memory cannot change through the
gated path: the C1 gate refuses every `.mneme/` change (`kind: policy`), and
the ruleset requires a PR with no bypass actor. CI1.4 §6.7 records this.

**What this is not.** C1 charter §8 option 2 disables enforcement in order to
merge a **revert PR** that restores the lab. A2 is a **new adaptation** of
the same temporary-disable mechanism, used to **construct a case**. It is not
a validated procedure and needs its own approval (section 11, item 4).

**Procedure.** A2 uses a PR rather than a direct push, so the change has a
reviewable record and an exact head SHA:

1. Open PR "M3 decision snapshot" from current `main`, changing only
   `.mneme/project_memory.json` to the bytes produced in section 4.1 (blob SHA
   recorded and compared before the PR is opened).
2. Record that the gate refuses it (`kind: policy`, BLOCK). This is expected
   and is evidence that the gated path cannot carry the change.
3. Snapshot ruleset `25313704`, policy `7806` and the rules applying to
   `main`.
4. Set ruleset enforcement to `disabled`.
5. Pinned squash merge of that PR's exact head.
6. Set enforcement back to `active`.
7. Snapshot again. Expected: identical to step 3 except `enforcement`
   history and `updated_at`. Verify `git diff --name-only <before> <after>`
   on `main` is exactly `.mneme/project_memory.json` and the landed blob
   equals the section 4.1 output.

**Rules.**
- **No bypass actor** is added (C1 charter §11).
- No other PR is opened, updated or merged while enforcement is disabled. The
  window is recorded with timestamps.
- The record labels A2 an **admin action used to construct a case**, not
  evidence about Option A and not a design for decision changes.

**Recovery.** If enforcement cannot be set back to `active`, or the step 7
snapshot differs in any other field: stop the batch, open no further PRs,
restore the ruleset by `PUT` from the step 3 snapshot, snapshot again, and
record the episode. If restoration also fails, archive the lab immediately
and record its state. No live row runs until a restored snapshot matches.

## 8. Ruleset change (A4) and final configuration

**A4.** One field changes:
`required_status_checks.parameters.strict_required_status_checks_policy`
from `false` to `true`. Required context `CI1 trusted gate`, `integration_id`
`15368`, `allowed_merge_methods: ["squash"]`, `bypass_actors: []` and all other
rules stay as archived. The change is made after A3 so the stale-green state
is observed first.

**Final configuration (fixed now, before unarchiving).** After the batch
completes or stops, and after evidence is preserved (section 11, item 8):

1. Set `strict_required_status_checks_policy` back to `false`, so the
   archived ruleset matches the CI1 final record (`final/ruleset.json`) in
   every field except `updated_at`. Snapshot and diff against the archive.
2. Leave every lab PR from this batch open except those that merged (PX, PY,
   and A2's PR). Lab `main` keeps M3 and the control commits; they are part
   of the record.
3. Re-archive the lab.

**If the final configuration cannot be restored** (for example the ruleset
`PUT` fails): archive anyway, record the actual final ruleset, and note the
difference from `final/ruleset.json` in the record. Archiving makes the
repository read-only, so a wrong ruleset cannot be exercised.

## 9. Evidence per step

As C1 charter §7 (PR, base, head, merge-base, `gate-report.json`, check runs
with app id and `head_sha`, artifact name and digest, merge API status line,
request id and body, full ruleset and policy snapshots before and after every
merge attempt and every admin action), plus:

- GitHub's reported `mergeable`, `mergeable_state` and `mergeStateStatus` for
  the PR at each observation, with timestamps
- lab `main` SHA and its `.mneme/project_memory.json` blob before and after
  each step
- for A5, A6 and A8: the update commit SHA, its parents and the event that
  triggered the new gate run
- for A2: the section 4.1 provenance, the enforcement-disabled window, and the
  step 7 diff
- for A7, if run: the pre-attempt checks
- for every up-to-date merge that lands (PX, PY): the squash commit's tree
  equals the evaluated head's tree (P1 property, live)

Raw artifacts expire in about 90 days; the record quotes what it relies on.

## 10. Outcomes and stop conditions

- **Proven (Option A, lab):** OA1 to OA9 and P1 pass; A3 shows the stale
  green; A5's behind attempt is refused for freshness alone; A6 recovers
  through a fresh run and lands with tree equality; A8 is refused as a
  VIOLATION after a fresh run on the advanced snapshot; evidence complete.
  A7, if run, is refused (405) as behind.
- **NOT PROVEN, freshness:** A5's behind attempt or A7 merges, or A5's
  refusal cannot be attributed to freshness alone.
- **NOT PROVEN, conformance:** A8's fresh run does not report the VIOLATION,
  or a landed squash tree differs from the evaluated head tree.
- **NOT PROVEN, always red:** PX or A6 cannot merge.
- **Gap not reproduced:** A3 shows the PR not mergeable for a reason other
  than strict mode. Record it; continue only with approval.

**Stop immediately** on any unexpected verdict or HTTP status; a check run on
a different `head_sha` or from an app other than 15368; lab `main` moving
other than by A2, PX or PY; the ruleset or policy changing other than at A2,
A4 or teardown; the evaluator wheel line missing or not the approved hash;
an artifact missing.

A proven result covers only: GitHub, squash-only, one protected branch, memory
stored on that branch, one literal-tier rule, no concurrent races. It does not
change the CI1.4 DEFER recommendation by itself.

## 11. Approvals required before execution

Each numbered item is a separate approval. Within an item, rows run as a
batch, in order, with stop-on-unexpected.

1. Acceptance of this charter (PR review), including the open questions.
2. The offline run (section 4), including the section 4.1 import. No GitHub
   change.
3. **Unarchiving the lab** (S0) and extending its lifetime for this
   experiment only. The end condition (batch complete or stopped) and the
   final configuration in section 8 are fixed by this charter.
4. **The A2 admin adaptation** (section 7), including its recovery procedure.
   Together with A1 and A3 (observe-only rows that bracket it).
5. **The ruleset change** (A4).
6. **Strict controls:** A5, A6, A8 and A9.
7. **A7**, the stale-green adversarial attempt. Optional; requested only after
   item 6 matched expectations.
8. Evidence preservation and teardown: preserve as the 2026-10-19 archive did
   (artifact digests against GitHub's, bundle, logs, snapshots, durable copy),
   then apply section 8's final configuration and re-archive.

No unarchive, admin action, ruleset change, PR or merge attempt happens
without the matching approval.

## 12. Explicitly not authorized

- Any change to `MnemeHQ/mneme` workflows, rulesets, `.mneme/`, Core code, the
  frozen benchmark or frozen fixtures, and any Layer 1 freeze amendment.
- Adding a bypass actor or exception route to any ruleset.
- A direct push to lab `main`.
- Editing the lab gate, workflow, evaluator pin or tests.
- Implementing Option B, C or D.
- Merging any head while its check is green against stale memory (A3), and
  attempting A7 without item 7's approval.
- Treating a proven result as a production control or as grounds to change
  the CI1.4 recommendation without a separate decision.

## 13. Open questions

- **Q1. Merge semantics record.** Two different constructions exist and the
  record should keep them apart:
  - **V11 (rename/modify):** the PR modifies a seeded file, the base renames
    that file. Local git 2.47.1 with no merge config merges cleanly
    (`git merge-tree --write-tree 1bb964dc e4d45bb8` exits 0) and places
    `install legacy-client` in `docs/v11-note.md`. GitHub reported the PR
    DIRTY (comment 6263454460).
  - **V11b (directory rename):** the PR adds a new file, the base renames the
    directory. Default git reports a file-location conflict; only the
    non-default `merge.directoryRenames=true` merges cleanly into a violating
    tree (comment 6263559908).
  - Neither demonstrated a nonconforming merge on GitHub.

  CI1.4 §5 ("no conflict-free violating fixture was found under default git
  merge semantics") generalizes V11b to V11 and should be corrected in a
  separate docs change. Option A does not depend on the answer: a behind PR
  is refused whatever a merge would produce.
- **Q2. Resolved** in section 4.1.
- **Q3. GitHub merge-state values.** The exact `mergeable_state` reported for a
  behind PR with strict off versus on is not documented as a contract.
  Expected values are observations to record; the pass criterion is the merge
  API status and body.
- **Q4. Update method.** A5, A6 and A8 use a merge update. A rebase update
  rewrites the head; the tree-equality argument holds for both, but only the
  merge update is in scope.
- **Q5. Post-2026-11-02 behavior.** As C1 charter §8: the record states which
  side of GitHub's `pull_request_target` default restriction each step ran
  on.
- **Q6. External memory.** Option A gives no freshness for decision memory
  stored outside the protected branch. Whether a later charter needs Option B
  for that case is open.
- **Q7. Archive durability.** The OneDrive copy (comment 6270862573) verified
  local integrity, not cloud synchronization, and excludes the executor
  evidence folders. The section 4 rebuild reads the local bundle; this
  charter does not depend on the cloud copy.

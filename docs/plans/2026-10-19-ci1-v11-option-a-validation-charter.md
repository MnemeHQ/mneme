# CI1 V11: Option A final validation charter (proposal)

**Status:** **PROPOSED, revision 3.** Design only. **Nothing here is executed
or authorized.** It does not unarchive `MnemeHQ/mneme-ci1-lab`, change ruleset
`25313704` or Actions policy `7806`, open a lab PR or attempt a merge, and
changes nothing in `MnemeHQ/mneme` beyond adding this document. Production
merge blocking stays **DEFERRED** (CI1.4 §7).
**Revision 3** consolidates V11 into one bounded validation after review:
archived V11 evidence is reused rather than re-run, the live decision-memory
update, the admin enforcement-disable step and the optional stale-green
violating merge are removed from scope, and approvals are reduced to two
decision points (section 7).
**Tracker:** #540 (CI1 Enforcement Assurance). Related: #488.
**Builds on:** [CI1.3 charter](2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md)
(V11 row, §7 evidence);
[C1 charter](2026-10-19-ci1-c1-lab-validation-charter.md) (§7 snapshots);
[CI1.4 record](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)
§5 and §7 condition 2;
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md) row E;
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md);
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) §7;
[Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md).
**Evidence reused:** #540 comments 6263454460 (V11 phases 1 to 4),
6263559908 (V11b offline), 6270380073 and 6270862573 (lab archive). Archived
bundle `C:\dev\ci1-tools\evidence\lab-archive\final\mneme-ci1-lab.bundle`;
lab `main` `3cd402fe` (C1 gate, `EVALUATOR_COMMIT` `0b74d410`, memory blob
`dd760bf0`); archived ruleset: squash only,
`strict_required_status_checks_policy: false`, `bypass_actors: []`. Lab
`main` has no classic branch protection (read-only check, 2026-10-19: 404).
**Core anchor:** `main` @ `c2b78199`.

## 1. The one question

V11 showed that the trusted gate evaluates merge-base..head, so a fresh run on
an advanced base can still PASS a head whose content the base has moved into
scope. GitHub stopped that merge only through a conflict.

> **With GitHub's "require branches to be up to date" enabled, does the
> existing trusted gate only ever approve a head that is current with the
> base, so that the squash result is exactly what was evaluated?**

**Why it should (analytic):** strict mode refuses a merge unless the base tip
is an ancestor of the head. Then the squash tree equals the head tree, and
the gate's diff is the whole landed change, judged against the memory at that
base tip. Any base advance makes the PR behind; updating it triggers a fresh
gate run. GitHub does not distinguish a decision-memory commit from any other
base commit, so memory freshness reduces to the same host mechanism plus the
gate reading memory from the base tip (`gate/ci1_gate.py`, `base_sha:.mneme/project_memory.json`).

**Not covered:** unchanged repository content (baseline violations); decision
memory held outside the protected branch; other merge methods or hosts;
throughput cost; concurrent updates and in-flight check races (CI1.4 §6.6).

## 2. What is reused, not repeated

| Already established | Source |
|---|---|
| Stale-base PASS: gate on M2 `1bb964dc` + H `e4d45bb8` reports PASS with merge-base M1 | V11 phase 4b |
| After updating H with M2, the gate reports VIOLATION | V11 offline stage (c) |
| GitHub blocked V11 only as DIRTY (conflict) | V11 phase 4a |
| Real host merge blocking on a failed required check | CI1.3 / CI1.4 |
| Gate resists same-PR and separate-PR tampering | CI1.3, C1 (B0, L1 to L6) |

No tampering matrix, evaluator validation or host-blocking matrix is re-run.

## 3. Phase 1: offline (scratch clone of the archived bundle)

Run with the C1 gate from `3cd402fe` and the approved evaluator, as V9-A and
V12 were. Nothing touches GitHub, the lab or Core fixtures.

| # | Check | Expected |
|---|---|---|
| O1 | Tree equality: `git merge-tree --write-tree <base> <head>` equals `<head>^{tree}` for M1/H and for M2/H′ (H updated with M2) | Equal |
| O2 | `git merge-base --is-ancestor M2 H` | false: H would be refused as behind |
| O3 | Memory-snapshot case: H_d adds `install legacy-client` in a new `docs/history/v11a-note.md` from M2. M3 = M2 + a new ADR-901 version without the `docs/history/**` exclusion, written by `mneme adr import --apply --update-existing --expected-predecessor ADR-901=dver-d3d431ff6d5edba8b555a040a7b85f9b` at `0b74d410` from a scratch copy of the fixture ADR (frozen fixture unmodified). Gate on base M2: PASS. Gate on base M3 (no update): VIOLATION | Confirms the gate applies the base tip's memory on a fresh run; the only failure mode is a stale green, which strict addresses |

O3 records the derived ADR's sha256, the old and new `decision_version_id`
and rule identities, and that `git diff --name-only M2 M3` is exactly
`.mneme/project_memory.json`. If the import produces anything else, O3 is
reported as not constructed and Phase 2 can still proceed; the conclusion
then says memory freshness was not examined.

## 4. Phase 2: one bounded lab session

Every merge attempt is a pinned squash merge (`PUT .../pulls/{n}/merge`,
`sha=<head>`). Steps run in order; stop at the first unexpected result.

| # | Step | Expected |
|---|---|---|
| L0 | Unarchive the lab. Snapshot ruleset, policy, repo and the rules applying to `main` | Matches the archived snapshots except archive state and `updated_at` |
| L1 | Set `strict_required_status_checks_policy: true`; nothing else. Snapshot | Only that field and `updated_at` differ |
| L2 | From current `main`, open two compliant PRs touching different `docs/` files: PX and PY. Both gate PASS | Two green checks from app 15368 on the exact heads |
| L3 | Pinned merge of PX | **200**; `main` moves |
| L4 | Pinned merge of PY's unchanged head | **405**. Attributed to freshness only: PY's required check is success on that head, no conflict, and the response names the out-of-date branch |
| L5 | Update PY with `main` (merge update) | New head; a `synchronize` gate run on the new base: PASS |
| L6 | Pinned merge of PY's new head | **200**; landed squash tree equals PY's evaluated head tree (also checked for PX) |

No PR in this session contains a violation, so no step can land one.

## 5. Phase 3: close (same session)

1. Record the results on #540: per step, PR, base, head, merge-base, gate run
   and check (`head_sha`, app id), artifact digest, merge status and request
   id, `mergeable_state` as observed, ruleset snapshots before and after L1 and
   each merge attempt.
2. Restore `strict_required_status_checks_policy: false`; snapshot and diff
   against the archived `final/ruleset.json` (only `updated_at` may differ).
3. Preserve the new evidence as the 2026-10-19 archive did (artifact digests
   against GitHub's, updated bundle, logs, snapshots, durable copy).
4. Re-archive the lab. If the ruleset cannot be restored, archive anyway and
   record the actual final ruleset.

## 6. Outcome and conclusion

- **Pass:** O1 to O3 as expected, and L3 to L6 as expected. Conclusion,
  conditional and GitHub-specific: with squash-only merges and strict
  up-to-date checks, the existing trusted gate's PASS applies to exactly the
  landed tree and to the base tip's decision memory at evaluation time. The
  memory-update path is supported by O3 plus the live freshness proof, **not
  proven end to end live**.
- **Fail:** L4 merges, or its refusal is not attributable to freshness alone;
  L6 cannot merge; landed tree differs from the evaluated head. Record and
  stop.
- **Stop immediately** on any unexpected HTTP status or verdict, a check on a
  different `head_sha` or from another app, `main` moving other than at L3 or
  L6, or the ruleset or policy changing other than at L1 or teardown.

A pass closes the V11 Option A validation. It does not change the CI1.4 DEFER
recommendation; the remaining production blockers (administrative root of
trust P7/P8, governed decision updates, availability policy, broader
evidence binding) are tracked separately and are not reasons to extend V11.

## 7. Decision points

1. **Accept this charter** (PR review). Phase 1 may then run; it is offline
   and changes nothing.
2. **After Phase 1 succeeds, approve one bounded lab session** covering
   Phases 2 and 3 as written: unarchive, the temporary ruleset change, the two
   control PRs, restore and re-archive. Within that session the steps run in
   order with stop-on-unexpected. Any unexpected result or scope change needs
   fresh approval.

## 8. Not in scope

- A live decision-memory update, any enforcement-disable or bypass-actor
  step, and any direct push to lab `main`.
- Any attempt to merge a head that is green on stale memory or that violates
  a rule.
- Re-running V11, V11b, CI1.3 or C1 rows.
- Options B, C, D; any change to the gate, workflow, evaluator pin, Core code,
  frozen benchmark, frozen fixtures, `.mneme/` or the Layer 1 freeze.
- Production adoption.

## 9. Notes

- **V11 vs V11b merge semantics.** V11 (rename/modify) merges cleanly in local
  git 2.47.1 with the literal in `docs/v11-note.md`, while GitHub reported
  DIRTY. V11b (directory rename) conflicts by default and merges cleanly only
  with `merge.directoryRenames=true`. CI1.4 §5 generalizes V11b to V11; a
  separate docs change should correct it. Option A does not depend on this:
  a behind PR is refused whatever a merge would produce.
- **Archive durability.** The OneDrive copy verified local integrity, not
  cloud sync, and excludes the executor evidence folders. Phase 1 reads the
  local bundle.
- **Timing.** The record states which side of GitHub's 2026-11-02
  `pull_request_target` default restriction Phase 2 ran on.

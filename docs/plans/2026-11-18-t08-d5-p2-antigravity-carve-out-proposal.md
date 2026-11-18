# T-08 D5 + P2: Antigravity experimental carve-out from the Phase 2 host gate (PROPOSED)

> **PROPOSED: architecture amendment proposal only**, for independent review and owner approval.
>
> This is a read-only proposal. It edits no other document. It changes no runtime code, harness, pin, evidence, ADR or Layer 1 freeze. It runs nothing and authorizes nothing. If it is approved, the amendment text it describes lands in a separate docs PR (§7).
>
> **Anchor:** `MnemeHQ/mneme` `main` at `31cb49cb` (#828 merged).

## 0. Proposal in one paragraph

**Owner direction (2026-11-18):** "Keep Antigravity experimental and defer H4a live validation until there is a concrete need."

**Proposal:**
- Remove **H4** (Antigravity) from the mandatory Phase 2 host gate. Antigravity's integration, the #828 H4a harness, all accepted evidence and the `2.8.1` pin stay as they are.
- During Phase 2, **Antigravity stays on the P2-first selection contract already on `main`** (charter A2 §5.2.2): today's unbounded walk with P2 precedence, and no host notice.
- B1, I3 and rows 3–5 apply to every other consumer. They reach Antigravity only after its own H4a probe passes.
- Hermes H6a and H6b form probe batch 2 on their own.
- H4a is recorded as **deferred, not run**. It is never PASS.
- The exception names **Antigravity only**. It is not a general deferral rule, and it sets no precedent for any other consumer, OpenCode included.
- Every other host's requirements, the OpenCode H7 question, and readiness gaps S1–S7 are unchanged.

## 1. What the accepted documents require today

| Requirement | Source | Effect on Antigravity |
|---|---|---|
| Every implicit-discovery consumer adopts one stop rule at once | D5 contract §5.3; charter I1, §4 | Antigravity (`antigravity/adapter.py:244`, calling the shared `resolve_memory`) is one of the eleven consumers. |
| B1 is acceptable only with a host-visible `NO_MEMORY_SELECTED` on every consumer, through a channel verified live | D5 §5.1 and §8 | Applies to Antigravity. |
| Anomalous outcomes are reported host-visibly on every host | charter I4 (`:41`: "on every host (§5 gate H1–H6)") | I4 is relaxed to I4-P2F (R-ii) **for P2-first only** (§5.2.4). |
| Q2's reporting clauses: rule 1 ("host-visible channel"), rule 3 ("never a silent skip"), the §6 notice mitigation, and §10's channel prerequisite | Q2 §5, §6, §10 | Relaxed by Q2 Amendment A1 **"for the P2-first phase only"**. |
| The freeze amendment waits for all of H1–H6, with every output path. The charter "adds no exception". "If any host gate cannot be met … D5 must be revisited explicitly." | charter §5; §11 C3 ("no per-host exception"); §12 step 3 ("All six gates must pass"); A2 §5.2.5 ("Phase 2 keeps every original prerequisite", "D5 itself (§5.1, §8) is not amended") | H4 is mandatory. |
| H*n* passes only when every path under it passes. The final gate summary lists all twelve paths. | probe scope §6, §8 | H4a is the only H4 path. |
| Batch 2 is H4a, H6a and H6b. Batch 3 starts only after every batch-2 path passes. "every one of H1–H6 must pass" before the freeze. | probe scope A4 §4.5.1 (#825) | H4a currently gates Hermes's successors. |
| P2-first applies to every consumer, Antigravity included | P2-first `[layer1-freeze]` amendment (#812), authorized change item 3 | Antigravity is on P2-first on `main` today. |

D5 itself ties Phase 2 to Antigravity, and the charter forbids per-host exceptions. **This proposal is the explicit D5 revisit the charter requires, scoped to one named consumer.** It reverses A2 §5.2.5's "D5 itself (§5.1, §8) is not amended" for that consumer only, and says so.

## 2. Options

| Option | What Antigravity does in Phase 2 | Verdict |
|---|---|---|
| **O1. Stay on P2-first (recommended)** | Unbounded walk; P2 rows 1, 2, 6, 7 and 8; no notice, no new field, no new output (A2 §5.2.4 items 1 and 4). This is exactly `main` today. | **Smallest change, and no new silent skips.** D5 §5.1 exists because B1 turns governed edits (L4, L5, L6) into skips. Under O1, Antigravity never adopts B1, so none of its edits becomes newly ungoverned. Its behavior is accepted and on `main` (#812, #815). **No Antigravity live evidence exists;** #818 is Claude Code evidence. |
| O2. Adopt B1 with no verified channel | B1, I3 and rows 3–5 apply. Rows 4 and 5 leave no record on Antigravity. | **Rejected.** On Antigravity, L4, L5, L6 and planted-marker edits would become **silent** skips. That is the outcome D5 §5.1 forbids, and governance would drop below today's. |
| O3. Keep H4 mandatory (status quo) | Blocks all of Phase 2 until H4a passes. | Contrary to the owner's direction. |

**Costs of O1, stated plainly:**
- **Antigravity keeps P2-first's known gaps** (readiness assessment Q3; G3 re-assessment §4). An ancestor memory, or a planted memory above the repository boundary, still governs edits made through Antigravity. L4, L5 and L6 layouts behave as on `main` today.
- **Rows 2 and 7 stay unreported on Antigravity, with no end date.** The R-ii relaxation that permits this (charter I4-P2F, §5.2.4; Q2 Amendment A1) is limited to P2-first, so it must be extended explicitly for Antigravity (§3).
- **Selection diverges across hosts, in rows 4 and 5 only.** Where a B1 consumer stops at a boundary and selects nothing (row 4, or row 5 with a conflicting override), Antigravity's unbounded walk selects the ancestor memory. Row 3 does not diverge: it selects the override that equals `shadowed`, which is the same ancestor. This departs from D5 §5.3 and charter I1 for one experimental consumer.
- **Q2's "land together" departure lasts longer for Antigravity.** P2 precedence without a boundary continues for that consumer. No P2 rule changes.
- **The shared resolver keeps two walk modes:** B1 for the other consumers, unbounded for Antigravity (§3, charter §3.1 and §3.2).

**What O1 does not cost:** planted Git markers cannot be used for evasion on Antigravity, because it honors none (A2 §5.2.1).

## 3. Required changes, per document (to be made in the amendment PR, not here)

| Document | Sections | Change |
|---|---|---|
| **D5 contract** (`2026-10-17-dg1f-t08-d5-repository-boundary-contract.md`) | new **Amendment A1** (after Revisions 2–4 and the owner-approved §5.1 refinement); §5.1, §5.3, §8 | **A named exception: Antigravity (`antigravity/adapter.py`) does not adopt B1** until its own H4a passes (§3 re-entry rule). It keeps the P2-first walk and makes no host-visible claim. §5.1 is met for Antigravity because it does not adopt B1, so no governed edit becomes a skip. §5.3 "every consumer at once" excludes Antigravity by name. The §8 channel prerequisite applies to every other host. **Any other consumer, OpenCode included, needs its own D5 amendment.** |
| **Shared charter** (`2026-10-17-t08-d5-p2-memory-resolution-charter.md`) | new **Amendment A3** | Header note, then the edits listed below. |
| | §2 I1 and I4 | I1 covers every consumer except Antigravity. **I4-P2F continues for Antigravity** past P2-first: rows 2 and 7 are computed but have no record and no notice there. That is stated in place of the "P2-first only" scope. |
| | §3.1, §3.2 | The shared resolver keeps an unbounded mode for Antigravity, with `walk: "unbounded"` and `boundary` and `shadowed` unpopulated (A2-5). The B1 mode serves every other consumer. `find_memory`'s wrapper semantics are stated for both modes. |
| | §4 | The Antigravity row: P2-first contract, deferred. |
| | §5 | **H4 moves from the gate table to a "deferred (experimental)" row.** The gate rule ("every listed gate, every listed path") is unchanged for H1, H2, H3, H5 and H6. "This charter adds no exception" and the "if any host gate cannot be met … D5 must be revisited" clause apply to every listed gate. The Antigravity exception is the D5 revisit itself. |
| | §5.2.5 | Phase 2 needs H1, H2, H3, H5 and H6 with every listed path, plus whatever S1 adds (H7). Records that "D5 itself (§5.1, §8) is not amended" is superseded **for Antigravity only** by D5 A1. |
| | **re-entry rule** | **Antigravity joins Phase 2 only after all of:** its own H4a pass on its pin; its own `[layer1-freeze]` amendment; and a reviewed consumer-parity flip (A2's extension pattern). **If H4a fails**, the result goes to the owner, Antigravity stays on the exception, and no other consumer is blocked. |
| | §7.1, §7.5 | The parity tests expect the P2-first selection for Antigravity, plus a test that it stays unbounded under layouts where B1 consumers stop. |
| | §8 | No Antigravity live evidence. |
| | §9 | The Phase 2 freeze amendment authorizes B1 and I3 for the other consumers only, and preserves Antigravity's P2-first behavior. |
| | §10 | Add that preserved behavior. |
| | §11 C3, §12 step 3 | "No per-host exception" and "All six gates must pass" become "except the D5 A1 Antigravity exception" and "every listed gate". |
| **D6/Q2** (`2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md`) | header pointer, **Amendment A2** | For Antigravity only, A1's relaxed clauses continue past Phase 2 until Antigravity re-enters. Those are rule 1's and rule 3's reporting clauses, the §6 notice mitigation, and §10's channel prerequisite. The §10 "land together" departure continues too. The P2 rules are unchanged. |
| **Probe scope** (`2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md`) | new **Amendment A5**; A4 §4.5; §8 | **Batch 2 becomes H6a and H6b only.** A4's positive gate covers both. A4's "Unchanged" line "every one of H1–H6 must pass" becomes "every listed gate". **H4a leaves the batch order** and becomes "deferred: run on concrete need", under the unchanged §3–§8 method, the #828 harness and the `2.8.1` pin. §8's final gate summary still lists all twelve paths, with H4a as **`DEFERRED (not run)`**: not a §6 label, never passing, and not counted in the gate. §6 is unchanged. A4 §4.5.2's reason for running H4a first is recorded as lapsed for H4a and still applying to H6a. |
| **Batch-2 harness README** (`docs/validation/artifacts/dg1f-t08-d5-p2-batch2-host-path/harness/README.md`) | §3 | A one-line pointer: A5 supersedes "batch 3 starts only when H4a, H6a and H6b all pass" with "H6a and H6b". The harness code is unchanged; no `.py` file depends on H4a. |
| **ADR-033 and its erratum** | — | **None.** ADR-033 "Applies to Claude Code `PreToolUse` for `Edit|Write|MultiEdit` only" (ADR-033:130). Gap S2 is unchanged. |
| **Layer 1 freeze** | — | **None now,** because nothing changes at runtime. #812 already covers Antigravity's behavior. The future Phase 2 freeze amendment carries the §9 scoping above. |
| **Readiness assessment** (#823) | — | **No edit.** It is a dated, accepted record. Through the charter amendment, its P8 ("H4 BLOCKED (at risk)") becomes "deferred" and its P14 ("every implicit-discovery consumer at once") reads "every consumer except Antigravity". S1–S7 stay open. |
| **#828 harness and the `2.8.1` pin** | — | **Unchanged.** |

**On the `2.8.1` artifact (no repo change):**
- Its official URL is recorded in #828, and a HEAD request verified it **available** (MD5 `5MZNTAsbA8WmWJRqm9EqYg==`).
- With the owner's approval on 2026-11-18, it was downloaded into quarantine (not executed) and verified:
  - Authenticode valid, signer Google LLC;
  - file version `2.8.1`;
  - size and MD5 matching the storage record;
  - SHA-256 `05085047994932949BB6777765710CDC28ADB61C804851167995A3C285ACCA47`.
- That verification is **not yet in any repository record**. It would be committed with the deferred H4a evidence, and it is not relied on here.

## 4. A separate status discrepancy (decision E0, decoupled)

The owner's direction says Antigravity should **stay** experimental. The repository does not currently classify it that way:
- `docs/integrations/README.md:26` lists it under **"Native integration"**, and `:59-60` say "tested against Antigravity IDE 2.8.1". Probe scope §4 recorded that claim as having "no run or artifact" behind it.
- `docs/adr/ADR-013-external-platform-presence-standards.md:117` (positioning copy) lists "Google Antigravity" among the native integrations.
- The `2.8.1` build is in the **Antigravity App** line; the IDE line ends at `2.7.0` (#828).

**The carve-out does not depend on reclassification.** It rests on H4a being unrun and deferred by the owner. Whether to reclassify Antigravity as Experimental, and correct the "IDE 2.8.1" wording, is a separate positioning decision. It can be taken now, later or never. ADR-013 copy may be reused outside this repository, so E0 belongs in its own PR.

## 5. What this does not weaken

- **H1, H2, H3, H5 and H6 are unchanged,** with every listed output path, their pins, the one-pin-per-gate rule and the §6 labels.
- **H4a is not PASS.** Its status is `DEFERRED (not run)`, which is outside the §6 labels and never counted as passing. Antigravity claims no host visibility.
- **Antigravity's governance does not drop below today's.** It keeps the accepted P2-first behavior on `main`.
- **The exception is named, not general.** Every other consumer still needs every D5 §5.1 and §8 condition, and any further exception needs its own D5 amendment. The OpenCode H7 question (readiness S1) is untouched: adding OpenCode as H7, or excluding it, still needs its own charter decision.
- **Readiness gaps S1–S7 all remain open.**
- **Charter §5's "D5 must be revisited" rule still binds** every listed gate.

## 6. Decisions requested of the owner

| # | Decision | Recommendation |
|---|---|---|
| E1 | O1: Antigravity stays on P2-first during Phase 2 (not O2, B1 without a verified channel) | **O1.** It creates no new silent skips and keeps today's behavior. |
| E2 | D5 Amendment A1: the named Antigravity exception to §5.1, §5.3 and §8 | **Yes.** Without it, the charter change would contradict D5. |
| E3 | Extend R-ii (I4-P2F, Q2 A1's relaxed clauses) to Antigravity past P2-first | **Yes.** It states plainly what O1 already implies. |
| E4 | The re-entry rule, and the H4a-failure rule | **Yes.** It mirrors A2's extension rule, and a failure blocks no one else. |
| E5 | Probe batch 2 becomes H6a and H6b; H4a moves out of the batch order as `DEFERRED (not run)` | **Yes.** |
| E0 | *(separate)* Reclassify Antigravity as Experimental and correct "IDE 2.8.1" | Owner's call, in its own PR. Not a prerequisite. |

## 7. Sequence, if approved

1. This proposal is approved (decisions E1–E5).
2. **One docs-only amendment PR** applies §3: D5 A1, charter A3, Q2 A2, probe scope A5, and the harness README pointer. It gets an independent review and owner acceptance.
3. **H6a/H6b live run (batch 2),** under the #828 harness, on a separate go-ahead.
4. The rest of Phase 2 is unchanged, rebased on step 2.

E0, if wanted, is its own PR at any time.

## 8. Not authorized by this proposal

- applying any of the §3 changes, or E0;
- any runtime, harness, pin or evidence change;
- installing or launching Antigravity; any probe, shape discovery or live run, including H4a and batch 2;
- credential use; Hermes candidate T (D4 stays unapproved);
- treating H4a as PASS, or changing any earlier label: H1 stays `PASS`, G3 stays `PARTIAL`, and Phase 2 stays NOT READY and BLOCKED;
- any decision on OpenCode H7, or on readiness gaps S1–S7;
- any release.

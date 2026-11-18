# T-08 D5 + P2: Antigravity experimental carve-out from the Phase 2 host gate (PROPOSED)

> **PROPOSED: architecture amendment proposal only**, for independent review and owner approval.
>
> This document is read-only. It edits no other document, and it changes no runtime code, harness, pin, evidence, ADR or Layer 1 freeze. It runs nothing and authorizes nothing. If it is approved, the amendment text it describes lands in a separate docs PR (§7).
>
> **Anchor:** `MnemeHQ/mneme` `main` at `31cb49cb` (#828 merged).

## 0. Proposal in one paragraph

**Owner direction (2026-11-18):** "Keep Antigravity experimental and defer H4a live validation until there is a concrete need."

**Proposal:**
- Remove **H4** (Antigravity) from the mandatory Phase 2 host gate.
- Keep Antigravity's integration, the #828 H4a harness, all accepted evidence, and the `2.8.1` pin with its verified artifact.
- During Phase 2, **Antigravity stays on the P2-first selection contract already on `main`** (charter A2 §5.2.2): today's unbounded walk with P2 precedence, and no host notice. B1, I3 and rows 3–5 apply to every other consumer, but not to Antigravity, until its own H4a probe passes.
- Hermes H6a and H6b then form probe batch 2 on their own.
- H4a is recorded as **deferred, not run**. It is never treated as PASS.
- Every other host's requirements, the OpenCode H7 question, and the readiness gaps S1–S7 are unchanged.

## 1. What the accepted documents require today

| Requirement | Source | Effect on Antigravity |
|---|---|---|
| Every implicit-discovery consumer adopts one stop rule, all at once | D5 contract §5.3; charter I1, §4 | Antigravity (`antigravity/adapter.py`) is one of the eleven consumers. |
| B1 is acceptable only with a host-visible `NO_MEMORY_SELECTED` on every consumer, through a channel verified live | D5 §5.1, §8 | Applies to Antigravity. |
| The freeze amendment waits until **all of H1–H6** pass, with every output path. "If any host gate cannot be met, the shared implementation stays blocked for all consumers (I1), and D5 must be revisited explicitly." | charter §5, §12; A2 §5.2.5 ("Phase 2 keeps every original prerequisite") | H4 (`H4a`) is mandatory. |
| H*n* passes only when every path under it passes | probe scope §6 | H4a is the only H4 path. |
| Batch 2 is H4a, H6a and H6b. Batch 3 starts only after every batch-2 path passes, or on an owner decision. | probe scope A4 §4.5.1 (#825) | H4a currently gates Hermes's successors. |
| P2-first applies to every consumer, including Antigravity | P2-first `[layer1-freeze]` amendment (#812), authorized change item 3 | Antigravity is on P2-first on `main` today. |

So D5 itself, not only the charter, ties Phase 2 to Antigravity. The charter's own escape clause ("D5 must be revisited explicitly") is the route. **This proposal is that explicit revisit, scoped to one consumer.**

## 2. A status discrepancy the owner must resolve first (E0)

The owner's direction says Antigravity should **stay** experimental. The repository does not currently classify it that way:
- `docs/integrations/README.md:26` lists it under **"Native integration"**. Lines `:59-60` say it was "tested against Antigravity IDE 2.8.1".
- `docs/adr/ADR-013-external-platform-presence-standards.md:117` (positioning copy) lists "Google Antigravity" among the native integrations.
- That README defines **Experimental** as "code exists behind a PR or validation is incomplete" (`:17`).

A carve-out from the host gate is easiest to defend for a host whose validation is admittedly incomplete. **This proposal therefore depends on reclassifying Antigravity as Experimental** in the support matrix (and the ADR-013 copy). It does not do that silently; the reclassification is decision E0 (§6).

The "IDE 2.8.1" wording is also inaccurate. The artifact verified on 2026-11-18 is in the **Antigravity App** line (the IDE line ends at `2.7.0`). That is recorded in #828, and the correction would ride along with E0.

## 3. Options

| Option | What Antigravity does in Phase 2 | Verdict |
|---|---|---|
| **O1. Stay on P2-first (recommended)** | Unbounded walk plus P2 rows 1, 2, 6, 7 and 8. No notice, no new field, no new output (A2 §5.2.4 item 4). This is exactly what `main` does today. | **Smallest change, and no new silent skips.** D5 §5.1 exists because B1 turns governed edits (L4, L5, L6) into skips. Under O1, Antigravity never adopts B1, so none of its edits becomes newly ungoverned. Its behavior is already accepted and live (#812, #815, #818). |
| O2. Adopt B1 with no verified channel | B1, I3 and rows 3–5 apply. Anomalous rows 4 and 5 leave no record on Antigravity. | **Rejected.** On Antigravity, L4, L5, L6 and planted-marker edits would become **silent** skips. That is the outcome D5 §5.1 forbids, and it would weaken Antigravity's governance below today's. |
| O3. Keep H4 mandatory (status quo) | Blocks all of Phase 2 until H4a passes. | Contrary to the owner's direction. |

**The costs of O1, stated plainly:**
- **Antigravity keeps P2-first's known gaps** (readiness assessment Q3; G3 re-assessment §4):
  - an ancestor memory, or a planted memory above the repository boundary, still governs edits made through Antigravity;
  - a worktree, submodule or parent layout (L4, L5, L6) behaves as on `main` today.
- **Selection diverges across hosts.** For the same target, Antigravity can select an ancestor memory where a B1 consumer selects nothing (row 4) or the override (row 3). This departs from D5 §5.3's "one rule for every consumer" and from charter I1, for one experimental consumer, and is stated as such.
- **Q2's "land together" departure lasts longer for Antigravity.** For Antigravity only, P2 precedence without a boundary continues beyond P2-first. This changes no P2 rule.

**What O1 does not cost:** planted Git markers cannot be used for evasion on Antigravity, because it honors none (A2 §5.2.1).

## 4. Required changes, per document (to be made in the amendment PR, not here)

| Document | Section | Change |
|---|---|---|
| **D5 contract** (`2026-10-17-dg1f-t08-d5-repository-boundary-contract.md`) | §5.1, §5.3, §8 (as its first amendment, A1) | Add one scoped exception. **A consumer whose host gate the owner has deferred does not adopt B1.** It keeps the P2-first walk and makes no host-visible claim. D5 §5.1 is satisfied for that consumer by not adopting B1, so no governed edit becomes a skip. The §5.3 "every consumer at once" becomes "every non-deferred consumer at once". The §8 prerequisite becomes "a verified channel per host **that adopts B1**". The only deferred consumer is Antigravity. |
| **Shared charter** (`2026-10-17-t08-d5-p2-memory-resolution-charter.md`) | header (new Amendment A3 note); §2 I1; §4; §5; §5.2.5; §7.1, §7.5; §8; §9; §10 | **Header and I1:** I1's scope is "every non-deferred consumer". **§4:** the Antigravity row stays on P2-first, marked deferred. **§5:** H4 moves from the gate table to a "deferred (experimental)" row; the gate rule ("every listed gate, every listed path") is unchanged for H1, H2, H3, H5 and H6; the "if any host gate cannot be met" clause applies to the listed gates. **§5.2.5:** Phase 2 needs H1, H2, H3, H5 and H6 with every listed path, plus anything S1 adds (H7). **Re-entry rule:** Antigravity joins Phase 2 only after its own H4a pass on its pin, its own `[layer1-freeze]` amendment, and a reviewed consumer-parity flip (A2's extension pattern). **§7.1/§7.5:** Antigravity's expected selection in the parity tests is the P2-first result. **§8:** no Antigravity live evidence. **§9:** the Phase 2 freeze amendment authorizes B1 and I3 for the non-deferred consumers only, and preserves Antigravity's P2-first behavior. **§10:** add that behavior to "Preserved". |
| **D6/Q2** (`2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md`) | header pointer (Amendment A2) | For Antigravity only, the §10 "land together" departure continues past Phase 2 until Antigravity re-enters. The P2 rules are unchanged. |
| **Probe scope** (`2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md`) | header (Amendment A5 note); A4 §4.5 | **Batch 2 becomes H6a and H6b only.** A4's positive gate then covers H6a and H6b: batch 3 starts after both pass, or on an owner decision. **H4a moves out of the batch order** to "deferred: run on concrete need", under the unchanged §3–§8 method, with the #828 harness and the verified `2.8.1` artifact. §6 labels and the gate rule are unchanged. H4 is left out of the Phase 2 gate summary, and its status is "deferred, not run". A4's reason for putting H4a first (§4.5.2) is recorded as lapsed for H4a and still applying to H6a. |
| **Integration docs** (`docs/integrations/README.md`, `antigravity.md`) | support matrix; status | **Only if E0 is approved:** move Antigravity from "Native integration" to "Experimental". Note that the T-08 Phase 2 boundary (B1) does not apply to it, and that no selection notice is host-visible on it. Correct "IDE 2.8.1" to the App line. |
| **ADR-013** | positioning copy (`:117`) | **Only if E0 is approved:** remove Antigravity from the "Native integrations" sentence, or qualify it. No other ADR change. |
| **ADR-033 and its erratum** | — | **None.** ADR-033 availability is scoped to Claude Code (#821's OpenCode amendment says the same: "ADR-033's `closed` authorization remains Claude Code-scoped"). Gap S2 (an ADR-033 analysis for Phase 2) is unchanged. |
| **Layer 1 freeze** (`layer1-freeze-e73ff7d.md`) | — | **No change now,** because nothing changes at runtime. The P2-first amendment (#812) already covers Antigravity's behavior. The future Phase 2 `[layer1-freeze]` amendment must carry the §9 scoping above. |
| **Readiness assessment** (#823) | — | **No edit.** It is a dated, accepted record. If this proposal is approved, its P8 ("H4 BLOCKED (at risk)") is superseded by "deferred" through the charter amendment. S1–S7 stay open. |
| **#828 harness, pins, provenance** | — | **Unchanged.** The H4a arms, the `2.8.1` pin, and the verified artifact (SHA-256 `05085047…ACCA47`) are kept for the deferred run. |

## 5. What this does not weaken

- **H1, H2, H3, H5 and H6 are unchanged,** with every listed output path, their pins, the one-pin-per-gate rule, and the §6 labels.
- **H4a is not PASS.** It is "deferred, not run". No document, record or gate summary may count it as passed. Antigravity claims no host visibility; that was already true under R-ii.
- **Antigravity's governance does not drop below today's.** It keeps exactly the accepted P2-first behavior on `main`.
- **The OpenCode H7 question is preserved.** Readiness S1 (OpenCode is a `resolve_memory` consumer outside charter §4 and the gate) is unchanged. The owner calls it a separate H7 requirement; whether it is added as H7 or excluded still needs its own charter amendment. This proposal does not touch it and sets no precedent for it: each deferral is a separate owner decision.
- **The readiness gaps S1–S7 all remain open,** including S2 (ADR-033 under Phase 2), S3, S4, S5 and S6.
- **Charter §5's "D5 must be revisited" rule still binds** every gate that is not deferred.

## 6. Decisions requested of the owner

| # | Decision | Recommendation |
|---|---|---|
| E0 | Reclassify Antigravity from "Native integration" to "Experimental" (support matrix, `antigravity.md`, ADR-013 copy) | **Yes.** The carve-out rests on validation being incomplete. Without it, the deferral would apply to a host the repository presents as native. |
| E1 | Choose O1: Antigravity stays on P2-first during Phase 2 (not O2: B1 without a verified channel) | **O1.** It creates no new silent skips and is already live. |
| E2 | Amend D5 §5.1, §5.3 and §8 with the deferred-consumer exception (§4) | **Yes.** Without it, the charter change would contradict D5. |
| E3 | The re-entry rule: H4a pass, its own freeze amendment, and a parity flip | **Yes.** It mirrors A2's extension rule. |
| E4 | Probe batch 2 becomes H6a and H6b; H4a is deferred out of the batch order | **Yes.** |

## 7. Sequence, if approved

1. This proposal is approved (decisions E0–E4).
2. **One docs-only amendment PR** applies §4: D5, the charter, the Q2 pointer, the probe scope and, if E0 is approved, the integration docs and ADR-013 copy. It gets an independent review and owner acceptance.
3. **H6a/H6b live run (batch 2)**, under the #828 harness, on a separate go-ahead.
4. The rest of Phase 2 is unchanged, rebased on step 2.

## 8. Not authorized by this proposal

- applying any of the §4 changes;
- any runtime, harness, pin or evidence change;
- installing or launching Antigravity; any probe, shape discovery or live run, including H4a and batch 2;
- credential use; Hermes candidate T (D4 stays unapproved);
- treating H4a as PASS, or changing any earlier label: H1 stays `PASS`, G3 `PARTIAL`, Phase 2 NOT READY and BLOCKED;
- any decision on OpenCode H7, or on readiness gaps S1–S7;
- any release.

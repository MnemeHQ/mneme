# T-08 D5 + P2 Phase 2 readiness assessment (2026-11-17)

> **PROPOSED: assessment only**, for independent review and owner acceptance.
>
> Read-only readiness assessment. It changes no code, test, harness, ADR,
> Layer 1 freeze, `.mneme/` content, pin or evidence, and it authorizes
> nothing. It asks whether **Phase 2** of the shared D5 + P2 charter (B1,
> I3, §3.3 rows 3–5 and the H1–H6 gate) can proceed, measured against the
> accepted sources below.
>
> **No earlier result is upgraded or re-classified.** H1 stays `PASS`
> (#808), G3 stays `PARTIAL` (#822), and every G3, H1 and P2-first label
> stays exactly as recorded.
>
> **Anchor:** `MnemeHQ/mneme` `main` at `72f32744`. Every T-08 source is
> unchanged since `eece797e` (#822). The three later merges (#610, #820,
> #821) touch no T-08 document; #821 is cited once, in §5 gap S1.

## 0. Answer

**Phase 2 is NOT READY, and its gate is BLOCKED.**

- **The design core is specified well enough to implement.** The B1 walk
  (charter §3.2), the P2 + I3 table (§3.3 rows 1–8) and the L4, L5, L6 and
  planted-marker outcomes are all defined, and the D5 §8 definition
  prerequisites are met.
- **The gate is the blocker.** Only H1 of the six host gates has passed.
  H2–H6 are not started; H3 has no harness; H4 and H6 are marked at risk by
  the probe scope, and either failing would reopen D5 (charter §5).
- **Seven specification gaps remain** (§5), two of them material:
  - Phase 2 has **no ADR-033 analysis**. In an enrolled repository, rows 4
    and 5 select no memory, and today's code then refuses with
    `MEMORY_MISSING` (exit 2) (S2).
  - **OpenCode S1** (#821, authorized, not yet implemented) adds a
    `resolve_memory` consumer that is outside the charter's §4 consumer
    list and the H1–H6 gate (S1).
- **Phase 2 would close** the ancestor-memory and above-boundary planted
  memory gaps from G3 §4. It **would not close** the row 6 absent-memory
  `PASS` route, start-point divergence (D1/D2/D7), in-boundary planted
  memory (D4) or the live-coverage gaps (§3).

**Recommended next step (one):** see §6.

## 1. Sources

All are merged on `main`.

| Source | Reference | Used for |
|---|---|---|
| Shared D5 + P2 charter | [`2026-10-17-t08-d5-p2-memory-resolution-charter.md`](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (#542; A1; A2 #809; A2-RT #811) | §2 invariants, §3 resolver, walk, rows and tiers, §4 consumers, §5 gate, §5.2.5 Phase 2 rebase, §6–§12 |
| D5 boundary contract | [`2026-10-17-dg1f-t08-d5-repository-boundary-contract.md`](2026-10-17-dg1f-t08-d5-repository-boundary-contract.md) | L1–L8b, B1, §5.1–§5.4 conditions, §8 prerequisites |
| D6/Q2 precedence | [`2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md`](2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md) (with Amendment A1) | P2 rules 1–4, §10 prerequisites |
| Probe scope | [`2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md`](2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md) | H1–H6 paths, harness per host, labels, pins, batch order |
| H1 gate | [`dg1f-t08-d5-p2-host-path-h1-gate-2026-11-16.md`](../validation/dg1f-t08-d5-p2-host-path-h1-gate-2026-11-16.md) (#808) | H1 `PASS` on `2.1.310` |
| P2-first live evidence | [`dg1f-t08-p2-first-live-2026-11-17.md`](../validation/dg1f-t08-p2-first-live-2026-11-17.md) (#818) | PASS 7/7, C2, Edit only |
| G3 re-assessment | [`t08-g3-reassessment-p2-first-2026-11-17.md`](../validation/t08-g3-reassessment-p2-first-2026-11-17.md) (#822) | §4 remaining gaps |
| ADR-033 and its erratum | [`ADR-033`](../adr/ADR-033-opt-in-fail-closed-enforcement.md) §4.1, Erratum 2026-11-16 | P2-first consequences; none stated for Phase 2 |
| Layer 1 freeze | [`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md), P2-first amendment (#812) and OpenCode S1 amendment (#821) | what is authorized and what stays Phase 2 |
| Code | `mneme/integrations/memory_selection.py`, `mneme/integrations/claude_code/hook.py`, `mneme/integrations/claude_code/availability.py`, `mneme/setup.py` | current resolver, consumers, ADR-033 routing |
| Characterization test | `tests/integrations/claude_code/test_memory_boundary_characterization.py` (#543, `5d8bf82a`; flipped by P2-first) | L4, L5, L6, L8b and planted-marker baselines |

## 2. Grades

- **READY:** specified well enough to implement or already met, with
  citations.
- **NOT READY:** missing or ambiguous specification, or missing work, that
  can be resolved by a document or owner decision without new evidence.
- **BLOCKED:** depends on an unmet external prerequisite (live evidence, a
  harness that does not exist, or an earlier gate), or on an authorization
  that has not been given.

## 3. Questions

### Q1. Is B1 specified enough to implement?

| Item | Grade | Basis |
|---|---|---|
| B1 walk and stop rule | **READY** | Charter §3.2 pseudocode: memory check before marker check in the same directory (L1), existence-only marker (L8a/L8b), `boundary` always the nearest marker from the start, `R = None` with no marker (L2). D5 §4 B1 states the same rule and its reasons. |
| Shared marker helper | **READY** | Charter §3.1: factor the marker test into one helper that `setup.find_project_root` also uses. Today `find_project_root` (`mneme/setup.py:113-122`) uses `(candidate / ".git").exists()`; `memory_selection._walk` (`memory_selection.py:51-60`) has no marker check. The target is unambiguous. |
| L4 worktree | **READY** | D5 §3 L4 and §4 B1: a worktree with no memory becomes row 4 (`BOUNDARY_SHADOWS_MEMORY`) instead of being governed by the outer checkout. Charter §8 lists the L4 live expectation. The characterization test pins today's crossing (`test_l4_task_worktree_without_memory_crosses_into_outer_checkout`). |
| L5 submodule | **READY** | D5 §4 B1 (L5 "changes"), D5 §7 item 3 (isolation is intended), charter §3.3 row 3 (declared inheritance through `MNEME_MEMORY`), §7.4 (legitimate row 3 test). |
| L6 parent memory | **READY** | D5 §4 B1 (L6 "changes"), charter §3.3 rows 3–5, Q2 §7 (P2 supplies the D5 §5.2 declared path). |
| Planted markers (D5 §5.4) | **READY as a definition** | Charter §11 C1: I3 is the §5.4 outcome; row 5 blocks the Q2 rule-2 substitution (charter §3.3 "adversarial case"). The P2-first freeze amendment lists B1 and I3 as Phase 2 (`layer1-freeze-e73ff7d.md`, "Not authorized by this amendment"). **Residual stated, not graded up:** with no override, a planted marker gives row 4, which is a visible notice only. D5 §5.4 says visibility "does not by itself restore enforcement". The H1a notice reaches the agent only (#808 §1), which may be the agent that planted the marker. See S6. |
| `shadowed` when `M_R` is found first | **NOT READY** | Charter §3.1 defines `shadowed` as "the nearest memory above `R`, if any", but the §3.2 pseudocode computes it only in the marker branch. §7.1 asks for an expected `shadowed` for L1 and L7, where `M_R` is found first. Whether `shadowed` is populated there is unspecified (S4). |
| `shadowed` across further markers | **NOT READY** | §3.2: "the `shadowed` lookahead walks the same ancestors today's walk would", so it can cross further `.git` markers above `R`. §3.3 "What I3 costs" says a user may inherit "only the memory directly above their boundary". For a nested submodule (`outer/.git`, `outer/sub/.git`, `outer/sub/inner/.git`, memory only in `outer`), the text does not say whether `inner` may inherit `outer`'s memory through row 3 (S4). |
| Marker edge cases | **NOT READY (minor)** | Existence-only via `Path.exists()` follows symlinks, so a dangling `.git` symlink is **not** a boundary, while a `.git` file with a dangling `gitdir:` **is** (L8b). The charter and D5 do not state this distinction. It only needs to be written down and pinned by a test (S4). |

**Q1 overall: READY for the walk and L4/L5/L6/planted-marker outcomes;
NOT READY on the `shadowed` field's definition (S4).**

### Q2. Are I3 and shadowed-memory handling (rows 3–5) specified enough?

| Item | Grade | Basis |
|---|---|---|
| Override equals shadowed (row 3) | **READY** | Charter §3.3 row 3: `M_X` an existing file equal to `shadowed` after `resolve()` → `M_X`, `OVERRIDE_DECLARED_INHERITANCE`, informational (§3.4). Test §7.4. |
| Shadowed and no override (row 4) | **READY** | Row 4: nothing selected, `BOUNDARY_SHADOWS_MEMORY`, anomalous (§3.4). |
| Conflict: override differs from shadowed, or is missing (row 5) | **READY** | Row 5: nothing selected, `OVERRIDE_REFUSED_AT_BOUNDARY`, anomalous. Row 5 takes precedence over row 7 when `shadowed` exists ("or missing"). Adversarial test §7.3. |
| Row 2 against a shadowed memory | **READY** | Rows 1–2 key on `M_R`; `shadowed` does not affect them. |
| Unreadable override | **NOT READY (contradiction)** | Charter §3.3 row 7 says "missing **or unreadable**". Q2 Amendment A1 says Phase 2 "restores … rule 3's classification of an unreadable override (charter §3.3 row 7)". But charter A2-3 rejected the open-probe needed to detect "unreadable" (Windows sharing-lock race, OneDrive placeholder downloads, loss of today's visible fail-open on Codex and the Agent SDK/LangChain), and nothing limits those reasons to P2-first. The same question arises in rows 3 and 5: is an unreadable file equal to `shadowed` row 3 or row 5? (S3, owner decision.) |
| Returned path form, row 3 | **NOT READY (minor)** | A2 §5.2.2 fixes the returned form for P2-first rows only (`Path(M_X)` as given). Phase 2 does not say whether row 3 returns `Path(M_X)` or `shadowed` (S5). |
| Notice text and emission conditions, rows 4 and 5 | **NOT READY** | `selection_notice` (`memory_selection.py:103-124`) covers rows 2 and 7 only. Charter §7.8 asks only for "the §5 candidate shape". The A2 §5.2.4 item 3 emission conditions (suppress on warn-mode `defer` and exit-2 events) apply to "P2-first only" (§5.2.4 heading). Phase 2 restates neither the texts nor the conditions (S5). |
| Informational recording (rows 3 and 6) | **NOT READY (minor)** | §3.4: "recorded in structured output". A2 §5.2.4 item 1 found such a record only in the Agent SDK/LangChain trace. Phase 2 restores I4 for anomalous rows, but does not say where rows 3 and 6 are recorded in other consumers (S5). |
| `boundary` and `walk` fields | **READY** | §3.1 and A2 §5.2.2: Phase 2 populates `boundary` and sets `walk: "b1"`. A2-5 keeps an absent boundary from being read as "no Git". |
| ADR-033 interaction with rows 3–5 | **NOT READY** | See S2. A2 §5.2.3 (F1) analysed ADR-033 for P2-first. No equivalent exists for Phase 2. |

**Q2 overall: READY for the precedence table; NOT READY on the unreadable
override (S3), the row 4/5 notices (S5) and ADR-033 (S2).**

### Q3. Which G3 §4 gaps does Phase 2 close?

"Closes" means by design, once Phase 2 ships and passes its gate. Nothing
here is evidence.

| G3 §4 gap | Phase 2 | Why |
|---|---|---|
| **Ancestor memory beats the override** (L4, L5, L6; charter §5.2.3 case 2) | **Closes** | The walk stops at `R`. An ancestor memory becomes `shadowed`, and is applied only through row 3 (override equals it). Otherwise row 4 or row 5. **Cost:** a user whose override names a memory **other than** the shadowed one is refused (row 5), not served (charter §3.3 "What I3 costs"). |
| **Planted memory above `R`** | **Closes** | Same mechanism: a memory above the boundary is never selected implicitly. |
| **Planted memory inside `R`** (V3/V6) | **Does not close** | Nearest-wins inside `R` is D4, out of scope (charter §3.3 "Residual, unchanged"; §10). |
| **Planted Git marker** | **New surface, made visible only** | B1 creates it. Row 5 blocks substitution; with no override, row 4 leaves edits under the marker ungoverned, with a notice (D5 §5.4; S6). |
| **Row 6 absent-memory `PASS`** | **Narrows, does not close** | Row 6 needs no `M_R` **and** no `shadowed`. Phase 2 refuses the override only where a memory sits above `R` (row 5). A repository whose memory is absent, with nothing above it, still takes any existing `M_X` (row 6, `OVERRIDE_FILLS_ABSENCE`; Q2 rule 2 "keeps U1 and U5"). Enrolled repositories behave as G3 §4 records (only `AUTHORIZED` refuses). |
| **Row 7** (missing override, nothing walked) | **Unchanged** | Still selects nothing, reported. |
| **Start points not unified** (D1/D2/D7) | **Does not close** | I5 (charter §2) keeps every start point. D5 §5.3: "D5 does not change any start point". A Bash write into A from a `cwd` in B still selects B's memory. |
| **Write and MultiEdit live** | **Does not close** | H1a's accepted design probes Edit and Bash only (probe scope §4: "Two sub-probes: an Edit and a Bash command"), and #808 passed on those. The H1 gate is met by that design; Write/MultiEdit live coverage stays a G3 limit. Charter §8 does not add it. |
| **Bash, SessionStart, Stop live under the resolver** | **Not by the gate** | The gate probes channels with a harness emitter, not Mneme (probe scope §3 step 1). Charter §8 behavioral evidence covers C2, the planted marker and L4, all as direct writes. |
| **C4 channel and `project,local`; enrolled repositories live** | **Does not close** | Those need the G3-2 and G3-1 re-runs (#822 §5), which are separate and not authorized. |
| **H2–H6 host visibility** | **Closes only through its own gate** | Phase 2 cannot proceed without all twelve paths passing (charter §5). |
| **Other versions and models; n = 1** | **Does not close** | Probe scope §9 "would not". |
| **Outside scope** (C3/C5/C6, `bypassPermissions`, hook removal, admin bypass) | **Does not close** | #822 §4; charter §10. |

**Q3 overall:** Phase 2 closes the boundary gaps (ancestor and
above-boundary planted memory) and nothing else in G3 §4. G3 would remain
`PARTIAL` after Phase 2 unless the row 6 route and start points are also
addressed. This is a reading, not a re-grade of G3.

### Q4. Which Phase 2 prerequisites are met?

| # | Prerequisite | Source | Grade | Status |
|---|---|---|---|---|
| P1 | D5 contract accepted | D5 §8 | **READY** | Accepted 2026-10-17. |
| P2 | Q2 resolved (P2 defined, D5 §5.2 declared path) | D5 §8; Q2 §10 | **READY** | Accepted 2026-10-17; P2-first implemented (#815). |
| P3 | D5 §5.4 planted-marker outcome defined, including the rule-2 case | D5 §8; Q2 §10 | **READY** | Charter §3.3 row 5, I3, §11 C1; A2 §5.2.5 records it as "already met". |
| P4 | L4 characterization test authorized and recorded | D5 §7 item 4, §8; charter §6 | **READY** | #543 (`5d8bf82a`); flipped for P2-first; Phase 2 flips the planted-marker pair to row 5 (A2 §5.2.5). |
| P5 | H1 Claude Code: H1a, H1b, H1c | charter §5 | **READY** | `PASS` on `2.1.310`, `claude-opus-5-5`, n = 1 (#808). Bound to that pin and its run conditions. |
| P6 | H2 Codex: H2a, H2b | charter §5; probe scope §4, §4.1 | **BLOCKED** | Not started. H2a needs a targeted re-run for artifact-backed delivery (§4.1, D1). H2b is unproven live. Existing harness (`validation/codex-cli/probe/`). Pin `0.149.1` installability not checked here. |
| P7 | H3 Kiro: H3a | same | **BLOCKED** | Not started. **No harness exists** (probe scope §5). |
| P8 | H4 Antigravity: H4a | same | **BLOCKED (at risk)** | Not started. IDE only, operator-driven, shape discovery first. A `NO_NONBLOCKING_CHANNEL` result fails the gate (probe scope §5, §6). |
| P9 | H5 Agent SDK: H5a, H5b, H5c | same | **BLOCKED** | Not started. H5a/H5b need a new harness and operator credentials; H5c extends `probe_m0.py` (scripted model allowed, D2). |
| P10 | H6 Hermes: H6a, H6b | same | **BLOCKED (at risk)** | Not started. New harness, live model, credentials; H6a shape discovery first, since `pre_tool_call` offers only block or nothing (probe scope §4). |
| P11 | Phase 2 `[layer1-freeze]` amendment | charter §9, §12 step 4; A2 §5.2.5 | **BLOCKED** | Needs P5–P10 first. The P2-first amendment explicitly leaves B1, I3, rows 3–5 and `boundary`/`shadowed` unauthorized (#812). |
| P12 | Offline evidence (§7 tests, including §7.1 boundary assertions and §7.5 parity) | charter §7, §12 step 5 | **BLOCKED** | Implementation is not authorized, and it follows P11. Gaps S2–S5 would also leave §7.1, §7.2 and §7.8 without fixed oracles. |
| P13 | Live behavioral evidence (§8: C2, planted marker plus override, L4) | charter §8, §12 step 6 | **BLOCKED** | Follows P12; separately authorized. |
| P14 | One cross-consumer adoption, every implicit-discovery consumer at once | D5 §5.3; charter §4, I1 | **NOT READY** | Eleven consumers listed; OpenCode S1 is not (S1). |

**Q4 overall:** the definition prerequisites (P1–P4) and H1 (P5) are met.
Every other prerequisite is BLOCKED, ultimately on H2–H6.

### Q5. Spec gaps, contradictions and owner decisions

See §5 for the list and §6 for the one recommended next step.

## 4. What stays true from earlier records

- **H1 `PASS`** (#808) is a channel result for one pin. It does not show
  that Mneme emits a row 4 or row 5 notice; nothing for Phase 2 is
  implemented. Its run conditions bind any Phase 2 claim on Claude Code
  (A2 §5.2.4 item 2).
- **G3 `PARTIAL`** (#822) is unchanged.
- **P2-first** (#815) is on `main` and unreleased. Phase 2's baseline is
  post-P2-first `main` (A2 §5.2.5).
- **The §4 call-site line numbers are stale** (A2 §5.2.6 already says so).
  At `72f32744` the resolver calls are `hook.py:213` (wrapper) and `:229`
  (`_select_memory`, shared by all four Claude Code paths),
  `codex_cli/gate.py:157`, `codex_cli/stop_audit.py:125`,
  `kiro/hook.py:300`, `antigravity/adapter.py:244`,
  `agent_sdk/adapter.py:366` and `hermes/adapter.py:262`. LangChain still
  delegates to its internal Agent SDK.

## 5. Specification gaps, contradictions and owner decisions

| # | Gap | Kind | Grade | Needed |
|---|---|---|---|---|
| **S1** | **OpenCode is a new `resolve_memory` consumer outside Phase 2.** The OpenCode S1 freeze amendment (#821) authorizes a bridge that "reuses `resolve_memory`" (`layer1-freeze-e73ff7d.md`, OpenCode S1 amendment). It is not yet implemented on `main`. Once it lands, D5 §5.3 ("adopts it for every consumer … at once") and charter I1 require OpenCode to take B1 too, but it is not in charter §4 and has no H-gate. | Owner decision | **NOT READY** | Owner chooses: add OpenCode to §4 with its own gate (H7) before the Phase 2 freeze, or record it as excluded with the reason (it is Experimental, #821). Either is a charter amendment. |
| **S2** | **ADR-033 consequences of Phase 2 are not analysed.** `discover_declaration` (`availability.py:43-72`) walks to the first ancestor `.mneme/` with no marker check; it is not a §4 consumer. On a direct write with no selected memory, the hook calls `emit_availability(..., "NOT_RUN", ...)` with `memory=None` (`hook.py:2108-2113`), and `refusal_category` returns `MEMORY_MISSING` under `AUTHORIZED` (`availability.py:191-213`). So in an enrolled repository, rows 4 and 5 (for example, a planted `.git` at `A/src/`, or an L4 worktree without memory under an enrolled checkout) would **refuse with exit 2**, not proceed with a notice. That may be the intended fail-closed result for an enrolled repository, but no document says so. Charter §10 preserves "every exit code: no outcome in §3.4 blocks", and if A2 §5.2.4 item 3's suppression carried into Phase 2, the row 4/5 notice would not appear on that exit-2 event. | Spec gap | **NOT READY** | An ADR-033 consequences section for Phase 2, like A2 §5.2.3 (F1): rows 3–5 under each authorization state, whether B1 applies to declaration discovery, the notice/refusal interaction, the rewritten tests, and whether an ADR-033 erratum is needed. |
| **S3** | **Unreadable override: Q2 A1 vs charter A2-3.** Q2 A1 says Phase 2 restores "unreadable" in row 7; A2-3 gives reasons against the open-probe that are not P2-first-specific. Rows 3 and 5 inherit the question. | Contradiction; owner decision | **NOT READY** | Owner chooses: keep `is_file()` only in Phase 2 (amend Q2 A1's Phase 2 sentence), or restore an open-probe with the A2-3 risks accepted. |
| **S4** | **`shadowed` definition.** (a) Populated or not when `M_R` is found first (§3.1 vs §3.2 vs §7.1). (b) Whether the lookahead may cross further markers above `R`, and so whether row 3 can inherit across two boundaries. (c) Dangling `.git` symlink vs dangling `gitdir:` file. | Spec gap | **NOT READY** | One charter clarification and the matching §7.1 oracle rows. |
| **S5** | **Phase 2 output contract.** Fixed notice texts for rows 4 and 5; Phase 2 emission/suppression conditions (A2 §5.2.4 item 3 is P2-first only); returned path form for row 3; where rows 3 and 6 are recorded outside the Agent SDK/LangChain trace. | Spec gap | **NOT READY** | One charter clarification, and shape binding to each passed probe (probe scope §3 step 5). |
| **S6** | **Planted-marker residual and audience.** With no override, a planted marker leaves edits ungoverned with a row 4 notice. On Claude Code PreToolUse that notice reaches the agent only (#808), possibly the agent that planted the marker. D5 §5.1 accepts developer **or** agent, so this meets the accepted rule; the question is whether it is enough for the §5.4 risk. | Owner decision (risk acceptance) | **NOT READY** | Owner accepts the residual as stated, or asks for a stronger §5.4 outcome. D5 §5.4 names "not honoring markers created during the session" as the alternative; charter §11 C1 rejected it because PreToolUse has no baseline. |
| **S7** | **Status lines and pins.** The charter header still reads "Amendment A2 (PROPOSED …)" and "A2-RT (PROPOSED …)", and Q2 reads "Amendment A1 (PROPOSED …)", although the merging PRs record acceptance (#809, #811). Probe-scope pins for H2–H6 (codex `0.149.1`, Kiro `2.19.2`, Antigravity `2.8.1`, hermes-agent `0.19.0`) date from 2026-08 to 2026-10; whether they are still installable was not checked here, and a re-pin needs a reviewed amendment (probe scope §7). | Hygiene; risk | **NOT READY (minor)** | Fold the status lines into the next charter amendment. Check pin installability at harness-build time for each batch. |

**No contradiction was found** between the charter's Phase 2 design and
D5, Q2, the P2-first freeze amendment or the H1 record, apart from S3.

## 6. Recommended next step (one)

**Run shape discovery for the two at-risk paths first: H4a (Antigravity)
and H6a (Hermes), as one probe batch under the accepted probe scope.**

Why this one:
- **The gate decides whether Phase 2 exists.** If any path is
  `NO_NONBLOCKING_CHANNEL`, charter §5 keeps the implementation blocked for
  all consumers and requires D5 to be revisited. H4a and H6a are the two
  paths the probe scope marks "At risk", and both need shape discovery
  before any probe (probe scope §4, §5).
- **The spec gaps (S1–S6) do not affect the probes.** Probes test the
  channel with a harness emitter and no Mneme code (probe scope §3 step 1).
  The gaps can be closed in one charter amendment later, before the Phase 2
  freeze amendment, and their answers depend on whether the gate is
  reachable.
- **It is the cheapest decisive evidence.** Front-loading it avoids
  building the H2, H3 and H5 harnesses for a gate that might fail on H4 or
  H6.

What it needs:
- **Owner go-ahead** for the batch (probe scope §11), and acceptance of
  the change to the probe scope's recommended batch order (D5 there puts H4
  last).
- An operator for the Antigravity IDE run, and credentials for a live
  Hermes model session (probe scope §5, D2).

## 7. Not authorized by this record

- any probe, harness, live run or shape discovery, including the one
  recommended in §6;
- Phase 2: B1, I3, rows 3–5, populating `boundary` or `shadowed`, or the
  Phase 2 flips;
- any charter, Q2, D5, ADR or ADR-033 amendment, including the fixes for
  S1–S7;
- the Phase 2 `[layer1-freeze]` amendment;
- H2–H6, H1 re-runs, G3 re-runs, or any change to an earlier label;
- any release.

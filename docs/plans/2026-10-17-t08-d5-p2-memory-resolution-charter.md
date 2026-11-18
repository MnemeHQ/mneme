# T-08 D5 + P2: shared memory-resolution implementation charter (ACCEPTED: no execution authorized)

**Date:** 2026-10-17
**Status:** **ACCEPTED as the implementation charter** (owner approval 2026-10-17, given in the owner's working session, following an independent-review ACCEPT on `37fc32c8`). Docs only. **Acceptance authorizes no execution:** no code, no tests (including the L4 characterization test), no experiments or live probes, no `[layer1-freeze]` amendment, no ADR or ADR-033 change, no change to C1–C4 evidence, pins or worktrees.
**Revision 2 (2026-10-17):** answers the #542 review.
- The resolver now always reports the nearest Git boundary, including when a memory is found first (§3.2, §7).
- C3 takes the wait-for-evidence path: every consumer's host needs a verified channel before the freeze amendment (§5, §12).

**Amendment A1 (ACCEPTED, 2026-10-17; owner approval following an independent-review ACCEPT on `19734ac8`):** implements the accepted [H1c Stop-path decision](2026-10-17-dg1f-t08-d5-p2-h1c-stop-path-decision.md) (#554, O1). It changes **only** Claude Code Stop's candidate channel in §5, from `hookSpecificOutput.additionalContext` to top-level `systemMessage`. It is coordinated with the probe-scope Amendment A1 and is reviewed together with it. D5's developer-or-agent visibility rule, the gate rule, every other channel, implementation and the Layer 1 freeze are unchanged (§5.1).

**Amendment A2 (PROPOSED, 2026-11-16; draft 4):** adds a **P2-first interim phase** (§5.2). It lands the D6/Q2 P2 precedence rule on today's unbounded walk, across every consumer at once, with reporting level R-ii:
- the selection is computed in every consumer, but recorded only in the Agent SDK/LangChain trace;
- host-visible notices appear only on the H1 paths that passed on Claude Code `2.1.310` (#808), and only under H1's run conditions.

It states the ADR-033 C2a/C2b consequences of P2 precedence, and it requires an ADR-033 §4.1 erratum. Its gate is H1 only. B1, I3, §3.3 rows 3–5 and the H1–H6 gate become Phase 2, with every original prerequisite kept. Acceptance would authorize no code, test, live run, ADR change or `[layer1-freeze]` amendment.

**Amendment A2-RT (PROPOSED, 2026-11-16; if accepted, the acceptance is recorded in the merging PR record and squash commit, as for A2 in #809):** amends Amendment A2 for exactly one change, decided in the [remediation-text decision](2026-11-16-dg1f-t08-d5-p2-first-remediation-text-decision.md) (option O4). It adds to §5.2.6's "authorize only" list, and to what §5.2.8 permits, the following: the `MEMORY_PATH_MISMATCH` remediation line is chosen at emit time from whether the declared memory is a file. When it is not a file, the line names restoring the declared memory, with the exact text fixed in that decision. When it is a file, the existing line is kept. The P2-first `[layer1-freeze]` amendment covers it by superseding C2b Amendment 1 preserved items 3 and 4 and C2b charter §17.6 "stderr text", for this line only. Everything else in A2 is unchanged.

**Amendment A3 (PROPOSED, 2026-11-18):** the Antigravity and Hermes experimental carve-out (§5.3). It applies the accepted proposals #829 (E1–E5) and #830 (F1–F4, with the owner's correction). **Antigravity and Hermes** (a closed list, named in D5 Amendment A1) stay on the P2-first contract during Phase 2. Their paths H4a, H6a and H6b are `DEFERRED (not run)` and never pass. Phase 2 then needs H1, H2, H3 and H5, and H7 (OpenCode), which must be defined and pass before the freeze, with no exception. Every other gate and requirement is unchanged. Acceptance would authorize no code, test, harness, run, freeze amendment or release.

**Revision 3 (2026-10-17):** records the provenance of the D5 §5.1 owner approval (§3.4, C2, and the D5 contract), and splits H1–H6 into per-output-path probe requirements (§5).
- C2 is applied through an owner-approved refinement of D5 §5.1, recorded in the D5 contract itself (§3.4).
- The C4 wrapper limit is stated (§3.1).

**Source anchor:** `MnemeHQ/mneme` `main` at `28df1442`, read-only.
**Implements (if accepted):** the [D5 repository-boundary contract](2026-10-17-dg1f-t08-d5-repository-boundary-contract.md) (ACCEPTED, definition only) and the [D6/Q2 P2 precedence rule](2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md) (ACCEPTED, definition only). One charter for both, as both documents require.
**Format:** follows the [T-08 slice-1 charter](2026-10-15-t08-target-path-memory-resolution-charter.md).

## 1. Basis

- **D5** accepted the B1 stop rule: implicit discovery stops at the nearest `.git` directory or file (existence-only, same as `setup.py:find_project_root`). Non-Git projects keep today's walk. It also accepted four conditions:
  - §5.1: a host-visible `NO_MEMORY_SELECTED`, distinct from `PASS`;
  - §5.2: a declared external path;
  - §5.3: one cross-consumer stop rule;
  - §5.4: a defined outcome for planted markers.
- **D6/Q2** accepted P2: the repository memory `M_R` wins, and the `MNEME_MEMORY` override `M_X` only fills an absence. Its guarantee is bounded to correct boundaries and start points. It added a constraint: the §5.4 outcome must also block rule-2 substitution.
- **Invariant both acceptances place on this charter:** *a repository-controlled boundary change must not allow an external memory override to replace governance that would otherwise apply to the target.*

## 2. Invariants this charter must deliver

1. **I1 Stop rule.** Every implicit-discovery consumer (§4) ends its walk by the same rule.
2. **I2 Precedence.** `M_X` never replaces an `M_R` that the walk found.
3. **I3 Boundary-substitution guard.** If the walk stopped at a Git marker and a memory exists above that marker, `M_X` is applied **only if it is that same memory**. This is how the §5.4 outcome blocks rule-2 substitution (§3.3).
4. **I4 No silent anomaly.** Every anomalous selection outcome (§3.4) produces a structured outcome and is reported through a verified host-visible channel on every host (§5 gate H1–H6).
5. **I5 No start-point change.** Each consumer's start (target, session `cwd` or `project_dir`) is unchanged (D1/D2/D7).

## 3. Proposed change

### 3.1 One shared resolver

Add one resolver, for example `resolve_memory(start) -> MemorySelection`, in one module that every consumer imports. `MemorySelection` carries:
- `path`: the selected memory, or `None`;
- `source`: `discovered`, `override` or `none`;
- `reason`: §3.4;
- `boundary`: the Git root `R`, or `None` for no boundary;
- `shadowed`: the nearest memory above `R`, if any; used for diagnostics and I3 only, never selected implicitly.

Keep `find_memory(start) -> Optional[Path]` as a thin wrapper returning `resolve_memory(start).path`, so imports keep working. Its **semantics change** to the new rule. **The wrapper carries no diagnostics** (no `reason`, `boundary` or `shadowed`), so every in-tree consumer in §4 must call `resolve_memory` directly. The wrapper exists only for external imports. That change is what the freeze amendment (§9) authorizes.

Factor the marker test into one helper that `setup.find_project_root` also uses. Setup's behavior does not change.

### 3.2 Walk (B1)

```text
cur = resolve(start)
loop:
  if is_file(cur/.mneme/project_memory.json):
      M_R = it
      R = nearest dir at or above cur with exists(dir/.git), else none
      stop
  if exists(cur/.git):  R = cur; M_R = none
                        shadowed = nearest memory strictly above R (read-only)
                        stop
  if cur is filesystem root: R = none; M_R = none; stop
  cur = parent(cur)
```

- **`boundary` is always the nearest Git marker from the start, whichever check stops the walk.** When `M_R` is found first, the walk keeps going upward from `M_R`'s directory to the first `.git` or the filesystem root, and records it as `R`. Nothing between the start and `M_R` can hold a marker, or the walk would have stopped there, so this is the nearest boundary from the start. The extra steps are read-only, and they do not change which memory is selected.
  - **L1:** `R` = the directory holding both `.mneme/` and `.git`.
  - **L7:** for a nested memory below the Git root, `R` = the Git root.
  - **L2:** no Git anywhere above, so `R` = `None`.

  This matters for G3-B: the binding of root to effective memory path needs a correct root, not only a correct memory.
- **The memory check comes before the marker check in the same directory**, so L1 (`R/.mneme` next to `R/.git`) keeps its own memory.
- **Existence-only marker** (D5 L8a/L8b). There is no `gitdir:` parsing and no `git` call.
- **The `shadowed` lookahead walks the same ancestors today's walk would.** Worst-case cost equals today's unbounded walk.

### 3.3 Precedence (P2) with the I3 guard

`M_X` is the non-empty `MNEME_MEMORY` value. Paths are compared after `resolve()`.

| # | Walk result | `M_X` | Selected | `reason` |
|---|---|---|---|---|
| 1 | `M_R` found | unset, or equal to `M_R` | `M_R` | `DISCOVERED` |
| 2 | `M_R` found | set, different, or missing | `M_R` | `OVERRIDE_IGNORED` |
| 3 | no `M_R`, `shadowed` exists | an existing file equal to `shadowed` | `M_X` | `OVERRIDE_DECLARED_INHERITANCE` (D5 L5/L6 path) |
| 4 | no `M_R`, `shadowed` exists | unset | none | `BOUNDARY_SHADOWS_MEMORY` |
| 5 | no `M_R`, `shadowed` exists | set and not equal to `shadowed` (or missing) | none | `OVERRIDE_REFUSED_AT_BOUNDARY` |
| 6 | no `M_R`, no `shadowed` | an existing file | `M_X` | `OVERRIDE_FILLS_ABSENCE` (U1) |
| 7 | no `M_R`, no `shadowed` | set but missing or unreadable | none | `OVERRIDE_MISSING` |
| 8 | no `M_R`, no `shadowed` | unset | none | `NO_MEMORY_ON_PATH` |

**The adversarial case** (D6/Q2 §5 rule 2): `A/.mneme` exists, `.git` is planted at `A/src/`, the target is `A/src/app.py`, and `M_X` points at a permissive B. That is row 5: nothing is selected, the reason is visible, and B is **not** applied. Without the I3 guard, P2 rule 2 would have selected B.

**What I3 costs.** A legitimate submodule or parent-fallback user can inherit only the memory directly above their boundary, by naming it in `MNEME_MEMORY` (row 3). Naming any other memory is refused (row 5). Broader external sources are DG2 declared federation, not this charter.

**Residual, unchanged.** Planting a `.mneme/project_memory.json` (V3/V6) is still nearest-wins. That is D4, out of scope.

### 3.4 Outcome tiers

- **Anomalous:** rows 2, 4, 5 and 7. Reported host-visibly where a verified channel exists (§5).
- **Informational:** rows 3 and 6. The override is in effect; it is recorded in structured output.
- **Plain absence:** row 8. Under the **owner-approved D5 §5.1 refinement** (2026-10-17, recorded with its approval provenance in the [D5 contract §5.1](2026-10-17-dg1f-t08-d5-repository-boundary-contract.md)), row 8 produces a **structured non-PASS** `NO_MEMORY_ON_PATH` outcome where the consumer has a structured result. It gets no per-event host notice. Reason: with a user-wide plugin, every edit in every repository without Mneme would emit a notice, and nothing was displaced. Row 8 is still never reported as `PASS`. Rows 2, 4, 5 and 7 stay host-visible, exactly as D5 §5.1 requires.

## 4. Consumers in scope (all at once, D5 §5.3)

| Consumer | Call site today | Start (unchanged) |
|---|---|---|
| Claude Code direct write | `hook.py:1124` | resolved target |
| Claude Code Bash class A | `hook.py:710` | session `cwd` |
| Claude Code SessionStart | `hook.py:772` | session `cwd` |
| Claude Code Stop | `hook.py:919` | session `cwd` |
| Codex gate | `codex_cli/gate.py:155` | `cwd` |
| Codex stop audit (baseline and Stop) | `codex_cli/stop_audit.py:121-123` (used at `:88`, `:137`) | payload `cwd` |
| Kiro hook | `kiro/hook.py:298` | `cwd` |
| Antigravity adapter | `antigravity/adapter.py:242` | `cwd` |
| Agent SDK | `agent_sdk/adapter.py:336` | `project_dir` |
| Hermes | `hermes/adapter.py:256` | `project_dir` |
| LangChain | through its internal Agent SDK (`langchain/adapter.py:101-104`) | `project_dir` |

**Unchanged** (explicit paths, not discovery, per D6/Q2 O3): constructor `memory=` in Agent SDK, Hermes and LangChain; the Codex `memory_override`; `mneme check --memory`. Constructor overrides record `source: explicit` in the trace.

## 5. Host-visible channels: verify, don't assume

| Host / consumer | Candidate channel for anomalous outcomes | Status at `28df1442` |
|---|---|---|
| Claude Code PreToolUse (direct write, Bash) | exit 0 with `hookSpecificOutput.additionalContext`, **no** `permissionDecision` | **Unverified live.** The precedent is the Agent SDK PreToolUse `additionalContext` for fail-open (`agent_sdk/adapter.py:295-304`). Must not use `defer` or `allow`: warn mode chose `defer` precisely so as not to change permissions (`hook.py:487-490`). |
| Claude Code SessionStart | `hookSpecificOutput.additionalContext` | **Passed H1b under R1–R3** (#553). |
| Claude Code Stop | **Amendment A1 (accepted):** top-level `systemMessage`, exit 0, with **no** `hookSpecificOutput` and **no** `decision` (§5.1). It was originally `hookSpecificOutput.additionalContext` (`_emit_stop_feedback`, `hook.py:743-758`). | The original shape failed H1c with host-induced continuation (#549, #553). The A1 shape is **unprobed**. |
| Agent SDK, LangChain | PreToolUse `additionalContext`, as `ACTION_FAIL_OPEN` already does. SKIP returns `{}` today (`agent_sdk/adapter.py:305`). | Code precedent. Visibility to the developer depends on the embedding host. |
| Hermes | structured gate `reason` | Host visibility depends on the embedder |
| Codex gate and stop audit | none proven | Non-DENY wire shapes are **unproven** (`codex_cli/gate.py:418-423`, "belongs to M1d's live probing") |
| Kiro, Antigravity | none proven | Unknown |

**Rule.** No consumer may be described as "host-visible" without a recorded live probe on a pinned host version.

**Gate (C3: wait for evidence).** D5 §8 makes a verified channel per host an implementation prerequisite, and this charter adds no exception. Before the `[layer1-freeze]` amendment (§12), a recorded live probe must show that an anomalous outcome (rows 2, 4, 5 and 7) reaches the developer or agent on **every** host below:

| Host gate | Output paths, each needing its own recorded probe |
|---|---|
| H1 Claude Code | **H1a** PreToolUse (direct write, Bash) · **H1b** SessionStart · **H1c** Stop |
| H2 Codex CLI | **H2a** gate · **H2b** stop audit Stop output (the baseline step emits nothing, so it has no output path to probe) |
| H3 Kiro | **H3a** hook |
| H4 Antigravity | **H4a** adapter |
| H5 Agent SDK | **H5a** PreToolUse · **H5b** context injection · **H5c** LangChain gate result (its own delivery path, not SDK hook output) |
| H6 Hermes | **H6a** gate result (file, patch, terminal) · **H6b** context injection |

**A gate passes only when every output path listed under it has a recorded probe** showing an anomalous outcome reaching the developer or agent. A probe of one event type proves nothing about another event type on the same host. H1–H6 remain the six organizing gates.

Today none of the twelve output paths is verified. H2's non-DENY output shapes are explicitly unproven, and no live Kiro or Antigravity harness is recorded in the repository. **If any host gate cannot be met, the shared implementation stays blocked for all consumers (I1), and D5 must be revisited explicitly.** The charter itself may be accepted before the probes exist, but it authorizes no runtime change.

## 5.1 Amendment A1: Claude Code Stop channel (ACCEPTED)

**Status: ACCEPTED** (owner approval 2026-10-17, following an independent-review ACCEPT on `19734ac8`). Acceptance changes the proposed delivery mechanism only; it authorizes no harness, run, runtime change or freeze amendment. It is coordinated with the probe-scope [Amendment A1](2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md) (§4.2 there), reviewed together with it, and implements the owner's O1 selection in the [H1c Stop-path decision](2026-10-17-dg1f-t08-d5-p2-h1c-stop-path-decision.md) (#554, O1).

**Change.** In the §5 channel table, Claude Code **Stop**'s candidate channel for anomalous outcomes (rows 2, 4, 5 and 7) changes from `hookSpecificOutput.additionalContext` to **top-level `systemMessage`** (exit 0, no `hookSpecificOutput`, no `decision`). By the shape-binding rule (probe scope §3 step 5), an eventual implementation would have to emit exactly the probed `systemMessage` form at Stop, and only once a probe has passed it.

**Why.** H1c showed that Stop `additionalContext` makes the host continue the session. The Claude Code documentation describes that as intended (decision note §2). `systemMessage` is documented as a user-facing warning, and nothing documents it as continuing a Stop.

**Unchanged:**
- D5 §5.1's **developer-or-agent** visibility rule;
- the §5 gate rule (all H1–H6 output paths must pass before the freeze amendment, with no per-host exception);
- every other row of the channel table;
- the §3 design and §4 consumers;
- §6–§12.

A Stop notice that reaches only the developer is acceptable, as it already is on any path (probe scope D3), and it would be recorded as developer-only.

**Not authorized by A1:**
- any harness change or live run, including the two H1c runs the probe-scope A1 specifies;
- any runtime change, including the shipped `_emit_stop_feedback` (#550);
- implementation;
- the `[layer1-freeze]` amendment.

**Gate status.** H1 remains **NOT MET** until H1c passes under the A1 shape, or until a D5 amendment for Stop is accepted (decision note O2, the fallback).

## 5.2 Amendment A2: P2-first interim phase (PROPOSED)

**Status: PROPOSED** (2026-11-16), for independent review. Acceptance would change this charter's sequence and gate for **one interim phase only**. It would authorize **no** code, test, live run, ADR change, `[layer1-freeze]` amendment or runtime change. Each of those keeps its own PR and its own go-ahead (§5.2.8).

**A2 draft 4 (2026-11-16):** answers the re-review of `1acdfdfc` (ACCEPT WITH CHANGES, N1–N6). Changes:
- the ADR-033 test-rewrite route now allows row 6 (N1);
- the freeze list adds preserved item 1 of C2a, C2b and C2b Amendment 1, and Amendment 1 item 4 (N2);
- the returned path form is specified, and the "same as today" claims are qualified to the same selection (N3);
- the Claude Code gap in A2-3 is stated (N4);
- the second SessionStart text line is cited (N5);
- labelling is fixed (N6).

**A2 draft 3 (2026-11-16):** answered the independent review of `4fd82f61` (REQUEST CHANGES, findings F1–F13). Changes:
- the ADR-033 C2a/C2b consequences are stated, with a required ADR-033 §4.1 erratum (F1);
- the already-merged §6 test is flipped by P2-first (F2);
- the freeze-supersession list is completed (F3);
- emission conditions for the H1 notices (F4);
- the R-ii wording is made consistent, and the Q2 pointer corrected (F5);
- the record map and citations are corrected (F6);
- the unreadable-override open-probe is dropped (F7);
- the selection knock-ons are listed (F8);
- H2–H6 extensions get freeze cover (F9);
- the run conditions are bound to the visibility claim (F10);
- Phase 2 is rebased (F11), plus wording fixes (F12, F13).

**Owner direction.**
- **2026-11-11:** in the owner's working session on the D6/P2 assessment, the owner chose reporting level **R-ii** for a proposed P2-first phase, in the words "Re-probe Claude Code first". The re-probe is done: H1 passed on Claude Code `2.1.310` ([H1 gate record](../validation/dg1f-t08-d5-p2-host-path-h1-gate-2026-11-16.md), #808).
- **2026-11-16:** the owner asked for this amendment ("Yes, draft it").

Neither statement accepts the amendment. Acceptance follows independent review.

### 5.2.1 What P2-first is

P2-first is a **distinct interim contract**, not "D5 postponed". It lands the [D6/Q2](2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md) P2 precedence rule on **today's unbounded walk**, across every §4 consumer at once, before the D5 B1 stop rule exists. The rest of this charter (B1, I3, all eight §3.3 rows, the H1–H6 gate) becomes **Phase 2**. Phase 2's prerequisites are unchanged; its starting point is rebased onto P2-first (§5.2.5).

Why it can go first:
- **The defect it fixes is a precedence defect, not a boundary defect.** Today `find_memory` returns the `MNEME_MEMORY` path whenever the variable is set, and returns nothing when that file is missing (`hook.py:202-206`). Those are V5/V5-own (replacement) and V4 (masking), reachable through committed settings (Q2 §3, C2). The G3-2 case (#793) is the same defect: the repository's own memory **is** found by today's walk, and only the env-first order is wrong. P2 rule 1 fixes it without a boundary.
- **No edit that today's walk governs becomes ungoverned.** D5 §5.1 makes a verified host-visible channel the price of B1, because B1 turns governed edits (L4, L5, L6) into skips. P2-first never stops a walk earlier than today. Rows 1 and 2 select the memory the walk finds. Rows 6, 7 and 8 occur only where today's walk finds none, and there the **selection** equals today's for the same override. Row 7 can additionally gain an H1 notice. A **different** memory can govern than today (§5.2.3).
- **Planted Git markers have nothing to act on.** Markers are not honored, so the D5 §5.4 planted-marker case, and the Q2 rule-2 substitution it would enable, cannot occur.
- **The ordering risk Q2 names does not arise.** Q2 §10 warns against a window in which "the boundary exists but the override can still replace `M_R`". P2-first is the opposite order: precedence first, boundary later. It is still a departure from Q2 §10's "land together", and the Q2 pointer records it.

### 5.2.2 Interim selection contract

`M_W` is the memory today's walk finds: the nearest `.mneme/project_memory.json` at or above the consumer's unchanged start, with **no** Git-marker check. That is today's `find_memory` walk without its env branch. `M_X` is the non-empty `MNEME_MEMORY` value. Paths are compared after `resolve()`. "Exists" means `is_file()`, exactly today's test. The resolver never opens or reads `M_X` (A2-3).

| Row (§3.3 numbering) | Walk result | `M_X` | Selected | `reason` |
|---|---|---|---|---|
| 1 | `M_W` found | unset, or equal to `M_W` | `M_W` | `DISCOVERED` |
| 2 | `M_W` found | set, and different or missing | `M_W` | `OVERRIDE_IGNORED` |
| 6 | no `M_W` | an existing file | `M_X` | `OVERRIDE_FILLS_ABSENCE` |
| 7 | no `M_W` | set but missing | none | `OVERRIDE_MISSING` |
| 8 | no `M_W` | unset | none | `NO_MEMORY_ON_PATH` |

- **Rows 3, 4 and 5 cannot occur**, because they need a boundary. Their reason codes are reserved for Phase 2 and are never emitted in P2-first. The row numbers and reason codes are §3.3's, so Phase 2 extends the contract rather than renaming it.
- **Returned path form.** Equality uses `resolve()`, but the returned `path` keeps today's form:
  - when the selection is the override (row 6, or row 1 with an equal override), it is `Path(M_X)` exactly as given, as `hook.py:204-205` returns it today;
  - otherwise it is the walk's path, as today.

  So `--memory` arguments and `ContextInjection.memory_path` are byte-identical to today for the same selection.
- **Resolver shape.** The §3.1 resolver and `MemorySelection` land in P2-first with `path`, `source` and `reason`.
  - `boundary` and `shadowed` are **not populated** (both `None`). A field `walk: "unbounded"` records why, so no consumer can read an absent boundary as "no Git repository" (A2-5). Phase 2 populates both and sets `walk: "b1"`.
  - The explicit constructor path (§4, Q2 O3) is recorded as `source: "explicit"`, with `reason` and `walk` set to `None`. It is not a resolver outcome.
- **`find_memory`** stays the thin wrapper of §3.1 (C4). Its semantics change to this table only.
- **§3.4 tiers apply:**
  - rows 2 and 7 are anomalous;
  - row 6 is informational;
  - row 8 is plain absence. Its "structured non-PASS" is the existing `SKIP` / `"no project memory"` result wherever a consumer has one; no new string.
- **Unchanged:** start points (I5); explicit constructor and CLI memory paths (Q2 O3); D4 nearest-wins.

### 5.2.3 Costs and consequences, stated plainly

The independent review of the 2026-11-11 assessment required that P2-first make **no** blanket "never weakens" claim.

**A more permissive memory can govern than today:**
- **Row 2 with a stricter override.** An operator or committed setting that points `MNEME_MEMORY` at a stricter memory now gets the walked memory instead. This is Q2's accepted P2 cost (Q2 §6), and it is the point of P2: ambient configuration cannot replace a repository's own memory.
- **Case 2: an ancestor memory beats the override.** Without B1, `M_W` can sit **above** the repository: a parent-directory memory (L6), or the outer checkout's memory seen from a worktree (L4) or a submodule (L5). In P2-first that ancestor wins under row 1 or row 2, and the override is ignored. In Phase 2 the same layout becomes row 3 (an override equal to the shadowed memory applies) or row 5 (refused). A user who relies on `MNEME_MEMORY` to govern a nested repository below an ancestor memory loses that override during P2-first.
- **Adversarial variant: a planted memory now beats the override.** Anyone who can write a `.mneme/project_memory.json` into the checkout or any ancestor (V3/V6) can make it the selected memory **even when the operator set `MNEME_MEMORY`**. Today the env-first order defeats such a plant whenever the override is set. Planting stays nearest-wins in Phase 2 too (D4, out of scope). P2-first removes the override as an incidental defense against it. This is part of A2-4.

**ADR-033 C2a/C2b consequences (F1).** These follow from P2 precedence, not from any change to ADR-033's logic:
- **SS-3 through `MNEME_MEMORY` becomes unreachable.** Today a `MNEME_MEMORY` that differs from the declared memory makes `memory_mismatch` true (`availability.py:110-113`). That produces the `MEMORY_PATH_MISMATCH` refusal (remediation "unset MNEME_MEMORY …", `:164-165`) and the SS-3 sentence in the C2b Amendment 1 proceed text. Under row 2 the walk finds the declared memory, so neither happens; the edit is checked against the declared memory instead. SS-3 through other routes stays reachable, for example parent-directory discovery selecting a memory other than the declared one.
- **`MEMORY_MISSING` through a missing override becomes unreachable** whenever the declared memory exists. The walk finds it, and row 2 applies.
- **ADR-033 §4.1 becomes inaccurate.** It says `MNEME_MEMORY` "still takes precedence in `find_memory`" and that V5 is handled only by the mismatch rule. An ADR-033 §4.1 erratum PR is required (§5.2.7). No other ADR-033 behavior changes.
- **G3-1's `REFUSED_MEMORY_PATH_MISMATCH`** (#793) will not reproduce through `MNEME_MEMORY`. The G3 re-assessment records this (§5.2.7).

**Knock-on effects of a different selected memory (F8).** Whenever row 2 selects a different memory than today, everything downstream of the selection follows it:
- the policy root;
- SessionStart's baseline and Stop's audit tree, and so Stop feedback and `decision: block`;
- `ContextInjection.memory_path` and the injected text (Agent SDK, Hermes);
- verdicts, including a new `DENY` through each host's existing deny channel (Codex, Kiro, Antigravity);
- the ADR-033 outcomes above.

These are consequences of the intended precedence change, not new output channels.

**Not removed:**
- Planted memory files (above).
- Start points are not unified (D1/D2/D7), as in §4.
- An unreadable but existing override (A2-3) keeps today's load-failure path.

What P2-first removes: env-based replacement (V5, V5-own) and env-based masking (V4) of a memory the walk finds, whichever channel sets the variable (C1, C2, C4).

### 5.2.4 Reporting at level R-ii (I4-P2F, replacing I4 for P2-first only)

1. **Every consumer computes the selection; it is recorded only where a non-wire record already exists.** Every §4 consumer calls the resolver and gets `reason`, `source` and `walk`. Where they are recorded was checked against `main` at `0118d91f`:
   - **Agent SDK and LangChain:** additive keys (`selection_reason`, `selection_source`, `walk`) on **every** trace record that follows a selection. That covers records written through `_record` (`agent_sdk/adapter.py:135`, via `_gate` and `context_for_task`), and LangChain's direct trace append `_record_annotation_gap` (`langchain/middleware.py:224`). Records written with no selection, such as `_record_unmapped_skip` (`langchain/adapter.py:169-170`), carry none. The trace is an in-process list the embedding program may read. It is not hook output.
   - **Every other consumer has no such record,** so the selection is held in-process only:
     - **Claude Code direct write** (`hook.py:2036-2042`): with nothing selected it returns 0 with no output, unless an ADR-033 declaration is present. Then `emit_availability` produces its existing outcome (an exit-2 refusal or a proceed-note object).
     - **Claude Code Bash** (`:1594-1596`), **SessionStart** (`:1656`) and **Stop** (`:1806`): return 0 with no output when nothing is selected. Their notices are items 2 and 3.
     - **Codex gate:** `GateResult` is internal, and `SKIP` prints nothing (`codex_cli/hook.py:10`).
     - **Codex stop audit:** returns `None` or 0 (`stop_audit.py:88-90`, `:137-139`).
     - **Kiro:** returns 0 (`kiro/hook.py:298-300`).
     - **Antigravity:** emits `{}` (`antigravity/adapter.py:242-247`).
     - **Hermes:** returns `GateResult.reason` to its embedding host (`hermes/adapter.py:277-281`), so changing it would be host-facing.
   - **No new log, file, field or sink is created.** Existing `reason` strings (for example `"no project memory"`) and the fields of `GateResult` and `ContextInjection` stay byte-identical in every consumer.
   - **Stated plainly:** on Codex, Kiro, Antigravity and Hermes, and on Claude Code events where item 3 suppresses the notice, rows 2 and 7 leave no observable record. Row 2 still selects the walked memory there; only the report is absent.
     This is narrower than "structured reasons in every consumer" as the owner phrased R-ii on 2026-11-11, and A2-6 asks for it to be accepted as R-ii's meaning here. **A structured reason is not host visibility**, and no document, release note or UI may describe it as such (§5 rule).
2. **Host-visible notices only on probed paths, in the probed shape, under the probed conditions.** Rows 2 and 7 are reported host-visibly only on the H1 paths. The shape-binding rule (probe scope §3 step 5) applies:

   | Path | Shape | Recorded audience |
   |---|---|---|
   | H1a PreToolUse (direct write, Bash) | exit 0, `hookSpecificOutput.additionalContext`, no `permissionDecision` | agent (`DELIVERED_TO_AGENT`) |
   | H1b SessionStart | `hookSpecificOutput.additionalContext` | agent (`DELIVERED_TO_AGENT`) |
   | H1c Stop | top-level `systemMessage`, exit 0, no `hookSpecificOutput`, no `decision` (§5.1) | developer only (`DELIVERED_TO_USER_ONLY`) |

   The visibility claim covers **only the conditions H1 ran under**:
   - Claude Code `2.1.310 (Claude Code)`, `claude-opus-5-5`;
   - `--permission-mode acceptEdits`, `--allowedTools`, `--setting-sources project`;
   - n = 1 per path;
   - headless for H1a and H1b. H1c's developer delivery comes from the operator-observed interactive run, with screenshot evidence the owner accepted (#804 §8.3, #808).

   Default-mode permission prompts, other versions and other models were not exercised. Documentation calls the notice **unverified** outside these conditions.
3. **Emission conditions (F4).** A notice is emitted **only when the event's output would otherwise fit the probed shape**. Otherwise it is suppressed, and the event's existing output is unchanged:
   - **H1a:** emitted when the hook would otherwise exit 0 with no `permissionDecision`. That includes a PASS or SKIP with no output, and the C2b proceed-note object (item 5). **Suppressed** on a warn-mode `defer` event (`hook.py:844-860`) and on any exit-2 event (strict `FAIL`, ADR-033 refusal).
   - **H1b:** emitted when SessionStart would otherwise write nothing to stdout. **Suppressed** when it writes either existing plain-text line (`hook.py:1672-1679`, `:1686-1690`).
   - **H1c:** emitted when Stop would otherwise write nothing. **Suppressed** when Stop emits `_emit_stop_feedback` (`hookSpecificOutput`) or `{"decision": "block"}`.

   C5 is narrowed accordingly: row 2 is reported on every PreToolUse event **whose output fits the H1a shape**. A suppressed notice leaves no record (item 1).
4. **No new host-facing output on unprobed paths.**
   - The Codex gate and stop audit, Kiro, Antigravity, the Agent SDK, LangChain and Hermes emit **no selection notice and no new field** in their hook output, wire JSON, returned result objects or exit codes, for any row. The only addition is item 1's trace keys.
   - Their outputs can still differ from today, through the selection knock-ons in §5.2.3.
   - Reason: an unprobed shape can change host behavior. The original H1c Stop shape made the host continue the session (#549).
   - These paths are recorded as **not host-visible** until their own probe passes and §5.2.5's extension rule is met.
5. **ADR-033 coexistence.** On H1a direct write, the notice shares the single PreToolUse `additionalContext` object with the C2b Amendment 1 proceed text (`ProceedNote.consumed`, probe-scope A2-3): one object, both texts, no `permissionDecision`. That changes the fixed 17.2 output, which needs freeze cover (§5.2.6).
6. **Unchanged:** exit codes and blocking **for the same selected memory** (ADR-021; no row blocks). Where the selection changes, the exit code follows it. For example, in the G3-1 layout the ADR-033 refusal (exit 2) becomes the check's own result.

### 5.2.5 Gate for P2-first, and what changes for Phase 2

- **The P2-first gate is H1 only, and H1 has PASSED** (#808). All four H1 paths share one pin (`2.1.310`).
- **H2–H6 are not prerequisites for P2-first.** Extending item 2 to another host's paths needs, for each extension:
  1. that path's own passed probe;
  2. its own `[layer1-freeze]` amendment, because each notice is a runtime output change;
  3. an offline shape and coexistence test.

  Under R-ii **each path is judged on its own pin** (probe-scope A2-1), and its claim is bound to that pin and those run conditions. No new charter amendment is needed.
- **Q2's prerequisites, as they apply to P2-first:**
  - Q2 §10's "the same host-visible channel as D5 §5.1", and the reporting clauses of Q2 §5 rules 1 and 3 ("host-visible", "never a silent skip"), are **relaxed** to I4-P2F. So is the "visible notice" mitigation in Q2 §6. This is the substance of R-ii and the main point the reviewer is asked to accept (A2-1). Q2 carries a pointer amendment naming these clauses (Q2 Amendment A1).
  - Q2 §10's "D5 §5.4 planted-marker outcome defined, including the rule-2 case" is a definition prerequisite. It is **already met** by §3.3 row 5 and I3, and is not exercised in P2-first, because no marker is honored.
- **Phase 2 keeps every original prerequisite:**
  - all of H1–H6, with every listed output path (§5);
  - its own freeze amendment;
  - D5 itself (§5.1, §8) is not amended.

  The §5 clause "if any host gate cannot be met … D5 must be revisited explicitly" still applies.
- **Phase 2 is rebased onto P2-first `main` (F11):**
  - the §6 characterization tests are already merged (#543, `5d8bf82a`). P2-first flips the planted-marker-plus-override pair to row 2 (§5.2.6); Phase 2 flips them again to row 5;
  - the §7.6 flips and the §8 C2 re-run are done by P2-first;
  - the precedence part of §9's supersession is done by the P2-first freeze amendment. Phase 2's freeze amendment supersedes only what remains: the walk, B1, I3 and rows 3–5;
  - §12 step 2's baseline is post-P2-first `main`.

  §10's "the §6 test, until the owner says so" and §12 step 2 were already stale before A2, because #543 merged the test.

### 5.2.6 Freeze amendment and tests (P2-first)

A separate `[layer1-freeze]` P2-first amendment PR, under Amendment Procedure §3(b), must:
- **authorize only:**
  - the shared resolver on today's walk;
  - the five §5.2.2 rows;
  - I4-P2F reporting on the H1 paths, under the §5.2.4 item 3 emission conditions;
  - the migration of every §4 consumer at once, with start points unchanged;
  - `find_memory` kept as a wrapper with the new precedence;
- **supersede, for `MNEME_MEMORY` precedence, its stated consequences (§5.2.3) and the H1 notices only:**
  - T-08 slice-1 preserved item 3: both "`find_memory` is not modified" and "`MNEME_MEMORY` precedence is unchanged: when set, it wins exactly as today". The walk, the parent-directory fallback and nested-memory behavior stay preserved;
  - T-08 slice-1 preserved item 6 (Bash, SessionStart and Stop selection and behavior);
  - C2a preserved item 4 (the "`find_memory`" and "`MNEME_MEMORY` precedence" clauses) and C2a item 6 (Bash, SessionStart and Stop behavior);
  - C2b preserved item 4 (the same two clauses) and C2b item 6;
  - preserved item 1 of C2a, C2b and C2b Amendment 1 ("No declaration → today's behavior, byte-identical output, the same exit codes"). On a direct write with no declaration, the H1a notice and the row-2 selection change both alter that output;
  - C2b Amendment 1:
    - preserved item 3 (refusals, exit codes, every existing stderr line), because SS-3 via `MNEME_MEMORY` and `MEMORY_MISSING` via a missing override become unreachable;
    - preserved item 4 (`AUTHORIZED`, `REVOKED` and `VERIFIED_ABSENT` outputs), because the `MNEME_MEMORY`-driven SS-3 stderr line is emitted under every authorization state;
    - preserved item 7 (Bash, SessionStart and Stop behavior);
    - its authorized "exactly one … object with the fixed 17.2 text", which gains the coexisting H1a notice;
- **leave unauthorized** everything else in §10, including B1, I3 and rows 3–5.
- **also authorize, under Amendment A2-RT:** the `MEMORY_PATH_MISMATCH` remediation line chosen at emit time (header note A2-RT; remediation-text decision, option O4).
- **confirm the list is exhaustive.** The later freeze amendments (DG1B1, #260, G1, G2-1, S1, C4, R0) were checked for preserved memory-selection items by keyword only. The freeze PR must confirm that none of them preserves memory selection.

The implementation PR carries a subset of §7, plus P2-first cases:
- **§7.2 precedence matrix** for rows 1, 2, 6, 7 and 8, including relative, symlinked and differently-cased (Windows) override paths. It also covers the A2-3 override classes:
  - missing, or a directory: row 7, or row 2 if `M_W` exists;
  - existing but unreadable, and existing but malformed: row 6, then today's load-failure path, unchanged.
- **§7.5 consumer parity** across all eleven consumers, including the `walk` field, against the §4 call sites as they are at implementation time. The §4 line numbers predate `0118d91f` and are stale.
- **§7.6 flips:** V4 to row 2 or row 7, whichever applies; V5 and V5-own to row 2.
- **§6 flips (F2):** in `tests/integrations/claude_code/test_memory_boundary_characterization.py`, `TestPlantedMarkerPlusOverride.test_override_replaces_repository_memory` and `test_forbidden_edit_is_permitted_under_override` flip to row 2 (A's memory selected, the forbidden edit refused). Every other §6 case is unchanged.
- **Case 2:** an ancestor memory plus a different override selects the ancestor (row 2). Pinned so that Phase 2's change to row 3 or 5 is a reviewable flip.
- **ADR-033 tests (F1):** these set `MNEME_MEMORY` beside a declared memory to produce SS-3 or `MEMORY_MISSING`:
  - C2a: `test_d5_mneme_memory_override_is_mismatch` (`test_availability_c2a.py:299`) and the real-check mismatch and incomplete cases;
  - C2b: `test_h7_mneme_memory_mismatch_refuses` (`test_availability_c2b.py:615`) and `test_h12`;
  - C2b Amendment 1: `test_a3_mismatch_sentence` (`test_availability_c2b_am1.py:124`) and `test_a9`.

  Each is rewritten to produce the same outcome through parent-directory discovery **or through row 6**: a `.mneme/` directory holding the declaration but no memory (for the P1 no-declaration parity case: no declaration and no memory), no ancestor memory, and `MNEME_MEMORY` naming a foreign memory.

  Row 6 is required for the two `incomplete` cases, which need the target outside the selected memory's root (`test_availability_c2a.py:424-426`). A walked memory is always an ancestor of the target, so parent discovery cannot produce that. The two cases are:
  - the D-matrix `incomplete` case;
  - `test_p1_real_check_no_declaration_byte_identical[incomplete]` (`:401`). Its oracle is the pinned pre-C2a hook (`78459d1a`), and under row 6 the selection, path form and output equal that oracle's. A new test asserts that `MNEME_MEMORY` alone no longer produces SS-3 (row 2). Every other C2a, C2b and Amendment 1 test stays green and unmodified.
- **§7.7** unchanged tests, and **§7.9** latency.
- **§7.8 channel shape:**
  - each H1 notice is in its probed shape;
  - each item-3 suppression case emits no notice, with output identical to today;
  - for every row and every consumer, hook output, exit code, `GateResult` and `ContextInjection` are identical to what the **same selected memory** produces today. The exceptions are the H1 notices and the Agent SDK/LangChain trace keys.
- **Offline coexistence tests** for all three H1 paths:
  - H1a: one object with the C2b proceed text, no `permissionDecision`, exit code unchanged (probe-scope A2-3);
  - H1b: no notice beside the plain-text line;
  - H1c: no notice beside `_emit_stop_feedback` or `decision: block`.

The full canonical suite must run.

### 5.2.7 Sequence (P2-first)

1. This amendment, accepted.
2. An ADR-033 §4.1 erratum PR, docs only. It states that `MNEME_MEMORY` no longer takes precedence over a discovered memory once P2-first lands, and that SS-3 stays reachable by other routes. The erratum takes effect with the implementation.
3. The P2-first `[layer1-freeze]` amendment PR (§5.2.6).
4. The implementation PR, with the §5.2.6 tests and a full-suite run, squash-merged under ADR-022.
5. The P2-first live evidence PR, on Claude Code `2.1.310` under the §5.2.4 item 2 conditions, using harness-planted state only:
   - the §8 C2 re-run: expect the repository memory to govern, and `OVERRIDE_IGNORED` to be visible where item 3 allows it;
   - planted marker plus override: expect A's memory, row 2.
6. A G3 re-assessment record. G3 stays partial until P2 exists (#793). The record covers what P2-first changes, including G3-1 (§5.2.3).

Each step needs the previous one merged and its own go-ahead. Phase 2 then continues with §12 steps 3–6, rebased as §5.2.5 states. The H2–H6 probes proceed by adoption. As each passes, it extends item 2 under §5.2.5's extension rule.

### 5.2.8 Not authorized by A2

Amendment A2-RT (header) permits exactly one diagnostic change beyond this list: the `MEMORY_PATH_MISMATCH` remediation line (option O4).

- code, tests, live runs, the ADR-033 erratum or the P2-first freeze amendment;
- B1, I3 or rows 3–5;
- any change to D5, to D5 §5.1's visibility rule for Phase 2, or to the H1–H6 gate for Phase 2;
- any host-visible claim beyond the three H1 rows under the §5.2.4 item 2 conditions;
- any change to ADR-033 beyond the stated consequences of P2 precedence (§5.2.3) and its §4.1 erratum;
- G3/G3-B authority, or any new fail-closed or availability behavior;
- DG2 federation, C5/C6;
- DG1 deferred B2b and C1b, which still need a trusted-context design;
- the C2/C3a release, which stays on hold.

### 5.2.9 Decisions requested of the reviewer

| # | Decision | Recommendation |
|---|---|---|
| A2-1 | Relax I4, Q2 §5 rules 1 and 3's reporting clauses, Q2 §6's notice mitigation and Q2 §10's host-visible prerequisite to I4-P2F, for P2-first only | **Yes.** It is the owner's chosen level (R-ii). On unprobed paths, row 2 now silently selects the right memory where today it silently selects the wrong one, and rows 6 to 8 select what today selects. Visibility is claimed only where it was proven. |
| A2-2 | Adopt `M_W` (today's unbounded walk) as the interim contract | **Yes.** The variant that computes `R` without stopping, so an ancestor memory loses to the override, was rejected on 2026-11-11: a planted `.git` would reopen the substitution. |
| A2-3 | Missing, unreadable and malformed overrides | **`is_file()` only; the resolver never opens the file.**<br>- *Missing* (`is_file()` false, including a directory) gives row 7, or row 2 when `M_W` exists. This matches Q2 rule 3's classification.<br>- *Unreadable* and *malformed* files both exist, so they are selected under row 6. They then take today's load-failure path, unchanged (ADR-021; CI1.4 §7 condition 4). That path is non-PASS. The review reports it as visible today on Codex, Kiro and the Agent SDK/LangChain, as an `UNEVALUATED` fail-open notice. That is **partly unverified**: what `mneme check` returns for an unreadable memory was not run.<br>- **Deviation from Q2 rule 3, stated:** rule 3 classifies an unreadable override as `NO_MEMORY_SELECTED`. An open-probe would make that a row 7, which is silent off the H1 paths (F7). It would lose today's visible fail-open, add a Windows sharing-lock race, and trigger OneDrive placeholder downloads. Keeping today's path serves rule 3's "never a silent skip" better **on Codex and the Agent SDK/LangChain only**. On Claude Code direct write, today's load-failure path is stderr-only (`hook.py:1527-1532`). So it is not visible there, where a row-7 notice would have been delivered. That gap is accepted.<br>- The pre-existing uncaught `MemoryStore.load` error in the Agent SDK `context_for_task` (`agent_sdk/adapter.py:151-152`) is unchanged and out of scope.<br>- Draft 2 (`4fd82f61`) proposed the open-probe; it is withdrawn. |
| A2-4 | Accept, for the interim, case 2 (an ancestor memory beats the override) **and** its adversarial variant (a planted memory beats the operator's override) | **Yes, with the risk stated** (§5.2.3). Case 2 ends in Phase 2. The adversarial variant is D4 territory. P2 removes the env override as an incidental defense, but repository memory was always meant to win (Q2 §4 finding). The reviewer is asked to accept or reject this risk explicitly. |
| A2-5 | Leave `boundary` and `shadowed` unpopulated, with a `walk` marker | **Yes.** It keeps a later G3-B root binding from reading an absent boundary as a real one. |
| A2-6 | No new output on unprobed paths, and the reason recorded only in the Agent SDK/LangChain trace (§5.2.4 item 1) | **Yes.** The H1c history shows an unprobed shape can change host behavior. Hermes's `reason` reaches its host, so it cannot carry the selection either. The cost: rows 2 and 7 leave no record on Codex, Kiro, Antigravity or Hermes, or on suppressed Claude Code events. Accepting this also accepts the narrower reading of R-ii in item 1. |
| A2-7 | Phase 2 keeps every original prerequisite, rebased onto P2-first | **Yes.** All of H1–H6 with every listed output path (§5) and its own freeze amendment are still required. §5.2.5 lists what P2-first has already done. A2 relaxes nothing for Phase 2. |
| A2-8 | Accept the ADR-033 C2a/C2b consequences of P2 precedence (§5.2.3), the rewritten tests (§5.2.6) and the §4.1 erratum (§5.2.7) | **Yes.** They are the intended effect of P2 on the one path where ADR-033 compensated for env-first precedence. The declared memory now governs instead of producing a mismatch refusal, and SS-3 stays reachable by other routes. |
| A2-9 | Notice emission conditions: suppress rather than reshape when the event's output does not fit the probed shape (§5.2.4 item 3) | **Yes.** Carrying the notice in another channel (for example exit-2 stderr, or warn-mode `permissionDecisionReason`) would be an unprobed shape. C5 narrows accordingly. |

## 5.3 Amendment A3: Antigravity and Hermes experimental carve-out (PROPOSED)

**Status: PROPOSED** (2026-11-18), for independent review and owner acceptance.

**Basis:** it applies two accepted proposals. Both were accepted after independent review:
- the [Antigravity carve-out proposal](2026-11-18-t08-d5-p2-antigravity-carve-out-proposal.md) (#829, `0ad042aa`; owner decisions E1–E5);
- the [Hermes follow-up](2026-11-18-t08-d5-p2-hermes-carve-out-follow-up.md) (#830, `466f22d7`; owner decisions F1–F4, with the owner's correction on Hermes selection).

It is coordinated with D5 Amendment A1, Q2 Amendment A2 and probe-scope Amendment A5, and is reviewed together with them.

Acceptance would authorize **no** code, test, harness, live run, `[layer1-freeze]` amendment or release.

### 5.3.1 Excepted consumers (a closed list)

The excepted consumers are **Antigravity** (`antigravity/adapter.py`) and **Hermes** (`hermes/adapter.py`), as named in D5 Amendment A1.
- The list is **closed**. Adding any consumer needs its own separately reviewed D5 amendment.
- Owner direction excludes OpenCode.

### 5.3.2 Contract for the excepted consumers during Phase 2

- **The P2-first contract stays.** Each excepted consumer keeps the §5.2.2 P2-first contract:
  - today's unbounded walk;
  - rows 1, 2, 6, 7 and 8;
  - `walk: "unbounded"`, with `boundary` and `shadowed` unpopulated (A2-5).

  B1, I3 and rows 3–5 do not apply to them.
- **Reporting continues at R-ii.** I4-P2F (§5.2.4) continues for them beyond P2-first: rows 2 and 7 are computed, but they get no record, no notice, and no new field or output (§5.2.4 items 1 and 4). The A2-3 classification of an unreadable override (selected, then today's load-failure path) also continues for them.
- **No claims.** No host-visible notice, and no Phase 2 boundary behavior, may be claimed for either consumer. H4a, H6a and H6b are **`DEFERRED (not run)`**. That status is not one of the probe-scope §6 labels, never passes, and is never counted in a gate.
- **Hermes specifics.**
  - The discovery start point is the fixed `project_dir` of the gate instance (`hermes/plugin.py`, `make_gate` and `register`).
  - The memory is **re-resolved on every invocation**: `context_for_turn` and each of the three gates call `_memory()` independently (`hermes/adapter.py:143`, `:291`, `:417`, `:499`). Nothing is cached.
  - The explicit constructor `memory=` is unchanged (Q2 O3). Its existing gap, no `source: explicit` record (§4), is recorded, not fixed.

### 5.3.3 What this amendment supersedes in this charter

The following passages read as stated here. **Any other mention** of H1–H6 (for example in the A2 header, §5.2.1 or §8), of "six gates" or "twelve paths", of "every consumer at once" (§4 heading), or of a "P2-first only" scope for I4-P2F (§5.2.4 heading, A2-1) reads as the listed gates and paths, or as excluding the excepted consumers, as the case requires. Every other passage is unchanged.

| Passage | Reads, under A3 |
|---|---|
| §2 **I1** | Applies to every §4 consumer **except the excepted consumers**. |
| §2 **I4** ("on every host (§5 gate H1–H6)"); §5.2.4 heading and A2-1 ("for P2-first only") | On every **listed** host. For the excepted consumers, **I4-P2F continues beyond P2-first**, through Phase 2, until each re-enters (§5.3.2). |
| §3.1, §3.2 (one resolver, the B1 walk) | The shared resolver has **two walk modes**: B1 for the non-excepted consumers, and the unbounded P2-first walk for the excepted consumers. `find_memory` keeps its §3.1 semantics. Neither excepted consumer calls it. |
| §4 (consumer table) | The Antigravity and Hermes rows are **deferred: P2-first contract**. |
| §5 (gate table; "six organizing gates"; "twelve output paths"; "this charter adds no exception"; "if any host gate cannot be met … D5 must be revisited explicitly") | **H4 and H6 move to a "deferred (experimental)" row.** The gate rule ("every listed path") is unchanged for **H1, H2, H3 and H5**, and for H7 once it is defined. "Six" and "twelve" read as "listed". "No exception" and the D5-revisit clause apply to every listed gate. **D5 Amendment A1 is that explicit revisit** for the two excepted consumers. |
| §5.1 (A1) "no per-host exception" | Except the D5 A1 exceptions. |
| §5.2.5 ("Phase 2 keeps every original prerequisite"; "all of H1–H6"; "D5 itself (§5.1, §8) is not amended") | Phase 2 needs **H1, H2, H3 and H5**, with every listed path. It also needs **H7 (OpenCode): Phase 2 cannot freeze until H7 is defined, by its own reviewed charter and probe-scope amendment, and passes**, unless the owner decides otherwise separately. "D5 itself is not amended" is superseded **for the excepted consumers only**, by D5 A1. |
| §5.2.7 ("The H2–H6 probes proceed by adoption"), §5.2.8 ("the H1–H6 gate for Phase 2"), A2-7 ("All of H1–H6") | They read as "the listed gates". |
| §7.1, §7.5 (offline tests) | The consumer-parity tests expect the **P2-first (unbounded) selection** for each excepted consumer. Each excepted consumer gets a case showing it stays unbounded in layouts where B1 consumers stop. **For Hermes**, `tests/integrations/test_p2_first_consumer_parity.py::test_hermes` covers only `context_for_turn`, so a **gate-path case** is added, and both paths must show the unbounded mode. The §7.8 `test_p2_first_same_selection.py` cases are unchanged. |
| §8 (live evidence; "the channel probes for H1–H6 (§5) are the gate before the freeze amendment") | The channel probes for the **listed** gates are that gate. There is no live evidence for the excepted consumers. |
| §9 (the Phase 2 `[layer1-freeze]` amendment) | It authorizes B1, I3 and rows 3–5 **for the non-excepted consumers only**, and preserves the excepted consumers' P2-first behavior. |
| §10 ("Preserved") | Adds the excepted consumers' P2-first behavior. |
| §11 C3 ("no per-host exception"), §12 step 3 ("All six gates must pass") | Except the D5 A1 exceptions. They read as "every listed gate". |

### 5.3.4 Re-entry and failure rules

- **Antigravity re-enters Phase 2** only after all of:
  - its own H4a pass on its pin (`2.8.1`);
  - its own `[layer1-freeze]` amendment;
  - a reviewed consumer-parity flip.
- **Hermes re-enters only as a whole consumer**, after all of:
  - **both** H6a and H6b pass on one hermes-agent pin;
  - its own `[layer1-freeze]` amendment;
  - a reviewed parity flip.

  A partial re-entry would let the separate `_memory()` calls use different discovery rules (B1 on one path, unbounded on the other).
- **H6a candidate T** (`transform_tool_result`) stays unapproved unless the owner accepts it.
- **Each consumer re-enters independently** of the other.
- **Failure rule:** a failing label on a deferred path goes to the owner. The consumer stays on the exception, and no other consumer is blocked.

### 5.3.5 Costs, stated plainly

- The excepted consumers keep P2-first's gaps: an ancestor memory, or a planted memory above the repository boundary, still governs. L4, L5 and L6 behave as on `main` today.
- Rows 2 and 7 are unreported on them, with no end date.
- Selection diverges from B1 consumers in rows 4 and 5.
- For Hermes, the divergence follows its fixed start point, independent of the edited file. An embedder that runs Hermes alongside the Agent SDK or LangChain gets diverging selections in rows 4 and 5.
- The resolver keeps two walk modes.

### 5.3.6 Not authorized by A3

- code, tests (including the new parity cases), harness changes or live runs;
- the Phase 2 `[layer1-freeze]` amendment, or any release;
- any change to H1, H2, H3, H5 or their paths and pins;
- any exception for OpenCode or any other consumer;
- H6a candidate T; reclassifying Antigravity (E0, separate);
- changing any earlier label: H1 stays `PASS`, G3 stays `PARTIAL`, and Phase 2 stays NOT READY and BLOCKED.

## 6. Characterization test first (D5 §7.4)

A **test-only PR, before any behavior change**, pins today's `main` behavior with temporary-directory layouts. Each case below asserts today's `find_memory` result:
- **L4:** `outer/.git/` plus `outer/.mneme/`, and `outer/.worktrees/wt/.git` (a file: `gitdir: …`) with no memory. Target `outer/.worktrees/wt/app.py` selects `outer`'s memory, i.e. it **crosses** the worktree.
- **L5:** a submodule-style `.git` file with no memory selects the outer memory.
- **L6:** a parent memory above a repository that has none governs.
- **L8b:** a `.git` file whose `gitdir:` target is missing is ignored by the walk.
- **Planted marker plus override:** `A/.mneme`, `A/src/.git` and `MNEME_MEMORY` = B select B.

It changes no runtime code, so it needs **no freeze amendment**. It does need explicit owner authorization (D5 §7.4: "running it is not yet authorized"). The implementation PR then flips these assertions to §3.3's outcomes, and that flip is the reviewable diff of the behavior change.

## 7. Offline acceptance tests (implementation PR)

1. **Stop-rule matrix:** L1, L2, L3, L4, L5, L6, L7, L8a and L8b, each with the expected `MemorySelection` (path, source, reason, boundary, shadowed). This explicitly includes the **boundary assertions when a memory is found first**: L1 (`boundary` = the same directory), L7 (nested memory, `boundary` = the Git root) and L2 (`boundary` = `None`).
2. **Precedence matrix:** all eight §3.3 rows, including path equality after `resolve()`, with `MNEME_MEMORY` given as a relative path, a symlinked path and a differently-cased path on Windows.
3. **Adversarial row 5:** planted `A/src/.git` with override B. Assert B is not selected, the reason is `OVERRIDE_REFUSED_AT_BOUNDARY`, and the hook does not exit as if it were a `PASS`.
4. **Legitimate row 3:** a submodule whose override names the outer memory is governed by it.
5. **Consumer parity:** each §4 consumer, given the same layout and start directory, gets the same selection. A table-driven test covers all eleven.
6. **Flipped characterizations:** V4 → row 2 or row 7 (whichever applies); V5 and V5-own → row 2; plus the §6 characterization set.
7. **Unchanged:** `test_memory_discovery.py` cases (tmp dirs without `.git`), every T-08 slice-1 test, the #484 coherence set, setup tests, and all strict/warn tests.
8. **Channel shape:** the anomalous outcomes emit the §5 candidate shape. They **never** emit `permissionDecision`, and exit codes are unchanged.
9. **Latency:** run the existing PreToolUse latency benchmark (#531/#535) and record before and after. No threshold is set here.

The full canonical suite must run. A docs-only CI skip is not enough.

## 8. Live evidence (separate evidence PR, separately authorized)

On the pinned Claude Code host (today 2.1.202 on Windows, `claude -p`), using harness-planted state only, as in the C3/C4 plumbing probes:
- **R0/R2 controls.**
- **Channel probe:** is a row-2/4/5/7 notice visible to the agent, and to the user, through the §5 channel?
- **C2 re-run:** committed `env.MNEME_MEMORY` set to B, in the R4 and own topologies. Expect `M_R` to govern, the forbidden edit refused, and `OVERRIDE_IGNORED` visible.
- **Planted marker plus override:** expect row 5, nothing selected, a visible reason, and B never applied.
- **L4 worktree:** expect row 4, visible.

The **channel probes** for H1–H6 (§5) are the gate before the freeze amendment, not follow-ups. They are recorded as their own evidence. Agent-written state stays out of scope. C5/C6 remain unauthorized.

## 9. Required `[layer1-freeze]` amendment (not made here)

After this charter merges, a separate `[layer1-freeze]` PR under Amendment Procedure §3(b) must:
- **authorize only** §3: the shared resolver; the B1 stop rule; P2 with the I3 guard; the §3.4 outcomes; the migration of every §4 consumer to the resolver, with start points unchanged; `find_memory` kept as a wrapper with the new semantics;
- **restate §10 as preserved**, and explicitly supersede the T-08 amendment's preserved item 3 ("`find_memory` is not modified; `MNEME_MEMORY` precedence unchanged; parent-directory fallback unchanged") **for these three points only**;
- **leave unauthorized** everything in §10's "not authorized" list.

## 10. Preserved, and not authorized

**Preserved:**
- ADR-021 fail-open and every exit code: no outcome in §3.4 blocks.
- The #260 coherence rules (#484).
- `mneme check`, its CLI, exit codes and `mneme.check/v1`: no new field.
- strict/warn and path-selector semantics (ADR-017, ADR-020).
- Each consumer's start point (D1/D2/D7).
- Explicit constructor and CLI memory paths.
- D4 nearest-wins inside `R`.
- D3 out-of-root behavior (still reachable through rows 3 and 6).
- `mneme setup` behavior.
- Canonical authority (ADR-023, ADR-029, ADR-030, ADR-031).
- Frozen benchmark fixtures; `.mneme/project_memory.json`.

**Not authorized:**
- implementation by this charter;
- the freeze amendment in this PR;
- the §6 test, until the owner says so;
- any live probe;
- D1, D2, D3, D4 and D7;
- G3/G3-B authority, ADR-033, or any fail-closed or availability behavior;
- hook registration or coverage changes;
- new CLI flags, schemas or MCP surfaces;
- DG2 federation;
- C5/C6.

## 11. Decisions requested of the reviewer

| # | Decision | Recommendation |
|---|---|---|
| C1 | Is I3 (override applies at a boundary only if it equals the shadowed memory) the D5 §5.4 outcome? | **Yes.** It blocks the adversarial case, keeps the L5/L6 inheritance path, and needs no session state. The alternative, ignoring markers created during the session, needs baselines that PreToolUse does not have. |
| C2 | Row 8 (plain absence) not reported per event | **Resolved:** the owner approved the D5 §5.1 refinement on 2026-10-17 in the owner's working session, in these words: "Approve the D5 §5.1 refinement (row 8: structured non-PASS only, no per-event notice) and amend D5 in the same PR." The D5 contract records it. The reviewer's conditional support is not the approval. Row 8 gets a structured non-PASS outcome only. |
| C3 | Per-host channel gate | **Resolved: wait.** H1–H6 must all be verified before the freeze amendment, with no per-host exception (§5). |
| C4 | Keep `find_memory` as a wrapper with new semantics | **Yes.** The wrapper changes behavior and carries no diagnostics, so in-tree consumers use `resolve_memory` (§3.1). |
| C5 | `OVERRIDE_IGNORED` (row 2) on every event vs. once per session | Every event for PreToolUse consumers. It signals a misconfiguration and should stay visible until fixed. |

## 12. Sequence

1. **Done:** this charter, accepted 2026-10-17 (independent-review ACCEPT on `37fc32c8`; owner approval).
2. **§6 characterization test PR** (test-only), after the owner authorizes it.
3. **H1–H6 channel probes** (§5), each recorded as evidence and each separately authorized. **All six gates must pass, with every listed output path probed.**
4. **`[layer1-freeze]` amendment PR** (§9), only after step 3.
5. **Implementation PR** with the §7 tests and a full-suite run, squash-merged under ADR-022.
6. **§8 behavioral live evidence PR.**

Each step needs the previous one merged.

# T-08 D5 + P2: shared memory-resolution implementation charter (ACCEPTED: no execution authorized)

**Date:** 2026-10-17
**Status:** **ACCEPTED as the implementation charter** (owner approval 2026-10-17, given in the owner's working session, following an independent-review ACCEPT on `37fc32c8`). Docs only. **Acceptance authorizes no execution:** no code, no tests (including the L4 characterization test), no experiments or live probes, no `[layer1-freeze]` amendment, no ADR or ADR-033 change, no change to C1–C4 evidence, pins or worktrees.
**Revision 2 (2026-10-17):** answers the #542 review.
- The resolver now always reports the nearest Git boundary, including when a memory is found first (§3.2, §7).
- C3 takes the wait-for-evidence path: every consumer's host needs a verified channel before the freeze amendment (§5, §12).

**Amendment A1 (ACCEPTED, 2026-10-17; owner approval following an independent-review ACCEPT on `19734ac8`):** implements the accepted [H1c Stop-path decision](2026-10-17-dg1f-t08-d5-p2-h1c-stop-path-decision.md) (#554, O1). It changes **only** Claude Code Stop's candidate channel in §5, from `hookSpecificOutput.additionalContext` to top-level `systemMessage`. It is coordinated with the probe-scope Amendment A1 and is reviewed together with it. D5's developer-or-agent visibility rule, the gate rule, every other channel, implementation and the Layer 1 freeze are unchanged (§5.1).

**Amendment A2 (PROPOSED, 2026-11-16):** adds a **P2-first interim phase** (§5.2). It lands the D6/Q2 P2 precedence rule on today's unbounded walk, across every consumer at once, with reporting level R-ii: a structured reason in every consumer, and host-visible notices only on the H1 paths that passed on Claude Code `2.1.310` (#808). Its gate is H1 only. B1, I3, §3.3 rows 3–5 and the H1–H6 gate become Phase 2, unchanged. Acceptance would authorize no code, test, live run or `[layer1-freeze]` amendment.

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

**Status: PROPOSED** (2026-11-16), for independent review. Acceptance would change this charter's sequence and gate for **one interim phase only**. It would authorize **no** code, test, live run, `[layer1-freeze]` amendment or runtime change. Each of those keeps its own PR and its own go-ahead (§5.2.8).

**Owner direction.**
- **2026-11-11:** in the owner's working session on the D6/P2 assessment, the owner chose reporting level **R-ii** for a proposed P2-first phase, in the words "Re-probe Claude Code first". The re-probe is done: H1 passed on Claude Code `2.1.310` ([H1 gate record](../validation/dg1f-t08-d5-p2-host-path-h1-gate-2026-11-16.md), #808).
- **2026-11-16:** the owner asked for this amendment ("Yes, draft it").

Neither statement accepts the amendment. Acceptance follows independent review.

### 5.2.1 What P2-first is

P2-first is a **distinct interim contract**, not "D5 postponed". It lands the [D6/Q2](2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md) P2 precedence rule on **today's unbounded walk**, across every §4 consumer at once, before the D5 B1 stop rule exists. The rest of this charter (B1, I3, all eight §3.3 rows, the H1–H6 gate) becomes **Phase 2**, unchanged.

Why it can go first:
- **The defect it fixes is a precedence defect, not a boundary defect.** Today `find_memory` returns the `MNEME_MEMORY` path whenever the variable is set, and returns nothing when that file is missing (`hook.py:202-206`). Those are V5/V5-own (replacement) and V4 (masking), reachable through committed settings (Q2 §3, C2). The G3-2 case (#793) is the same defect: the repository's own memory **is** found by today's walk, and only the env-first order is wrong. P2 rule 1 fixes it without a boundary.
- **No edit that today's walk governs becomes ungoverned.** D5 §5.1 makes a verified host-visible channel the price of B1, because B1 turns governed edits (L4, L5, L6) into skips. P2-first never stops a walk earlier than today. Rows 1 and 2 select the memory the walk finds; rows 6, 7 and 8 occur only where today's walk finds none. A **different** memory can govern than today (§5.2.3), but no edit loses its memory.
- **Planted Git markers have nothing to act on.** Markers are not honored, so the D5 §5.4 planted-marker case, and the Q2 rule-2 substitution it would enable, cannot occur.
- **The ordering risk Q2 names does not arise.** Q2 §10 warns against a window in which "the boundary exists but the override can still replace `M_R`". P2-first is the opposite order: precedence first, boundary later.

### 5.2.2 Interim selection contract

`M_W` is the memory today's walk finds: the nearest `.mneme/project_memory.json` at or above the consumer's unchanged start, with **no** Git-marker check. That is today's `find_memory` walk without its env branch. `M_X` is the non-empty `MNEME_MEMORY` value. Paths are compared after `resolve()`. An override is **usable** only if it is an existing regular file (`is_file()`, today's test) that the process can open for reading. Otherwise it is treated as missing (A2-3).

| Row (§3.3 numbering) | Walk result | `M_X` | Selected | `reason` |
|---|---|---|---|---|
| 1 | `M_W` found | unset, or equal to `M_W` | `M_W` | `DISCOVERED` |
| 2 | `M_W` found | set, and different or not usable | `M_W` | `OVERRIDE_IGNORED` |
| 6 | no `M_W` | usable | `M_X` | `OVERRIDE_FILLS_ABSENCE` |
| 7 | no `M_W` | set but missing or unreadable | none | `OVERRIDE_MISSING` |
| 8 | no `M_W` | unset | none | `NO_MEMORY_ON_PATH` |

- **Rows 3, 4 and 5 cannot occur**, because they need a boundary. Their reason codes are reserved for Phase 2 and are never emitted in P2-first. The row numbers and reason codes are §3.3's, so Phase 2 extends the contract rather than renaming it.
- **Resolver shape.** The §3.1 resolver and `MemorySelection` land in P2-first with `path`, `source` and `reason`. `boundary` and `shadowed` are **not populated** (both `None`), and a field `walk: "unbounded"` records why, so no consumer can read an absent boundary as "no Git repository" (A2-5). Phase 2 populates both and sets `walk: "b1"`.
- **`find_memory`** stays the thin wrapper of §3.1 (C4). Its semantics change to this table only.
- **§3.4 tiers apply:** rows 2 and 7 are anomalous; row 6 is informational; row 8 is plain absence (structured non-PASS, no per-event notice, per the D5 §5.1 refinement).
- **Unchanged:** start points (I5); explicit constructor and CLI memory paths (Q2 O3); D4 nearest-wins.

### 5.2.3 Costs, stated plainly

The independent review of the 2026-11-11 assessment required that P2-first make **no** blanket "never weakens" claim. P2-first can select a more permissive memory than today in these cases:
- **Row 2 with a stricter override.** An operator or committed setting that points `MNEME_MEMORY` at a stricter memory now gets the walked memory instead. This is Q2's accepted P2 cost (Q2 §6), and it is the point of P2: ambient configuration cannot replace a repository's own memory.
- **Case 2: an ancestor memory beats the override.** Without B1, `M_W` can sit **above** the repository: a parent-directory memory (L6), or the outer checkout's memory seen from a worktree (L4) or a submodule (L5). In P2-first that ancestor wins under row 1 or row 2, and the override is ignored. In Phase 2 the same layout becomes row 3 (an override equal to the shadowed memory applies) or row 5 (refused). A user who relies on `MNEME_MEMORY` to govern a nested repository below an ancestor memory loses that override during P2-first. `OVERRIDE_IGNORED` is reported host-visibly on the H1 paths only (§5.2.4).
- **Planted memory files (V3/V6)** stay nearest-wins, as today and as in Phase 2 (D4, out of scope).
- **Start points are not unified** (D1/D2/D7), as in §4.

What P2-first removes: env-based replacement (V5, V5-own) and env-based masking (V4) of a memory the walk finds, whichever channel sets the variable (C1, C2, C4). What it does not remove: a repository-controlled memory file still governs, as today.

### 5.2.4 Reporting at level R-ii (I4-P2F, replacing I4 for P2-first only)

1. **Every consumer computes the selection; it is recorded only where a non-wire record already exists.** Every §4 consumer calls the resolver and gets `reason`, `source` and `walk`. Where they are recorded was checked against `main` at `0118d91f`:
   - **Agent SDK and LangChain:** recorded as additive keys (`selection_reason`, `selection_source`, `walk`) in the existing `trace` records (`agent_sdk/adapter.py:135`, `_record` via `_gate` and `context_for_task`). LangChain inherits them through its internal SDK. The trace is an in-process list the embedding program may read. It is not hook output.
   - **Every other consumer has no such record,** so the selection is held in-process only:
     - Claude Code: exit 0 with no output when nothing is selected (`hook.py:1125-1126`, `:711-712`). Its H1 notices are item 2.
     - The Codex gate: `GateResult` is internal, and `SKIP` prints nothing (`codex_cli/hook.py:10`).
     - The Codex stop audit returns `None` or 0 (`stop_audit.py:88-90`, `:137-139`).
     - Kiro returns 0 (`kiro/hook.py:298-300`).
     - Antigravity emits `{}` (`antigravity/adapter.py:242-247`).
     - Hermes returns `GateResult.reason` to its embedding host (`hermes/adapter.py:277-281`), so changing it would be host-facing.
   - **No new log, file, field or sink is created.** Existing `reason` strings (for example `"no project memory"`) and the fields of `GateResult` and `ContextInjection` stay byte-identical in every consumer.
   - **Stated plainly:** outside the Agent SDK and LangChain, and outside the H1 paths, rows 2 and 7 leave no observable record. Row 2 still selects the walked memory there; only the report is absent. This is narrower than "structured reasons in every consumer" as the owner phrased R-ii on 2026-11-11, and A2-6 asks for it to be accepted as R-ii's meaning here. **A structured reason is not host visibility**, and no document, release note or UI may describe it as such (§5 rule).
2. **Host-visible notices only on probed paths, in the probed shape, on the probed pin.** Rows 2 and 7 are reported host-visibly only on the H1 paths, which passed on Claude Code `2.1.310 (Claude Code)` with `claude-opus-5-5` (#808). The shape-binding rule (probe scope §3 step 5) applies:

   | Path | Shape | Recorded audience |
   |---|---|---|
   | H1a PreToolUse (direct write, Bash) | exit 0, `hookSpecificOutput.additionalContext`, no `permissionDecision` | agent (`DELIVERED_TO_AGENT`) |
   | H1b SessionStart | `hookSpecificOutput.additionalContext` | agent (`DELIVERED_TO_AGENT`) |
   | H1c Stop | top-level `systemMessage`, exit 0, no `hookSpecificOutput`, no `decision` (§5.1) | developer only (`DELIVERED_TO_USER_ONLY`) |

   The visibility claim is bound to that version. Other Claude Code versions receive the same shape, and documentation calls it **unverified** there.
3. **No new host-facing output on unprobed paths.** The Codex gate and stop audit, Kiro, Antigravity, the Agent SDK, LangChain and Hermes emit **no selection notice and no new field** in their hook output, wire JSON, returned result objects or exit codes, for any row. The only addition is item 1's trace keys. They differ from today only in which memory they select. Reason: an unprobed shape can change host behavior. The original H1c Stop shape made the host continue the session (#549). These paths are recorded as **not host-visible** until their own probe passes.
4. **ADR-033 coexistence.** On H1a direct write, the notice shares the single PreToolUse `additionalContext` object with the C2b proceed note (`ProceedNote.consumed`), as probe-scope A2-3 requires.
5. **Unchanged:** exit codes and blocking (ADR-021; no row blocks); row 2 reported on every PreToolUse event (C5).

### 5.2.5 Gate for P2-first

- **The P2-first gate is H1 only, and H1 has PASSED** (#808). All four H1 paths share one pin (`2.1.310`), so the probe-scope A2-1 question (combining pins) does not arise.
- **H2–H6 are not prerequisites for P2-first.** Each one that passes later extends I4-P2F rule 2 to that host's paths, through a small reviewed change (channel plus offline shape test), without a new charter amendment.
- **Q2 §10's P2 prerequisites, as they apply to P2-first:**
  - "The same host-visible channel as D5 §5.1" is **relaxed** to I4-P2F: host-visible on the H1 paths, structured-only elsewhere. This is the substance of R-ii and the main point the reviewer is asked to accept (A2-1). Q2 carries a pointer amendment recording it (Q2 Amendment A1).
  - "The D5 §5.4 planted-marker outcome including the rule-2 case" is vacuous in P2-first, because no marker is honored. It binds again in Phase 2, through I3.
- **Phase 2 is unchanged.** B1, I3 and rows 3–5 still need all of H1–H6 (§5), the §6 characterization test and their own freeze amendment. The §5 clause "if any host gate cannot be met … D5 must be revisited explicitly" still applies to Phase 2. D5 itself (§5.1, §8) is not amended.

### 5.2.6 Freeze amendment and tests (P2-first)

A separate `[layer1-freeze]` P2-first amendment PR, under Amendment Procedure §3(b), must:
- **authorize only:** the shared resolver on today's walk; the five §5.2.2 rows; I4-P2F reporting on the H1 paths; the migration of every §4 consumer at once, with start points unchanged; `find_memory` kept as a wrapper with the new precedence;
- **supersede, for `MNEME_MEMORY` precedence and the H1 notices only:**
  - T-08 slice-1 preserved item 3 ("`MNEME_MEMORY` precedence is unchanged: when set, it wins exactly as today");
  - the "`MNEME_MEMORY` precedence" clause of the C2a and C2b preserved item 4;
  - preserved item 6 (Bash, SessionStart and Stop selection and behavior), for those two points only.
  The walk, the parent-directory fallback and nested-memory behavior stay preserved;
- **leave unauthorized** everything else in §10, including B1, I3 and rows 3–5.

The implementation PR carries a subset of §7, plus P2-first cases:
- §7.2 precedence matrix for rows 1, 2, 6, 7 and 8, including relative, symlinked and differently-cased (Windows) override paths;
- the override classes of A2-3: missing, a directory, unreadable (open fails), and malformed (opens, fails to parse). The first three give row 7 (or row 2); malformed gives row 6 and today's malformed-memory outcome, unchanged;
- §7.5 consumer parity across all eleven consumers, including the `walk` field;
- §7.6 flips: V4 to row 2 or row 7, whichever applies; V5 and V5-own to row 2;
- **case 2:** an ancestor memory plus a different override selects the ancestor (row 2). Pinned so that Phase 2's change to row 3 or 5 is a reviewable flip;
- **planted marker plus override** (`A/.mneme`, `A/src/.git`, `MNEME_MEMORY` = B): selects A's memory, row 2. Today B is selected;
- §7.7 unchanged tests, §7.9 latency;
- §7.8 channel shape on the H1 paths, plus a per-consumer assertion that, for every row, hook output, exit code, `GateResult` and `ContextInjection` are identical to what the same selected memory produces today, and only the Agent SDK trace gains the item-1 keys;
- the ADR-033 coexistence test (§5.2.4 item 4), with the C2a and C2b suites green and unmodified.

The full canonical suite must run. The §6 characterization test is **not** a P2-first prerequisite: its layouts are B1 cases, and the one whose selection P2-first changes (planted marker plus override) is covered above. §6 stays a Phase 2 step.

### 5.2.7 Sequence (P2-first)

1. This amendment, accepted.
2. The P2-first `[layer1-freeze]` amendment PR (§5.2.6).
3. The implementation PR, with the §5.2.6 tests and a full-suite run, squash-merged under ADR-022.
4. The P2-first live evidence PR, on Claude Code `2.1.310`, using harness-planted state only: the §8 C2 re-run (expect the repository memory to govern and `OVERRIDE_IGNORED` to be visible) and planted marker plus override (expect A's memory, row 2).
5. A G3 re-assessment record: G3 stays partial until P2 exists (#793), and this step records what P2-first changes.

Each step needs the previous one merged and its own go-ahead. Phase 2 then continues with §12 steps 2–6, unchanged. The H2–H6 probes proceed by adoption and, as each passes, also extend I4-P2F.

### 5.2.8 Not authorized by A2

- code, tests, live runs or the P2-first freeze amendment;
- B1, I3, rows 3–5 or the §6 characterization test;
- any change to D5, to D5 §5.1's visibility rule for Phase 2, or to the H1–H6 gate for Phase 2;
- any host-visible claim beyond the three H1 rows on `2.1.310`;
- G3/G3-B authority, ADR-033, or any fail-closed or availability behavior;
- DG2 federation, C5/C6;
- DG1 deferred B2b and C1b, which still need a trusted-context design;
- the C2/C3a release, which stays on hold.

### 5.2.9 Decisions requested of the reviewer

| # | Decision | Recommendation |
|---|---|---|
| A2-1 | Relax I4 and Q2 §10's host-visible requirement to I4-P2F for P2-first | **Yes.** It is the owner's chosen level (R-ii). P2-first leaves no governed edit ungoverned (§5.2.1), and visibility is claimed only where it was proven. |
| A2-2 | Adopt `M_W` (today's unbounded walk) as the interim contract | **Yes.** The variant that computes `R` without stopping, so an ancestor memory loses to the override, was rejected on 2026-11-11: a planted `.git` would reopen the substitution. |
| A2-3 | Missing, unreadable and malformed overrides | **Follow Q2 rule 3.** *Missing* (`is_file()` false, including a directory) and *unreadable* (exists, but opening it for reading fails, for example a permission error) are both "not usable": row 7 (`OVERRIDE_MISSING`, Q2's "override missing") with no `M_W`, row 2 with one. The resolver tests readability by opening the file in binary mode and closing it, without reading or parsing it. The test runs only when no `M_W` exists, because row 2 ignores the override either way. *Malformed* (opens, but fails to decode, parse or validate) is **not** a selection outcome. It is selected under row 6 and follows today's malformed-memory path unchanged (ADR-021; CI1.4 §7 condition 4). A file that becomes unreadable after selection also takes today's load-failure path. The earlier draft (`342bc929`) used `is_file()` alone, which conflicts with Q2 rule 3. |
| A2-4 | Accept case 2 (ancestor memory beats the override) for the interim | **Yes**, as documented in §5.2.3. It ends in Phase 2. The reviewer is asked to accept or reject this risk explicitly. |
| A2-7 | Confirm Phase 2 keeps every original prerequisite | **Yes.** B1, I3 and rows 3–5 still need all of H1–H6 with every listed output path (§5), the §6 characterization test and their own freeze amendment (§5.2.5). A2 relaxes nothing for Phase 2. |
| A2-5 | Leave `boundary` and `shadowed` unpopulated, with a `walk` marker | **Yes.** It keeps a later G3-B root binding from reading an absent boundary as a real one. |
| A2-6 | No new output on unprobed paths, and the reason recorded only in the Agent SDK/LangChain trace (§5.2.4 item 1) | **Yes.** The H1c history shows an unprobed shape can change host behavior. Hermes's `reason` reaches its host, so it cannot carry the selection either. The cost is that rows 2 and 7 leave no record on Codex, Kiro, Antigravity, Hermes or the non-H1 Claude Code rows. Accepting this also accepts the narrower reading of R-ii in item 1. |

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

# DG1F T-08 D5 + P2: H1c Stop-path architectural decision (ACCEPTED: O1 selected)

**Status:** **ACCEPTED as an architectural decision note** (owner approval 2026-10-17, following an independent-review ACCEPT on `3db021d5`). **Owner decision: O1 selected as the direction** (probe Stop top-level `systemMessage`), **O2 as the fallback, O3 rejected.** Docs only. Accepting it does not mean O1 is proven, and it authorizes **no** probe, harness change, scope amendment, D5 amendment, runtime change or freeze amendment (§7).

**Anchor:** `main` @ `220ee31e`.
**Revision 2 (2026-10-17):** answers the #554 review. O1 now requires a bounded charter §5 channel update alongside the probe-scope amendment (§4 O1). The interactive delivery run gets a paired no-op control (§4 O1). §2 keeps apart what is documented from what the live record established about the loop ending.

**Inputs:**
- the accepted [D5 contract](2026-10-17-dg1f-t08-d5-repository-boundary-contract.md) (§5.1 visibility condition);
- the accepted [D5 + P2 charter](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (§4 consumers, §5 host gates);
- the accepted [probe scope](2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md) (§3.1, §6, D3);
- the H1 evidence and its R1–R3 reclassification ([record](../validation/dg1f-t08-d5-p2-host-path-h1-2026-10-17.md) §4.3 and §7; #549, #553);
- issue #550.

## 1. Problem

Under the accepted rules R1–R3, H1a (Edit and Bash) and H1b (SessionStart) pass, and **H1c fails**: `DELIVERED_WITH_SIDE_EFFECT`. With the candidate shape `hookSpecificOutput.additionalContext` on Stop, the Stop hook ran **9 times** (8 of them with `stop_hook_active: true`), against once in the no-op control, with 9 model replies against 1. The charter (§5) requires every H1 path to pass before the freeze amendment, and it says that if a gate cannot be met, D5 must be revisited explicitly. This note is that explicit decision point for H1c.

## 2. Evidence, including host documentation

| Source | What it shows |
|---|---|
| H1 live evidence (#549, §4.3; reclassified in #553 §7) | Stop `additionalContext` with exit 0 made the host re-enter: 9 invocations against 1, a reply after each, `num_turns: 1`, and the session ended without operator action. |
| Claude Code hooks documentation (<https://code.claude.com/docs/en/hooks>, read 2026-10-17), *Add context for Claude* | For Stop, the added context arrives "at the end of the turn. The conversation continues so Claude can act on the feedback." |
| Same page, *Stop input* | "Claude Code applies an 8-consecutive-continuation cap … overrides the next block and ends the turn", adjustable with `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`. |
| Same page, common JSON output fields | `systemMessage`: "Warning message shown to the user." In `--output-format stream-json` it "can arrive as an `SDKInformationalMessage`". The page also says some events discard `systemMessage` or deliver it elsewhere. The Stop sections describe nothing Stop-specific for it. |

**Reading.** The H1c re-entry is **documented host behavior, not a defect or an artifact**. Stop `additionalContext` is by design a *continuation* channel. The 9 invocations are **consistent with** 1 plus the documented cap of 8. **However, the live record did not independently establish what ended the continuation sequence.** It shows 9 invocations and a normal end, not the cause of that end, so the cap explanation is a documented hypothesis, not a measured fact. No reclassification or rule change can make this shape non-interfering. The documentation is cited as an explanation only: the live evidence decides, and nothing in the docs has been probed except what H1 recorded.

## 3. What the Stop path is needed for

Under the charter (§4), the Claude Code **SessionStart** and **Stop** consumers both start discovery at the **session `cwd`**. So the memory-selection outcome a Stop notice would report is normally already known, and reportable, at SessionStart, which passed H1b. The direct-write PreToolUse path (H1a, passed) covers the edited target's own selection.

The residual case only Stop can see is **a change during the session** that alters selection for the session `cwd` after SessionStart has run. Examples: an override introduced by mid-session settings plumbing (C3 and C4 showed that propagation mechanism), or a Git marker created mid-session. Any option has to say how that residue is handled.

## 4. Options

### O1: Probe a different Stop channel: top-level `systemMessage`

- **Shape.** Stop, exit 0, top-level `{"systemMessage": "<notice>"}`, with **no** `hookSpecificOutput` and **no** `decision`.
- **Why it fits.** It is documented as a user-facing warning, and nothing documents it as continuing the conversation. D5 §5.1 and probe-scope decision D3 already accept **developer-only** delivery, recorded as `DELIVERED_TO_USER_ONLY`. That keeps D5 unchanged.
- **What it needs (each separately gated):**
  1. **A coordinated pair of amendments, reviewed together:**
     - a **probe-scope amendment** changing H1c's candidate shape to top-level `systemMessage`;
     - a **bounded charter §5 channel update** replacing Claude Code Stop's candidate channel (`hookSpecificOutput.additionalContext`, charter §5 table) with `systemMessage`, so the charter's channel table and its shape binding stay consistent with the scope.

     Both change only the proposed **delivery mechanism** at Stop. Neither changes D5's developer-or-agent visibility requirement, authorizes implementation, or amends the Layer 1 freeze.
  2. **A harness change:** an emitter mode, plus classifier rules for evidence that the warning reached the developer.
  3. **Two runs, each with its own paired no-op control** (scope §3.1, lifecycle-event control):
     - **Headless:** an emitter arm and a no-op control arm. They verify non-interference (equal Stop invocations, `stop_hook_active` never true, a normal end) and record whether stream-json carries the notice as an informational message.
     - **Operator-observed interactive:** an emitter arm and a **paired no-op control arm**, both captured (screen recording or host UI log). The scope accepts developer delivery only from observation (§3), and the interactive host's behavior may differ from headless. The evidence must show **both** that the developer saw the notice in the emitter arm **and** that the emitter session started, ran and ended exactly as its paired control did: no extra turn, re-entry, prompt or blocked tool. A separately reviewed scope amendment could establish a different but equivalent interactive control, but none exists today.
- **Risks.**
  - The host may discard `systemMessage` at Stop, which the page says some events do. That would be `NOT_DELIVERED`.
  - It may not reach the agent. That is acceptable under D5 §5.1, but the implementation charter would then record that Stop anomalies are developer-only.
  - The §3 mid-session residue is covered for the developer only.

### O2: Revisit D5 for the Claude Code Stop path

- **Change.** Amend D5 §5.1, and the charter's §5 H1 gate, so the **Claude Code Stop consumer** is excepted from per-event host-visible reporting. It would still produce the structured outcome, never shown as `PASS`. Selection anomalies would be reported through the proven channels instead: **SessionStart** for the shared session-`cwd` selection, and **PreToolUse** for direct writes.
- **Residue.** A mid-session change (§3) would have no host-visible report at Stop. It would need either an accepted, documented gap, or a separate mechanism (for example re-evaluating at the next PreToolUse), which would be its own design.
- **Cost.** It amends an accepted contract and needs explicit owner approval, recorded as for the earlier §5.1 refinement. It needs no new probe.

### O3: Bounded-continuation exception

- **Change.** Accept Stop `additionalContext` despite re-entry, relying on the host's 8-continuation cap.
- **Why not.** It contradicts the accepted non-interference rule (scope §3 step 4 and §3.1 lifecycle control: no forced continuation and no host-driven extra turn). It would allow up to 8 extra model turns per Stop, during which the model may act on a notice it was never asked to act on. The cap is also user-configurable. **Not recommended.**

**Excluded outright.** Stop `decision: "block"` with a `reason`, and exit 2, are documented as forcing continuation. They are blocking mechanisms, not notices.

## 5. Recommendation

**O1 first, with O2 as the fallback.**
- **O1** keeps the accepted D5 contract intact. It tests the one documented channel whose stated purpose is a user-facing notice, and it costs one bounded, separately authorized probe.
- If O1 gives `NOT_DELIVERED` or `DELIVERED_WITH_SIDE_EFFECT`, take **O2**, as an explicit and owner-approved D5 amendment, with the §3 residue either accepted as a documented gap or given its own design.
- **Reject O3.**

## 6. Relation to #550 (shipped `_emit_stop_feedback`)

The documentation cited in §2 strengthens #550's concern without reproducing it. The shipped adapter's Stop feedback (`hook.py:743-758`) uses Stop `additionalContext`, which the host documents as continuing the conversation, up to the 8-continuation cap. When one of its six conditions holds and recurs, that feedback can therefore be expected to make the session continue. This is **still not reproduced with the shipped adapter**. #550 remains an investigation, and any fix needs its own charter.

Whatever this note's decision, it also informs #550: an accepted O1 shape (`systemMessage`) or O2 routing would be the natural candidate for that fix. Adding a comment to #550 that points to this note is left to the owner.

## 7. Not decided or authorized here

- No probe (including any O1 run), harness change, probe-scope amendment, D5 or charter amendment, classifier change, runtime change (including `_emit_stop_feedback`), freeze amendment or implementation.
- H2a's targeted re-run, and H2–H6.
- **H1 remains NOT MET** until H1c passes under an accepted channel, or D5 is amended for Stop.

## 8. Decision requested (resolved 2026-10-17: O1 selected, O2 fallback, O3 rejected)

1. Choose O1 (recommended), O2 or O3.
2. If O1: approve drafting the **coordinated** probe-scope amendment and charter §5 channel update for H1c, to be reviewed together. That means shape `systemMessage`; a headless run with a paired control; and an operator-observed interactive run with a paired control. The harness and the live runs stay separately gated.
3. If O2, now or as the fallback: approve drafting the D5 §5.1 and charter §5 amendment, and state how the §3 mid-session residue is handled.

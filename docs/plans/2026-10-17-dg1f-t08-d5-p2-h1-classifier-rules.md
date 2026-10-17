# DG1F T-08 D5 + P2: H1 evidence-classification rule review (ACCEPTED: rules only)

**Status:** **ACCEPTED as the H1 classification rules R1–R3 only** (owner approval 2026-10-17, following an independent-review ACCEPT on `c729686d`). Docs only. It does **not** reclassify anything. Acceptance authorizes no classifier code change, no reclassification run, no live probe, no runtime change and no Stop-path decision (§6).

**Anchor:** `main` @ `de4766ea`.
**Revision 2 (2026-10-17):** answers the #551 review. It narrows the reproducibility claim and adds a completeness check for material the collector omitted (§5), and it corrects the SessionStart ordering (§2). R1–R3 are unchanged.

**Inputs:**
- the accepted probe scope (#545), §3 and §6;
- the accepted H1 harness (#546);
- the accepted H1 evidence record [`docs/validation/dg1f-t08-d5-p2-host-path-h1-2026-10-17.md`](../validation/dg1f-t08-d5-p2-host-path-h1-2026-10-17.md) (#549), whose §6 decisions 1–2 this note answers;
- the published evidence in [`docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/`](../validation/artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/).

## 1. Why a rule review

The H1 batch came out `INCONCLUSIVE` on all four paths. The as-run classifier made the right call under its rules: it had never seen the transcript shape Claude Code 2.1.202 actually uses, and its strict host-event rule could not tell model reasoning telemetry apart from host behavior. This note asks whether three rules should change, based only on what the published evidence shows. Adopting a rule here changes how evidence is **read**, never what the host did.

## 2. What the evidence shows (published files, all eight arms)

| Observation | Emitter arms (H1a-edit, H1a-bash, H1b-start, H1c-stop) | No-op control arms |
|---|---|---|
| Transcript `attachment` entries with `attachment.type: "hook_additional_context"` | Exactly one per emitter hook invocation (1, 1, 1 and 9). **Every one** has `hookEvent` equal to the probed event and `content` equal, byte for byte, to the notice the emitter wrote (`hook-log.jsonl` `emitted.hookSpecificOutput.additionalContext`). | **None** |
| Transcript `attachment` entries with `attachment.type: "hook_success"` | One per emitter invocation. `stdout` is the emitter's raw JSON; it also carries `exitCode`, `durationMs`, `command` and `hookName`. | **None.** The no-op printed nothing. |
| What follows each `hook_additional_context` entry | The next non-attachment entry is: for **PreToolUse**, the tool result (`user`); for **SessionStart**, the initial user prompt (`user`), since SessionStart context is recorded before the prompt; for **Stop**, the model's reply (`assistant`). The model then repeats the nonce in its reply on every path. | n/a |
| Stream-json `thinking_tokens` events | Counts differ from the paired control: H1a-edit 4 vs 2, H1a-bash 0 vs 2; equal for H1b and H1c (2 vs 2). The fields are only `estimated_tokens`, `estimated_tokens_delta` and `session_id`, with no permission, block, retry or continuation field. | Same field set |
| All other non-init `system` event subtypes | Identical between arms on every path (`task_started` and `task_notification` for Bash; `hook_started` and `hook_response` for SessionStart). | Identical |

## 3. Proposed rules

### R1: `hook_additional_context` counts as model-bound delivery, narrowly

**Rule.** A transcript entry with `type: "attachment"` and `attachment.type: "hook_additional_context"` is categorised `model_bound` only if **all** of these hold:
1. `attachment.hookEvent` equals the probed event;
2. the probe's own emitter invoked that event in this arm (`hook-log.jsonl`);
3. the nonce occurrence is in `attachment.content`.

Any other attachment type, or a `hook_additional_context` entry failing a condition, stays `unclassified`.

**For:**
- the entry is the host's own record of hook context, typed as additional context;
- it exists only when the emitter emitted, and never in the no-op controls;
- its content equals the emitted notice exactly;
- on every path the model then repeats the nonce, which is consistent with the content having entered the model's context.

**Limits, stated for the record:**
- this is the host's transcript, not a capture of the model request, so R1 accepts the host's record as delivery evidence;
- the echo corroborates, but by itself still cannot establish delivery (scope §3 step 3, unchanged).

R1 does not relax the unclassified-first rule: any remaining `unclassified` location still blocks a pass.

### R2: `hook_success.stdout` is host output

**Rule.** A transcript entry with `type: "attachment"` and `attachment.type: "hook_success"` is categorised `host_output`, the same as stream-json `system` events.

**Basis.** It records the hook's own execution: raw stdout, exit code, duration and command. That is the host's log of what the hook printed, not a statement of what the model received. Under R2 it **never** counts as delivery and **never** masks anything, because a pass still requires a separate `model_bound` location (R1).

### R3: exclude `thinking_tokens` from the host-event subtype comparison

**Rule.** Stream-json `system` events with `subtype: "thinking_tokens"` are left out of the strict subtype comparison between arms. Every other subtype stays in, and nonce-carrying events stay in. The strict rule is otherwise unchanged, including that any unexplained difference gives `INCONCLUSIVE`.

**Safeguard.** `thinking_tokens` events are **still scanned for indicator fields**. If one ever carries `decision`, `permissionDecision`, `blocked`, `retry`, `continue`, `stopReason` or a similar field, the indicator comparison applies exactly as today. So R3 removes a count comparison, not a safety check.

**Basis.** The only fields observed are token estimates. Their counts vary between paired arms in both directions (4 vs 2, 0 vs 2) while every host-decision signal (tool execution, permission decisions, other subtypes, indicators) matches. That fits model reasoning that varies run to run, not a host flow decision. **Limit:** the evidence does not establish the host's internal meaning for this event. R3 relies on the field content and the absence of indicators, not on documentation.

## 4. What R1–R3 would change, by reasoning only (not a reclassification)

This section projects the effect of the rules so the reviewer can judge them. **It is not a result.** Only an authorized offline reclassification run establishes labels.

| Path | As classified | Under R1–R3 (projected) | Why |
|---|---|---|---|
| H1a-edit | INCONCLUSIVE | likely `DELIVERED_TO_AGENT` | R1 gives a model-bound location; R2 removes the other unclassified location; R3 removes the only host-event difference; all other controls held |
| H1a-bash | INCONCLUSIVE | likely `DELIVERED_TO_AGENT` | Same; the remaining subtypes (`task_*`) match |
| H1b-start | INCONCLUSIVE | likely `DELIVERED_TO_AGENT` | R1 and R2; there was no host-event difference |
| **H1c-stop** | INCONCLUSIVE | **`DELIVERED_WITH_SIDE_EFFECT` (fails)** | R1 gives delivery, but the lifecycle control fails: 9 Stop invocations, 8 of them re-entries, against 1. **No rule change removes this.** |

**Projected H1 gate: still NOT MET**, because of H1c. Stop is a separate architectural decision (§6), not a classification question.

## 5. If accepted: the reclassification procedure (separate go-ahead)

1. **Classifier change.** One harness PR changes `classify_h1.py`: the `categorise()` table for R1 and R2, and `host_events()` for R3. It adds regression tests:
   - R1 positive;
   - R1 with the wrong `hookEvent` → unclassified;
   - R1 when the emitter did not invoke → unclassified;
   - R2 never counts as delivery;
   - R3 with a `thinking_tokens` count difference → ignored;
   - R3 with an indicator field inside `thinking_tokens` → still compared.
2. **Offline reclassification**, with no host session.
   - **Authoritative run: the raw evidence** in `C:\dev\d5p2-h1-live`, kept unchanged and bound to the published `MANIFEST.json` SHA-256s, which must match before the run. Only this run scans **every** raw input, so only this run can apply the unclassified-first rule completely.
   - **Completeness check for omitted material**, recorded with the run. The collector did not publish everything:
     - transcript entries outside `user`, `assistant` and `hook_*` attachments, such as tool, skill and agent listings, queue operations and titles;
     - thinking content;
     - most `init` fields.

     For each arm, the run records how many omitted entries were scanned and how many contain the emitter nonce. It publishes, redacted, **every omitted entry that contains the nonce**. If any omitted entry contains it, that location is categorised under the table like any other, and it can block a pass.
     - Read-only observation made while drafting this note (2026-10-17), to be repeated and recorded by the authorized run: **no omitted material contained the nonce in any arm.** The arms had 6–9 omitted transcript entries each, and there were 0 hits in omitted transcript entries, omitted thinking blocks and omitted `init` fields.
   - **Repository-only replay is a subset check, not an independent reproduction.** A loader can replay the classifier on the published `*.selected.jsonl`, checking files against the `observer.txt` hashes. Its result is reproducible against the **published subset**, and it is complete only together with the raw run's recorded completeness check. The reviewer cannot verify that check from the repository alone. The record must say this, and must not present the subset replay as a fully independent reproduction. Any label that differs between the raw run and the subset replay is reported, not reconciled.
3. **Record.** An addendum to the H1 evidence record gives the new labels next to the as-run labels, which stay as historical fact, plus the classifier SHA-256 used. The as-run `outcome.json` files are never overwritten; new outcomes are published alongside them.

## 6. Not decided here

- **The H1c Stop path.** Options are a different channel (for example top-level `systemMessage`) under a scope amendment and new probe, or an explicit D5 revisit for Stop. Neither is proposed here.
- The shipped `_emit_stop_feedback` behavior, which is tracked in #550 as an investigation only.
- H2a's targeted re-run, and H2–H6.
- Any runtime change, freeze amendment or implementation.

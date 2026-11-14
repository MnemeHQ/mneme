# DG1F T-08 D5 + P2: host-output-path channel probes H1–H6, live-evidence design (ACCEPTED: nothing executed or authorized to run)

**Status:** **ACCEPTED as the probe design** (owner approval 2026-10-17, following an independent-review ACCEPT on `37009457`). Design only. **Nothing here is executed, and acceptance authorizes nothing to run:** no probe, no harness build, no live host session, no runtime change, no `[layer1-freeze]` amendment and no implementation (see §11). Each batch needs its own go-ahead.
**Anchor:** `main` @ `5d8bf82a`. That is after the accepted [D5 + P2 implementation charter](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (#542) and its §6 characterization tests (#543).
**Revision 2 (2026-10-17):** answers the #545 review.
- Side-effect criteria are narrowed to host-induced effects; turn count and model text are evidence only (§3, §6).
- Developer-only delivery may pass any path, recorded separately from agent delivery (§3, §6, D3).
- An explicit H2a equivalence mapping against the committed M1d-a artifacts is added (§4.1).

**Amendment A1 (ACCEPTED, 2026-10-17; owner approval following an independent-review ACCEPT on `19734ac8`):** implements the accepted [H1c Stop-path decision](2026-10-17-dg1f-t08-d5-p2-h1c-stop-path-decision.md) (#554, O1). It replaces **H1c's** candidate shape with top-level `systemMessage` and specifies two H1c runs, a headless one and an operator-observed interactive one, **each with a paired no-op control** (§4.2). It is coordinated with the charter's §5.1 Amendment A1 and reviewed together with it. Nothing else in this scope changes, including the developer-or-agent rule (D3).

**Amendment A2 (PROPOSED, 2026-11-11):** re-pins **H1a and H1b** to Claude Code `2.1.310` with `--model claude-opus-5-5`, in a separate disposable root, after the owner chose reporting level R-ii (re-probe Claude Code first) in the D6/P2 assessment (§4.3). Candidate shapes, controls, labels and rules are unchanged. H1c stays on the A1 track. Nothing runs without a separate go-ahead.

**Amendment A3 (PROPOSED, 2026-11-13):** re-pins the **H1c A1 track** (Stop top-level `systemMessage`, headless and interactive) to Claude Code `2.1.310` with `--model claude-opus-5-5`, the host and model of A2, in a separate disposable root (§4.4). Both runs are repeated on that pin, and H1c is judged on one host version. Shape, controls, labels and rules are unchanged. Nothing runs without a separate go-ahead.

**Revision 3 (2026-10-17):** answers the #545 re-review. The emitter mechanism and the side-effect control are now specific to each **path type**: command hook on a tool event, command hook on a lifecycle event, in-process callback, and middleware (§3.1). The nonce, evidence, audience and non-interference requirements stay common. No gate, decision or D5/P2 semantics change.
**Parent:** charter §5 (gate rule) and §12 step 3. The format follows the D6 scopes [#519](2026-10-15-dg1f-t08-d6-mneme-memory-live-scope.md) and [#527](2026-10-16-dg1f-t08-d6-c4-local-settings-scope.md).

## 1. Where this sits

Charter §5 says the `[layer1-freeze]` amendment is blocked until **every one** of twelve host output paths has a recorded live probe. Each probe must show that an anomalous memory-selection outcome (charter §3.3 rows 2, 4, 5 and 7) reaches the developer or the agent. If any gate cannot be met, the shared implementation stays blocked and D5 is revisited. This document designs those probes.

## 2. Question

For each output path P, two questions:

> **Q-P1.** Does the candidate wire shape for P, emitted at P's event with exit 0, reach the **agent's context** (or the developer) on the pinned host?
>
> **Q-P2.** Does it do so **without host-induced side effects**, judged by the control for P's path type (§3.1)? The host's normal flow for that path must continue. Depending on the type, that means the tool still executes, the session still starts or ends normally, the callback's return is not treated as a block, or the tool result is otherwise preserved. No permission prompt or decision may change, and the host must not itself block, retry or force a continuation. Differences in what the model says or how many turns it takes are **not** side effects: a delivered notice is expected to influence the model.

Q-P2 matters because a channel that delivers a notice by blocking or re-prompting is not a notice. Codex Stop `decision: block` is an example: it is proven live, but it forces continuation, so it does not qualify (§4, H2b).

## 3. Method: probe the channel, not the outcome

The §3.3 outcomes do not exist in code yet, and implementing them is not authorized. So each probe tests the **delivery channel** directly:

1. **Harness-only emitter.** A probe-only emitter, outside `mneme/` and running no Mneme code, replaces the Mneme integration at P's surface and produces P's candidate shape (§4) carrying a fresh nonce `MNEME-PROBE-<16 hex>`. **What "emitter" means depends on P's path type** (§3.1): a command for hook paths, a registered callback for in-process paths, or a middleware for LangChain. It also logs what it received and what it produced. The probes therefore need **no freeze amendment** and do not depend on Mneme's version.
2. **Recorded delivery** (primary evidence). The nonce appears in a message delivered to the model, in the host's own session record. Examples: Claude Code stream-json or the session transcript, the Codex rollout, the SDK message stream, the LangChain model input.
3. **Echo** (secondary evidence). The prompt asks the agent to repeat verbatim any token beginning `MNEME-PROBE-` that it received from a hook or system notice. An echo without recorded delivery is `INCONCLUSIVE`. Recorded delivery without an echo still passes.
4. **Side-effect controls.** Each probe runs **paired with a no-emitter control**: the same prompt and flow, with the emitter replaced by the path type's no-op (§3.1). The pair is used to **attribute** differences, not to require identical transcripts. **Pass/fail criteria are host-induced only, and they are the path type's control in §3.1**, plus two common to every path:
   - **common:** the permission prompt or decision is unchanged wherever the host has one;
   - **common:** the host did not block, retry or force a continuation because of the emitter's output.

   **Recorded as evidence only, never pass/fail:** turn count, model reply text, extra model-chosen tool calls, and whether the agent echoed the nonce. The echo request in step 3 is expected to change the reply; the probe records that rather than failing on it.
5. **Shape binding.** The implementation PR must reproduce the probed form for P structurally: the same surface and event, the same keys or fields, and the same exit code where the path has one. That covers a command's JSON and exit code, a callback's returned dict, or a middleware's message annotation. An offline test must compare it against the recorded probe output. A passing probe is evidence **for that form only**.

### 3.1 Emitter and control by path type

| Path type | Paths | Emitter | No-op for the paired control | Host-induced side-effect control (pass/fail) |
|---|---|---|---|---|
| **Command hook, tool event** | H1a, H2a, H3a, H4a | probe command registered for the tool event; writes the candidate JSON or stdout; exits 0 | command that writes nothing and exits 0 | the tool executes (the host applies it and its result is not an error); file bytes match the control where the host applied the same tool input |
| **Command hook, lifecycle event** | H1b (SessionStart), H1c (Stop), H2b (Codex Stop) | probe command registered for the lifecycle event; writes the candidate JSON; exits 0. No tool call is involved. | same as above | the session **starts** (H1b) or **ends** (H1c, H2b) normally: no forced continuation, no host-driven extra turn or re-entry, and the exit status matches the control |
| **In-process callback** | H5a (SDK PreToolUse), H5b (SDK context injection), H6a (Hermes tool-call notice), H6b (Hermes `pre_llm_call`) | probe callback registered **in place of** the adapter's callback through the host's own registration API; **returns** the candidate value: a dict such as `hookSpecificOutput`, or Hermes `{"context": ...}`. There is no stdout or exit code. | callback returning the host's "no opinion" value (`{}` or `None`) | the host's normal flow continues: the tool still **dispatches** (H5a, H6a), or the turn still **proceeds** (H5b, H6b). The host does not treat the return value as a block or deny. For H6a, shape discovery comes first (§5), because `pre_tool_call` offers only a block or nothing. |
| **Middleware** | H5c (LangChain) | probe middleware inserted into LangChain's **real** middleware chain that annotates the actual `ToolMessage` on its way back to the model | pass-through middleware | the annotation reaches the model input; the tool result's content and status are otherwise **unchanged** versus the control; the tool still runs once |

**Common to every path type:** the fresh nonce; recorded delivery as primary evidence and the echo as secondary; the audience recorded (`agent`, `developer` or both); the two common criteria in §3 step 4; and shape binding.

**Visibility target.** D5 §5.1 accepts the developer **or** the agent, and this scope uses exactly that criterion on **every** path. Agent delivery is established from the host's session record (headless or interactive). Developer delivery is established only by an operator-observed interactive run with capture (screen recording or host UI log), and it is never inferred. Each path records **which audience was reached** (`agent`, `developer`, or both), so the implementation charter knows where the agent will not see the notice.

## 4. Probe set: twelve output paths

| Path | Event / surface | Candidate shape (exit 0 where the path type has an exit code; §3.1) | Existing evidence (`5d8bf82a`) | Probe needed |
|---|---|---|---|---|
| **H1a** | Claude Code PreToolUse, direct write **and** Bash matchers | `hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext}` with **no** `permissionDecision` | **None.** Only exit 2 with stderr is proven (G1 live record; T-08 re-probe). `defer`/`allow` must not be used (`hook.py:487-490`). | **Yes.** Two sub-probes: an Edit and a Bash command. |
| **H1b** | Claude Code SessionStart | `hookSpecificOutput: {hookEventName: "SessionStart", additionalContext}`; plain stdout recorded as a variant | **None.** Every live registration so far was PreToolUse only (C1:114, C2:172, C4:142). | **Yes** |
| **H1c** | Claude Code Stop | **Amendment A1 (accepted):** top-level `{"systemMessage": "<notice>"}`, exit 0, with no `hookSpecificOutput` and no `decision` (§4.2). It was originally `hookSpecificOutput: {hookEventName: "Stop", additionalContext}` (`_emit_stop_feedback`, `hook.py:743-758`). | The original shape was run in the H1 batch: `DELIVERED_WITH_SIDE_EFFECT` under R1–R3 (#549, #553). The A1 shape is **unprobed**. | **Yes, under A1:** a headless run and an interactive run, each with a paired control (§4.2). |
| **H2a** | Codex PreToolUse (gate) | `hookSpecificOutput.additionalContext` (`codex_cli/hook.py:52-70`) | **LIVE.** M1d-a run `20260824T110210Z`, codex-cli 0.149.1 on Windows with `codex exec`: delivered to agent context as a developer-role message (`validation/codex-cli/capability-matrix.md:49-53`) | **Evidence reuse with a targeted re-run** of artifact-backed delivery only (decision D1, §10; mapping §4.1). A full re-run happens only if the pin has changed. |
| **H2b** | Codex Stop (stop audit) | `systemMessage` (`stop_audit.py:126-127`) | **Unproven live.** It is covered by unit tests only. Stop `decision: block` is proven (M3) but has side effects, so it does not qualify. | **Yes** |
| **H3a** | Kiro hook | exit-0 stdout (`kiro/hook.py:274-276`) | **Documented live, no artifacts.** `docs/integrations/kiro-hook-spec.md:167-168`, CLI 2.19.2 with `--v3` (v3 engine): "Exit-0 stdout reaches agent context (observed in allow tests)". | **Yes**, with artifacts. A harness is needed: none exists in the repository. |
| **H4a** | Antigravity adapter | to be determined: `{}` plus a stderr reason, or a JSON reason field (`docs/integrations/antigravity.md:70-76`) | **None.** "Verified against 2.8.1 (IDE)" with no run or artifact. | **Yes.** Shape discovery first (§5). **At risk:** IDE only, no harness. |
| **H5a** | Agent SDK PreToolUse callback | `hookSpecificOutput.additionalContext` (`agent_sdk/adapter.py:295-304`) | **None** for SDK hooks. Managed Agents evidence uses a different delivery path (`tool_confirmation`). | **Yes** |
| **H5b** | Agent SDK context injection | UserPromptSubmit `additionalContext` (`agent_sdk/adapter.py:166-178`) | **None** | **Yes** |
| **H5c** | LangChain middleware | `ToolMessage` annotation (`langchain/middleware.py` `_append_note`, `:240`) | **Dispatch-layer LIVE, scripted model.** Run `validation/langgraph/evidence/runs/20260825T162444Z-m0`: a DENIED reason reached the model input. The non-blocking annotation path is documented, not recorded. | **Yes**, for the non-blocking annotation path |
| **H6a** | Hermes tool-call notice | to be determined. `pre_tool_call` offers `block` or nothing, so a non-blocking notice may need next-turn context (`plugin.py:57`, `adapter.py:509-519`) | **Dispatch-layer only**, hermes-agent 0.19.0. No live model session (no credentials, `docs/integrations/hermes.md:76`). | **Yes.** Shape discovery first. **At risk.** |
| **H6b** | Hermes context injection | `pre_llm_call` `{"context"}` (`adapter.py:214-219`) | Dispatch-layer only | **Yes**, with a live model session |

### 4.1 H2a equivalence mapping: M1d-a against the §6 criteria

Source: committed run `validation/codex-cli/evidence/runs/20260824T110210Z-applypatch/`. It has three arms in one run: `allow` (control), `deny`, and `diagctx` (the emitter arm). It was read at `5d8bf82a`.

| §6 criterion | M1d-a artifact | Status |
|---|---|---|
| Pin: codex-cli 0.149.1, binary hash, Windows, `codex exec` | `env.json`: `codex_version: codex-cli 0.149.1`, `pinned_sha256_verified: true`, `platform: win32`, `hook_trust_bypass: false` | **Covered** |
| Same event and shape: PreToolUse `hookSpecificOutput.additionalContext`, no `permissionDecision`, exit 0 | `analysis-m1da.md` quotes the exact emitted JSON; `transcript-diagctx.log` shows exit 0 with no hook-failure mentions | **Covered.** The shape equals `codex_cli/hook.py:_context_output`; only the text differs. |
| Harness-only emitter, no Mneme code | the hook is `validation/codex-cli/probe/log_hook.py` (`.codex/hooks.json` hash is identical across arms) | **Covered** |
| Unique token | fixed sentinel `NONBLOCKING_DIAGNOSTIC_1491`, not a fresh random nonce | **Covered with a note.** The token is unique in the repository, apart from the analysis and the emitter that defines it, so no collision is possible. |
| Tool executed | `diagctx/worktree-after.json`: `probe_target.py` created; `events-diagctx/events/` contains `PreToolUse`, `PostToolUse`, `Stop` | **Covered** |
| File bytes match the control | the `probe_target.py` hash `4e523a8b…` is identical in `allow/worktree-after.json` and `diagctx/worktree-after.json`; all other file hashes are identical too | **Covered** |
| Permission unchanged | both arms ran `codex exec --sandbox workspace-write` with identical commands, and neither recorded an approval prompt | **Covered** |
| No host block, retry or forced continuation | same event sequence in the `allow` and `diagctx` arms (`summary.json` `hook_events_observed`); both return code 0 | **Covered** |
| **Recorded delivery: the token in a model-bound message in the host's session record** | `analysis-m1da.md` fact 4 quotes the rollout entry (`role: developer`, `input_text` containing the sentinel). The **raw rollout file is not committed**: the sentinel appears in the repository only in `analysis-m1da.md` and `log_hook.py`. It was also not found under the local `~/.codex/sessions` at review time. | **Not covered by an artifact.** It rests on the reviewed analysis quote. |
| Echo, turn count | not part of M1d-a's design | Evidence-only under §6; **not required** |

**Result:** every criterion is covered except artifact-backed recorded delivery. Per D1, H2a needs a **targeted re-run** on the same pin that collects and commits a redacted rollout excerpt containing the token. No full re-run is needed.

### 4.2 Amendment A1: H1c with top-level `systemMessage` (ACCEPTED)

**Status: ACCEPTED** (owner approval 2026-10-17, following an independent-review ACCEPT on `19734ac8`). Acceptance authorizes no harness, run, runtime change or freeze amendment. It is coordinated with the charter's §5.1 Amendment A1 and implements the owner's O1 selection ([H1c Stop-path decision](2026-10-17-dg1f-t08-d5-p2-h1c-stop-path-decision.md) (#554, O1)).

**Shape.** The Stop command hook prints `{"systemMessage": "<notice with nonce>"}` and exits 0. There is no `hookSpecificOutput`, no `decision`, no `continue` and no `stopReason`. The paired no-op control prints nothing and exits 0. The path type is unchanged: a command hook on a lifecycle event (§3.1).

**Two runs, each with its own paired no-op control.** Each run is an emitter arm plus a no-op arm, with the same workspace layout, prompt and pins as the H1 batch.

| Run | Purpose | Evidence | Pass/fail criteria |
|---|---|---|---|
| **A1-headless** (`claude -p`, stream-json; the query exits) | Non-interference; also records whether the host surfaces the notice to the stream consumer | hook log, stream-json events, session transcript, the paired control's same files | **Fails only on demonstrated host-induced interference:** Stop invocations exceed the control's, or any envelope has `stop_hook_active: true` (host continuation or re-entry); a permission decision differs for an equivalent request; the host blocks or retries; the run does not end with a normal `result` event; the strict host-event and indicator rules (unchanged) flag a difference. **Evidence only:** model reply text, turn counts, and any extra assistant activity **without** a demonstrated host cause. |
| **A1-interactive** (operator-run interactive `claude`, which starts a session and stays open; observed and captured) | Developer delivery, and non-interference in the interactive host | screen recording from launch until the session has been idle at the input prompt for at least 30 seconds after the reply; hook log; session transcript; the operator's written observation; the same for the paired control | **Developer delivery:** the nonce text is visible in the emitter arm's capture, in the host UI, and absent from the control's. **Fails only on demonstrated host-induced interference:** Stop invocations exceed the control's, or `stop_hook_active: true` appears (hook log); a permission decision differs for an equivalent request, or a prompt appears that the control lacks; the host blocks or retries; or the capture does **not** show the session returning to the input prompt after the reply, as the control does. There is no `result` event or headless stream-json in this mode, so neither is required or compared. **Evidence only:** model reply text, turn counts, and model-chosen activity without a demonstrated host cause. |

**Evidence classification (specification only; any classifier change needs its own harness PR):**
- **Developer delivery** comes **only** from the A1-interactive capture: the nonce is visible in the UI of the emitter arm and not in the control, confirmed against the recording, not only the operator's note. Stream-json output is never developer evidence on its own.
- **A stream-json informational message** carrying the nonce (documented as a possible `SDKInformationalMessage`), or any stream `system` event, is `host_output`: recorded, never delivery.
- **A nonce in a model-bound location** (the existing table, including R1 for `hook_additional_context`) is agent delivery, and the label is `DELIVERED_TO_AGENT` with `developer_also` from the interactive capture.
- **Labels** (§6): `DELIVERED_TO_USER_ONLY` when the interactive capture shows the notice, it is absent from every model-bound location, and **no host-induced interference** is demonstrated in either run. `DELIVERED_WITH_SIDE_EFFECT` when either run demonstrates host-induced interference as defined in the table. Model-chosen differences alone never produce it, consistent with §3 step 4. `NOT_DELIVERED` when the notice appears neither in the UI capture nor model-bound. `INCONCLUSIVE` when the capture is missing or unreadable, a control is missing, or a location is unclassified.
- **H1c passes under A1** only when both runs' evidence supports a passing label.

**Evidence handling.** A full screen recording can show personal data. So the recording stays local, its SHA-256 goes in the evidence manifest, and only redacted still frames showing the notice area (or its absence) are published. Each frame is listed with its timestamp in the recording. The written operator observation is published.

**Pins** (§7): Claude Code `2.1.202` and the init model as in H1; the interactive host on the same machine and version. A pin change needs a reviewed amendment.

**History.** The H1 batch's H1c evidence (`hookSpecificOutput.additionalContext`) stands as the record of the original shape. A1 does not reclassify it.

**Not authorized by A1:**
- the harness change (an emitter mode for `systemMessage`, interactive-run tooling, classifier rules);
- either live run;
- any runtime change, including `_emit_stop_feedback` (#550);
- implementation;
- the `[layer1-freeze]` amendment.

Each needs its own go-ahead, in that order: harness PR, then the runs.

### 4.3 Amendment A2: H1a and H1b re-pinned to Claude Code 2.1.310 (PROPOSED)

**Status: PROPOSED**, for independent review. It is reviewed together with its harness change in the same PR (§5 harness, below). Acceptance would authorize **no** live run, evidence PR, runtime change, charter amendment or `[layer1-freeze]` amendment.

**Why.**
- **The H1 evidence is pinned to a host this machine no longer runs.** H1a and H1b passed under R1–R3 on Claude Code `2.1.202` (#549, #553). On 2026-10-19 the host auto-updated to `2.1.303` between two A1 attempts, and the T-08 G3 batch (#793, `621d0212`) ran on `2.1.310`. §7 counts evidence only for its pinned version, and re-pinning needs a reviewed amendment. This is that amendment for H1a and H1b.
- **Owner decision, 2026-11-11.** In the owner's working session on the D6/P2 assessment, the owner chose reporting level **R-ii** for a proposed P2-first phase. Under R-ii every consumer carries a structured selection reason, and a host-visible notice is claimed only on output paths re-probed on the pinned host, Claude Code first. The owner's words were "Re-probe Claude Code first", and then "Yes, draft it" for this amendment and its harness change.
- **P2-first itself is not accepted here.** It needs its own charter amendment. This re-probe stands on its own as channel evidence that the accepted charter §5 gate or a later P2-first amendment can cite.

**Change** (everything not listed is unchanged):

| Item | H1 batch (#549, unchanged) | A2 |
|---|---|---|
| Host | Claude Code `2.1.202` | Claude Code `2.1.310 (Claude Code)`. `DISABLE_AUTOUPDATER=1` is required in the launching shell; the preflight and every probe check it. The version is re-checked immediately before **every** session, and a mismatch aborts. |
| Model | init model as observed (`claude-opus-4-8[1m]`) | `--model claude-opus-5-5` on every session. The first init event must report exactly that model (abort otherwise), and every pair is classified against it. |
| Paths | H1a-edit, H1a-bash, H1b-start, H1c-stop | **H1a-edit, H1a-bash, H1b-start**: three pairs, six sessions. H1c is not in A2. |
| Candidate shapes | §4 | Unchanged: PreToolUse `hookSpecificOutput.additionalContext` with no `permissionDecision`; SessionStart `hookSpecificOutput.additionalContext`. |
| Controls, labels, classifier rules | §3.1, §6, R1–R4 | Unchanged |
| Version pin in the classifier | Not checked (preflight only) | Each arm's recorded `claude_version` must equal the pin; otherwise `NOT_EXECUTED` |
| Flags | `-p --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools <per path> --setting-sources project` | The same, plus `--model claude-opus-5-5` |
| Disposable root | `C:\dev\d5p2-h1-live` | `C:\dev\d5p2-h1-a2-live`. Its guarded delete refuses the H1 and A1 live roots, both archives and the preserved A1 attempts. |
| Batch result | The H1 gate line | A **listed-path result** that states it is not the H1 gate, because H1c is not probed |

**H1c.** H1c stays on its own A1 track (§4.2), pinned to `2.1.202`. The A1 interactive run did not complete because the host auto-updated. Re-pinning A1 needs its own amendment and is not part of A2.

**A passing A2 would establish** that the two candidate shapes reach the agent without host-induced side effects for these three paths, on Claude Code `2.1.310`, headless, with `claude-opus-5-5`, n = 1 each. **It would not establish:**
- the H1 gate;
- developer delivery in an interactive session;
- any other host version or model;
- that Mneme emits any of these outcomes, since nothing is implemented;
- the mixed-pin question in A2-1.

**Decisions for the reviewer:**

| # | Decision | Recommendation |
|---|---|---|
| A2-1 | Can H1a and H1b on `2.1.310` combine with H1c on another version into one H1 gate result under charter §5? | **No**, not under the charter §5 gate as written: one gate's paths share one pin. Under R-ii, if a P2-first amendment adopts it, each path is judged on its own pin. A2 decides neither. It records each path's host version in the summary, and the classifier never prints a gate or listed-path `PASS` unless every included path records the same host version. |
| A2-2 | Add `--model` to the fixed flag list | **Yes.** It follows the G3 precedent (C3 harness, `C3_PINSET=G3`). It removes the account-default drift seen in the A1 attempts, and the init model is still checked. |
| A2-3 | Coexistence with the ADR-033 proceed note | **An implementation obligation, not covered by A2.** A2 probes only the delivery of the existing `additionalContext` shape. On a direct write, an eventual selection notice must share the single PreToolUse `additionalContext` object with the ADR-033 C2b proceed note (`ProceedNote.consumed`). Whether the two are emitted correctly together is **not** established here. The implementation PR must include its own offline coexistence test: one object, both texts, no `permissionDecision`, exit code unchanged. |
| A2-4 | Repeat count | Unchanged (D4): n = 1 per path plus its control. A re-run happens only on `INCONCLUSIVE`. |

**Harness (same PR).** All changes are under `docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/`; every H1 default is unchanged.
- `pins.env` gains the A2 pin set. It is selected only by `run_h1.sh A2`, which exports `H1_PINSET=A2`, following the C3 `C3_PINSET=G3` pattern. Any other value aborts, and so does `H1_PINSET` set to the empty string. `run_h1.sh` refuses to start whenever `H1_PINSET` is already set in the environment (even empty), with or without an argument; it never overwrites it.
- The untracked `pins.local.env` may set operator paths (`PY`) only. `pins.env` snapshots every pinned value before sourcing it: host version, model, model flag, live root, guarded delete, paths, settings sources and the pin set. Any change, including an unset, aborts and names the variables. This holds for both the A2 and the H1 pins.
- `pins_a1.env` refuses any pin set.
- New `safe_rmtree_a2.py`: the A2 root, the six A2 arms, and the protected trees listed above.
- `run_h1_probe.sh`:
  - an arm must belong to the active pin set;
  - the live root and guarded delete come from the pin set;
  - A2 requires `DISABLE_AUTOUPDATER=1`;
  - the host version is checked before every session;
  - `--model` is passed when the pin set defines one;
  - the observer records the pin set, the model flag and the checked version.
- `preflight.sh` reports the pin set and checks `DISABLE_AUTOUPDATER` for A2.
- `classify_h1.py`:
  - `pair` takes an optional version pin;
  - `verify` and `summary` take an optional path subset;
  - only an all-four summary carries the H1 gate line;
  - a gate or listed-path result is `PASS` only when every included path records one host version;
  - the summary shows the host version per path.
- The self-test stub follows `--model` and the active pin set's version.
- New `selftest/test_a2_harness.py`.

**Offline validation:** 161 harness tests pass (103 existing, 58 new, including the regressions from both #794 review rounds). Mutation checks confirm the new guards matter: with the host-version rule disabled, its four tests fail; with the `pins.local.env` guard disabled, all 12 override tests fail. The end-to-end stub self-test of `run_h1.sh A2` gave `DELIVERED_TO_AGENT` on all three paths and a listed-path result of `PASS` (stub, not evidence). It aborted at the preflight without `DISABLE_AUTOUPDATER=1`, and it never touched `C:\dev\d5p2-h1-live`. The A2 root was emptied afterwards.

**Run, if separately authorized.** The operator runs it from their own terminal (never inside Claude Code) with `claude --version` printing `2.1.310 (Claude Code)`, `pins.local.env` setting `PY`, and `DISABLE_AUTOUPDATER=1 bash run_h1.sh A2`. Evidence is collected with `collect_h1.py` into a separate evidence PR: `docs/validation/dg1f-t08-d5-p2-host-path-h1-a2-<date>.md`.

**Not authorized by A2:**
- the live run or the evidence PR;
- re-pinning A1/H1c;
- H2–H6;
- any change under `mneme/`;
- a P2-first or D5 + P2 charter amendment;
- the `[layer1-freeze]` amendment;
- implementation.

### 4.4 Amendment A3: H1c (A1 track) re-pinned to Claude Code 2.1.310 (PROPOSED)

**Status: PROPOSED**, for independent review. It is reviewed together with its harness change in the same PR, following A2. Acceptance would authorize **no** live run, evidence PR, H1 gate record, runtime change, charter amendment or `[layer1-freeze]` amendment.

**Why.**
- **H1c is the only H1 path without a usable result.**
  - The A1 headless run on `2.1.202` gave `NOT_DELIVERED` with no host interference under R1–R4 (#560, #563).
  - The A1 interactive run never completed. The host auto-updated to `2.1.303` between the two attempts, and both attempts are preserved and unusable (§4.3).
  - H1c passes under A1 only when **both** runs support a passing label (§4.2), so H1c has no result.
- **H1a and H1b now have a result on `2.1.310`.** A2 (#795), reclassified under R1–R5 (#800), gives `DELIVERED_TO_AGENT` on all three paths: a listed-path `PASS` that is not the H1 gate.
- **A2-1 still applies.** Under charter §5, one gate's paths share one pin. With H1c on the same host and model as A2, the H1 gate can be computed on one host version without deciding A2-1.
- **Owner instruction, 2026-11-13:** "Start H1c Stop-path validation", after the #801 review named H1c as the remaining H1 blocker.

**Change** (everything not listed is unchanged; A1's own pins stay as they are and select nothing new):

| Item | A1 (§4.2, unchanged) | A3 |
|---|---|---|
| Host | Claude Code `2.1.202` | Claude Code `2.1.310 (Claude Code)`, as A2. `DISABLE_AUTOUPDATER=1` is required in every shell that prepares, runs or finishes an arm, and in the operator's interactive window. The version is checked immediately before every headless session, before an interactive arm is prepared, and again when it is finished. A mismatch aborts. |
| Model | init model as observed (`claude-opus-4-8[1m]`) | `--model claude-opus-5-5` on every session, headless and interactive. The headless init event must report exactly that model, and every interactive transcript model must equal it (the existing A1 rule). |
| Runs | headless pair, then an interactive pair (control first) | Unchanged: **both** runs are repeated on the A3 pin. The `2.1.202` headless result is not reused (A3-2). |
| Shape, controls, labels | §4.2 | Unchanged: top-level `systemMessage`, exit 0, and a paired no-op control in each run. The criteria are those of the §4.2 table. |
| Classifier rules | R1–R4 (#563) | The merged table, now R1–R5 (#798). R5 is anchored on tool-attributed `hook_additional_context` entries, so it cannot classify the Stop `systemMessage` (A3-5). |
| Version pin in the classifier | Interactive only | **Headless too:** an arm whose recorded `claude_version` differs from the pin, or is unrecorded, gives `NOT_EXECUTED`. **`combine` judges H1c on one host version:** both headless arms' recorded versions and the interactive pin must be present and equal, otherwise `NOT_EXECUTED`. |
| Interactive operator steps | §4.2 | Hardened from the 2026-10-19 attempts. Everything happens in **one** window: set `DISABLE_AUTOUPDATER`, check `claude --version`, start the session with `--model`, and stop if the session is not signed in. The prompt is sent **once**, there is never `/model` or `/login` in the session, there is at least 30 seconds of counted idle time, and then `/exit`. |
| Disposable root | `C:\dev\d5p2-h1c-a1-live` | `C:\dev\d5p2-h1c-a3-live`. Its guarded delete refuses the H1, A1 and A2 roots, every archive and the preserved A1 attempts. |
| Result | H1c under A1 | H1c under A1 **on `2.1.310`**, from `classify_a1.py combine`. It is still not the H1 gate. |

**After A3, if separately authorized.** The H1 gate on `2.1.310` would combine:
- A2's three R1–R5 outcomes (#800);
- A3's combined H1c outcome.

That is a separate gate-record step, and it uses only outcomes that record the same host version. It is not part of this PR.

**What 2.1.310 may change for Stop.** On `2.1.310` the host added a `rendered` copy to `hook_additional_context` attachments and a new `api-request-blob` entry (#795, R5). The Stop `systemMessage` may gain similar records.
- **Not pre-decided here.** A new nonce location is `unclassified`, so the run is `INCONCLUSIVE` and needs a reviewed rule (the #551 → #552 → #553 and R5 precedent). The raw evidence allows offline reclassification.
- **An api-request-blob.** If the `systemMessage` appears in one, that is a candidate model-bound location for review, not delivery by default.
- **The A1 known collision still stands.** If the notice appears as a stream `system` event in the emitter arm only, the strict host-event rule makes the headless run `INCONCLUSIVE`.

**Decisions for the reviewer:**

| # | Decision | Recommendation |
|---|---|---|
| A3-1 | The pin for H1c: `2.1.310` (A3), or reinstalling `2.1.202` to finish A1 on its original pin | **`2.1.310`.** It matches A2, G3 (#793) and the host this machine runs, so H1 can be gated on one current pin. Returning to `2.1.202` would mean downgrading the operator's host, and the H1 gate would then rest on an outdated host. The cost is re-running the A1 headless pair, which takes a few minutes. |
| A3-2 | Reuse the `2.1.202` headless result? | **No.** `combine` now requires one host version, so the headless pair is re-run on `2.1.310`. The `2.1.202` result stays as history (#563). |
| A3-3 | Interactive capture method | **Unchanged:** an operator-run screen recording plus a named independent capture review (`capture_review.json`), bound by SHA-256 to the recording and the frames. No automated terminal capture is proposed. |
| A3-4 | Repeat count | Unchanged (D4): n = 1 per run, plus its control. A run is repeated only on `INCONCLUSIVE`. An arm refused before its session (pin, version or flag) is prepared again and is never counted. |
| A3-5 | R5 and the Stop path | **R5 does not apply to H1c.** Its anchors are tool-attributed `hook_additional_context` entries. A new `2.1.310` Stop location goes through its own rule review, as A3 says above. |

**Harness (same PR).** All changes are under `docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/`. Every A1 and H1 pin value is unchanged. Three A1 behaviors become stricter, and each can only refuse:
- the host version is checked before every headless session;
- `finish` refuses without writing;
- `combine` requires one recorded host version.

- **`pins_a1.env` gains the A3 pin set.** It is selected only by `A1_PINSET=A3`, which the A1 entry points set from their argument:
  - `run_a1_headless.sh A3`;
  - `prep_a1_interactive.sh A3 <arm>`;
  - `finish_a1_interactive.sh A3 <arm> <recording>`.

  An inherited `A1_PINSET` (even empty) is refused by every entry point and by `run_h1.sh`, and an unknown value aborts. `A1_PINSET` joins the `pins.env` snapshot, so `pins.local.env` can neither set nor clear it.
- **New `safe_rmtree_a3.py`:** the A3 root, the four A1 arm names, and the protected trees listed above.
- **`run_a1_probe.sh`:**
  - the root and guarded delete come from the pin set;
  - A3 requires `DISABLE_AUTOUPDATER=1`;
  - the host version is checked immediately before every session;
  - `--model` is passed when the pin set defines one;
  - the observer records the pin set, the model flag and the checked version.
- **`run_a1_headless.sh`:** pin-set selection, and the version pin is passed to the headless classifier under A3.
- **`prep_a1_interactive.sh` and `finish_a1_interactive.sh`:**
  - pin-set selection and the A3 root;
  - the A3 operator steps;
  - `finish` refuses an arm prepared under another pin set;
  - its version check now refuses **without writing into the arm**;
  - it prints the exact classify commands for the active pins.
- **`preflight.sh` and the self-test stub** read the A1 pins under an A1 pin set. The preflight checks `DISABLE_AUTOUPDATER` for A3.
- **`classify_a1.py`:**
  - `headless … <pin_model> [<pin_version>]`, which records both arms' host versions;
  - `combine` checks the host version first and fails closed.
- **New `selftest/test_a3_harness.py`.** In `test_a1_harness.py`, the headless fixture now records the host version, as the runner always does.

**Offline validation:**
- **Tests:** 277 harness tests pass (234 existing, 43 new).
- **Mutation checks:** each of 12 mutants is caught: the pins, the snapshot, the `combine` version check, the headless version pin, the inherited pin-set refusals, the auto-updater checks in the probe, preflight and `finish`, the protected trees and `--model`. A thirteenth mutant, a broken preflight line continuation, is caught by a strengthened preflight test.
- **End-to-end stub self-test** of `run_a1_headless.sh A3`, plus the interactive prep and finish for one arm:
  - the preflight reported pin set A3, `DISABLE_AUTOUPDATER=1` and `2.1.310`;
  - the observers recorded `pinset=A3`, the `claude-opus-5-5` model flag and `2.1.310`, and the init event reported `claude-opus-5-5`;
  - a stub host version of `2.1.311` at finish was refused, with nothing written.

  The A3 root was emptied afterwards through `safe_rmtree_a3.py`.
- **Self-test incident (fixed in this PR):** one `finish` call made without `A3` targeted the A1 root.
  - It wrote a new `harness_failure.txt` into the leftover attempt-2 control arm, through the old failure path.
  - The file was removed. The arm's file set and hashes match the preserved `2026-10-19-ctl-attempt2` copy, and nothing else in the A1 root or archive changed.
  - `finish` now refuses on its version check without writing.

**Run, if separately authorized.** The operator runs it from their own windows, never inside Claude Code, with `PY` set in `pins.local.env` and `DISABLE_AUTOUPDATER=1`:
1. `run_a1_headless.sh A3`.
2. The interactive pair, control first: `prep_a1_interactive.sh A3 <arm>`, the recorded session as printed, then `finish_a1_interactive.sh A3 <arm> <recording>`.
3. A named reviewer completes `capture_review.json` for both arms.
4. `classify_a1.py interactive` and `combine`, as printed by `finish`.

Evidence goes into a separate PR: `docs/validation/dg1f-t08-d5-p2-host-path-h1c-a3-<date>.md`.

**Not authorized by A3:**
- the live runs or the evidence PR;
- the H1 gate record;
- H2–H6;
- any change under `mneme/`, including `_emit_stop_feedback` (#550);
- a P2-first or D5 + P2 charter amendment;
- the `[layer1-freeze]` amendment;
- implementation.

## 5. Harness: reuse and build, per host

- **H1 (Claude Code).** Derived from the D6 C4 harness (`docs/validation/artifacts/dg1f-t08-d6-c4-mneme-memory-live/harness/`): `preflight.sh`, the `pins.env` pattern, redaction and the collector are reused. The hook command becomes the emitter. The PreToolUse probes keep `-p --output-format stream-json --verbose`. SessionStart and Stop registrations are added. Recorded delivery is read from stream-json **and** the session transcript, and the harness records which of the two carried the nonce.
- **H2 (Codex).** Reuses `validation/codex-cli/probe/` (`log_hook.py`, the `run_*_live.py` pattern). H2b adds a Stop `systemMessage` emitter. Delivery is read from the session rollout.
- **H3 (Kiro).** **New harness.** CLI driver with `--v3`, envelope logger, emitter, and transcript capture. The existing spec observation is not artifact-backed, so it does not count as a probe.
- **H4 (Antigravity).** **New, operator-driven.** It is IDE only, so there is likely no headless driver. Step 1 is shape discovery: what the adapter host accepts on exit 0 without blocking. Step 2 is an operator-observed run with screen capture and a hook log. If no non-blocking shape exists, the label is `NO_NONBLOCKING_CHANNEL` (§6), and the gate fails by charter §5.
- **H5a/H5b (Agent SDK).** **New harness:** a minimal `claude-agent-sdk` script with the adapter's callbacks replaced by the emitter, a real model, and the message stream captured. It needs API credentials supplied by the operator. The SDK version is pinned at harness-build time.
- **H5c (LangChain).** Extends `validation/langgraph/probe/probe_m0.py` with a non-blocking annotation case. A scripted model is acceptable, subject to decision D2 (§10).
- **H6 (Hermes).** **New harness:** a hermes-agent 0.19.0 session with a live model, which needs operator-supplied credentials. Shape discovery for H6a comes first.

Every harness gets an offline self-test, with a stub host where one is possible, before any live run. That follows the C3/C4 discipline.

## 6. Labels and exact criteria

| Label | Criteria |
|---|---|
| `DELIVERED_TO_AGENT` | The nonce appears in a model-bound message in the host's session record, **and** the path type's control (§3.1) plus the common criteria (§3 step 4) hold. Sub-fields: `path_type`; `echoed` (true/false); `developer_also` (true, false or `not_observed`); `turns` and `turns_control` (evidence only). **Passes** the path. |
| `DELIVERED_TO_USER_ONLY` | The nonce is shown to the developer in an operator-observed, captured interactive run; it is absent from every model-bound message; and the path type's control plus the common criteria hold. **Passes** the path under D5 §5.1 (developer **or** agent), on **any** path, and is reported separately from agent delivery. |
| `DELIVERED_WITH_SIDE_EFFECT` | The nonce is delivered, but the path type's control or a common criterion fails. Examples: the tool did not execute or dispatch; the session did not start or end normally; the host treated a callback return as a block; the tool result changed beyond the annotation; a permission changed; or the host retried or forced a continuation. Model-chosen differences (reply text, turn count, extra tool calls) never produce this label. **Fails** the path. |
| `NOT_DELIVERED` | The emitter ran (its log shows the surface was invoked and what it produced), and the nonce is in no model-bound message and no observed UI. **Fails** the path. |
| `NO_NONBLOCKING_CHANNEL` | Shape discovery (H4a, H6a) found no exit-0 shape the host accepts without side effects. **Fails** the path. |
| `EVIDENCE_REUSED` | Decision D1 applies, and the §4.1 equivalence mapping shows every §6 criterion as **covered** by committed artifacts: same host version, same event, same shape. **Passes** the path, citing the record. A criterion mapped **not covered** requires a targeted re-run of that criterion only. |
| `NOT_EXECUTED` | Preconditions not met: pin mismatch, credentials absent, emitter not registered, no session record. **Never** a negative result. |
| `INCONCLUSIVE` | Echo without recorded delivery; emitter output missing from the hook log; the paired control run is missing, or a host-induced difference cannot be attributed to the emitter; a nonce collision. Reasons are listed. |

**Gate rule** (from the charter): H*n* passes only when **every** path under it is `DELIVERED_TO_AGENT`, `DELIVERED_TO_USER_ONLY` or `EVIDENCE_REUSED`. One `NOT_DELIVERED`, `DELIVERED_WITH_SIDE_EFFECT` or `NO_NONBLOCKING_CHANNEL` anywhere blocks the freeze amendment for all consumers. The gate summary record lists the audience reached per path.

## 7. Pins and safety guards

**Pins** (recorded per probe; a mismatch aborts the run; re-pinning needs a reviewed amendment):

| Gate | Pin |
|---|---|
| H1 | Claude Code `2.1.202` and the init model recorded at run time, as in C1–C4 (`pins.env`). If 2.1.202 is no longer installable, re-pinning needs a reviewed amendment. Amendment A2 (§4.3, proposed) re-pins H1a and H1b only to `2.1.310` with `--model claude-opus-5-5`. |
| H2 | codex-cli `0.149.1` with the binary SHA-256 from `validation/codex-cli/pinned-build.json` |
| H3 | Kiro CLI `2.19.2` with `--v3` (v3 engine), as in the spec; IDE 1.x is out of scope |
| H4 | Antigravity `2.8.1` (IDE) |
| H5 | `claude-agent-sdk` version and model recorded at harness build; langchain `1.3.17`, langchain-core `1.6.0` and langgraph `1.2.11` (`validation/langgraph/pinned-build.json`) |
| H6 | hermes-agent `0.19.0` |

**Safety guards:**
- The operator runs every live probe from an external terminal, never nested in a Claude Code session; the preflight refuses when `CLAUDECODE` is set.
- Probe workspaces are disposable, outside any Git checkout and outside any `.mneme` ancestor.
- The emitter never runs Mneme code and never writes outside its log.
- Credentials are supplied by the operator through the environment, never logged or committed, and covered by the leak scan.
- No user or managed settings source is loaded where the host allows that choice.

## 8. Evidence and provenance

- **Per probe:**
  - the emitter bytes and its hook log (envelope and emitted payload);
  - the selected host session record;
  - the paired control record;
  - the side-effect comparison;
  - `outcome.json` with the label and its sub-fields;
  - file hashes before and after;
  - the pins.
- **Redaction:** the C2–C4 conventions. Local paths become placeholders and session IDs are pseudonymized. Credentials are never present, and the leak scan enforces that.
- **Records:** one validation record per gate batch: `docs/validation/dg1f-t08-d5-p2-host-path-<gate>-<date>.md`, each in its own evidence PR. A final gate summary record lists all twelve paths with their labels before any freeze-amendment PR.

## 9. What these probes would and would not establish

**Would:** whether each candidate shape reaches the agent (or the developer) on the pinned host version without side effects. That is the only evidence charter §5 requires before the freeze amendment.

**Would not:**
- that Mneme emits these outcomes: nothing is implemented;
- that any specific memory-selection outcome is correct;
- other host versions, models or modes;
- repeatability (n = 1 per path unless D4 says otherwise);
- that an agent acts on the notice;
- anything about agent-controlled settings (C5/C6 remain unauthorized).

**Correction to the accepted charter's §5 table.** It lists H2 (Codex) and H3 (Kiro) as "none proven". At `5d8bf82a` the repository records:
- **Codex:** live PreToolUse `additionalContext` delivery (M1d-a) and a live Stop `decision: block` (M3);
- **Kiro:** a documented, though not artifact-backed, live exit-0 stdout delivery.

The `codex_cli/gate.py:420-424` docstring that the charter relied on is stale. This changes no charter decision: §4 above classifies each path from the actual evidence. A one-line erratum to the charter, and the docstring fix (which touches runtime code), are left to separate PRs.

## 10. Decisions requested of the reviewer

| # | Decision | Recommendation |
|---|---|---|
| D1 | May H2a reuse M1d-a instead of re-running? | **Yes for every criterion §4.1 maps as covered.** The one criterion that is not artifact-backed (the raw rollout record) gets a **targeted** re-run on the same pin, collecting only the rollout delivery record, provided the implementation emits `codex_cli/hook.py:_context_output`'s shape unchanged. A pin change requires a full re-run. |
| D2 | Is a scripted-model dispatch-layer run enough for H5c (LangChain is a library, and the model input is the observable)? | **Yes** for H5c. **No** for H6 (Hermes is an agent application): it needs a live model session. |
| D3 | Can developer-only delivery pass a path? | **Yes, on any path**, per D5 §5.1 (developer **or** agent). It is recorded separately as `DELIVERED_TO_USER_ONLY`, and the gate summary shows the audience per path. No owner approval is needed, because this is the accepted D5 criterion, not a stronger one. |
| D4 | Repeat count | n = 1 per path, plus the paired control. A re-run is required only on `INCONCLUSIVE`. |
| D5 | Batch order | H1 (harness reuse), then H2b and H5c (existing harnesses), then H3, H5a/H5b and H6 (new harnesses, credentials), then H4 last (IDE, operator-driven, highest risk). Each batch gets its own evidence PR. |

## 11. Non-authorization

Merging this proposal authorizes **none** of the following:
- running any probe or building any harness, which needs a separate harness PR and an explicit go-ahead per batch;
- any live host session;
- any change to `mneme/`, including the stale docstring;
- the `[layer1-freeze]` amendment;
- the shared D5 + P2 implementation;
- any charter amendment, including the §9 erratum;
- C5/C6;
- ADR or ADR-033 changes;
- changes to C1–C4 evidence, pins or worktrees.

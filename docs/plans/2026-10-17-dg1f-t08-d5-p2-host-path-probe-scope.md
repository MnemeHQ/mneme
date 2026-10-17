# DG1F T-08 D5 + P2: host-output-path channel probes H1–H6, live-evidence design (proposal)

**Status:** **PROPOSED.** Design only. **Nothing here is executed.** It authorizes no probe, no harness build, no live host session, no runtime change, no `[layer1-freeze]` amendment and no implementation (see §11).
**Anchor:** `main` @ `5d8bf82a`. That is after the accepted [D5 + P2 implementation charter](2026-10-17-t08-d5-p2-memory-resolution-charter.md) (#542) and its §6 characterization tests (#543).
**Revision 2 (2026-10-17):** answers the #545 review.
- Side-effect criteria are narrowed to host-induced effects; turn count and model text are evidence only (§3, §6).
- Developer-only delivery may pass any path, recorded separately from agent delivery (§3, §6, D3).
- An explicit H2a equivalence mapping against the committed M1d-a artifacts is added (§4.1).

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
| **H1c** | Claude Code Stop | `hookSpecificOutput: {hookEventName: "Stop", additionalContext}` (`_emit_stop_feedback`, `hook.py:743-758`) | **None** | **Yes.** Also record whether a Stop notice can reach the agent at all once the turn has ended (§6, `DELIVERED_TO_USER_ONLY`). |
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
| H1 | Claude Code `2.1.202` and the init model recorded at run time, as in C1–C4 (`pins.env`). If 2.1.202 is no longer installable, re-pinning needs a reviewed amendment. |
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

# DG1F T-08 D5 + P2: H1 Claude Code host-output-path probe, live batch (2026-10-17)

> This is the evidence record for gate **H1** of the accepted
> [host-output-path probe scope](../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md)
> (#545), run with the accepted harness from #546 (merge `06d83f82`).
>
> **Result: H1 gate NOT MET.** All four paths are `INCONCLUSIVE` as classified.
> The labels are reported exactly as `classify_h1.py` produced them during the
> run. **Nothing is reclassified here.** §4 records three findings for review.
> They are not decisions.
>
> This record is evidence only. It changes no runtime behaviour, amends no
> charter, freeze or ADR, and authorizes no H2–H6 probe, re-run or implementation.

## 1. Authorization, environment and provenance

| Item | Value |
|---|---|
| Authorization | Owner, 2026-10-17: the H1 live batch only, with the #546 harness at `06d83f82`; four paths, one emitter and one no-op control each (eight sessions at most); pinned Claude Code 2.1.202; fixed root `C:\dev\d5p2-h1-live`; every guard mandatory; raw evidence preserved; no runtime changes, freeze amendments, H2–H6 probes or further batches. |
| Operator | Ran the commands from an external PowerShell window, invoking Git Bash (`bash.exe -l`), not nested in Claude Code. The preflight reported `[preflight] OK` with 0 `MNEME_*` variables. |
| Host | **Claude Code `2.1.202`** on Windows; init model **`claude-opus-4-8[1m]`** in every probe that recorded an init event, matching the pin. Flags: `-p --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools <per path> --setting-sources project`. |
| Harness | `06d83f8229720a213d0e1f97cf6ebe406facd098`, clean. The per-file SHA-256s are in `run_h1.log` (published). |
| Run time | 2026-10-17, 17:51:24Z (first control) to about 17:53Z (last emitter). One run per arm. Every `claude` process exited 0. |
| Collection | [`harness/collect_h1.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/collect_h1.py) was **added after the run**: it is not part of the hashed as-run harness. It selects and redacts, and it **does not reclassify**; each `outcome.json` is published as written, apart from path redaction. `MANIFEST.json` records the collector SHA-256 and the hashes and sizes of the unpublished raw files. |
| Evidence | [`artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/). The raw `events.jsonl`, `transcript.jsonl` and `claude.stderr.txt` remain in `C:\dev\d5p2-h1-live`, unchanged. They are not published because they carry the operator's environment listings and model thinking. Their SHA-256s are in the manifest. |

## 2. Results as classified

| Path | Path type | Label | Reasons (exact strings from the published `<path>/outcome.json`) |
|---|---|---|---|
| `H1a-edit` | command hook, tool event | **INCONCLUSIVE** | `unexplained host-event difference between arms (emitter ['thinking_tokens', 'thinking_tokens', 'thinking_tokens', 'thinking_tokens'], control ['thinking_tokens', 'thinking_tokens'])`<br>`nonce found in locations the category table does not recognise; review needed` |
| `H1a-bash` | command hook, tool event | **INCONCLUSIVE** | `unexplained host-event difference between arms (emitter ['task_notification', 'task_started'], control ['task_notification', 'task_started', 'thinking_tokens', 'thinking_tokens'])`<br>`nonce found in locations the category table does not recognise; review needed` |
| `H1b-start` | command hook, lifecycle event | **INCONCLUSIVE** | `nonce found in locations the category table does not recognise; review needed` |
| `H1c-stop` | command hook, lifecycle event | **INCONCLUSIVE** | `nonce found in locations the category table does not recognise; review needed` |

**H1 gate: NOT MET** (`summary_h1.md`). `H1_DONE` exists. It means only that the batch finished.

Controls that held, as recorded in each `outcome.json`:
- **Every pair:** `permission_decisions_equal_for_equivalent_requests: true`, with no unmatched denials and no non-equivalent requests; no permission/block/retry indicator fields in any `system` event; non-error results.
- **H1a-edit and H1a-bash:** the tool ran, was not denied, and produced the exact expected file (`beta\n` and `probe-ran\n`), identical to the control.
- **H1b-start:** both arms started normally. `hook_started` and `hook_response` events appeared in **both** arms.
- **H1c-stop:** `no_stop_reentry: false` and `stop_invocations_equal: false` (§4.3).

## 3. Where the nonce was recorded

On every path, the nonce appears in three kinds of place:

| Location | Category under the as-run table | Example |
|---|---|---|
| A transcript `attachment` entry with `attachment.type: "hook_additional_context"`, `hookEvent` = the probed event, and `content` = the exact emitted notice | `unclassified` | `H1a-edit/transcript.selected.jsonl`, entry `"line": 12` |
| A transcript `attachment` entry with `attachment.type: "hook_success"`, whose `stdout` is the emitter's raw JSON | `unclassified` | `H1a-edit/transcript.selected.jsonl`, entry `"line": 11` |
| The model's reply text, repeating the nonce (stream-json `assistant` text, `result.result` and the transcript `assistant` entry) | `echo` | `H1a-edit/events.selected.jsonl` |

For **H1b-start** the nonce also appears in the stream-json `system` `hook_response` event's `output` and `stdout`, categorised `host_output`. The control arm has the same event subtypes, carrying an empty output.

## 4. Findings for review (no decision taken here)

### 4.1 The host records delivered hook context as `attachment` entries

On all four paths, Claude Code 2.1.202 recorded the emitter's `additionalContext` as a transcript entry of type `attachment`, with `attachment.type: "hook_additional_context"`. On every path, a model reply repeating the nonce came next. That is strong evidence the context reached the model.

The as-run category table deliberately leaves `attachment` unclassified, so the unclassified-first rule correctly forced `INCONCLUSIVE`. Recognising `hook_additional_context` as `model_bound`, and `hook_success`'s `stdout` as host output, would be a **reviewed change to the category table**. The preserved raw evidence would then allow re-classification without a new live run.

### 4.2 The strict host-event rule tripped on `thinking_tokens`

The host-event differences in H1a-edit (4 vs 2) and H1a-bash (0 vs 2) are all `thinking_tokens` events. The other subtypes (`task_started`, `task_notification`, `hook_started`, `hook_response`) matched between arms. `thinking_tokens` looks like accounting of the model's own reasoning, which varies from run to run, not a host permission or flow decision. However, this record does not establish what the host uses the event for. Excluding it from the strict comparison would be a reviewed rule change.

### 4.3 Stop `additionalContext` caused the host to re-enter the session (H1c)

This is a host-induced side effect, and no re-classification removes it:
- **Emitter arm:** the Stop hook ran **9 times**. The first invocation had `stop_hook_active: false` and the next eight had `stop_hook_active: true` (`H1c-stop/hook-log.jsonl`). The model produced **9** assistant replies (`events.selected.jsonl`), and the transcript shows 9 pairs of `hook_success` / `hook_additional_context` Stop attachments, each followed by a reply.
- **Control arm (no-op):** the Stop hook ran **once**, with one reply.

The result event in both arms reports `num_turns: 1` and `subtype: success`, and the session ended without operator action. The scope §3.1 lifecycle control (the session ends normally, with no forced continuation or host-driven extra turn) fails for the emitter arm. So even after the rule changes in 4.1 and 4.2, H1c would classify as `DELIVERED_WITH_SIDE_EFFECT`, and **H1 cannot pass with this shape on the Stop path**. Under the accepted charter (§5) and scope (§6), the Stop path then needs either a different, separately probed channel or an explicit D5 revisit.

**Relevance to shipped code (observation only).** The Claude Code adapter's `_emit_stop_feedback` (`mneme/integrations/claude_code/hook.py:743-758`) emits this same shape (`hookSpecificOutput.additionalContext` on Stop) for degraded-but-permit states. This evidence suggests that on 2.1.202 such feedback can make the session continue rather than only inform. This record proposes no runtime change; that would need its own charter.

## 5. What this batch establishes and does not

**Establishes** (Claude Code 2.1.202, Windows, `-p`, n = 1 per arm):
- the emitter shapes are accepted and run at PreToolUse (Edit and Bash), SessionStart and Stop with exit 0;
- the host records the context as `hook_additional_context` attachments, and the model then repeats the nonce;
- the tool runs and permissions are unaffected at PreToolUse;
- a Stop `additionalContext` makes the host continue the session with `stop_hook_active` re-entry.

**Does not establish:**
- H1 PASS, or any gate;
- developer (UI) visibility, since this run was headless (`developer_also: not_observed`);
- other versions, models or interactive mode;
- repeatability;
- what `thinking_tokens` means to the host;
- anything about H2–H6, the freeze amendment or implementation.

## 6. Decisions for review (not taken here)

1. Whether to amend the category table: `hook_additional_context` → `model_bound`; `hook_success.stdout` → host output. Then re-classify this evidence offline.
2. Whether to exclude `thinking_tokens` from the strict host-event comparison, and then re-classify offline.
3. The Stop path (H1c): probe a different Stop channel, for example `systemMessage`, under a new scope amendment, or revisit D5 for Stop.
4. Whether to open a separate issue for the shipped `_emit_stop_feedback` behaviour (§4.3).

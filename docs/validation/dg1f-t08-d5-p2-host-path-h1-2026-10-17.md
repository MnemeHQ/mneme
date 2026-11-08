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

---

## 7. Addendum: offline reclassification under R1–R3 (2026-10-17)

> Sections 1–6 above are the as-run record and are **unchanged**. The as-run
> `outcome.json` files are unchanged too. This addendum records a separately
> authorized **offline** reclassification under rules R1–R3 (accepted in #551 and
> implemented in #552, merge `5300799e`). No host session ran. Decisions 1 and 2
> in §6 were answered by #551. Decisions 3 (the Stop path) and 4 (now issue #550)
> are unaffected.

### 7.1 Archive and integrity

- **Archive.** `C:\dev\d5p2-h1-live` was copied to `C:\dev\d5p2-h1-archive\2026-10-17` before any further tool touched the evidence. The copy is byte-identical: 97 files with identical SHA-256 listings. The listing is stored beside it as `2026-10-17.SHA256SUMS` (SHA-256 `f50f1221…89a87`).
- **Manifest check.** All **24** unpublished raw files (`events.jsonl`, `transcript.jsonl` and `claude.stderr.txt` for each of the eight arms) match the SHA-256 and sizes in this record's `MANIFEST.json`.
- **Protection.** The archive files are set read-only. On Windows that blocks changes to the files but not the creation of new files in the folders. A test file created while checking writability was removed before the final verification, and the 97-file listing verified again after the reclassification.
- **The original `C:\dev\d5p2-h1-live` is untouched.**

### 7.2 Procedure

[`harness/reclassify_h1.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/reclassify_h1.py) (SHA-256 `1dbbfdd4…ddef0f89b`; revised after the #553 review, see §7.5) ran the merged `classify_h1.py` (SHA-256 `bd883ca3…7fd6082`, rules id `as-run table + R1-R3 (#551)`) in this order:
1. **Integrity:** archive checksums plus the manifest raw-file check. Both passed, with no problems.
2. **Authoritative run** on the archived **raw** evidence.
3. **Completeness check: a per-entry collector diff.** Every raw `events.jsonl` and `transcript.jsonl` entry in all eight arms is compared with exactly what the #549 collector publishes for it (the same selection functions and the same key-dropping redaction). Each entry is classed **whole**, **trimmed** (published with fields removed: `init` fields, `result` usage, thinking content, or any non-role/content field of user and assistant entries) or **dropped** (not published). A nonce occurrence is omitted when the raw entry holds more occurrences than its published form.
4. **Subset replay** on the published selected evidence. This is supporting only: it depends on step 3 and is **not** an independent reproduction.

The output is [`live-2026-10-17/<path>/outcome.r1r3.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/) (redacted, from the raw run) plus [`live-2026-10-17/reclassification.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/reclassification.json), all published alongside the unchanged as-run files.

### 7.3 Results

| Path | As-run (§2) | R1–R3, raw (authoritative) | R1–R3, subset replay | Notes |
|---|---|---|---|---|
| `H1a-edit` | INCONCLUSIVE | **DELIVERED_TO_AGENT** | DELIVERED_TO_AGENT | `hook_additional_context` counts as model_bound (R1), `hook_success` as host_output (R2), and the only event difference was `thinking_tokens` (R3) |
| `H1a-bash` | INCONCLUSIVE | **DELIVERED_TO_AGENT** | DELIVERED_TO_AGENT | same; the remaining `task_*` subtypes match |
| `H1b-start` | INCONCLUSIVE | **DELIVERED_TO_AGENT** | DELIVERED_TO_AGENT | R1 and R2; stream `hook_response` counts as host_output |
| `H1c-stop` | INCONCLUSIVE | **DELIVERED_WITH_SIDE_EFFECT** | DELIVERED_WITH_SIDE_EFFECT | reason `host-induced side-effect control failed`: 9 Stop invocations, `no_stop_reentry: false` |

**Completeness check: 0 omitted nonce occurrences in every arm.** Across the eight arms, the diff covered:
- **events:** 78 entries (24 whole, 54 trimmed, 0 dropped);
- **transcript:** 128 entries (0 whole, 70 trimmed, 58 dropped).

Per-arm counts are in `reclassification.json`. The raw and subset labels agree on all four paths.

**H1 gate under R1–R3 (raw, authoritative): NOT MET.** H1a (Edit and Bash) and H1b now pass under the accepted rules. **H1c fails** with a demonstrated host side effect, so H1 cannot pass with Stop `additionalContext`. The H1c path needs the separate architectural decision in §6.3 (a different Stop channel under a scope amendment and new probe, or a D5 revisit).

### 7.4 Not established by this addendum

- Developer (UI) visibility: still `not_observed`.
- Any other host version, model, interactive mode, or repeatability (n = 1).
- Anything about H2–H6, the freeze amendment, implementation, or the shipped `_emit_stop_feedback` behaviour (#550).

### 7.5 Revision after review (#553)

The first version of the completeness check listed the omitted categories by hand. It did not cover two kinds of omission:
- fields stripped from user and assistant entries;
- whole stream events of unselected types.

It was replaced by the per-entry collector diff in §7.2 step 3, with six synthetic regression tests (`harness/selftest/test_reclassify_completeness.py`) covering a stripped assistant field, a stripped user-message field, a dropped stream event, dropped transcript entries, thinking/`init`/`result` omissions, and published occurrences that must not count.

The reclassification was re-run from the same verified archive:
- **all four raw-run `outcome.r1r3.json` files are byte-identical to the first run**, so no classification changed;
- the archive re-verified;
- the as-run outcomes are unchanged.

`reclassification.json` now carries the per-entry counts and the revised tool hash.

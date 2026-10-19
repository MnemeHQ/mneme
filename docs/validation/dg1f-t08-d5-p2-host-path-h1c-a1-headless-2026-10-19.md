# DG1F T-08 D5 + P2: H1c Amendment A1, headless run (2026-10-19)

> This is the evidence record for the **A1-headless** run of the accepted
> [probe scope §4.2](../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md)
> (Amendment A1, #555), run with the accepted A1 harness from #556 (merge `626941df`).
>
> **Result as classified: `INCONCLUSIVE`.** The label is reported exactly as
> `classify_a1.py headless` produced it during the run. **Nothing is reclassified here.**
> The only reason is one nonce location that the category table does not recognise
> (§3). **No host-induced interference** was found (§2): one Stop invocation in each
> arm, no `stop_hook_active`, and a normal `result` in both.
>
> **The H1 gate stays NOT MET.** H1c under A1 also needs the interactive run (§4.2),
> which is separately gated and has not run.
>
> This record is evidence only. It changes no runtime behaviour or classifier rule.
> It amends no charter, freeze or ADR, and it authorizes no interactive run, re-run,
> H2–H6 probe or implementation.

## 1. Authorization, environment and provenance

| Item | Value |
|---|---|
| Authorization | Owner, 2026-10-19: the A1 headless live run only, with the accepted pinned host, the disposable workspace, the paired control and the existing #556 harness; no runtime changes. The interactive pair stays separately gated. |
| Operator | Ran `run_a1_headless.sh` from an external PowerShell window through Git Bash (`bash.exe -l`), not nested in Claude Code. The preflight reported `[preflight] OK` with 0 `MNEME_*` variables. |
| Host | **Claude Code `2.1.202`** on Windows; init model **`claude-opus-4-8[1m]`**, matching the pin (checked by the runner). Flags: `-p --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools Read --setting-sources project`. |
| Harness | `626941df56b436d4acd45f31c966952839f1fbca`, clean. Per-file SHA-256s are in `run_a1_headless.log` (published). |
| Run time | 2026-10-19, 09:01:55Z (control) and 09:02:04Z (emitter); `A1_HEADLESS_DONE` at 09:02:11Z. One run per arm, control first. Both `claude` processes exited 0. |
| Live root | `C:\dev\d5p2-h1c-a1-live`, created fresh by this run. The H1 live root `C:\dev\d5p2-h1-live` and the H1 archive `C:\dev\d5p2-h1-archive\2026-10-17` were **re-verified after the run**: all 97 files match `2026-10-17.SHA256SUMS` in both, and nothing in the H1 live root is newer than this task. |
| Collection | [`harness/collect_a1.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/collect_a1.py) was **added after the run**: it is not part of the hashed as-run harness. It reuses `collect_h1.py`'s selection, redaction and leak scan, unchanged, and adds one redaction (the H1 live root printed by the preflight becomes `<H1_LIVE>`). It **does not reclassify**: `outcome_a1_headless.json` is published as written, apart from path redaction. |
| Evidence | [`artifacts/dg1f-t08-d5-p2-h1-host-path/live-a1-headless-2026-10-19/`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a1-headless-2026-10-19/). The raw `events.jsonl`, `transcript.jsonl` and `claude.stderr.txt` stay in the live root, unchanged and unpublished (they carry the operator's environment listings and model thinking). `MANIFEST.json` records their SHA-256s and sizes. |

## 2. Non-interference (§4.2 headless criteria)

| §4.2 failure criterion | Emitter `H1c-sm` | Control `H1c-sm-ctl` | Interference? |
|---|---|---|---|
| Stop invocations exceed the control's | 1 | 1 | No |
| Any envelope with `stop_hook_active: true` | none (`false`) | none (`false`) | No |
| A permission decision differs for an equivalent request | no requests, no denials | no requests, no denials | No |
| The host blocks or retries | no | no | No |
| No normal `result` event | `result/success`, `end_turn`, `num_turns` 1 | `result/success`, `num_turns` 1 | No |
| The strict host-event and indicator rules flag a difference | none after R3 (see below) | | No |

`a1.host_interference` in the outcome is empty.

**Evidence only, with no host cause shown:**
- The emitter stream has two `system/thinking_tokens` events and two `assistant` events (one thinking, one text); the control has one `assistant` text event. Under R3, `thinking_tokens` is excluded from the subtype comparison, and the extra assistant event is model reasoning.
- Both replies were `OK` plus `NO-PROBE-TOKEN` (`echoed: false`). Stop fires after the reply, so no echo was expected in a one-turn session.

## 3. Where the nonce was recorded

The nonce `MNEME-PROBE-51055b6bd898f00a` appears **only** in the emitter's session transcript, in two `attachment` entries written after the reply. It appears in **no** stream-json event: no `system` event and no informational message carried it, so a headless stream consumer did not receive the notice.

| Transcript line (0-based, as in the outcome) | Entry | Location | Category |
|---|---|---|---|
| 9 | `attachment`, `type: hook_success`, `hookEvent: Stop` | `attachment.stdout` (the emitter's raw JSON) | `host_output` (R2) |
| 10 | `attachment`, `type: hook_system_message`, `hookEvent: Stop` | `attachment.content` (the notice text) | **unclassified** |

The as-run table has no entry for `hook_system_message`, so the rule "any unclassified nonce location → `INCONCLUSIVE`" decided the label. This entry type is new evidence: Claude Code 2.1.202 records a Stop hook's top-level `systemMessage` as a separate `hook_system_message` transcript attachment.

The control transcript has no `hook_*` attachment at all; its no-op hook printed nothing.

## 4. Known collision: did not occur

The #556 review flagged a risk: an emitter-only stream `system` event for the `systemMessage` would make the run `INCONCLUSIVE` under the unchanged strict rule. **That did not happen.** The emitter's stream had no `system` subtype beyond `init` and `thinking_tokens`, and both are handled by the existing rules.

## 5. What this run establishes and does not

**Establishes (headless, this host and pin, one run per arm):**
- Stop top-level `systemMessage` caused **no host continuation or re-entry**, unlike the original `additionalContext` shape (H1 batch: 9 Stop invocations, 8 with `stop_hook_active`).
- The headless host showed no permission, block, retry or result difference against its control.
- The host records the notice in the session transcript as `hook_system_message`, and it doesn't put it in the stream-json output.

**Does not establish:**
- **developer delivery.** Under §4.2 that comes only from the interactive capture;
- **whether `hook_system_message` reaches the model.** The model didn't echo the nonce, but the Stop hook fires after the only turn, so the absence of an echo says nothing about model-boundness. Its category has to be decided by a reviewed rule, not here;
- a passing H1c label, or the H1 gate.

## 6. Decisions for review (not taken here)

1. **A category rule for `hook_system_message`.** If reviewed and accepted (for example as `host_output`, or as developer-facing host output with model-boundness left to the interactive run), a classifier PR followed by an offline reclassification of this run's raw evidence would follow the R1–R3 precedent (#551 → #552 → #553). The as-run outcome here is never overwritten.
2. **The A1-interactive run**, which is separately gated: prep, recording, finish, capture review, then `classify_a1.py interactive` and `combine`. It is the only source of developer-delivery evidence.

Order and go-aheads are the owner's call. The raw evidence in `C:\dev\d5p2-h1c-a1-live` must be kept until any reclassification is recorded.

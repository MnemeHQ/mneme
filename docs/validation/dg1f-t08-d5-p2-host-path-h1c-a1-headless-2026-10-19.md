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

## 7. Addendum: offline reclassification under R1–R4 (2026-10-19)

> Sections 1–6 above are the as-run record and are **unchanged**. The as-run
> `outcome_a1_headless.json` is unchanged too, and the as-run label stays
> `INCONCLUSIVE` as historical fact. This addendum records a separately authorized
> **offline** reclassification under rules R1–R4 (R4 accepted in #561 and implemented
> in #562, merge `1d9148f4`). No host session ran, and nothing was re-run. Decision 1
> in §6 was answered by #561. Decision 2 (the A1-interactive run) is unaffected and
> remains separately gated.

### 7.1 Archive and integrity

- **Archive.** `C:\dev\d5p2-h1c-a1-live` was copied to `C:\dev\d5p2-h1c-a1-archive\2026-10-19` before any tool read it for this step. The copy is byte-identical: 25 files with identical SHA-256 listings. The listing is stored beside it as `2026-10-19.SHA256SUMS` (SHA-256 `ac05749a…6c870bf0`).
- **Manifest check.** All **9** raw files that this record's `MANIFEST.json` hashes were checked, and all match its SHA-256s and sizes. They are `events.jsonl`, `transcript.jsonl` and `claude.stderr.txt` for both arms, plus the batch files `outcome_a1_headless.json`, `run_a1_headless.log` and `A1_HEADLESS_DONE`.
- **The tool stops before classifying.** A copy of the checksum list with one hash altered made it abort ("integrity check failed; nothing classified") without writing any output.
- **Protection.** The archive files are read-only. As with the H1 archive (§7.1 of the H1 record), Windows still allows new files in the folders. A test file created while checking writability was removed. The tool rejects any archive file missing from the checksum list, and after the reclassification the archive held exactly the 25 listed files and verified again.
- **The original `C:\dev\d5p2-h1c-a1-live` is untouched.** It also verified against the same listing after the run.

### 7.2 Procedure

[`harness/reclassify_a1.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/reclassify_a1.py) (SHA-256 `9b26e01b…785d92c2`) reuses the #553 tool's integrity, completeness and subset-replay helpers unchanged (`reclassify_h1.py`, `1dbbfdd4…def0f89b`), with the #560 collector's selection (`collect_h1.py`, `64445c3c…9570b25c`). It ran the merged classifiers from `1d9148f4`: `classify_a1.py` `3f407814…795ef58b` and `classify_h1.py` `ba908114…c9760568`, with rules id `as-run table + R1-R4 (#551, #561)`. The order was:
1. **Integrity:** archive checksums, no unlisted files, and the manifest raw-file check. All passed with no problems.
2. **Authoritative run:** `classify_a1.headless()` on the archived **raw** evidence.
3. **Completeness check:** a per-entry collector diff of every raw `events.jsonl` and `transcript.jsonl` entry in both arms (whole, trimmed or dropped; an omitted occurrence is a raw entry holding more nonce occurrences than its published form), plus a nonce scan of each arm's `claude.stderr.txt`.
4. **Subset replay** of the same `headless()` on the published selected evidence. This is supporting only: it depends on step 3 and is **not** an independent reproduction.

The output is [`outcome_a1_headless.r1r4.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a1-headless-2026-10-19/outcome_a1_headless.r1r4.json) (redacted, from the raw run) and [`reclassification.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a1-headless-2026-10-19/reclassification.json), both published alongside the unchanged as-run files. The collector's redaction and leak scan applied to both.

### 7.3 Results

| Run | As-run (§2–§3) | R1–R4, raw (authoritative) | R1–R4, subset replay |
|---|---|---|---|
| A1-headless (`H1c-sm` vs `H1c-sm-ctl`) | INCONCLUSIVE | **NOT_DELIVERED** | NOT_DELIVERED |

- **Nonce locations under R1–R4:** `hook_success` `attachment.stdout` → `host_output` (R2), and `hook_system_message` `attachment.content` → `host_output` (R4). No location is unclassified, and none is model-bound.
- **The change from the as-run outcome is exactly what R4 accounts for.** That location's category goes from `unclassified` to `host_output`; the label goes from `INCONCLUSIVE` to `NOT_DELIVERED`; the reason list is now empty; and `side_effect_observed: false` is added. Every other field is identical, apart from `rules`.
- **Host interference:** none, unchanged (`a1.host_interference` is empty in both).
- **Completeness: 0 omitted nonce occurrences.** The diff covered events: 9 entries (2 whole, 7 trimmed, 0 dropped), and transcript: 21 entries (0 whole, 7 trimmed, 14 dropped). Both `claude.stderr.txt` files are empty (0 bytes, 0 occurrences).
- The raw run and the subset replay agree.

**What `NOT_DELIVERED` means here:** the headless evidence does not establish delivery to either accepted audience. Headless delivery to the developer cannot be observed by design (§4.2), and R4 never counts as delivery. It does **not** mean the A1-interactive run must fail. Under `combine`, a headless `NOT_DELIVERED` with no interference blocks nothing: H1c under A1 passes only if the interactive run passes.

**H1 gate: still NOT MET.** H1c under A1 also needs the A1-interactive run, which has not run and is not authorized.

### 7.4 Not established by this addendum

- **Developer (UI) visibility**, which comes only from the A1-interactive capture.
- **Whether the host ever feeds `hook_system_message` to the model** on a later turn (#561 §3 limit, option C).
- **Independent inspection of the raw files.** The review of #560 inspected the published evidence and the manifest hashes, not the unpublished raw contents. This addendum's integrity and completeness results come from the operator-side tool run. The reviewer can check them only through the published hashes, the tool source and the subset replay.
- Any other host version, model or mode, and repeatability (n = 1).
- Anything about H2–H6, the freeze amendment, implementation, or the shipped `_emit_stop_feedback` behaviour (#550).

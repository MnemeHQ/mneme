# DG1F T-08 D5 + P2: Amendment A3, H1c (Stop `systemMessage`) on Claude Code 2.1.310 (2026-11-16)

> This is the evidence record for the live runs defined by
> [probe scope §4.4](../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md)
> (Amendment A3, accepted with its harness in #802, merge `0670b17a`), run with the
> finished-batch guard of #803 (merge `c9480c11`).
>
> **Results as classified during the run:**
> - **Interactive: `DELIVERED_TO_USER_ONLY`**, a passing label under D5 §5.1 (developer **or** agent).
> - **Headless: `INCONCLUSIVE`.**
> - **Combined H1c under A1: `INCONCLUSIVE`**, on one host version (`2.1.310 (Claude Code)`).
>
> The labels are reported exactly as `classify_a1.py` produced them. **Nothing is reclassified here.**
>
> **The only reason the headless run is `INCONCLUSIVE`** is the collision A1 (§4.2) and A3 (§4.4) both predicted: on 2.1.310, the Stop `systemMessage` is also surfaced as a stream-json `system` event with subtype `informational`, in the emitter arm only. The unchanged strict host-event rule counts that as an unexplained difference between the arms (§4).
>
> **No host interference was observed in either run**, and **the notice never reached the model** (§3, §4).
>
> **H1 gate: still NOT MET.** H1c has no passing combined label until a reviewed rule covers the stream event, the archived headless pair is reclassified, and a separate gate record combines H1c with A2's three paths (#800).

## 1. Authorization, environment and provenance

**Authorization.**
- The owner authorized the run on 2026-11-13 ("Start the A3 live H1c run"), after #802 and #803 merged.
- The evidence PR was authorized on 2026-11-16 ("Draft evidence PR").

**Host and model.** Claude Code `2.1.310 (Claude Code)`, with `--model claude-opus-5-5` on every session, on Windows. `DISABLE_AUTOUPDATER=1` was set in the operator's PowerShell window.
- **Version checks:** the version was checked before every headless session, when each interactive arm was prepared, again in the operator's window before each session, and again when each arm was finished. Every check gave `2.1.310`.
- **Model:** every init event and every transcript assistant message reports `claude-opus-5-5`.
- **The "Updated to latest" banner:** the interactive control's banner shows the post-update notice of an *earlier* update. Its session header, like the emitter's, shows `v2.1.310`.

**Harness.** At `c9480c11`, with no uncommitted changes, and `pins.local.env` sets `PY` only. The as-run harness hashes are in `run_a1_headless.log`.

**Disposable root.** `C:\dev\d5p2-h1c-a3-live`. It was empty before the run, and the A3 preflight was OK.

| Run | Arm | Time (UTC) |
|---|---|---|
| Headless | `H1c-sm-ctl`, then `H1c-sm` | 18:48:18 and 18:48:26; both exited 0 |
| Interactive | `H1c-sm-int-ctl` | prepared 18:51:04, session 18:53 (local 13:53), finished 18:59:44 |
| Interactive | `H1c-sm-int` | prepared 18:55:31, session 18:55 (local 13:55), finished 19:02:04 |

**Recorded deviations and handling, for the reviewer:**
1. **Screenshots instead of a screen recording (owner decision, 2026-11-16).**
   - §4.2 asks for a recording from launch until the session has been idle at the prompt for at least 30 seconds. The owner decided that "a screenshot is enough".
   - Each interactive arm's capture is therefore the operator's own screenshot of the session window, and its SHA-256 is the arm's `recording_sha256`: control `9f88e1c2…`, emitter `63278d67…`.
   - The idle time is shown by the reply's "done" time against the taskbar clock in the screenshot: 1:53 PM against 13:54 for the control, and 1:55 PM against 13:58 for the emitter.
2. **The interactive prep instructions did not print in the operator's window.** The cause is unknown.
   - Preparation itself completed in full: workspace, nonce, hook registration, observer and template.
   - The operator steps were given in the chat instead, with the same content.
3. **`observation.json` and `capture_review.json` were written to file by the agent.**
   - The observations were transcribed from the operator's screenshots.
   - The capture reviews record the **owner's own confirmation in the chat**: no token in either control screenshot, and `MNEME-PROBE-ac6914cfa1176045` in the emitter's `Stop says:` line. **The named reviewer is Theo Valmis.**
   - The reviewer is not the classifier. The agent wrote the files and ran the classifier, but did not decide what the captures show.
4. **The arms were finished by the agent** (`finish_a1_interactive.sh A3`) after the operator had closed each session with `/exit`. Each transcript shows exactly one prompt, then `/exit`.
5. **A stray `S` is visible in the input box** in all three screenshots. It was never sent: each transcript holds one prompt.

## 2. Results (as classified during the run)

| Run | Label | Classifier facts |
|---|---|---|
| Headless (`H1c-sm` vs `H1c-sm-ctl`) | `INCONCLUSIVE` | reason: `unexplained host-event difference between arms (emitter ['informational'], control [])`; `host_interference: []` |
| Interactive (`H1c-sm-int` vs `H1c-sm-int-ctl`) | **`DELIVERED_TO_USER_ONLY`** | `capture_review: confirmed`, Stop invocations 1 and 1, no reasons |
| **Combined H1c (A1)** | **`INCONCLUSIVE`** | `headless run is INCONCLUSIVE`; `host_version: 2.1.310 (Claude Code)`; `h1c_passes_under_a1: false` |

## 3. Non-interference

**Headless.** Both arms:
- reached a normal `result` (`success`, one turn);
- had one Stop invocation each, with `stop_hook_active: false`, so there was no re-entry;
- had equal permission decisions and host indicators, and no error result;
- left the workspace (`notes.txt`) unchanged.

**Interactive.** Both arms:
- had one Stop invocation each, with no re-entry;
- returned to the input prompt and stayed idle there for at least 30 seconds (§1);
- showed no unexpected prompt.

**Evidence only, as §3 step 4 says:**
- the replies: headless control `OK\nNO-PROBE-TOKEN`, headless emitter `OK NO-PROBE-TOKEN`, and `OK` / `NO-PROBE-TOKEN` in both interactive arms;
- the headless emitter's one additional assistant event, which is model activity.

## 4. Where the nonce was recorded

Every raw entry of all four arms was checked for both nonces. Only these hold one, and every one of them is published:

| Arm | Location | Category |
|---|---|---|
| `H1c-sm` (headless emitter) | stream `system` / `informational`, `content` = `Stop says: <systemMessage>`, `level: notice` | `host_output` (A1 table: a stream informational or system event is host output, never delivery) |
| `H1c-sm` | transcript `attachment` `hook_success`, `stdout` | `host_output` (R2) |
| `H1c-sm` | transcript `attachment` `hook_system_message`, `content` | `host_output` (R4) |
| `H1c-sm-int` (interactive emitter) | transcript `hook_success` `stdout`, and `hook_system_message` `content` | `host_output` (R2, R4) |
| `H1c-sm-int` | the host UI (screenshot): `Stop says: MNEME-PROBE-ac6914cfa1176045 This is a Mneme H1 channel-probe notice. …` under the reply | developer delivery (capture review) |
| controls | none | — |

- **No model-bound location.**
  - The nonce is in no user, assistant or tool content.
  - It is in no `api-request-blob`: neither emitter arm has a blob containing it. On 2.1.310 those blobs record what was sent to the model (#795), so the Stop `systemMessage` was not part of the model request.
  - The model did not echo it in any arm.
- **Why the headless run is `INCONCLUSIVE`.**
  - The informational event is categorised (`host_output`), but the strict host-event subtype rule (unchanged) independently flags any event subtype present in one arm only.
  - It is fully attributable to the probed hook:
    - its text is exactly `Stop says: ` followed by the `systemMessage` the emitter's single Stop invocation logged;
    - it appears only in the emitter arm;
    - it appears after the assistant reply and before `result`.
  - **Classifying it needs a reviewed rule** (the #551 → #552 → #553 and R4/R5 precedent). It is **not** decided here.

## 5. Other host differences observed (evidence only)

- **The interactive transcripts** hold local-command records for `/exit` (a caveat, the command, and its output, `See ya!` or `Bye!`), plus 2.1.310 entry types that are not published (MANIFEST.json counts them).
- **No `api-request-blob` was excerpted in any arm**, because none contains a nonce.

## 6. What this run establishes, and what it does not

**It establishes**, on Claude Code `2.1.310` with `claude-opus-5-5`, n = 1 per run:
- **The developer sees the notice:** a Stop command hook's top-level `systemMessage` is shown to the developer in an interactive session (`Stop says: …`, under the reply) and is absent from the paired control (capture-reviewed).
- **The agent does not:** the notice does not reach the model in either mode.
- **No host interference in either mode:** no forced continuation or re-entry, which the original `additionalContext` shape caused (#549), no blocked or retried turn, and a normal end.

**It does not establish:**
- **A passing combined H1c label.** That needs the stream-event rule and an offline reclassification of the archived headless pair.
- **The H1 gate.** That needs a separate gate record over H1a, H1b (A2, #800) and H1c on one host version.
- **Repeatability** (n = 1), other host versions, models or terminals.
- **Anything about Mneme's own Stop output.** `_emit_stop_feedback` (#550) is unchanged.

## 7. Artifacts

- **Harness:** `harness/collect_a3.py` (new; added after the run, so it is not in the as-run hashes). It reuses `collect_h1.py` (redaction and leak scan) and `collect_a2.py` (`select_transcript_a2`) unchanged.
- **Published evidence:** [`live-a3-2026-11-16/`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a3-2026-11-16/), 42 redacted text files and 6 frame crops:
  - per arm: the observer, prompt, probe, hook registration, hook log, nonce, and the selected events and transcript;
  - for the interactive arms: the observation, capture review and template;
  - the three outcomes as classified, the run log, and `MANIFEST.json`.
- **Frames.** Each screenshot is published as two PNG crops, the terminal and the taskbar clock. The operator's user folder is masked in both control terminal crops. MANIFEST.json records each original frame's SHA-256 (the one the capture review is bound to), the crop and mask boxes, and each crop's SHA-256. The originals are not published, because they show the operator's desktop.
- **Not published:** the raw `events.jsonl`, `transcript.jsonl` and `claude.stderr.txt`, and the captures. MANIFEST.json records their SHA-256 and size.
- **Leak scans:** the collector's leak scan passed, and so did a second sweep (paths, emails, tool IDs, UUIDs, encoded project folders) with 0 findings.
- **Archive.** `C:\dev\d5p2-h1c-a3-archive\2026-11-16`: 56 files (the live root plus the two captures under `_captures/`), read-only, with listing `2026-11-16.SHA256SUMS` (SHA-256 `17c73d1a…249f74f`). The live root verified against it after collection. Keep the live root, `C:\dev\d5p2-h1c-a3-captures` and the archive.

**Next steps, each needing its own go-ahead:**
1. A rule review for the stream `system:informational` event attributable to the probed hook.
2. Its implementation, then an offline reclassification of the archived headless pair and a new combine.
3. The H1 gate record.

# DG1F T-08 D5 + P2: Amendment A3, H1c (Stop `systemMessage`) on Claude Code 2.1.310 (2026-11-16)

> This is the evidence record for the live runs defined by
> [probe scope §4.4](../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md)
> (Amendment A3, accepted with its harness in #802, merge `0670b17a`), run with the
> finished-batch guard of #803 (merge `c9480c11`).
>
> **Results as classified during the run:**
> - **Interactive: `DELIVERED_TO_USER_ONLY`** as run, which is a passing label under D5 §5.1 (developer **or** agent). **It is not an accepted, protocol-compliant pass.** The capture was screenshots, not the continuous recording §4.2 requires, and that substitution needs a reviewed evidence decision (§2.1).
> - **Headless: `INCONCLUSIVE`.**
> - **Combined H1c under A1: `INCONCLUSIVE`**, on one host version (`2.1.310 (Claude Code)`).
>
> The labels are reported exactly as `classify_a1.py` produced them. **Nothing is reclassified here.**
>
> **The only reason the headless run is `INCONCLUSIVE`** is the collision A1 (§4.2) and A3 (§4.4) both predicted: on 2.1.310, the Stop `systemMessage` is also surfaced as a stream-json `system` event with subtype `informational`, in the emitter arm only. The unchanged strict host-event rule counts that as an unexplained difference between the arms (§4).
>
> **No host interference was observed in either run** (§3). **No model-bound nonce location was observed, and the model did not echo the nonce**, so agent delivery was not established (§4).
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
1. **Screenshots instead of a screen recording (owner decision, 2026-11-16).** §4.2 asks for a recording from launch until the session has been idle at the prompt for at least 30 seconds. The owner decided that "a screenshot is enough". Each interactive arm's capture is therefore the operator's own screenshot of the session window, and its SHA-256 is the arm's `recording_sha256`: control `9f88e1c2…`, emitter `63278d67…`. §2.1 sets out what this does and does not support.
2. **The interactive prep instructions did not print in the operator's window.** The cause is unknown.
   - Preparation itself completed in full: workspace, nonce, hook registration, observer and template.
   - The operator steps were given in the chat instead, with the same content.
3. **`observation.json` and `capture_review.json` were written to file by the agent.**
   - The observations were transcribed from the operator's screenshots.
   - The capture reviews record the **owner's own confirmation in the chat**: no token in either control screenshot, and `MNEME-PROBE-ac6914cfa1176045` in the emitter's `Stop says:` line. **The named reviewer is Theo Valmis.**
   - The reviewer is not the classifier. The agent wrote the files and ran the classifier, but did not decide what the captures show.
4. **The arms were finished by the agent** (`finish_a1_interactive.sh A3`) after the operator had closed each session with `/exit`. Each transcript shows exactly one prompt, then `/exit`.
5. **A stray `S` is visible in the input box** in all three screenshots. It was never sent: each transcript holds one prompt.
6. **The screenshot crops are not published (owner decision, 2026-11-16, review of #804).**
   - The pinned ADR-033 C4 trusted gate evaluates every changed regular file and cannot evaluate binary files. The first version of this PR committed six PNG crops, and the gate returned `UNEVALUATED`, which fails under the `closed` posture.
   - The owner chose to keep the crops local rather than change the accepted gate policy.
   - §4.2 asks for redacted still frames to be published, so this is a deviation, recorded with deviation 1.
   - The crops are byte-identical to those in the first version. §7 says what each shows, and MANIFEST.json binds each by SHA-256.

## 2. Results (as classified during the run)

| Run | Label | Classifier facts |
|---|---|---|
| Headless (`H1c-sm` vs `H1c-sm-ctl`) | `INCONCLUSIVE` | reason: `unexplained host-event difference between arms (emitter ['informational'], control [])`; `host_interference: []` |
| Interactive (`H1c-sm-int` vs `H1c-sm-int-ctl`) | **`DELIVERED_TO_USER_ONLY`** | `capture_review: confirmed`, Stop invocations 1 and 1, no reasons |
| **Combined H1c (A1)** | **`INCONCLUSIVE`** | `headless run is INCONCLUSIVE`; `host_version: 2.1.310 (Claude Code)`; `h1c_passes_under_a1: false` |

The as-run outcome files are published unchanged.

### 2.1 Status of the interactive label: as run, not yet accepted (review of #804)

`DELIVERED_TO_USER_ONLY` is what `classify_a1.py` produced. The classifier checks:
- the capture hashes;
- that the listed frames exist;
- the reviewer's declarations.

It does **not** check that the capture was a continuous recording.

**What the screenshots support:**
- the notice `Stop says: MNEME-PROBE-ac6914cfa1176045 …` is visible to the developer in the emitter session;
- no `MNEME-PROBE-` token appears in the control's two screenshots;
- each session is back at its input prompt when the screenshot was taken.

**What they do not support** is the continuous observation a recording gives: everything that happened on screen between launch and the idle period.

**The reviewer's point about the clock times is correct.** The control's reply ("done 1:53 PM") and its later screenshot (taskbar 13:54) do not by themselves show 30 seconds; the two could be seconds apart across a minute boundary. The emitter's (1:55 PM against 13:58) do.

**Host-recorded idle time.** The session transcripts, not the screenshots, show how long each session stayed open after the reply:

| Arm | Last assistant message | Stop hook | `/exit` | Reply → `/exit` |
|---|---|---|---|---|
| control | 18:53:12.7Z | 18:53:13.0Z | 18:55:18.1Z | 125 s |
| emitter | 18:55:50.5Z | 18:55:50.7Z | 19:01:51.7Z | 361 s |

Between the reply and `/exit`, each transcript holds only host bookkeeping entries (and, in the emitter, the Stop hook's `hook_success` and `hook_system_message`). It holds no user input. This shows each session stayed open and idle for well over 30 seconds. It is a host record, not an observation of the screen.

**Disposition requested:** a reviewed evidence decision on whether the screenshots, together with the host-recorded idle time and the capture review, satisfy §4.2 for this run. Until that decision:
- the interactive label stands as an as-run classifier output;
- it is not claimed as an independently accepted, protocol-compliant pass;
- H1c is `INCONCLUSIVE` in any case (§2).

## 3. Non-interference

**Headless.** Both arms:
- reached a normal `result` (`success`, one turn);
- had one Stop invocation each, with `stop_hook_active: false`, so there was no re-entry;
- had equal permission decisions and host indicators, and no error result;
- left the workspace (`notes.txt`) unchanged.

**Interactive.** Both arms:
- had one Stop invocation each, with no re-entry;
- were back at the input prompt in the screenshots, and stayed open with no user input for over 30 seconds before `/exit` (125 s and 361 s, from the transcripts; §2.1);
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

- **No model-bound nonce location was observed, and the model did not echo the nonce, so agent delivery was not established.**
  - The nonce is in no user, assistant or tool content of any arm.
  - No `api-request-blob` contains it. This is recorded as an observation only. Under the accepted R5 semantics these blobs are not shown to be complete records of what reached the model, so their silence is **not** proof that the notice never reached it (review of #804).
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

**It provides evidence**, on Claude Code `2.1.310` with `claude-opus-5-5`, n = 1 per run, that:
- **The developer sees the notice.** A Stop command hook's top-level `systemMessage` is shown to the developer in an interactive session (`Stop says: …`, under the reply) and is absent from the paired control. This is capture-reviewed from screenshots, subject to the disposition in §2.1.
- **Agent delivery was not established.** No model-bound nonce location was observed in either mode, and the model never echoed the nonce (§4).
- **No host interference in either mode.** There was no forced continuation or re-entry (the original `additionalContext` shape caused one, #549), no blocked or retried turn, and a normal end.

**It does not establish:**
- **An accepted, protocol-compliant pass for the interactive run.** The screenshot substitution needs a reviewed evidence decision (§2.1).
- **That the notice could never reach the model.** Absence was observed, not proven (§4).
- **A passing combined H1c label.** That needs the stream-event rule and an offline reclassification of the archived headless pair.
- **The H1 gate.** That needs a separate gate record over H1a, H1b (A2, #800) and H1c on one host version.
- **Repeatability** (n = 1), other host versions, models or terminals.
- **Anything about Mneme's own Stop output.** `_emit_stop_feedback` (#550) is unchanged.

## 7. Artifacts

- **Harness:** `harness/collect_a3.py` (new; added after the run, so it is not in the as-run hashes). It reuses `collect_h1.py` (redaction and leak scan) and `collect_a2.py` (`select_transcript_a2`) unchanged.
- **Published evidence:** [`live-a3-2026-11-16/`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a3-2026-11-16/), 42 redacted text files and no binary files:
  - per arm: the observer, prompt, probe, hook registration, hook log, nonce, and the selected events and transcript;
  - for the interactive arms: the observation, capture review and template;
  - the three outcomes as classified, the run log, and `MANIFEST.json`.
- **Frames: not published (deviation 6).**
  - Each screenshot is cropped to the terminal and to the taskbar clock. The operator's user folder is masked in both control terminal crops.
  - The crops are kept locally in `C:\dev\d5p2-h1c-a3-captures\crops-2026-11-16`. The collector refuses a crops folder inside the repository.
  - MANIFEST.json records each original frame's SHA-256 (the one the capture review is bound to), the crop and mask boxes, and each local crop's SHA-256 (`published: false`).
  - What the crops show:
    - control `f1`/`f2`: the launch command with `--model claude-opus-5-5`, the session header `Claude Code v2.1.310 · Opus 5.5`, the prompt, the reply `OK` / `NO-PROBE-TOKEN`, no notice, and the input prompt; clock 13:53 and 13:54;
    - emitter `f1`: the same, plus the `Stop says: MNEME-PROBE-ac6914cfa1176045 This is a Mneme H1 channel-probe notice. It carries no instruction and requires no action.` line under the reply; clock 13:58.
- **Operator-attested, not independently verifiable from GitHub:**
  - the raw-archive integrity checks;
  - the completeness check that every nonce-bearing raw entry is published;
  - the screenshots and crops themselves, including the visual check that the masks cover the user folder.

  A reviewer can verify the published text artifacts, the manifests and the collector source, but cannot inspect the original screenshots.
- **Not published:** the raw `events.jsonl`, `transcript.jsonl` and `claude.stderr.txt`, and the captures. MANIFEST.json records their SHA-256 and size.
- **Leak scans:** the collector's leak scan passed, and so did a second sweep (paths, emails, tool IDs, UUIDs, encoded project folders) with 0 findings.
- **Archive.** `C:\dev\d5p2-h1c-a3-archive\2026-11-16`: 56 files (the live root plus the two captures under `_captures/`), read-only, with listing `2026-11-16.SHA256SUMS` (SHA-256 `17c73d1a…249f74f`). The live root verified against it after collection. Keep the live root, `C:\dev\d5p2-h1c-a3-captures` and the archive.

**Next steps, each needing its own go-ahead:**
1. A rule review for the stream `system:informational` event attributable to the probed hook.
2. Its implementation, then an offline reclassification of the archived headless pair and a new combine.
3. The H1 gate record.

## 8. Addendum: offline reclassification of the headless pair under R1–R6 (2026-11-16)

> §1–§7 above are the as-run record and are **unchanged**, as are the as-run `outcome_a1_headless.json`, `outcome_a1_interactive.json` and `outcome_a1.json`. This addendum records the separately authorized **offline** reclassification under rule R6 (accepted in #805, `ca02b3f2`; implemented in #806, `457ab70c`). **No host session ran, and nothing was re-run.**

### 8.1 Procedure

[`harness/reclassify_a3.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/reclassify_a3.py) (SHA-256 `e1fcd7d9…eea01506e4`) reuses the #800 integrity, completeness and fail-closed publication helpers (`reclassify_a2.py`) unchanged:

1. **Integrity.** The archive `C:\dev\d5p2-h1c-a3-archive\2026-11-16` verified against `2026-11-16.SHA256SUMS` (`17c73d1a…`): 56 files, none unlisted, and every raw and batch file recorded in MANIFEST.json matched. It verified again after classification, again immediately before publication, and again after the run.
2. **Authoritative run.** `classify_a1.headless()` (rules `as-run table + R1-R6 (#551, #561, #796, #805)`) ran on the archived **raw** headless pair with the A3 pins. Each arm was keyed to its recorded live-root location, so workspace masking matches the as-run classification.
3. **Combine.** `classify_a1.combine()` paired that outcome with the **unchanged** as-run interactive outcome. R6 does not touch the interactive classifier.
4. **Omitted-material completeness check.** For both headless arms, every raw event, transcript entry and stderr line was compared with what `collect_a3.py` publishes, for each arm's own nonce and the emitter's. **0 omitted occurrences.**
5. **Subset replay** of the published headless subset. This is supporting only.

**Outputs.** These are published beside the unchanged as-run files:
- [`outcome_a1_headless.r1r6.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a3-2026-11-16/outcome_a1_headless.r1r6.json)
- [`outcome_a1.r1r6.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a3-2026-11-16/outcome_a1.r1r6.json)
- [`reclassification.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a3-2026-11-16/reclassification.json)

All three are redacted and leak-scanned, with 0 findings.

### 8.2 Results

| Run | As run (§2) | R1–R6, raw (authoritative) | R1–R6, subset replay |
|---|---|---|---|
| Headless | `INCONCLUSIVE` | **`NOT_DELIVERED`** | `INCONCLUSIVE` (see below) |
| Interactive | `DELIVERED_TO_USER_ONLY` | unchanged, not reclassified | – |
| **Combined H1c** | `INCONCLUSIVE` | **`DELIVERED_TO_USER_ONLY`** as classified (`h1c_passes_under_a1: true`, one host version `2.1.310`) | – |

- **What R6 excluded.** Exactly the emitter's `system:informational` echo (event index 3; `host_events.r6_excluded`) was left out of the subtype comparison. The indicator scan still covered it and found nothing.
- **What changed against the as-run headless outcome:**
  - `label` and `reasons` (now empty);
  - `rules` and `a1.rules`;
  - `host_events`, where the emitter subtypes are now empty and `r6_excluded` is added;
  - `side_effect_observed`, which was `null` as run, because classification stopped at the INCONCLUSIVE reason, and is now `false`, because the controls hold.

  The set of nonce locations is unchanged.
- **Why the subset replay differs, which is reported and not reconciled.**
  - The published echo has five fields, because the collector's redaction drops `uuid`. R6's S1 requires the exact six-field shape, so R6 correctly does not fire on the published subset.
  - A subset replay therefore cannot reproduce this exclusion by design; only the raw run can. That is why the raw run is authoritative.
  - The subset's sole reason is the as-run one (the one-sided `informational` subtype).

### 8.3 Status

**Owner decision, 2026-11-16:** the screenshot captures, host-recorded idle intervals and capture review are accepted as sufficient evidence for this specific A3 interactive run, despite the deviation from the continuous-recording requirement. This resolves the disposition requested in §2.1. The historical outcomes are unchanged.

- **The combined H1c label `DELIVERED_TO_USER_ONLY` is as classified.** It counts as an accepted H1c pass only if the separate **screenshot evidence decision** (§2.1) accepts the interactive capture.
- **H1 gate: still NOT MET** until that decision and a separate H1 gate record. With A2 under R1–R5 (#800), all four H1 paths would then be on one host version, `2.1.310`.
- **Not established here:** the screenshot decision, the H1 gate, repeatability (n = 1), or any other host version.
- **Operator-attested:** the archive checks and the completeness check. The published outcomes, the tool source and the subset replay are reviewable from GitHub.

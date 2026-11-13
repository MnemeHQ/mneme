# DG1F T-08 D5 + P2: Amendment A2, H1a and H1b on Claude Code 2.1.310 (2026-11-11)

> This is the evidence record for the live run defined by
> [probe scope §4.3](../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md)
> (Amendment A2, accepted with its harness in #794, merge `4c1c270e`).
>
> **Result as classified: `INCONCLUSIVE` on all three paths**, so the listed-path result
> is `NOT MET`. The labels are reported exactly as `classify_h1.py` produced them during
> the run. **Nothing is reclassified here.**
>
> The **only** reason, on every path, is that Claude Code 2.1.310 records the hook context
> in two transcript locations the category table does not recognise (§4). **No
> host-induced interference** was found (§3). The R1 model-bound location is present on
> every path, and the model echoed the nonce on every path.
>
> A2 does not cover H1c, so this batch is **not** the H1 gate, and H1 stays **NOT MET**.
>
> This record is evidence only. It changes no runtime behaviour or classifier rule. It
> amends no charter, freeze or ADR. It authorizes no reclassification, re-run, H1c/A1
> re-pin, H2–H6 probe, P2-first charter or implementation.

## 1. Authorization, environment and provenance

| Item | Value |
|---|---|
| Authorization | Owner, 2026-11-11: the A2 live run ("Authorize A2 run"), with the harness merged in #794. Then this as-run evidence PR, separately ("Open evidence PR"). |
| Operator | Ran `run_h1.sh A2` from an external PowerShell window through Git Bash (`bash.exe -l`), not nested in Claude Code, after clearing `MNEME_*`, `CLAUDECODE`, `H1_PINSET`, `H1_SELFTEST` and `H1_LIVE` and setting `DISABLE_AUTOUPDATER=1`. `claude --version` printed `2.1.310 (Claude Code)` immediately before the run. |
| Preflight | `[preflight] OK`: pin set A2, `DISABLE_AUTOUPDATER=1`, claude `2.1.310 (Claude Code)`, 0 `MNEME_*` variables, live root `<LIVE>`, model pin passed as `--model`. |
| Host | **Claude Code `2.1.310`** on Windows 11, headless. Every one of the six init events reports model **`claude-opus-5-5`**, `claude_code_version` `2.1.310` and `permissionMode` `acceptEdits`. The version was re-checked before every session, and every observer records `claude_version=2.1.310 (Claude Code)`, `pinset=A2`, `model_flag=claude-opus-5-5` and `disable_autoupdater=1`. Flags: `-p --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools <per path> --setting-sources project --model claude-opus-5-5`. |
| Harness | `4c1c270e6e7b0c1c27f3d124ed2f71c8a5fd681c` (merged #794), clean. Per-file SHA-256s are in `run_h1.log` (published). |
| Run time | 2026-11-11, from 17:41:31Z (first control) to 17:42:39Z (last emitter); `H1_DONE` at 17:42:45Z. One run per arm, control before emitter; every `claude` process exited 0. |
| Raw evidence | Live root `C:\dev\d5p2-h1-a2-live`, created fresh by this run. Archived before collection to `C:\dev\d5p2-h1-a2-archive\2026-11-11`: 74 files, byte-identical, read-only. Its `2026-11-11.SHA256SUMS` has SHA-256 `bbd4c5e51b393cc425a7ce24a80cc7ae72b8547e7091f17270cc4db521089e34`. Keep both. |
| Earlier evidence | **Re-verified after the run:** the H1 live root `C:\dev\d5p2-h1-live` matches `2026-10-17.SHA256SUMS`, and nothing in it is newer than this run. The H1 archive (2026-10-17) and the A1 archive (2026-10-19) also verify against their sums. |
| Collection | [`harness/collect_a2.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/collect_a2.py) was **added after the run**; it is not part of the hashed as-run harness. It reuses `collect_h1.py`'s selection, redaction and leak scan, unchanged, with three A2 additions:<br>1. `rendered` and `renderedRole` are published on `hook_*` attachments only. On other attachment types they can carry environment details.<br>2. A minimal excerpt is published of each `api-request-blob` that contains the arm's nonce: type, hash, role, item and line counts, and **only** the nonce line.<br>3. Claude Code's encoded project directory for the live root becomes `<LIVE_PROJECT>`.<br>It **does not reclassify**: each `outcome.json` is published as written, apart from path redaction. |
| Leak checks | The collector's built-in scan passed. An independent sweep, written as a script with a self-check, covered:<br>- the home, live root, archive, checkout and scratchpad paths, each in literal, JSON-escaped, forward-slash, MSYS and URL-encoded forms;<br>- encoded project ids, the host and user names, e-mail addresses and token shapes.<br>It found **0 hits in 55 files**. |

## 2. Results (as classified during the run)

| Path | Label | Emitter / control invocations | Turns (emitter / control) | R1 model-bound location | Echoed | Unclassified locations |
|---|---|---|---|---|---|---|
| H1a-edit (PreToolUse, Edit) | **INCONCLUSIVE** | 1 / 1 | 3 / 3 | yes | yes | 2 |
| H1a-bash (PreToolUse, Bash) | **INCONCLUSIVE** | 1 / 1 | 2 / 2 | yes | yes | 2 |
| H1b-start (SessionStart) | **INCONCLUSIVE** | 1 / 1 | 1 / 1 | yes | yes | 2 |

Every outcome gives the same single reason: *"nonce found in locations the category table does not recognise; review needed"*. The summary line is: `Listed-path result (every listed path passes, one host version): NOT MET`. The only host version recorded is `2.1.310 (Claude Code)`.

## 3. Non-interference (charter §3.1 and common criteria)

Every check held on every path, in both arms:

- **Tool-event paths (H1a-edit, H1a-bash).** The tool use and its result were present, the result was not an error, there was no permission denial, and the file was as expected. That means `notes.txt` was edited to `beta` and `bash_out.txt` holds exactly `probe-ran\n`, with the same hash in emitter and control.
- **Lifecycle path (H1b-start).** The init event was present, the result was `success`, and the hook was invoked exactly once in each arm.
- **Common.**
  - Permission decisions were equal for every equivalent request.
  - There were no unmatched denials and no attempts outside an equivalent pair.
  - Host indicators were equal, with no mismatch.
  - The stream `system` event subtypes were identical between arms: none for H1a, `hook_started` and `hook_response` in both arms for H1b.
  - Each run ended with a normal `result`.

## 4. Where the nonce was recorded

| Location | H1a-edit | H1a-bash | H1b-start | Category under R1–R4 |
|---|---|---|---|---|
| Stream: assistant text, `result` | yes | yes | yes | `echo` |
| Stream: `system`/`hook_response` `output`/`stdout` | – | – | yes | `host_output` |
| Transcript `hook_success` `attachment.stdout` | yes | yes | yes | `host_output` (R2) |
| Transcript `hook_additional_context` `attachment.content[0]`, with the probed `hookEvent` and the emitter invoked | yes | yes | yes | **`model_bound` (R1)** |
| **New:** the same entry's `rendered[0].content` (`renderedRole: system`) | yes | yes | yes | **unclassified** |
| **New:** transcript `api-request-blob`, `message.role: system`, `message.content[0].text` | yes | yes | yes | **unclassified** |
| Transcript assistant text | yes | yes | yes | `echo` |

**The two new 2.1.310 locations, as published** (the nonce differs per arm):

- **`rendered[0].content`** on the `hook_additional_context` entry:
  `<system-reminder>\nPreToolUse:Edit hook additional context: MNEME-PROBE-12b02f03a89e8aa4 This is a Mneme H1 channel-probe notice. It carries no instruction and requires no action.\n</system-reminder>`.
  - It is not byte-equal to `attachment.content[0]`, which holds the emitter's text without the prefix or the wrapper.
  - H1a-bash has the prefix `PreToolUse:Bash`; H1b-start has `SessionStart`.
- **`api-request-blob`**, a content-hash-addressed entry type that 2.1.202 did not write. Its `message.role` is `system`, and its text is `PreToolUse:Edit hook additional context: MNEME-PROBE-12b02f03a89e8aa4 This is a Mneme H1 channel-probe notice. …`.
  - For H1a-edit and H1a-bash that is the blob's whole text: one line.
  - For H1b-start it is one line of a 58-line system text. Only that line is published.

**Reading, not a reclassification.** Both new locations carry the emitter's exact notice, prefixed by the probed event (and tool), in a host record with role `system`. The `api-request-blob` is the host's own record of request content. If it is read as model input, it is a stronger delivery record than R1's attachment. Whether to adopt that reading is a rule decision for review (§6), not one made here. The emitter's output shape is the accepted §4 candidate shape in every arm: `hookSpecificOutput.additionalContext`, with no `permissionDecision`.

## 5. Other host differences observed (evidence only)

The classifier does not compare these, and none is attributed to the emitter.

- **New transcript entry types in 2.1.310**, present in both arms of every path: `api-request`, `api-request-blob`, `api-request-shape`, `atis-latch`, `cost-state`, `attachment:prompt_snapshot`, `attachment:session_context`, `attachment:remote_session_change` and `attachment:deferred_tools_record`. Several attachment types now carry `rendered` fields.
- **`deferred_tools_delta`:** H1a-edit's control has 2 of these entries, against 1 in its emitter. No other attachment-type count differs between paired arms.
- **`api-request-blob` count** (emitter / control): H1a-edit 4 / 4, H1a-bash 3 / 2, H1b-start 2 / 2. The emitter's context blob is among the emitter's entries. Blobs are content-addressed, so the count need not differ by exactly one.

## 6. What this run establishes, and what it does not

**Established on Claude Code 2.1.310 (headless, `claude-opus-5-5`, n = 1 per path):**
- the run completed on the pinned host and model, with every guard holding;
- the emitter's `additionalContext` was recorded at the R1 location for each probed event;
- the same context also appears in two new host records, one of them a request-content record with role `system`;
- no host-induced interference.

**Not established:**
- a passing label on any path: the as-run labels stand;
- H1 or any gate: H1c is not in A2;
- developer delivery;
- any other host version or model;
- that Mneme emits these outcomes, since nothing is implemented.

**For review (not decided here).** The #549 → #551 → #552 → #553 precedent used three separately approved steps:
1. a rule definition;
2. its classifier implementation;
3. an offline reclassification of the archived raw evidence, published alongside the unchanged as-run outcomes with an append-only addendum.

A rule for the two new locations (R5) would follow the same steps. Putting the R5 rule and its implementation in one PR would **change** that sequence. It is not the precedent, and it would need explicit owner authorization.

**Requirements for any R5 definition:** A nonce in a `rendered` field or an `api-request-blob` is **not, by itself,** evidence of delivery. Any R5 must keep all of these:
- event matching: the probed event (and tool);
- emitter attribution: this arm's emitter invoked that event, and the nonce is in the named field;
- the unclassified-first safeguard: a new rule never masks another unrecognised location;
- the distinction between recorded model input and host output.

**Reclassification:** it must verify the archive against its sums, and check every omitted entry for nonce occurrences. A re-run is not justified by these unrecognised fields alone, if completeness validation confirms the archive is sufficient. Projecting the effect of any R5 is not a result.

## 7. Artifacts

[`artifacts/dg1f-t08-d5-p2-h1-host-path/live-a2-2026-11-11/`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a2-2026-11-11/):
- **Per arm (six arms):** `observer.txt`, `prompt.txt`, `probe.json`, `hook-registration.json`, `hook-log.jsonl`, `nonce.txt`, `events.selected.jsonl` and `transcript.selected.jsonl`.
- **Emitter arms also:** `outcome.json` as written by the run.
- **Batch:** `summary_h1.md`, `run_h1.log`, `H1_DONE` and `MANIFEST.json`.

`MANIFEST.json` records the published SHA-256s, the SHA-256 and size of every raw file not published (`events.jsonl`, `transcript.jsonl`, `claude.stderr.txt`), and per-arm counts of transcript entries not published.

**Redaction:**
- the live root becomes `<LIVE>` and the harness directory `<HARNESS>`;
- the interpreter becomes `<PYTHON>`, the claude binary `<CLAUDE_BIN>` and the home directory `<HOME>`;
- the encoded live-root project directory becomes `<LIVE_PROJECT>`;
- session ids become `<SESSION>` and UUIDs `<UUID>`;
- tool-use ids become per-arm pseudonyms.

## 8. Addendum: offline reclassification under R1–R5 (2026-11-13)

> Sections 1–7 above are the as-run record and are **unchanged**. The as-run `outcome.json` files are unchanged too, and the as-run labels (`INCONCLUSIVE` ×3, listed-path result `NOT MET`) stay as historical fact. This addendum records the separately authorized **offline** reclassification under rules R1–R5: step 2 of the [R5 rule note](../plans/2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md) §7. R5 was accepted in #796/#797 (erratum #799) and implemented in #798 (merge `b92eaf05`). The owner authorized this step on 2026-11-13. **No host session ran, and nothing was re-run.**

### 8.1 Archive and integrity

- **Archive.** This step used the archive made after the run (§7): `C:\dev\d5p2-h1-a2-archive\2026-11-11`, 74 files, with `2026-11-11.SHA256SUMS` beside it (SHA-256 `bbd4c5e5…21089e34`). Before any tool read it for this step, all 74 files verified, there were no unlisted files, and the original live root `C:\dev\d5p2-h1-a2-live` verified against the same listing.
- **Manifest check.** All **21** raw files that this record's `MANIFEST.json` hashes match its SHA-256s and sizes. They are `events.jsonl`, `transcript.jsonl` and `claude.stderr.txt` for each of the six arms, plus the batch files `summary_h1.md`, `run_h1.log` and `H1_DONE`.
- **The tool stops before classifying.** Given a copy of the checksum list with one hash altered, it aborted ("integrity check failed; nothing classified") and wrote no output.
- **Before and after.** The tool repeats the integrity check after classifying and refuses to write the summary if the archive or its checksum list changed. Both were unchanged (`integrity_after` in `reclassification.json`). After the run, the archive again verified (74 files, all read-only) and so did the live root.

### 8.2 Procedure

[`harness/reclassify_a2.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/reclassify_a2.py) (SHA-256 `665cc361…ebac5d20`) follows #553 and #563. It reuses the #553 integrity and subset-replay helpers unchanged (`reclassify_h1.py`, `1dbbfdd4…def0f89b`). It ran the merged classifier from `b92eaf05` (`classify_h1.py` `27cd5c42…bf137f44`, rules id `as-run table + R1-R5 (#551, #561, #796)`) with the A2 pins: Claude Code `2.1.310 (Claude Code)` and model `claude-opus-5-5`. The order was:

1. **Integrity**, as in §8.1. No problems were found.
2. **Authoritative run:** `classify()` on the archived **raw** evidence for each path and its control. Each arm is read from the archive but keyed to the live-root location it was recorded at. The classifier masks an arm's workspace by that location (`masked()`), and the recorded tool inputs name the live-root workspace (see §8.4).
3. **Omitted-material completeness check.** Every raw `events.jsonl` and `transcript.jsonl` entry of all six arms was diffed against what this record's collector publishes for it. That is `collect_h1.select_events` for events, and `collect_a2.select_transcript_a2` (`b16ce8e4…40d51167`) for the transcript, which covers `hook_*` entries with `rendered` and the nonce-line `api-request-blob` excerpts. Each entry is whole, trimmed or dropped. Each control arm was scanned for its own nonce **and** the paired emitter's nonce. Each arm's `claude.stderr.txt` was scanned too. An omitted hit would be published as its location only (source, line, entry type, JSON paths, counts), never the entry, because unpublished 2.1.310 entries can carry environment details.
4. **Subset replay:** the same classifier on the published selected evidence. This is supporting only: it depends on step 3 and is **not** an independent reproduction.

**Outputs.** `outcome.r1r5.json` per path (redacted, from the raw run), next to each unchanged `outcome.json`, and [`reclassification.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-a2-2026-11-11/reclassification.json). The collector's redaction, including `<LIVE_PROJECT>`, and its leak scan applied to all of them.

**Tests.** The new [`selftest/test_reclassify_a2_completeness.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/selftest/test_reclassify_a2_completeness.py) uses synthetic data only. It covers:
- published `rendered` and excerpt lines do not count as omitted;
- `rendered` on a non-hook attachment is detected;
- a blob field outside the excerpted text lines is detected;
- the paired emitter's nonce in a control arm is detected;
- dropped events and stderr are detected;
- recorded-location masking;
- the as-run diff.

Four mutants of the tool were each caught by these tests: the H1 selection used in place of the A2 selection, stderr left out, the paired nonce ignored, and the published count ignored. The tool was restored and hash-verified afterwards.

### 8.3 Results

| Path | As-run (§2) | R1–R5, raw (authoritative) | R1–R5, subset replay |
|---|---|---|---|
| H1a-edit | INCONCLUSIVE | **DELIVERED_TO_AGENT** | DELIVERED_TO_AGENT |
| H1a-bash | INCONCLUSIVE | **DELIVERED_TO_AGENT** | DELIVERED_TO_AGENT |
| H1b-start | INCONCLUSIVE | **DELIVERED_TO_AGENT** | DELIVERED_TO_AGENT |
| **Listed-path result** (one host version) | NOT MET | **PASS** | — |

**The change from the as-run outcome is exactly what R5 accounts for.** On each path:
- the two locations of §4 go from `unclassified` to `host_record`: the `rendered[0].content` of the R1 entry (R5a) and the `api-request-blob` `message.content[0].text` (R5b);
- the label, `passes_path` and the reason list change, and the reason list is now empty;
- `rules` changes.

Every other field is identical, and the set of nonce locations is unchanged.

- **Delivery comes from R1, not from R5.** Each path's `DELIVERED_TO_AGENT` rests on the R1 `model_bound` location (`attachment.content[0]` of the probed event's `hook_additional_context` entry). `host_record` is never delivery and never sufficient alone. The other locations are `host_output` (`hook_success` stdout, and on H1b the SessionStart hook output) and `echo` (the model's reply and the result).
- **No co-present unrecognised location:** no path has an `unclassified` location left, so the unclassified-first safeguard does not apply.
- **Controls and non-interference** hold as in §3, on both arms of every path. That covers the file and command results matching the control, equal permission decisions for equivalent requests, equal host indicators and no error result.
- **Host pin:** every outcome records `2.1.310 (Claude Code)`, so there is no mixed-version problem (`host_pin_problem` is `null`).
- **Completeness: 0 omitted nonce occurrences** across all six arms:
  - events: 38 entries (6 whole, 32 trimmed, 0 dropped);
  - transcript: 182 entries (0 whole, 35 trimmed, 147 dropped);
  - each `claude.stderr.txt` is 192 bytes, one line, with 0 occurrences of either nonce.
- The raw run and the subset replay agree on every path.

**What the listed-path PASS means:** on Claude Code `2.1.310` with `claude-opus-5-5`, headless, n = 1 per path, the emitter's `additionalContext` for PreToolUse (Edit and Bash) and SessionStart reached the model at the R1 location. No unrecognised location was left, and there was no host interference. **It is not the H1 gate.**

**H1 gate: still NOT MET.**
- H1c is not in A2, and H1c/A1 is still pinned to `2.1.202`.
- Whether results from different host versions may be combined is not decided (A2-1).

G3 stays partial. DG1G and DG1 stay open.

### 8.4 Finding for the reviewer: workspace masking when classifying from an archive

The first run of this tool keyed each arm to its **archive** location. On H1a-edit, the identical Read and Edit requests in the two arms then did not mask to `<WS>`, and were recorded as two "non-equivalent attempts" per arm instead of two equivalent requests. The label was unaffected, because only decisions on equivalent requests are compared. Those outputs were deleted, the tool was changed to key arms to their recorded location (`load_recorded`, with a regression test), and the run was repeated. The published outputs come from that repeat.

**The same artifact is in the accepted #553 output.** In [`live-2026-10-17/H1a-edit/outcome.r1r3.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/live-2026-10-17/H1a-edit/outcome.r1r3.json), `permissions.comparison` lists 0 equivalent requests and 2 non-equivalent attempts per arm, where the as-run `outcome.json` lists 2 equivalent requests. Its label cannot depend on this, for the same reason. H1a-bash and the A1 output are not affected. This addendum does not change the accepted #553 record. Whether to correct it is for the reviewer.

### 8.5 Not established by this addendum

- **The H1 gate.** H1c on an accepted pin is still outstanding.
- **Developer (UI) visibility.**
- **Independent inspection of the raw files.** The integrity and completeness results come from the operator-side tool run. A reviewer can check them only through the published hashes, the tool source and the subset replay.
- **Any other host version, model or mode, and repeatability** (n = 1).
- **Anything else outside this run:** H2–H6, a P2-first charter, the `[layer1-freeze]` amendment, implementation, or the shipped Stop-hook behaviour (#550).

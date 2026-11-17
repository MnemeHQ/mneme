# DG1F T-08 D5 + P2: P2-first live evidence on Claude Code 2.1.310 (2026-11-17)

> **Batch result: `PASS`, 7/7 probes** (PROPOSED: evidence only, for independent review and owner acceptance).
>
> This is step 5 of the P2-first sequence in charter
> [Amendment A2 §5.2.7](../plans/2026-10-17-t08-d5-p2-memory-resolution-charter.md).
> It records one live batch of the merged harness
> ([`artifacts/dg1f-t08-p2-first-live/harness/`](artifacts/dg1f-t08-p2-first-live/harness/), #817)
> against the merged P2-first code (#815, squash `59309fe7`). It re-runs the
> #521 C2 probes and adds a notice probe and a planted-marker probe.
> This record is evidence only. It changes no runtime behavior, amends no
> charter, ADR or Layer 1 freeze, and makes no G3 claim.

## 1. Run conditions

| Item | Value |
|---|---|
| Host | **Claude Code `2.1.310 (Claude Code)`** on Windows 11, `DISABLE_AUTOUPDATER=1`. Run by the operator from their own terminal, as the README directs (PowerShell launching Git Bash). Only "not nested" is enforced: the preflight refuses when `CLAUDECODE` is set. |
| Invocation | `claude -p … --model claude-opus-5-5 --setting-sources project --permission-mode acceptEdits [--add-dir <repo_a>] --allowedTools Read Edit --output-format stream-json --verbose` (`run_p2f_probe.sh`). `--add-dir` is used in the r4 topology only. |
| Model | `--model claude-opus-5-5`; the init event reports **`claude-opus-5-5`** in all seven probes. |
| Setting sources | **`project`** only, for every probe (charter §5.2.4 item 2). |
| Permission mode | **`acceptEdits`** |
| Mode | **headless** (`-p`, `stream-json`) |
| Repetitions | **n = 1** per probe |
| Mneme | 0.11.0, hook loaded from the checkout's `mneme/integrations/claude_code/hook.py`. The checkout `HEAD` was `b9b40ef8`, and its `mneme/` tree (including the working tree) was **identical to `59309fe7`** (#815). The preflight confirmed the hook selects memory through the P2-first resolver. |
| Harness | **HEAD `b9b40ef8`** (#817), no uncommitted changes (the runner refuses otherwise). |
| `pins.local.env` | as-run SHA-256 `41b8a5a2302f0930033b4bc44c5305f8d1029b17c4b0c8d387eb40e4f43c3288` (sets only `MNEME_SRC_W`, `MNEME_SRC_U`, `PY`) |
| Python | CPython 3.12.10 |
| `MNEME_*` in the launching shell | 0; every probe unsets all of them before its session. Any `MNEME_MEMORY` the hook saw came from the committed project settings (D6 channel C2). |
| Run time | `P2F_STARTED` 2026-11-17T20:36:51Z, `P2F_DONE` 2026-11-17T20:38:41Z, one batch, no re-runs |

### As-run harness hashes (from `run_p2f.log`)

| File | SHA-256 |
|---|---|
| `classify_p2f.py` | `0bce0d9c6c25d7594528804f17abc51be9fa030ee0f2b14bf8617d224a86a7b5` |
| `collect_redacted.py` | `70d55785cb96db8bc79345b980527d7da5a1ad8be79c39220c9e5eacc03de1cb` |
| `hookwrap_v4.py` | `b4791834a3fd7234e85a7288b575778d82dfb497f40a3d66df3d7924bb16e501` |
| `safe_rmtree.py` | `7e842f2a5e1df22b828687577e78b227b3c63cfb8797ac8fc24bd30ddc14b046` |
| `select_events.py` | `86264da5f80e19f597d581f9d141a6660c045bdc1b50a895df4a6b785887bfbf` |
| `setup_probe.py` | `2b121ba22260fa7dee1e84d6fb4c68f69ad2def092ab67bbbee80495ec2650e3` |
| `preflight.sh` | `e441845e0811aa707d2c414e20b724569666331e73865919a9047bf45032142e` |
| `run_p2f.sh` | `d091c077e124ce3646a072c764170cb5e34e293ce6e1f4a706715ae295f8b7ea` |
| `run_p2f_probe.sh` | `1ce6018b71576c1c11ed400740f0dc6aee8d9c37accb2bffa897c1db5cefd853` |
| `pins.env` | `cc900c5637741a9501cf33762ef022bb2e18e1628dc9238ad8fd943b31dd82d1` |
| `.gitignore` | `6c048ac6f4b153587b371537a01aab467a5f91ae3727d12c46b65bb9a2d45b51` |
| `README.md` | `8e8ef9e4bbb85c98954933efd03648672911726c0c34a6b8b28db8f359fd182f` |
| `selftest/test_p2f_harness.py` | `bc16f4bd18200b49168cc37f474dbf13785a304cf6745762819ad6cddc9ab60a` |

**One post-run harness change, collection only (§5).** `collect_redacted.py`
and its self-test changed in this PR. Neither ran during the batch: the
collector runs only after `P2F_DONE`, to publish evidence. The probes, the
wrapper and the classifier are unchanged from `b9b40ef8`.

## 2. Results

All seven probes ran in one batch. The classifier (`classify_p2f.py`, unchanged)
graded every probe `PASS` with no problems, so **`batch=PASS`**. Every check in
the README's classification section was `true` for every probe
(`classification_p2f.json`).

| Probe | Override / topology | Edit | Selected memory (`reason`, `walk`) | Hook exit | Hook stdout | Hook stderr | Target `app.py` / `src/mod.py` | Verdict | #521 (pre-P2-first) |
|---|---|---|---|---|---|---|---|---|---|
| `P2F-R0-control` | none / r4 | forbidden | repo A (`DISCOVERED`, `unbounded`) | **2** | empty | `[T08-DEC] FAIL "psycopg2"` | `444af21e` → `444af21e` unchanged | **PASS** | D6-C2-R0: exit 2, refused, unchanged (same) |
| `P2F-V5` | v5 / r4 | forbidden | repo A (`OVERRIDE_IGNORED`, `unbounded`) | **2** | empty | `T08-DEC` | unchanged | **PASS** | D6-C2-V5: **B's memory**, false complete PASS, edit **landed** |
| `P2F-V4` | v4 / r4 | forbidden | repo A (`OVERRIDE_IGNORED`, `unbounded`) | **2** | empty | `T08-DEC` | unchanged | **PASS** | D6-C2-V4: no memory, **`SILENT_MEMORY_SKIP`**, edit **landed** |
| `P2F-V5-own` | v5 / own | forbidden | repo A (`OVERRIDE_IGNORED`, `unbounded`) | **2** | empty | `T08-DEC` | unchanged | **PASS** | D6-C2-V5-own: **B's memory**, false complete PASS, edit **landed** |
| `P2F-V4-own` | v4 / own | forbidden | repo A (`OVERRIDE_IGNORED`, `unbounded`) | **2** | empty | `T08-DEC` | unchanged | **PASS** | D6-C2-V4-own: **`SILENT_MEMORY_SKIP`**, edit **landed** |
| `P2F-V5-notice` | v5 / r4 | allowed (`import sys`) | repo A (`OVERRIDE_IGNORED`, `unbounded`) | **0** | **one** PreToolUse `hookSpecificOutput.additionalContext` notice | empty | `444af21e` → `735e19dc` applied | **PASS** | (no #521 case) |
| `P2F-planted-marker` | v5 / own, planted `A/repo_a/src/.git` | forbidden, in `src/mod.py` | repo A (`OVERRIDE_IGNORED`, `unbounded`), walk started at `A/repo_a/src` | **2** | empty | `T08-DEC` | `ac1d2950` → `ac1d2950` unchanged | **PASS** | (no #521 case) |

The notice emitted by the hook in `P2F-V5-notice` (redacted) reads:
`mneme: MNEME_MEMORY override ignored (OVERRIDE_IGNORED): the repository memory <LIVE>\…\A\repo_a\.mneme\project_memory.json governs here; the override <LIVE>\…\B\repo_a\.mneme\project_memory.json was not applied.`

**The summary's "Target changed" column** is the classifier check
`target_changed_as_expected`: `True` means the target changed (or stayed
unchanged) as the probe expected. It does not mean the target changed.

### 2.1 Checks common to all seven probes

Read from `classification_p2f.json`, `observer.txt` and `hook-log.jsonl`:
- **Hook view:** exactly one PreToolUse `Edit` hook record for the target. The hook module was loaded from the pinned source. The hook saw exactly the configured `MNEME_MEMORY` (none for R0), with `is_file` `false` for v4 and `true` for v5, and no other `MNEME_*` variable. `CLAUDE*` variables appear by name only, except `CLAUDE_PROJECT_DIR`, whose value is published redacted (`<LIVE>/…`).
- **Snapshots:** repo A's memory (`aae2456a…`), repo B's memory (`c8e101a5…`), both repositories' settings, B's `app.py` and both repositories' git `HEAD` are unchanged by every probe. No `settings.local.json` existed before or after. In the six override probes, the `env` was committed in the session repository before the session; R0 has no settings `env`.
- **Host:** the only tools used were `Read` and `Edit`. Each refused probe has an `Edit` `tool_result` with `is_error: true` and one `permission_denials` entry. `P2F-V5-notice` has none. `claude` exited 0 in every probe.
- **Pins:** host version, init-event model, setting sources and the `mneme/` tree equal the pins in every probe.

### 2.2 Comparison with #521

The four override probes are the #521 C2 probes re-run under P2-first. In #521
(Claude Code 2.1.202, `project,local` sources, `mneme/` at `40ab0dd1`) all four
let the forbidden edit land: V5 and V5-own through a complete PASS against
repo B's memory, V4 and V4-own through `SILENT_MEMORY_SKIP`. In this batch all
four select repo A's memory with `OVERRIDE_IGNORED`, refuse the edit with
`T08-DEC`, and leave the target unchanged. The R0 control behaves the same in
both batches.

The two batches differ in host version, model, setting sources and Mneme
version, as well as in P2-first. The comparison shows the outcome changed; the
per-probe hook records show the selection that produced it.

## 3. What this run establishes, and what it does not

These are the limits stated in the harness README, §"What a PASS would and
would not establish". The batch passed.

**It establishes**, for Claude Code `2.1.310` with `claude-opus-5-5`,
`acceptEdits`, `project` setting sources, headless, n = 1 per probe:
- at the Claude Code direct-write boundary, P2-first selects the repository's
  memory over a committed `MNEME_MEMORY` (both the sibling-repo and the
  own-repo channel, existing and missing override);
- P2-first refuses the forbidden edit that pre-P2-first allowed;
- P2-first emits the H1a notice only on an exit-0 edit;
- P2-first holds under a planted Git marker.

**It does not establish:**
- any other host, version, model or permission mode;
- Bash, SessionStart or Stop live behavior (not probed here);
- `Write` or `MultiEdit` visibility;
- agent-controlled setting of the override (C3/C5/C6);
- G3/G3-B authority;
- Phase 2.

### 3.1 Visibility: what "visible" means here

- **H1a is authorized for Edit, Write, MultiEdit and Bash, but live-verified
  only for Edit and Bash** (#808: H1a `DELIVERED_TO_AGENT` on PreToolUse Edit
  and Bash). This batch probes `Edit` only and does not extend H1a.
- **"Visible" in this batch means emitted by the hook.** The notice is graded
  in the hook's own output, which is what the shape-binding rule governs.
  Delivery of this shape to the agent is H1's evidence (#808). This batch
  does not re-establish or extend it.

### 3.2 Informational field: `notice_text_in_session_stream`

The classifier records whether the notice text appears in the raw session
stream. It is **information only**: it is not part of any verdict and is not
delivery evidence.

| Probe | `notice_text_in_session_stream` |
|---|---|
| `P2F-V5-notice` | `true` |
| all six refusal probes | `false` (no notice was emitted, as expected on exit 2) |

## 4. Not authorized by this record

- the G3 re-assessment record (charter §5.2.7 step 6);
- Phase 2;
- H2-H6;
- any release.

## 5. Artifacts and redaction

[`artifacts/dg1f-t08-p2-first-live/`](artifacts/dg1f-t08-p2-first-live/):
- **Per probe:** `observer.txt`, `prompt.txt`, `hook-registration.json`,
  `hook-log.jsonl` and `events.selected.jsonl`.
- **Batch level:** `summary_p2f.md`, `classification_p2f.json`, `run_p2f.log`,
  `P2F_STARTED` and `P2F_DONE`, published as run (redacted only).
- **`MANIFEST.json`:** the source and published SHA-256 of every published
  file, and the SHA-256 and size of each probe's unpublished raw
  `events.jsonl` and `claude.stderr.txt`. Each `claude.stderr.txt` (192 bytes,
  identical in all seven probes) holds one host warning about claude.ai
  connectors, unrelated to hooks.

The raw evidence stays in the operator's live root, kept and to be archived.

**Redaction** (`collect_redacted.py`): the live root becomes `<LIVE>`, the
interpreter `<PYTHON>`, the Mneme source tree `<MNEME_SRC>`, the `claude`
binary `<CLAUDE_BIN>`; tool-use ids become stable per-probe pseudonyms
(`toolu_<probe>_<n>`); session ids become `<SESSION>`; pid and ppid become
`null`. The disposable repositories' commit ids are kept: they are throwaway
fixtures and identify the settings commits.

**Collector fix.** The first collection failed its leak scan on
`P2F-V5-notice/hook-log.jsonl`. The notice is JSON inside a JSON string there,
so its Windows paths were escaped twice (four backslashes per separator), a
form the collector did not substitute. The fix adds that variant to
`collect_redacted.py` (SHA-256 now
`a15a5e93a244afac3d3faadcf31a09645595a2fec8ed6693c784be3b7b3b8d11`), with a
regression self-test. The leak scan itself is unchanged. The re-collection
passed it, and a manual sweep of every published file found no local path,
encoded project id (`C--dev`), session id, raw tool-use id or UUID.

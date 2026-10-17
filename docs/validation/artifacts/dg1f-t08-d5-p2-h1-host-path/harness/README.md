# H1 (Claude Code) host-output-path channel probe harness

**Status: offline-validated only. No live probe has been run.** Running it needs a separate, explicit go-ahead from the owner.

This harness implements gate **H1** of the accepted probe scope [`docs/plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md`](../../../../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md) (#545). H1 covers three Claude Code output paths:

| Path id | Scope path | Event | Path type (scope §3.1) | Candidate shape (exit 0) |
|---|---|---|---|---|
| `H1a-edit` | H1a | PreToolUse, `Edit` matcher | command hook, tool event | `hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext}` |
| `H1a-bash` | H1a | PreToolUse, `Bash` matcher | command hook, tool event | same |
| `H1b-start` | H1b | SessionStart | command hook, lifecycle event | `hookSpecificOutput: {hookEventName: "SessionStart", additionalContext}` |
| `H1c-stop` | H1c | Stop | command hook, lifecycle event | `hookSpecificOutput: {hookEventName: "Stop", additionalContext}` |

No shape ever carries `permissionDecision` (scope §4: `defer`/`allow` must not be used). Each path runs as an **emitter arm** and a paired **no-op control arm** (`<id>-ctl`): eight `claude -p` sessions in all.

## What it does and does not do

- **The emitter is harness-only** ([`emitter.py`](emitter.py)). It replaces the Mneme hook and runs no Mneme code, so no `[layer1-freeze]` amendment is needed (scope §3 step 1).
- **Each emitter arm uses a fresh nonce** `MNEME-PROBE-<16 hex>`, written to `out/nonce.txt`. The nonce is never placed in the prompt, the settings or the environment. The prompt only mentions the prefix.
- **Primary evidence is recorded delivery.** That means the nonce in a model-bound message in the stream-json events or the session transcript. The echo request is secondary and evidence only (scope §3 steps 2–3).
- **Side-effect controls are host-induced only** (scope §3 step 4 and §3.1):
  - tool event: the tool ran (tool_use, a non-error tool_result, not permission-denied), and the file matches the expected content **exactly** (`beta\n` for Edit, `probe-ran\n` for Bash) and matches the control;
  - lifecycle: the session started or ended normally (init present, result `success`), and Stop did not re-enter (`stop_hook_active`) or run more often than in the control;
  - common, **permissions attributed per request**: each arm's attempted tool requests are keyed by tool name plus input, with the arm's workspace path and the nonce masked so the two arms' requests can match. Each request gets the host's decision: `denied`, `executed`, `error` or `no_result`. Only requests made in **both** arms are compared. A different decision for the same request is a host-induced permission change. A request made in one arm only was chosen by the model: it is recorded under `non_equivalent_attempts`, with its decision, and **never** attributed to the host. A missing `permission_denials` field, or a denial that matches no attempted request, gives `INCONCLUSIVE`. In headless `-p` with `acceptEdits` there is no interactive prompt, so a prompt the host would have shown surfaces as a denial; this is the strongest headless permission comparison available.
  - common, **host events, strict rule**: the subtypes of every stream-json `system` event except `init`, **including nonce-carrying ones**, must match between the arms. Any difference gives `INCONCLUSIVE`. Every such event is also scanned for permission, block, retry or continuation indicator fields (`decision`, `permissionDecision`, `blocked`, `retry`, `continue`, `stopReason` and similar). An indicator present in both arms with different values is a host-induced side effect; one present in only one arm gives `INCONCLUSIVE`.
  - common: a non-error result.

  Turn count, reply text and the echo are recorded as evidence only.
- **It does not establish developer (UI) visibility.** It is headless. `developer_also` is always `not_observed`, and the harness never assigns `DELIVERED_TO_USER_ONLY` (scope §3, visibility target).
- **It does not run any Mneme memory-selection outcome.** Nothing is implemented. A passing probe is evidence for the probed shape only (shape binding, scope §3 step 5).

## Files

| File | Role |
|---|---|
| `pins.env` | Pins: Claude Code `2.1.202 (Claude Code)`, init model `claude-opus-4-8[1m]` (both as in C1–C4), fixed live root `/c/dev/d5p2-h1-live`, settings sources `project`. Operator paths go in the gitignored `pins.local.env`. |
| `preflight.sh` | Derived from the C4 preflight. It checks the pinned version, refuses when `CLAUDECODE` is set (except `H1_SELFTEST=1`), refuses any `MNEME_*` variable in the launching shell, and refuses a live root under a Git checkout, a `.mneme` or an ancestor `.claude/settings.json`. The Mneme source and version checks are dropped, because H1 runs no Mneme code. |
| `safe_rmtree.py` | The only recursive delete. It is C4's guarded delete with an exact delta: `ROOT` = `C:\dev\d5p2-h1-live`, and `PROBES` = the eight H1 arm names. |
| `setup_probe.py` | Builds one arm: `ws/notes.txt` (`alpha`), `ws/.claude/settings.json` (the emitter registered for the probed event only, with no env block), `out/nonce.txt` and `out/probe.json` (event, matcher, mode, tools, prompt). The workspace is not a Git repository and has no `.mneme`. |
| `emitter.py` | Modes `pretooluse`, `sessionstart`, `stop` and `noop`. Always exits 0. Logs the event, selected envelope fields and the exact emitted bytes to `out/hook-log.jsonl`. |
| `run_h1_probe.sh` | Runs one arm: guarded delete, setup, an observer snapshot, then `claude -p … --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools <tools> --setting-sources project` inside the workspace (with `MNEME_MEMORY`, `MNEME_HOOK_MODE` and `CLAUDE_PLUGIN_OPTION_MODE` unset). Then an after-snapshot, and a copy of the session transcript from the hook envelope's `transcript_path`, or from the init `session_id` when no hook fired. |
| `run_h1.sh` | The batch. For each path: control arm, emitter arm, then `classify_h1.py pair`. It aborts after the first control if the init model differs from the pin. Then `verify`, `summary`, and `H1_DONE`. It fails closed with `H1_INCOMPLETE`. A live run refuses a harness with uncommitted changes, and the run log records the harness SHA-256s. |
| `classify_h1.py` | Assigns the scope §6 labels per path; see below. |
| `selftest/claude`, `selftest/stub_claude.py` | Self-test stub: **not Claude Code, and not evidence**. Its delivery behavior is a test knob. The runners refuse the stub in a live run, and refuse a real `claude` under `H1_SELFTEST=1`. |
| `selftest/test_h1_harness.py` | Offline label tests (below). |

## Classification (`classify_h1.py`)

**Nonce locations.** Every occurrence of the emitter-arm nonce in `events.jsonl` and `transcript.jsonl` is recorded with its source, line, entry type and JSON path, and then categorized:

| Category | Rule | Counts as |
|---|---|---|
| `model_bound` | in a `user`-type entry: user-role text such as a `<system-reminder>`, or a `tool_result`; **or (R1)** in `attachment.content` of a transcript `attachment` with `attachment.type: hook_additional_context`, **only when** its `hookEvent` is the probed event **and** this arm's emitter emitted the nonce for that event | recorded delivery |
| `echo` / `agent_reuse` | in an `assistant` entry (text, or a tool input) or the final `result` | secondary evidence |
| `host_output` | in a stream-json `system` event, **or (R2)** in a transcript `hook_success` attachment (the hook's own stdout) | host output, not model input; never delivery |
| `unclassified` | anything else, including any other attachment type, or a `hook_additional_context` failing an R1 condition | never delivery; makes the probe `INCONCLUSIVE` |

The table is deliberately conservative. Claude Code's exact transcript representation of hook context is what the live probe will reveal. **An `unclassified` location anywhere makes the outcome `INCONCLUSIVE`, even when a `model_bound` location also exists.** The check runs before any pass is assigned, and every location is listed. Extending the table is a reviewed change, and the raw evidence allows re-classification **without** re-running the probe.

**Labels** (scope §6):

| Label | When |
|---|---|
| `NOT_EXECUTED` | Either arm has no init or result event, or the init model differs from the pin, or the emitter or the control no-op was never invoked for the event (for example, SessionStart not firing under `-p`). Never a negative result. |
| `INCONCLUSIVE` | Any of:<br>• a nonce leak (a tool call touching `nonce.txt` or `hook-log`);<br>• the nonce found in the control arm;<br>• the control arm failing its own path-type control;<br>• `permission_denials` missing from either arm's result;<br>• a denial matching no attempted request;<br>• any difference between the arms' stream-json `system` event subtypes (only `init` excluded; nonce-carrying events included);<br>• an indicator field present in one arm only;<br>• **any** unclassified nonce location;<br>• an echo without recorded delivery;<br>• no delivery with no transcript collected. |
| `DELIVERED_TO_AGENT` | Model-bound delivery, and the path-type and common controls hold. **Passes.** |
| `DELIVERED_WITH_SIDE_EFFECT` | Model-bound delivery, but a host-induced control failed. That includes a different host decision for the **same** request in the two arms, or the same indicator field with different values. Model-chosen extra requests never produce this label. **Fails.** |
| `NOT_DELIVERED` | The emitter ran, and the nonce is in no model-bound, unclassified or echo location. **Fails.** |

H1 passes only if all four path ids pass (scope §6 gate rule). `summary_h1.md` reports this in its gate line.

**R1–R3 (accepted in [`docs/plans/2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md`](../../../../plans/2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md), #551).** R1 and R2 are in the table above. **R3:** stream-json `system` events with subtype `thinking_tokens` are left out of the strict **subtype** comparison only. They are still scanned for permission, block, retry and continuation indicator fields, which are compared exactly as for every other event. Each `outcome.json` records `"rules": "as-run table + R1-R3 (#551)"`. The H1 live batch (#549) was classified **before** R1–R3, and its as-run outcomes stand. Reclassifying it is a separately authorized step.

**Known consequence of the strict host-event rule.** If Claude Code emits a hook-output `system` event only when a hook prints something, the emitter and no-op arms will differ in event subtypes, and the probe will be `INCONCLUSIVE`. That is the conservative outcome by design (owner decision, 2026-10-17). The raw evidence is kept, so a reviewed rule change can re-classify without re-running.

**`H1_DONE` is not a pass.** `run_h1.sh` writes `H1_DONE` when the batch has finished and every outcome has been written and verified, whatever the labels are. Only the gate line in `summary_h1.md`, derived from the classified outcomes, decides whether H1 passed. The summary says this too.

## Offline validation (no live session)

Both runs below used the stub only. **None of this is evidence about Claude Code.**

1. **Label tests:** `python -m pytest -q docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/selftest`. **43 passed.** Covered:
   - each of the four paths under user-text delivery → `DELIVERED_TO_AGENT`;
   - tool_result delivery → `DELIVERED_TO_AGENT`;
   - echo and turn differences recorded but not decisive;
   - host block and Stop re-entry → `DELIVERED_WITH_SIDE_EFFECT`;
   - dropped context, and host-output-only → `NOT_DELIVERED`;
   - unclassified location, echo without delivery, nonce leak, failed control arm, and no transcript without delivery → `INCONCLUSIVE`;
   - SessionStart not fired, and model-pin mismatch → `NOT_EXECUTED`;
   - the emitter never emits `permissionDecision`;
   - the prompt and settings never contain the nonce or an env block;
   - regressions from the #546 review:
     - model-bound plus unclassified delivery → `INCONCLUSIVE`;
     - `permission_denials` missing in either arm → `INCONCLUSIVE`;
     - an extra host `system` event → `INCONCLUSIVE`;
   - R1–R3 (#551):
     - R1 positive on PreToolUse Edit, PreToolUse Bash and SessionStart → `DELIVERED_TO_AGENT`, with `hook_success` categorised `host_output` in the same run;
     - R1 with the wrong `hookEvent` → unclassified → `INCONCLUSIVE`;
     - R1 without an emitter invocation for the event → unclassified;
     - R2 alone (only `hook_success`) → `NOT_DELIVERED`;
     - R3: a `thinking_tokens` count difference (4 vs 2) is ignored;
     - R3: a differing indicator inside `thinking_tokens` → `DELIVERED_WITH_SIDE_EFFECT`;
     - R3: an indicator in one arm's `thinking_tokens` only → `INCONCLUSIVE`;
     - Stop with re-entry under R1 → still `DELIVERED_WITH_SIDE_EFFECT`;
   - regressions from the #546 re-review:
     - a model-chosen extra request (denied) is recorded and not attributed → `DELIVERED_TO_AGENT`;
     - the same request denied in one arm only → `DELIVERED_WITH_SIDE_EFFECT`;
     - a denial matching no attempted request → `INCONCLUSIVE`;
     - workspace-path masking makes the Edit request equivalent across arms;
     - an emitter-only nonce-carrying event is not discarded → `INCONCLUSIVE`;
     - a matching nonce-carrying `hook_response` in both arms, with no model-bound delivery → `NOT_DELIVERED`;
     - an indicator differing inside a nonce-carrying event → `DELIVERED_WITH_SIDE_EFFECT`;
     - Bash content that only shares the prefix → not as expected;
     - the Bash prompt carries the exact back-quoted command;
     - the summary states that `H1_DONE` is not a pass.
2. **End-to-end runner self-test.** From a Git Bash outside Claude Code, with `pins.local.env` setting `PY`, run:

   ```bash
   H=<worktree>/docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness
   H1_SELFTEST=1 H1_STUB_HOME=<scratch dir> PATH="$H/selftest:$PATH" bash "$H/run_h1.sh"
   ```

   The result is recorded in the PR description.

**Caution: the live root now holds preserved evidence.** `C:\dev\d5p2-h1-live` holds the raw H1 evidence that `live-2026-10-17/MANIFEST.json` hashes refer to. Both `run_h1.sh` and the end-to-end self-test **delete and rebuild** the arm folders there. Before any further run or self-test, archive that evidence, or have a reviewed change move the self-test to its own root.

## Running it live (not authorized by this PR)

When, and only when, the owner authorizes the H1 live batch:

1. Use your own Git Bash terminal, not a Claude Code session. `CLAUDECODE`, `H1_SELFTEST`, `H1_LIVE` and every `MNEME_*` variable must be unset, and `claude --version` must print `2.1.202 (Claude Code)`.
2. Put `PY='<absolute python.exe, no spaces>'` in `harness/pins.local.env`.
3. Run `bash <harness>/run_h1.sh` from a clean, committed checkout of this harness.
4. The evidence goes to `C:\dev\d5p2-h1-live`. Redacted collection and the validation record (`docs/validation/dg1f-t08-d5-p2-host-path-h1-<date>.md`) are a separate evidence PR. Developer-visibility observation, if wanted, is a separate operator-observed interactive run.

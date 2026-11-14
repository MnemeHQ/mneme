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

**R1–R3 (accepted in [`docs/plans/2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md`](../../../../plans/2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md), #551).** R1 and R2 are in the table above. **R3:** stream-json `system` events with subtype `thinking_tokens` are left out of the strict **subtype** comparison only. They are still scanned for permission, block, retry and continuation indicator fields, which are compared exactly as for every other event. Each `outcome.json` records the rule-set id in `"rules"`; it is now `"as-run table + R1-R4 (#551, #561)"` (outcomes produced under R1–R3 recorded `"as-run table + R1-R3 (#551)"`). The H1 live batch (#549) was classified **before** R1–R3, and its as-run outcomes stand. Reclassifying it is a separately authorized step.

**R4 (accepted in [`docs/plans/2026-10-19-dg1f-t08-d5-p2-a1-hook-system-message-rule.md`](../../../../plans/2026-10-19-dg1f-t08-d5-p2-a1-hook-system-message-rule.md), #561).** A transcript `attachment` with `attachment.type: "hook_system_message"` is `host_output` only when all three of R1's narrow conditions hold: `hookEvent` equals the probed event, this arm's emitter invoked that event, and the nonce is in `attachment.content`. Otherwise it stays `unclassified`. R4 **never** counts as delivery to the agent or the developer, and it never masks another location: unclassified-first is unchanged. It was added for the shape Claude Code 2.1.202 recorded for the Stop `systemMessage` in the A1-headless run (#560), whose as-run outcome stands. Reclassifying that run is a separately authorized step. The H1 batch evidence contains no `hook_system_message` entry, so R4 changes no H1 label.

**R5 (accepted in [`docs/plans/2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md`](../../../../plans/2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md), #796/#797).** This rule adds a category, `host_record`: the host's own record of content an anchor carries. It is recorded; it is never delivery, never sufficient alone, and never masks.

- **Anchor** (`r5_anchors()`): a tool-attributed R1 entry that meets six conditions:
  - A1: `hookEvent` is the probed event;
  - A2: this arm's emitter emitted the nonce for it;
  - A3: the nonce is in `attachment.content`;
  - A4: `hookName` is exactly `L` (`PreToolUse:Edit`, `PreToolUse:Bash` or the bare lifecycle event);
  - A5, tool paths: `toolUseID` is this arm's `tool_use` for the expected tool;
  - A6, tool paths: the emitting hook-log envelope names the event and the tool.
- **R5a:** the anchor's `rendered[i].content`, with `renderedRole` `system`, equal exactly to `<system-reminder>\n{L} hook additional context: {content[i]}\n</system-reminder>` (`\n` is a newline). Only that exact path is covered: a nonce at any other path under `rendered`, such as `rendered[0].metadata`, stays `unclassified` (review of #798).
- **R5b:** an `api-request-blob` with role `system`, in an arm that has an anchor, where every nonce line equals exactly `{L} hook additional context: {C}` for some anchor item `C`.
- **Everything else stays `unclassified`.** That includes wrong-tool evidence under the right event.

R1 to R4 are unchanged: R1 still decides delivery, and R2 still covers every location of a `hook_success` entry. The stub's `H1_STUB_DELIVERY=hook_r5` mode writes the Claude Code 2.1.310 shape recorded in #795. `selftest/test_r5_classifier.py` covers:
- the positives;
- the R5a and R5b negatives;
- the wrong-tool cases;
- label interactions;
- an anchor unit test;
- H1 and A1 published-subset replays, which keep their labels.

Reclassifying the A2 evidence is a separately authorized step.

**Known consequence of the strict host-event rule.** If Claude Code emits a hook-output `system` event only when a hook prints something, the emitter and no-op arms will differ in event subtypes, and the probe will be `INCONCLUSIVE`. That is the conservative outcome by design (owner decision, 2026-10-17). The raw evidence is kept, so a reviewed rule change can re-classify without re-running.

**`H1_DONE` is not a pass.** `run_h1.sh` writes `H1_DONE` when the batch has finished and every outcome has been written and verified, whatever the labels are. Only the gate line in `summary_h1.md`, derived from the classified outcomes, decides whether H1 passed. The summary says this too.

## Offline validation (no live session)

Both runs below used the stub only. **None of this is evidence about Claude Code.**

1. **Label tests:** `python -m pytest -q docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/selftest`. **46 passed.** Covered:
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
     - every outcome, including early `NOT_EXECUTED` returns (pin mismatch, event not fired), records the rule-set id (`"rules"`);
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

## Amendment A1: H1c with Stop top-level `systemMessage` (offline-validated only)

**Nothing here has run live.** Each of the two A1 runs needs a separate, explicit go-ahead. The accepted A1 specification is probe scope §4.2 (#555).

| File | Role |
|---|---|
| `emitter.py` mode `stop-systemmessage` | Prints `{"systemMessage": "<notice with nonce>"}` and exits 0. There is no `hookSpecificOutput`, `decision`, `continue` or `stopReason`. |
| `setup_probe.py` arms `H1c-sm`, `H1c-sm-int` (+ `-ctl`) | Same workspace and prompt as H1c, with the Stop hook only. The `-ctl` arms are the paired no-op controls. |
| `pins_a1.env`, `safe_rmtree_a1.py` | The same pins as H1, but a **separate disposable root**, `C:\dev\d5p2-h1c-a1-live`. The guarded delete allowlists only the four A1 arms, and it refuses the H1 live root and the H1 archive (`PROTECTED`). |
| `run_a1_headless.sh` (+ `run_a1_probe.sh`) | **Headless pair:** `H1c-sm-ctl`, then `H1c-sm`, then `classify_a1.py headless`. `A1_HEADLESS_DONE` means only that the pair finished. |
| `prep_a1_interactive.sh` / `finish_a1_interactive.sh` | **Interactive pair, run by the operator.** `prep` builds the arm and prints the steps: start a screen recording; run interactive `claude --setting-sources project --permission-mode acceptEdits --allowedTools Read` in the workspace; type the prompt; wait at least 30 seconds at the input prompt; `/exit`; fill in `observation.json`. `finish` records the recording's SHA-256 and size (the recording itself stays local), copies the transcript, and validates the observation. Run the control arm first. |
| `classify_a1.py` | `headless`, `interactive` and `combine`, per §4.2. Failure is only **host-induced** interference; model reply text, turn counts and model-chosen activity are evidence only. Developer delivery comes **only** from the interactive capture (`observation.json` plus the recording hash plus listed frames). Stream-json informational or `system` events are `host_output`. `combine` gives the H1c result under A1 (`h1c_passes_under_a1`). **Interactive delivery is verified, not just asserted:** the emitter's `notice_text_seen` must contain the exact nonce and the control's must not; every listed frame must be an existing, non-empty file inside the arm's `out/` (hashed into the outcome); both arms need a collected transcript. Anything missing gives `INCONCLUSIVE`. **Pins are enforced:** `prep` and `finish` refuse a Claude Code version other than the pin, and the classifier requires `claude_version` to equal the pin and every transcript `message.model` to equal the pinned model without its `[...]` suffix. The transcript records `claude-opus-4-8` where the stream init reports `claude-opus-4-8[1m]`. A mismatch gives `NOT_EXECUTED`, and an unrecorded model gives `INCONCLUSIVE`. **A passing verdict also needs an evidence review of BOTH captures:** a `capture_review.json` per arm (`finish` writes a pre-filled template). It names the reviewer, is bound by SHA-256 to that arm's recording and listed frames (frames are now required and verified for the control too), and states per frame whether it shows the nonce. The emitter review must confirm the nonce in at least one frame, and the control review must find it in none. Without both, a result that would pass is `INCONCLUSIVE` (`capture review pending`); the operator's observation alone never passes. |

**Known collision (reported, not decided).** If Claude Code surfaces the Stop `systemMessage` as a stream-json `system` event (the docs mention an `SDKInformationalMessage`) that appears only in the emitter arm, the unchanged strict host-event subtype rule makes the headless run `INCONCLUSIVE`, and therefore H1c too. A test pins this. Changing it would need its own reviewed rule; the raw evidence allows reclassification without a re-run. The A1-headless run (#560) showed that this collision did **not** occur on 2.1.202. The notice was recorded only as a transcript `hook_system_message`, which R4 (#561) categorises.

**Offline validation (stub only, NOT evidence):**
- `python -m pytest -q …/harness/selftest`: **103 passed**, of which 51 are A1 tests. They cover:
  - the emitter's shape;
  - setup for all four A1 arms;
  - `safe_rmtree_a1` refusing H1 and archive names;
  - headless: dropped notice → `NOT_DELIVERED` with no interference; stream event → strict-rule `INCONCLUSIVE`; re-entry → host interference; model delivery → `DELIVERED_TO_AGENT`; model reply differences → evidence only;
  - interactive: developer-only → `DELIVERED_TO_USER_ONLY`; not seen → `NOT_DELIVERED`; no return to the prompt, an unexpected prompt, or re-entry → `DELIVERED_WITH_SIDE_EFFECT`; missing recording or frames, or the control showing the notice → `INCONCLUSIVE`; model reply differences → evidence only;
  - combine: pass, interference fail, and `INCONCLUSIVE` blocking a pass;
  - #556 review negatives: observed text without the nonce, control text containing it, a missing, empty or escaping frame path, a missing transcript in either arm → `INCONCLUSIVE`; a version or model mismatch → `NOT_EXECUTED`; an unrecorded model → `INCONCLUSIVE`; verified frame hashes on a pass;
  - #556 review round 2: a pass needs confirmed reviews of both captures; a missing emitter or control review, missing control frames, a review not bound to the recording, a reviewed-frame hash mismatch, a review not confirming the nonce, a control review finding it, or no reviewer named → `INCONCLUSIVE`;
  - R4 (#561), using the stub's `transcript` mode, which writes the `hook_success` + `hook_system_message` shape recorded in #560:
    - R4 positive → `host_output`; the headless run → `NOT_DELIVERED` with no interference, recording the R1–R4 rule id;
    - wrong `hookEvent` → unclassified → `INCONCLUSIVE`;
    - no emitter invocation for the event → unclassified;
    - nonce outside `attachment.content` → unclassified → `INCONCLUSIVE`;
    - R4 never yields `model_bound` or `DELIVERED_TO_AGENT` by itself, even with a forced echo;
    - a co-present unrecognised attachment is not masked → `INCONCLUSIVE`;
    - interactive: capture-reviewed developer delivery → `DELIVERED_TO_USER_ONLY` and a combined pass, and a notice that isn't seen → `NOT_DELIVERED`.
- **The runners were run end to end under `H1_SELFTEST=1`** in the A1 root: the headless pair, and both interactive arms through prep, a stub session, a filled observation, finish, classify and combine. The H1 live root and the H1 archive were not touched; the archive re-verified. The A1 self-test output was removed with `safe_rmtree_a1.py`.

**Running from PowerShell (when authorized).** Use your own window, never inside Claude Code:

```powershell
& "C:\Program Files\Git\bin\bash.exe" -l "<harness>/run_a1_headless.sh"
& "C:\Program Files\Git\bin\bash.exe" -l "<harness>/prep_a1_interactive.sh" H1c-sm-int-ctl
```

## Amendment A2: H1a and H1b re-pinned to Claude Code 2.1.310 (offline-validated only)

**Nothing here has run live.** The live run needs a separate, explicit go-ahead. The specification is probe scope §4.3 (proposed in the same PR as this harness change).

| File | Role |
|---|---|
| `pins.env` (A2 pin set) | Selected only by `run_h1.sh A2`, which exports `H1_PINSET=A2` (the C3 `C3_PINSET=G3` pattern). Claude Code `2.1.310 (Claude Code)`, `--model claude-opus-5-5` (`PIN_MODEL_FLAG`), paths H1a-edit, H1a-bash and H1b-start only, root `C:\dev\d5p2-h1-a2-live`, guarded delete `safe_rmtree_a2.py`. An unknown or empty `H1_PINSET` aborts; `run_h1.sh` refuses to start whenever `H1_PINSET` is already set in the environment (even empty), with or without an argument, and never overwrites it; `pins_a1.env` refuses any, including empty. Without a pin set, every H1 value is unchanged. **`pins.local.env` may set `PY` only:** every pinned value (host version, model, model flag, live root, guarded delete, paths, settings sources, pin set) is snapshotted before it is sourced, and any change or unset aborts, naming the variables. This applies to the H1 pins too. |
| `safe_rmtree_a2.py` | `safe_rmtree.py` with an exact delta: the A2 root, the six A2 arms, and `PROTECTED` covering the H1 and A1 live roots, both archives and `C:\dev\d5p2-h1c-a1-attempts`. |
| `run_h1_probe.sh` | The arm must belong to the active pin set; A2 needs `DISABLE_AUTOUPDATER=1`; `claude --version` is checked against the pin immediately before **every** session; `--model` is passed when the pin set defines one; `observer.txt` records `pinset`, `model_flag` and the checked `claude_version`. |
| `classify_h1.py` | `pair … <pin_model> [<pin_version>]`: with a version pin (A2 always passes one), an arm whose recorded `claude_version` differs, or is unrecorded, gives `NOT_EXECUTED`. `verify` and `summary` take an optional comma-separated path subset. Only an all-four summary carries the `H1 gate` line; a subset summary carries a `Listed-path result` that names the missing paths and says it is not the H1 gate. Either result is `PASS` only when every included path records the same host version; mixed or unrecorded versions give `NOT MET` with a `Host pin not established` note (review of #794). The summary now shows each path's host version. |
| `selftest/claude`, `stub_claude.py` | The stub answers with the active pin set's version (`H1_STUB_VERSION`) and, like the host, takes its session model from `--model`. |

**Offline validation (stub only, NOT evidence):**
- `python -m pytest -q …/harness/selftest`: **161 passed** (58 in `test_a2_harness.py`). They cover:
  - the A2 root, arms and protected trees, including refusal of every Stop and A1 arm name;
  - path selection (default, order, refusal of unknown, duplicate or empty subsets);
  - the subset `verify`, and a subset summary that never prints the H1 gate line;
  - `--model` plumbing: present → `DELIVERED_TO_AGENT`, absent → `NOT_EXECUTED` under the A2 model pin;
  - the version pin: match → pass; a mismatch in either arm, or no recorded version → `NOT_EXECUTED`; no pin → H1 behavior;
  - shell plumbing through Git Bash: A2 and default pin values, unknown pin set, `pins_a1.env` refusing a pin set, Stop arms refused under A2, and `run_h1.sh` refusing an unknown pin set argument;
  - #794 review regressions: an all-four set with H1c on another version, or with an unrecorded version, is `NOT MET` (never an H1 `PASS`); a mixed-version subset is never a listed-path `PASS`; an environment `H1_PINSET` is refused before the preflight, with no argument, the same argument, or a different one. A mutation check (rule disabled) failed all four version tests;
  - second #794 review: a `pins.local.env` that overrides the A2 host version is refused, and so is one that overrides or unsets any other pinned value (model, model flag, live root, Windows root, guarded delete, paths, sources, the A2 pins, the pin set), for the H1 pins too; a `PY`-only file is accepted and the pins hold. An empty `H1_PINSET` is refused by `run_h1.sh`, `pins.env` and `pins_a1.env`. These tests copy `pins.env` into a temporary directory, so the operator's real `pins.local.env` is never touched. A mutation check with the guard disabled failed all 12 override tests.
- **`run_h1.sh A2` was run end to end under `H1_SELFTEST=1`** in the A2 root: preflight OK, all three pairs `DELIVERED_TO_AGENT` (stub), `Listed-path result … PASS`, with every init event reporting `claude-opus-5-5` and every observer `2.1.310 (Claude Code)`. Without `DISABLE_AUTOUPDATER=1` it aborted at the preflight. `C:\dev\d5p2-h1-live` was not touched. The A2 root was emptied afterwards through `safe_rmtree_a2.py`.

**Running it live (when authorized).** Use your own window, never inside Claude Code, with `claude --version` printing `2.1.310 (Claude Code)`, `PY` set in `pins.local.env`, and no `MNEME_*`, `CLAUDECODE`, `H1_SELFTEST`, `H1_LIVE` or `H1_PINSET` variables:

```powershell
$env:DISABLE_AUTOUPDATER = "1"
& "C:\Program Files\Git\bin\bash.exe" -l "<harness>/run_h1.sh" A2
```

The evidence goes to `C:\dev\d5p2-h1-a2-live`. Collection with `collect_h1.py` and the record `docs/validation/dg1f-t08-d5-p2-host-path-h1-a2-<date>.md` form a separate evidence PR.

## Amendment A3: H1c (A1 track) re-pinned to Claude Code 2.1.310 (offline-validated only)

**Nothing here has run live.** The live runs need a separate, explicit go-ahead. The specification is probe scope §4.4 (proposed in the same PR as this harness change).

| File | Role |
|---|---|
| `pins_a1.env` (A3 pin set) | Selected only by `A1_PINSET=A3`, which the A1 entry points set from their first argument `A3`. Claude Code `2.1.310 (Claude Code)`, `--model claude-opus-5-5` (`PIN_MODEL_FLAG`), root `C:\dev\d5p2-h1c-a3-live` (`A1_LIVE_W`), guarded delete `safe_rmtree_a3.py` (`A1_RMTREE`). An unknown or empty `A1_PINSET` aborts. Without it every A1 value is unchanged. `A1_PINSET` is in the `pins.env` snapshot, so `pins.local.env` can neither set nor clear it. |
| `safe_rmtree_a3.py` | `safe_rmtree_a1.py` with an exact delta: the A3 root, and `PROTECTED` covering the H1, A1 and A2 roots, every archive and `C:\dev\d5p2-h1c-a1-attempts`. Same four arm names. |
| `run_a1_headless.sh [A3]` | Pin-set selection from the argument only. An inherited `A1_PINSET` is refused, even empty. Under A3 the headless classifier gets the version pin. |
| `run_a1_probe.sh` | The root and guarded delete come from the pin set. A3 needs `DISABLE_AUTOUPDATER=1`. `claude --version` is checked immediately before **every** session (A1 too, since a mismatch only aborts). `--model` is passed when the pin set defines one. `observer.txt` records `pinset`, `model_flag`, `disable_autoupdater` and the checked `claude_version`. |
| `prep_a1_interactive.sh [A3] <arm>` | Pin-set selection, the A3 root and `DISABLE_AUTOUPDATER`. It records `pinset` and `model_flag`. Under A3 it prints hardened operator steps for one window: auto-updater off, version check, `--model`, stop if signed out, the prompt sent once, no `/model` or `/login`, at least 30 s idle, `/exit`. |
| `finish_a1_interactive.sh [A3] <arm> <recording>` | Pin-set selection and `DISABLE_AUTOUPDATER` under A3. It refuses an arm prepared under another pin set. The version check refuses **without writing into the arm**. It prints the exact `classify_a1.py interactive` and `combine` commands for the active pins. |
| `classify_a1.py` | `headless <live> <pin_model> [<pin_version>]`: with a version pin, an arm whose recorded version differs, or is unrecorded, gives `NOT_EXECUTED`. Both arms' versions are recorded under `a1.claude_versions`. `combine` first requires both headless versions and the interactive pin to be present and equal (`NOT_EXECUTED` otherwise), and records `host_version`. |
| `preflight.sh`, `selftest/claude` | Under an A1 pin set they read `pins_a1.env`. The preflight reports the pin set and checks `DISABLE_AUTOUPDATER` for A3. `run_h1.sh` refuses an inherited `A1_PINSET`. |

**Offline validation (stub only, NOT evidence):**
- `python -m pytest -q …/harness/selftest`: **277 passed** (43 in `test_a3_harness.py`). They cover:
  - the A3 root, arms and protected trees;
  - the headless version pin: match, mismatch in either arm, unrecorded, and no pin (A1 behavior);
  - `combine` on one version, and `NOT_EXECUTED` for mixed versions (including A1 headless plus A3 interactive) or an unrecorded version, checked before any passing label;
  - the A3 and default A1 pin values, and unknown or empty `A1_PINSET`;
  - `pins.local.env` unable to set, export or clear `A1_PINSET`;
  - every entry point and `run_h1.sh` refusing an inherited `A1_PINSET`;
  - `DISABLE_AUTOUPDATER` required by the probe, prep, finish and preflight under A3, with the preflight's success line checked exactly;
  - `--model` in the probe.

  The `test_a1_harness.py` headless fixture now records the host version, as the runner does.
- **Mutation checks:** all 12 A3 mutants were caught, plus a broken preflight line continuation (a real bug found in the stub self-test and fixed).
- **`run_a1_headless.sh A3` was run end to end under `H1_SELFTEST=1`**, together with `prep_a1_interactive.sh A3` and `finish_a1_interactive.sh A3` for the control arm, all in the A3 root:
  - the preflight reported pin set A3, `DISABLE_AUTOUPDATER=1` and `2.1.310`;
  - the observers recorded `pinset=A3`, `model_flag=claude-opus-5-5` and `2.1.310`, and the init event reported `claude-opus-5-5`;
  - the stub's default `stream` mode reproduced the known A1 collision (`INCONCLUSIVE`);
  - a stub version of `2.1.311` at finish was refused with nothing written.

  The A3 root was emptied afterwards through `safe_rmtree_a3.py`.
- **Incident during the self-test (fixed):** one `finish_a1_interactive.sh` call was made **without** `A3`, so it targeted the A1 root. The leftover attempt-2 control arm there received a new `harness_failure.txt` from the old failure path. The file was removed. That arm's file set and hashes match the preserved `2026-10-19-ctl-attempt2` copy, and nothing else in the A1 root or archive changed. `finish` now refuses on the version check without writing.

**Running it live (when authorized).** Use your own windows, never inside Claude Code, with `claude --version` printing `2.1.310 (Claude Code)`, `PY` set in `pins.local.env`, and no `MNEME_*`, `CLAUDECODE`, `H1_SELFTEST`, `H1_LIVE`, `H1_PINSET` or `A1_PINSET` variables:

```powershell
$env:DISABLE_AUTOUPDATER = "1"
& "C:\Program Files\Git\bin\bash.exe" -l "<harness>/run_a1_headless.sh" A3
& "C:\Program Files\Git\bin\bash.exe" -l "<harness>/prep_a1_interactive.sh" A3 H1c-sm-int-ctl
```

Then follow the printed steps for the control arm, then for `H1c-sm-int`, then the capture reviews, `classify_a1.py interactive` and `combine`. The evidence goes to `C:\dev\d5p2-h1c-a3-live`. The record `docs/validation/dg1f-t08-d5-p2-host-path-h1c-a3-<date>.md` goes in a separate evidence PR.

## Finished-batch guard: kept evidence is never touched

`guard_finished.sh` is sourced by every runner and probe and runs **before the script's first write**. It changes nothing; it only refuses:

| Script | Refuses when |
|---|---|
| `run_h1.sh`, `run_h1_probe.sh` | the root holds `H1_DONE` or `summary_h1.md` |
| `run_a1_headless.sh`, `run_a1_probe.sh` | the root holds `A1_HEADLESS_DONE` or `outcome_a1_headless.json` |
| `prep_a1_interactive.sh`, `finish_a1_interactive.sh` | the root holds `outcome_a1_interactive.json` or `outcome_a1.json`, **or** the arm is already finished (its `observer.txt` records `recording_sha256`) |

The interactive steps deliberately ignore the headless markers, because the interactive pair follows the headless pair in the same root. An unfinished batch (`H1_INCOMPLETE`, `A1_HEADLESS_INCOMPLETE`) may still be re-run.

**To start a new batch in a root that holds a finished one:** archive the root (copy plus SHA-256 listing), then empty it (`safe_rmtree*.py delete <arm>` per arm, and remove the batch files). There is no override flag.

`finish_a1_interactive.sh` now validates `observation.json` **before** writing anything. An incomplete observation leaves the arm unfinished, and `finish` can be re-run once the observation is filled in.

**Why.** On 2026-11-13 a mutation check of #802 disabled a pin-set guard. The shell test then ran `run_h1.sh A2` against the kept A2 root, which deleted `H1_DONE` and `summary_h1.md` and overwrote `run_h1.log` before aborting at the preflight. The files were restored from `C:\dev\d5p2-h1-a2-archive\2026-11-11`, and the root again verifies 74/74.

**Rule for mutation checks:** never mutate a runner while running tests that execute it. Those tests use the real, fixed roots, so a disabled guard can let the runner write. `selftest/test_finished_batch_guard.py` executes no runner: it exercises the helper only on temporary directories and checks each call site's position from the source. Mutate the guard only against that file.

**Offline validation:**
- `python -m pytest -q …/harness/selftest`: **293 passed** (16 in `test_finished_batch_guard.py`).
- **Mutation checks:** 12 mutants, all caught, run against that file only. They covered the helper exiting, the helper matching the arm, the helper writing, each removed or late call site, prep keying on the headless markers, and `finish` validating after writing.
- **Replaying the incident:** `run_h1.sh A2`, `run_h1.sh` and `run_a1_headless.sh` against the kept A2, H1 and A1 roots each refused with `nothing was changed`.
- **Evidence trees:** the H1, A1, A2 and A3 roots, the archives and the A1 attempts were byte-identical before and after.

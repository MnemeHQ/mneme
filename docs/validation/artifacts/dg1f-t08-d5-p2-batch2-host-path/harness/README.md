# Batch-2 (H4a, H6a, H6b) host-output-path channel probe harness

**Status: offline-validated only. No live probe, shape discovery or host session has been run, and none is authorized by this harness or its PR.** Live execution needs a separate, explicit owner go-ahead.

This harness implements **batch 2** of the accepted probe scope [`docs/plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md`](../../../../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md), as reordered by Amendment A4 (§4.5). It covers:
- **H4a**: Antigravity;
- **H6a**: Hermes tool-call notice;
- **H6b**: Hermes context injection.

A4 was owner-accepted in #825 (squash `5dfc0ea4`). Its in-file status and the squash title still read PROPOSED, because the PR merged before its retitle. The acceptance is recorded in the #825 PR description.

It follows the scope's emitter, paired-control, evidence, safety and non-interference rules (§3, §3.1, §6, §7, §8).

**A live run is blocked today by the discrepancies in §2.** The harness reports them and does not resolve them. Its pin checks refuse a live run until they are resolved.

> **Deferred (probe-scope Amendment A5 and charter Amendment A3, PROPOSED 2026-11-18):** H4a, H6a and H6b are deferred out of the Phase 2 gate as `DEFERRED (not run)`, and never pass. This whole harness now serves deferred paths only: it is kept intact, and runs only on a concrete need. The batch-3 condition in §3 ("H4a, H6a and H6b all pass") is superseded, and no later batch depends on this harness. D3 (refuted), D4 (candidate T unapproved) and D5 stay recorded.

## 1. Accepted contract, verified before building

| Item | Accepted contract (probe scope) | Verified against | Result |
|---|---|---|---|
| H4a surface | Antigravity adapter, PreToolUse command hook (§4) | `docs/integrations/antigravity.md`; the public hooks page (`antigravity.google/docs/hooks`, read 2026-11-18) | Same surface: `.agents/hooks.json`, `PreToolUse`, a command hook with stdin/stdout JSON. |
| H4a candidate shape | "to be determined: `{}` plus a stderr reason, or a JSON reason field" (§4); shape discovery first (§5) | same | Both are built: A is `{}` with stderr; B is `{"reason"}` with no `decision`. **The current public page differs, see D2.** |
| H4a path type | command hook, tool event (§3.1) | same | Unchanged. |
| H6a surface | "`pre_tool_call` offers `block` or nothing, so a non-blocking notice may need next-turn context" (§4) | hermes-agent source at the 0.19.0 tag `v2026.7.20`: `hermes_cli/plugins.py`, `model_tools.py`, `hermes_cli/oneshot.py`, `hermes_cli/_parser.py`, `website/docs/user-guide/features/hooks.md` | **Confirmed.** `pre_tool_call` honors only `{"action": "block"\|"approve"}`. `block` vetoes the tool; `approve` escalates to human approval; any other return is ignored. **A further surface exists, see D4.** |
| H6b surface | `pre_llm_call` `{"context"}` (§4) | same, plus `agent/turn_context.py`, `hermes_state.py` and `agent/conversation_loop.py` | **Confirmed.** Context is appended to the API copy of the current turn's user message. The sent text is persisted as that row's `api_content` (see D3). |
| H6 path type | in-process callback (§3.1) | same | Unchanged. The control returns `None` ("no opinion"). |
| H6 live model | D2: a live model session is needed for H6 | — | Unchanged. The live path refuses without operator-supplied credentials. |

## 2. Pin checks and discrepancies (reported, not resolved)

The pin checks ran on 2026-11-18. They were read-only: nothing was installed or downloaded.

| # | Discrepancy | Evidence | Effect | Needs |
|---|---|---|---|---|
| **D1** | **The Antigravity pin `2.8.1` is not the installed host, and its availability is unconfirmed.** The installed IDE is **`2.17.0`** (`Antigravity.exe` FileVersion), with an auto-updater feed configured (`resources/app-update.yml`). The official releases page renders client-side and listed no versions to a static fetch. A public developer-forum thread reports 404s on older (1.x) download links. | `check_pins.py antigravity <exe>` → MISMATCH | H4a live arms refuse to prepare. A live `prepare` requires the installed executable, not a version string. | Owner decision: obtain `2.8.1`, or re-pin by a reviewed amendment (§7). The harness never re-pins. |
| **D2** | **The current Antigravity hook contract differs from the 2.8.1 contract that the accepted scope and the adapter rely on.** The public hooks page says `decision` is **required** on PreToolUse output, and lists `allow` as "proceeds, delegating to the next hook or default policy". The repository's 2.8.1 notes say `"allow"` **auto-grants**. The page describes `reason` as "the explanation shown to the agent or to you for the decision", and lists no `additionalContext` or `systemMessage` for PreToolUse. | the page as read 2026-11-18 (no version stated on it); `docs/integrations/antigravity.md` "Policy" | If `decision` is required on the probed host, candidates A and B may both be rejected, and Antigravity fails closed. That gives `NO_NONBLOCKING_CHANNEL` and A4's stop rule. A candidate carrying `decision` (for example `{"decision": "allow", "reason": …}`) is **not** built, because `decision` carries permission semantics and the accepted scope excludes `allow`. | Owner decision, with D1: which host version's contract governs H4a, and whether a decision-carrying candidate may enter shape discovery. |
| **D3** | **Refuted by source: the injected context *is* in the host's own session record.** The `invoke_hook` docstring calls `pre_llm_call` context "ephemeral, never persisted to session DB", but the 0.19.0 code says otherwise. `compose_user_api_content` stamps the exact sent text onto the turn's user message as `api_content`, "persisted alongside the clean content" (`agent/turn_context.py`), and `messages.api_content` is a column (`hermes_state.py`). The stamp is skipped only in MoA mode and with `api_mode == codex_app_server`. | the 0.19.0 source | A nonce in that `role=user` row is `model_bound` in the host's own record (§3 step 2), so H6b and N need no owner decision. The `pre_api_request` observer reads the raw `request_messages` list (unsanitised; the payload cap is raised anyway). It is supplementary: never counted by default, and used only to judge whether a record is complete. | Nothing, unless a live arm runs in a mode that skips the stamp. Then the arm is `INCONCLUSIVE`, and `--accept-observer-record` exists only for an owner decision. |
| **D4** | **hermes-agent 0.19.0 has a surface the accepted contract does not name: `transform_tool_result`.** It runs after a tool returns and before the result is appended to the conversation, and its first string return replaces the result. | `model_tools.py`, `hooks.md` at the 0.19.0 tag | It is a candidate non-blocking tool-call notice. It is included as **H6a candidate T, after the accepted wording's candidate N**. Because T rewrites a tool result, its control adds the middleware rule: the result is otherwise unchanged (§3.1). **T is never bound without the owner's decision:** `h6_classify.py path H6a` treats T as pending unless `--accept-candidate-T` is given, and while T is pending, H6a cannot fail. | Owner acceptance before T can be bound (shape binding, §3 step 5). |
| **D5** | **`-z/--oneshot` cannot drive a two-turn session.** The source settles this. `-z` goes to `run_oneshot(prompt, model, provider, toolsets, usage_file)`, which takes no session argument, so `--continue`/`--resume` are ignored. It also forces `HERMES_YOLO_MODE=1` and `HERMES_ACCEPT_HOOKS=1` (`hermes_cli/oneshot.py`). | `hermes_cli/main.py`, `oneshot.py`, `_parser.py` at the 0.19.0 tag | The harness does not use `-z`. Every arm uses `hermes chat -Q -q <prompt>` (non-interactive single query). Candidate N's second turn uses `--resume <session_id>` with the session the plugin recorded in turn 1, and N emits only when turn 2's session equals turn 1's. If resume fails, N is `NOT_EXECUTED`. The runtime behavior of `chat -q` and `--resume` is unverified until shape discovery. | Settled by shape discovery. |
| — | **hermes-agent `0.19.0` is installable.** `pip index versions hermes-agent` lists `0.19.0` as the newest release on the configured index. Upstream GitHub has later tags (`0.21.x`) that this index does not list. It is not installed on this machine. | `pip index versions` (metadata only) | none | The operator installs it into a dedicated environment at harness-run time. That interpreter is the one that runs the host (`python -m hermes_cli.main`), so the pin applies to the binary that actually runs. |

## 3. What it does and does not do

- **The emitters are harness-only.** `h4a_emitter.py` and `h6_plugin/` replace the Mneme adapter and plugin and run no Mneme code. So no `[layer1-freeze]` amendment is needed, and nothing under `mneme/` changes (§3 step 1).
- **Every emitter arm gets a fresh nonce** (`MNEME-PROBE-<16 hex>`), written to `out/nonce.txt`. It never appears in a prompt, hook config or environment variable. Only this arm's own nonce counts: the observer records a hash of each match.
- **Paired controls.** Each emitter arm has a `-ctl` arm with the same workspace, hook registrations and prompt. Every callback there returns the host's "no opinion" value: `{}` for H4a, `None` for H6.
- **H6a and H6b are separate.** They use different arms, nonces, `HERMES_HOME` directories, sessions and outcome files, and are summarized separately (`outcome.H6a.json`, `outcome.H6b.json`). A pair whose control belongs to another path or candidate is `NOT_EXECUTED`.
- **Attribution (§3 step 4, §6).** A control failure counts as host-induced (`DELIVERED_WITH_SIDE_EFFECT`) only in these cases:
  - the permission prompt changed (H4a);
  - the identical tool call, with the workspace path masked from the argument hash, ran cleanly in the control but not with the emitter;
  - the host demonstrably altered the annotated result (H6a T).

  A permission prompt that differs on a *different* call is model-chosen, and so is `INCONCLUSIVE`. A failure that cannot be attributed is **`INCONCLUSIVE`, never a failing label**. Examples are a failed turn, a different model-chosen call, and a record that is not available. The controls:
  - **H4a:** the tool executed, no host error or block, the same permission prompt as the control, and the same file bytes when the tool input was the same.
  - **H6a:** the probed tool dispatched with no error.
  - **H6b:** every planned turn completed.
- **Absence is evidence only when the record is complete.**
  - H4a's `NOT_DELIVERED` needs a copied transcript that has been shown to carry model-bound tool results.
  - H6's `NOT_DELIVERED` needs every observed request to carry a non-empty raw `request_messages` list.
  - Otherwise the arm is `INCONCLUSIVE`.
- **The session dump skips the FTS5 virtual tables and their shadow tables** (`messages_fts`, `messages_fts_trigram`). They copy message text without a role and would otherwise create unclassified locations.
- **Developer delivery (H4a) comes only from a named reviewer's capture review.** It must be bound to the recording, give the host version shown, and give a fixed `nonce_ui_location`. A nonce seen in the agent's own reply (`agent_reply`) is an echo, never developer delivery. An echo without model-bound delivery is `INCONCLUSIVE`, whatever the developer saw.
- **Shape discovery is pre-registered.** H4a tries candidate A, then B. H6a tries N, then T, with T pending D4. A path takes the first eligible passing candidate as its bound shape. With none passing:
  - an unresolved or pending candidate leaves the path unresolved;
  - if no candidate was accepted by the host without side effects, the path is `NO_NONBLOCKING_CHANNEL` (§6).
- **Under A4's positive gate**, batch 3 starts only when H4a, H6a and H6b all pass, or on an owner decision. A failing label goes to the owner for the D5 revisit (charter §5).
- **Live guards (§7):**
  - the pinned live root `C:\dev\d5p2-batch2-live`, with no loadable marker in the root or any ancestor;
  - no `CLAUDECODE` and no `MNEME_*` variable;
  - a verifiably committed harness;
  - for H4a, no user-level Antigravity hook source (`~/.gemini/config/hooks.json`, or a plugin's `hooks.json`);
  - for H6, an allowlisted host environment: system variables, the named credential variables and the arm's own `HERMES_HOME` with only `plugins.enabled: [mneme_probe]`;
  - a credential leak scan of every evidence file.
- **It does not establish:**
  - that Mneme emits these shapes, since nothing is implemented;
  - other host versions or models;
  - repeatability (n = 1 plus control, D4);
  - that an agent acts on a notice;
  - anything about agent-controlled settings.

## 4. Files

| File | Role |
|---|---|
| `pins.env` | The pins: Antigravity `2.8.1`, hermes-agent `0.19.0` (source tag `v2026.7.20`), the live root, and the **names** (never the values) of the provider-credential variables. |
| `check_pins.py` | A read-only pin check: the Antigravity executable's FileVersion, or the hermes-agent version in a given Python. It reports MATCH or MISMATCH and never re-pins. |
| `common.py` | Shared code: nonce, notice text, labels, JSON I/O, the live-root and environment guards, the Antigravity user-hooks guard, the leak scan, and the path summary (pre-registered order, pending candidates). |
| `h4a_emitter.py` | Modes `empty-stderr` (A), `reason-only` (B) and `noop` (control). It always writes exactly one JSON object to stdout, never a `decision`, and exits 0. It logs selected envelope fields, the emitted bytes, and a hash of the masked tool arguments. |
| `h4a_arm.py` | `prepare`: the guards (in a live run: pinned root, installed executable at the pin, committed harness, no user hooks), a disposable workspace with `.agents/hooks.json`, the nonce, the prompt, and a review template. `finish`: the after-state, the copied host transcript, and the recording SHA-256. |
| `h4a_classify.py` | `pair` and `path`. The transcript table is provisional: an unclassified location gives `INCONCLUSIVE`. Contains the review validation and the attribution rules. |
| `h6_plugin/` | The harness Hermes plugin (`mneme_probe`). Every mode registers the same five hooks. Modes: `h6b-context`, `h6a-next-turn` (same session only), `h6a-transform` and `noop`. `pre_tool_call` never returns a directive. The observers record key paths, roles and hashes, never values: the `pre_api_request` observer reads the raw `request_messages`, and the argument hashes have the workspace path masked. State persists in `out/`. |
| `h6_arm.py` | `prepare`; `run --selftest` (the stub); `run --live` (guards, `python -m hermes_cli.main chat -Q -q`, `--resume` for N's second turn; never MoA or `codex_app_server`). It then backs up every SQLite session file (WAL-safe), dumps the ordinary tables to `session.jsonl` (FTS tables skipped), and runs the leak scan. |
| `h6_classify.py` | `pair` and `path`, separately for H6a and H6b. `--accept-observer-record` applies D3 and `--accept-candidate-T` applies D4, each only after an owner decision. |
| `selftest/stub_antigravity.py`, `selftest/stub_hermes.py` | **Not the hosts, and never evidence.** The Hermes stub mirrors the 0.19.0 contract in §1: `chat -q`, `--resume`, the `api_content` stamp, the FTS5 mirror table, the raw `request_messages` and sanitised `request`, the directive rules and transform semantics. Its counterfactual behaviors, and the Antigravity decision-required rule (D2), are test knobs. |
| `selftest/test_batch2_harness.py` | 46 offline tests (§6). |

## 5. Operator procedure (documented only; NOT authorized)

From an external terminal, never inside Claude Code, with no `MNEME_*` variable set:
1. **Resolve D1, D2 and D4 with the owner first.** Until D1 is resolved, `h4a_arm.py prepare` refuses.
2. **H4a.** Run the arms in order: `h4a-A-ctl`, `h4a-A`, then `h4a-B-ctl`, `h4a-B` (B only if A did not pass). For each arm:
   - `prepare <root> <arm> --antigravity <Antigravity.exe>`;
   - a screen-recorded IDE session in that workspace with the printed prompt;
   - `finish --recording <file>`;
   - a named reviewer completes `capture_review.json`.

   Then run `h4a_classify.py pair <root> A|B` and `path`.
3. **H6.** Install hermes-agent `0.19.0` in a dedicated environment, and put the credentials in the shell only.
   - `prepare` the arms `h6b-ctl`, `h6b`, `h6a-N-ctl`, `h6a-N`, `h6a-T-ctl` and `h6a-T`.
   - For each arm: `run --live --python <py> --model <m> --provider <p>`.
   - Then run `h6_classify.py pair` for each pair, and `path H6b` and `path H6a`.
4. **Evidence.** One validation record per gate batch (§8), in its own PR, after redaction and a clean leak scan.

## 6. Self-tests

```
python -m pytest docs/validation/artifacts/dg1f-t08-d5-p2-batch2-host-path/harness/selftest -q -p no:cacheprovider
```

46 tests, using the stubs only. Like the H1 harness self-tests, they sit outside the repository's `testpaths` (`tests`), so CI does not collect them. They are run for the harness PR. They cover:
- **Emitters:** every mode, and misuse.
- **H4a outcomes:** delivered to agent, user only, not delivered and side effect.
- **H4a evidence rules:**
  - a differing permission prompt on the identical call (side effect) or a different call (`INCONCLUSIVE`);
  - decision-required fail-closed;
  - review completeness, recording binding and pin;
  - an agent-reply echo never counting as developer delivery;
  - absence needing a transcript with tool results;
  - identical versus different tool input;
  - a nonce in the control;
  - an unclassified transcript location.
- **H4a live refusals:** a version string, a pin mismatch, and arm reuse.
- **Path summary:** `NO_NONBLOCKING_CHANNEL` and pending candidates.
- **H6b:**
  - context found in the host's `api_content` record;
  - a skipped stamp (`INCONCLUSIVE`, and the owner-decision flag);
  - dropped context with a complete record (`NOT_DELIVERED`);
  - a missing raw record (`INCONCLUSIVE`);
  - a truncated sanitised copy not affecting completeness;
  - FTS tables never dumped.
- **H6a:**
  - T (passes; an altered result is a side effect; a dropped return is not delivered);
  - N across two processes, found in the host record, and N whose resume lands in a new session (`NOT_EXECUTED`);
  - T needing the D4 decision before it binds.
- **H6 attribution and setup:**
  - a tool that was never called;
  - a failed turn (`INCONCLUSIVE`);
  - an identical call failing only with the emitter (side effect);
  - H6a/H6b separation, and mismatched pairs.
- **H6 live refusals.**
- **Guards:** the live-root, environment, Antigravity user-hooks, leak-scan and pin guards.

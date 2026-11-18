# Batch-2 (H4a, H6a, H6b) host-output-path channel probe harness

**Status: offline-validated only. No live probe, shape discovery or host session has been run, and none is authorized by this harness or its PR.** Live execution needs a separate, explicit owner go-ahead.

This harness implements **batch 2** of the accepted probe scope [`docs/plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md`](../../../../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md), as reordered by Amendment A4 (§4.5, #825, `5dfc0ea4`): **H4a** (Antigravity), **H6a** (Hermes tool-call notice) and **H6b** (Hermes context injection). It follows the scope's emitter, paired-control, evidence, safety and non-interference rules (§3, §3.1, §6, §7, §8).

**The live run is blocked today by the discrepancies in §2.** The harness does not resolve them. It reports them, and its pin checks refuse a live run until they are resolved.

## 1. Accepted contract, verified before building

| Item | Accepted contract (probe scope) | Verified against | Result |
|---|---|---|---|
| H4a surface | Antigravity adapter, PreToolUse command hook (§4) | `docs/integrations/antigravity.md`; the public hooks page (`antigravity.google/docs/hooks`, read 2026-11-18) | Same surface: `.agents/hooks.json`, `PreToolUse`, a command hook with stdin and stdout JSON. |
| H4a candidate shape | "to be determined: `{}` plus a stderr reason, or a JSON reason field" (§4); shape discovery first (§5) | same | Both candidates are built (A: `{}` with stderr; B: `{"reason"}` with no `decision`). **The current public page differs, see D2.** |
| H4a path type | command hook, tool event (§3.1) | same | Unchanged. |
| H6a surface | "`pre_tool_call` offers `block` or nothing, so a non-blocking notice may need next-turn context" (§4) | hermes-agent source at the 0.19.0 tag `v2026.7.20` (`hermes_cli/plugins.py`, `model_tools.py`, `website/docs/user-guide/features/hooks.md`) | **Confirmed.** `pre_tool_call` honors only `{"action": "block"\|"approve"}`. A `block` vetoes the tool; an `approve` escalates to human approval. Every other return is ignored. **A further surface exists, see D4.** |
| H6b surface | `pre_llm_call` `{"context"}` (§4) | same | **Confirmed.** Context is appended to the current turn's user message. **It is "ephemeral, never persisted to session DB"; see D3.** |
| H6 path type | in-process callback (§3.1) | same | Unchanged. The control returns `None` ("no opinion"). |
| H6 live model | D2: a live model session is needed for H6 | — | Unchanged. The live path refuses without operator-supplied credentials. |

## 2. Pin checks and discrepancies (reported, not resolved)

Pin checks ran on 2026-11-18. They were read-only: nothing was installed or downloaded.

| # | Discrepancy | Evidence | Effect | Needs |
|---|---|---|---|---|
| **D1** | **The Antigravity pin `2.8.1` is not the installed host, and its availability is unconfirmed.** The installed IDE is **`2.17.0`** (`Antigravity.exe` FileVersion), with an auto-updater feed configured (`resources/app-update.yml`). The official releases page renders client-side and listed no versions to a static fetch. A public developer-forum thread reports 404s on older (1.x) download links. | `check_pins.py antigravity <exe>` → MISMATCH | H4a live arms refuse to prepare (`h4a_arm.py prepare` checks the pin). | Owner decision: obtain `2.8.1`, or re-pin through a reviewed amendment (§7). The harness never re-pins. |
| **D2** | **The current Antigravity hook contract differs from the 2.8.1 contract that the accepted scope and the adapter rely on.** The public hooks page says `decision` is **required** on PreToolUse output, and lists `allow` as "proceeds, delegating to the next hook or default policy". The repository's 2.8.1 notes say `"allow"` **auto-grants**. The page describes `reason` as "the explanation shown to the agent or to you for the decision". It lists no `additionalContext` or `systemMessage` for PreToolUse. | the page as read 2026-11-18 (version not stated on it); `docs/integrations/antigravity.md` "Policy" | If `decision` is required on the probed host, candidates A and B may both be rejected, and Antigravity fails closed. That would give `NO_NONBLOCKING_CHANNEL` and trigger A4's stop rule. A shape carrying a `decision` (for example `{"decision": "allow", "reason": …}`) is **not** built: a `decision` field carries permission semantics, and the accepted scope excludes `allow`. | Owner decision, together with D1: which host version's contract governs H4a, and whether a decision-carrying candidate may enter shape discovery. |
| **D3** | **H6b (and H6a candidate N) context is never in the host's own session record.** On 0.19.0, `pre_llm_call` context is "ephemeral, never persisted to session DB" (`plugins.py` `invoke_hook` docstring). The scope's primary evidence is the nonce in a model-bound message "in the host's own session record" (§3 step 2). | the 0.19.0 source | Recorded delivery for these shapes cannot come from the session DB. The harness records a `pre_api_request` observer (a plugin callback the host dispatches with the outgoing request), but **does not count it by default**, so such arms classify `INCONCLUSIVE`, never a false `NOT_DELIVERED`. | Owner decision: whether the host-dispatched `pre_api_request` record counts as recorded delivery. If yes, re-classify with `--accept-observer-record` (no re-run). |
| **D4** | **hermes-agent 0.19.0 has a surface the accepted contract does not name: `transform_tool_result`.** It runs after a tool returns and before the result is appended to the conversation; its first string return replaces the result, and the session DB records it. | `model_tools.py`, `hooks.md` at the 0.19.0 tag | It is a candidate non-blocking tool-call notice that would appear in the host's own record. The harness includes it **as shape-discovery candidate T, tried after the accepted wording's candidate N**. Because it rewrites a tool result, its control adds the middleware rule: the result is otherwise unchanged (§3.1). | Owner acceptance before T can be bound as H6a's shape (shape binding, §3 step 5). |
| **D5** | **Two-turn continuation is unverified.** Candidate N needs a second turn. `-z/--oneshot` and `-c/--continue` exist in `hermes_cli/main.py` at the tag, but their combined behavior is not verified. | the 0.19.0 source | If `-c` does not continue the session, N's second turn starts a new session, and N is `NOT_EXECUTED` (the emitter never emits). | Confirmed or refuted by shape discovery itself. |
| — | **hermes-agent `0.19.0` is installable.** `pip index versions hermes-agent` lists `0.19.0` as the newest release on the configured index. Upstream GitHub has later tags (`0.21.x`) that this index does not list. The package is not installed on this machine. | `pip index versions` (metadata only) | none | The operator installs it into a dedicated environment at harness-run time. |

## 3. What it does and does not do

- **The emitters are harness-only.** `h4a_emitter.py` and `h6_plugin/` replace the Mneme adapter and plugin, and run no Mneme code. No `[layer1-freeze]` amendment is needed, and no file under `mneme/` changes (§3 step 1).
- **Fresh nonce per emitter arm** (`MNEME-PROBE-<16 hex>`), written to `out/nonce.txt`. It is never in a prompt, hook config or environment variable. The prompt only mentions the prefix.
- **Paired controls.** Every emitter arm has a `-ctl` arm with the same workspace, hook registration and prompt, where every callback returns the host's "no opinion" value: `{}` for H4a, `None` for H6.
- **H6a and H6b are kept separate.** They use different arms, nonces, `HERMES_HOME` directories, sessions, outcome files and path summaries (`outcome.H6a.json`, `outcome.H6b.json`). A pair whose control belongs to another path or candidate is `NOT_EXECUTED`.
- **Shape discovery is pre-registered.** H4a tries A then B; H6a tries N then T. A path takes the first passing candidate as its bound shape. With none passing:
  - an unresolved candidate (`NOT_EXECUTED`, `INCONCLUSIVE`) leaves the path unresolved, to be re-run first (D4);
  - if no candidate was accepted by the host without side effects, the path is `NO_NONBLOCKING_CHANNEL` (§6).
- **Under A4's positive gate**, batch 3 starts only when H4a, H6a and H6b all pass, or on an owner decision. Any failing label goes to the owner for the D5 revisit (charter §5).
- **It does not establish:** that Mneme emits these shapes (nothing is implemented); other host versions or models; repeatability (n = 1 plus control, D4); that an agent acts on a notice; or anything about agent-controlled settings.

## 4. Files

| File | Role |
|---|---|
| `pins.env` | Antigravity `2.8.1`, hermes-agent `0.19.0` (source tag `v2026.7.20`), live root `C:\dev\d5p2-batch2-live`, and the **names** of the provider-credential variables (never values). |
| `check_pins.py` | Read-only pin check: the Antigravity exe FileVersion, or the hermes-agent version in a given Python. It reports MATCH or MISMATCH and never re-pins. |
| `common.py` | Nonce, notice text, labels, JSON I/O, the live-root guard (no Git checkout, no ancestor `.git`, `.mneme`, `.agents/hooks.json`, `.hermes/plugins` or `.claude/settings.json`), the environment guard (`CLAUDECODE`, `MNEME_*`), the Antigravity user-level hooks guard (`~/.gemini/config/hooks.json`, plugin `hooks.json`), the credential leak scan, and the path summary. |
| `h4a_emitter.py` | Modes `empty-stderr` (A), `reason-only` (B) and `noop` (control). Always exactly one JSON object on stdout, never a `decision`, exit 0. Logs selected envelope fields and the exact emitted bytes. |
| `h4a_arm.py` | `prepare`: guards and pin check, a disposable workspace with `.agents/hooks.json`, the nonce, the prompt and a capture-review template. `finish`: after-state, the copied host transcript (`transcriptPath`), and the screen recording bound by SHA-256. |
| `h4a_classify.py` | `pair` (one candidate against its control) and `path` (shape-discovery summary). Developer delivery comes only from a named reviewer's `capture_review.json`, bound to the recording and recording the host version shown. The transcript table is provisional (unclassified → `INCONCLUSIVE`). |
| `h6_plugin/` | The harness Hermes plugin (`mneme_probe`). The same five hooks are registered in every mode. Modes `h6b-context`, `h6a-next-turn`, `h6a-transform` and `noop`. `pre_tool_call` never returns a directive. The `pre_api_request` and `post_tool_call` observers record key paths, roles and hashes, never values. State persists in `out/` across `-z` turns. |
| `h6_arm.py` | `prepare`: workspace, plugin copy, a per-arm `HERMES_HOME` with only `plugins.enabled: [mneme_probe]`, nonce and prompts. `run --selftest` uses the stub. `run --live` refuses unless the pin, environment, credential presence, a clean harness and the real executable all check out. It then dumps every SQLite session file to `session.jsonl` and runs the leak scan. |
| `h6_classify.py` | `pair` and `path` for H6a and H6b separately. The `--accept-observer-record` flag applies D3 only after an owner decision. |
| `selftest/stub_antigravity.py`, `selftest/stub_hermes.py` | **Not the hosts, never evidence.** The Hermes stub mirrors the 0.19.0 contract in §1. Its behaviors, and the Antigravity stub's decision-required rule (D2), are test knobs. |
| `selftest/test_batch2_harness.py` | 34 offline tests (§6). |

## 5. Operator procedure (documented only; NOT authorized)

From an external terminal, never inside Claude Code, with no `MNEME_*` variable set:
1. **Resolve D1–D4** with the owner first. Until D1 is resolved, `h4a_arm.py prepare` refuses.
2. **H4a**, for each arm in the order `h4a-A-ctl`, `h4a-A`, then `h4a-B-ctl`, `h4a-B` (B only if A did not pass):
   - `prepare` with `--antigravity <Antigravity.exe>`;
   - a screen-recorded IDE session in that workspace, with the printed prompt;
   - `finish --recording <file>`;
   - a named reviewer completes `capture_review.json`;
   - then `h4a_classify.py pair <root> A|B` and `path`.
3. **H6**, with hermes-agent `0.19.0` in a dedicated environment and credentials in the shell only:
   - `prepare` for `h6b-ctl`, `h6b`, `h6a-N-ctl`, `h6a-N`, then `h6a-T-ctl`, `h6a-T`;
   - `run --live --hermes <exe> --python <py> --model <m> --provider <p>` for each arm;
   - then `h6_classify.py pair` for each pair, and `path H6b` and `path H6a`.
4. **Evidence.** One validation record per gate batch (§8) in its own PR, after redaction and a clean leak scan.

## 6. Self-tests

```
python -m pytest docs/validation/artifacts/dg1f-t08-d5-p2-batch2-host-path/harness/selftest -q -p no:cacheprovider
```

The 34 tests use the stubs only. Like the H1 harness self-tests, they sit outside the repository's `testpaths` (`tests`), so CI does not collect them; they are run for the harness PR. They cover:
- every emitter mode, including misuse;
- H4a delivery to the agent, to the user only, not delivered, with a side effect, decision-required fail-closed, a missing review, review binding and pin, a nonce in the control, an unclassified transcript location, a refused live pin mismatch, and no arm reuse;
- the path summary, including `NO_NONBLOCKING_CHANNEL`;
- H6b ephemeral context (not counted by default; counted only with the D3 flag; counted when the host persists it; not delivered when unrecorded and unechoed);
- H6a T (passes in the host record; an altered result is a side effect; a dropped return is not delivered), H6a N across two processes, the probed tool not called (`NOT_EXECUTED`), a failed turn (side effect), H6a/H6b separation, and mismatched pairs;
- live refusals (the stub as host, a missing pin, a selftest flag on a live arm);
- the live-root, environment, Antigravity user-hooks, leak-scan and pin guards.

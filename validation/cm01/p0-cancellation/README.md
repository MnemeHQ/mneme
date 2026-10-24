# CM-01-P0-01 — In-Flight MCP Cancellation Validation

**Status:** bounded diagnostic complete. **Verdict: FAIL** in two independent runs.

**Baseline:** `ddeb85eec8f7734edde1c921250592d51afedbee` (squash merge of S1-A1, PR #627)
**Scope:** validation only. No production change, no S1-A2, no ADR-034 M4 change, no S1-A1 evidence change.

## Repository state during the runs

The declared baseline is `ddeb85ee`. During the session the working tree fast-forwarded to an upstream docs-only commit, `0d367fc6` (PR #628, one new ADR-034 M4 results document). The recorded runs therefore executed at `0d367fc6`.

This drift is recorded explicitly in `evidence/verdict.json`:

- `git diff ddeb85ee..0d367fc6 -- validation/cm01 mneme` is empty; the code under test is unchanged.
- The reused executor, M1 fixture, pre-migration fixture, M4 fixture, and M4 guard are byte-identical to `ddeb85ee` (SHA-256 compared against the baseline blobs).
- No commit was made by this validation; the only working-tree delta is the new `validation/cm01/p0-cancellation/` directory.
- The M4 guard is anchored at `HEAD`, so it measures this validation's delta rather than unrelated upstream main commits. It reports no violation. The upstream M4 document that arrived during the session is listed separately in `m4_validation_scope.upstream_m4_docs_arrived_during_session`.

## Question

When the local QuickJS executor times out while awaiting a genuine MCP `client.callTool()` request, does the underlying MCP operation also terminate, or does it remain outstanding?

This experiment stalls a real MCP request at the **transport-response boundary**. It does **not** prove or disprove cancellation of tool code already executing on the server.

## Topology

```text
Code Mode tool (@cloudflare/codemode/browser 0.5.5)
  -> QuickJSExecutor (validation/cm01/s1a-local/e0/quickjs-executor.mjs, unchanged)
  -> M2 four-method read-only adapter (replicated in the runner, instrumentation only)
  -> @modelcontextprotocol/sdk 1.32.2 Client.callTool()
  -> StdioClientTransport
  -> test-only stdio relay (relay.mjs)
  -> genuine `python -m mneme decision-mcp` over stdio
  -> frozen M1 synthetic canonical fixture (ADR-9901)
```

The relay forwards the real `tools/call` upstream, waits for the genuine upstream response, withholds that response from the client, reports the withhold over a loopback control channel, and releases it only on an explicit harness command after the post-timeout observation.

## Controls and fault injection

Each independent run performs three fresh-process phases:

1. **Control — direct**: real Decision MCP, Code Mode `decision.get("ADR-9901")`, successful canonical response.
2. **Control — relay passthrough**: same call through the relay with no withholding. Proves the relay is transparent and distinguishes normal completion from cancellation.
3. **Fault — withheld response**: same call through the relay in `withhold` mode.
   - Upstream request and response are confirmed by relay events.
   - The executor deadline is 1500 ms; normal upstream latency is far shorter.
   - The response is withheld before the deadline.
   - The client request state is sampled at Code Mode timeout, at executor cleanup, and after a 1500 ms bounded observation window.
   - The held response is then released and the harness records whether it still settles the request.
   - Cleanup is explicit and records relay/upstream child exit.

## Measured result

| Measurement | Run 1 and Run 2 |
|---|---|
| Executor timeout | `Code execution failed: execution exceeded 1500ms`; `stats.timedOut: true` |
| MCP request initiated | JSON-RPC id `2`, `tools/call`, `decision.get`, `{"record_id":"ADR-9901"}` |
| MCP response withheld | Relay event `response_withheld` after `upstream_response_received` |
| MCP client promise at timeout | **pending** |
| MCP client promise after 1500 ms window | **pending** |
| Cancellation signal | **absent** — 0 `notifications/cancelled` sent; relay observed 0 |
| Client/transport lifecycle | Transport open; client not closed; upstream child alive |
| Late completion | Released response **fulfilled** the abandoned client request |
| Host cleanup | `cleanupErrors: []`, `pendingAtEnd: 0` (not used as cancellation proof) |
| Process cleanup | Relay and upstream both exited; no surviving children |

The decisive observations are the pending client promise **and** the late fulfillment. `executor.stats().pendingAtEnd === 0` is reported for completeness only and is explicitly **not** treated as evidence of MCP cancellation: the executor rejects and disposes its own deferred handle in `finally` while the MCP client promise remains outstanding.

The M2 adapter calls `client.callTool({ name, arguments })` with no options. In MCP SDK 1.32.2, `Protocol.request` emits `notifications/cancelled` only when an `AbortSignal` aborts or the SDK's own 60s request timeout fires. The experiment's 1500 ms post-timeout window is well below that SDK timeout, so an observed notification would have come from the integration; none was observed.

## Why this is FAIL

Acceptance requires the integration itself to cancel or terminate the outstanding client request within a bounded period, with no late revival. Instead:

- The request was still pending when Code Mode returned its timeout error.
- It was still pending after the bounded observation period.
- No cancellation notification was emitted.
- The withheld late response still settled the request (the executor stats even recorded a post-timeout `resolvedCalls` increment).
- Settling required harness release, not integration behavior.

The result is reproducible across two independent runs (`repeatable: true`) and no frozen artifact changed (`no_mutation.pass: true`).

## Smallest potential correction boundary

Analysis only; nothing was implemented.

Host-call boundary: the adapter/executor bridge would need to propagate an `AbortSignal` (or equivalent cancellation token) from QuickJS timeout cleanup into `client.callTool()` and await transport-level settlement. This would exercise the MCP SDK's existing `notifications/cancelled` path. It would still not establish server-side cancellation of code that is already executing.

## Evidence verification

The recorded FAIL has been independently verified against both runs, relay logs, child-process logs, source versions, fixture hashes, and baseline preservation.

- `verify-evidence.mjs` — read-only verifier (46 checks, optional clean-checkout reproduction).
- `evidence/verification.json` — machine-readable verification record.
- `VERIFICATION.md` — human-readable verification record.

```text
node verify-evidence.mjs
node verify-evidence.mjs --reproduce
```

The verifier preserves the original FAIL classification and does not modify `verdict.json`, `run1.json`, or `run2.json`.

## Artifacts

- `run-cancellation.mjs` — test runner (two independent runs, controls, fault, cleanup, verdict).
- `relay.mjs` — instrumented stdio relay and loopback control channel.
- `evidence/run1.json`, `evidence/run2.json` — full per-run observations.
- `evidence/verdict.json` — PASS/FAIL/BLOCKED, exact reason, identities, preservation checks.
- `evidence/versions.json` — pinned execution versions.
- `evidence/raw/*-relay.jsonl` — raw relay events.
- `evidence/raw/*-child-events.jsonl` — raw upstream child stdin/stdout/spawn/exit events.
- `evidence/raw/*-child-stderr.log` — raw upstream child stderr.
- `evidence/raw/*-harness-events.jsonl` — raw harness transport/cleanup events.
- `evidence/raw/runner-console.log` — console capture.

`evidence/verdict.json` records SHA-256 identities for the reused fixture, pre-migration fixture, executor, relay, runner, M4 guard, and lockfile.

## Reproduction

Requires the S1-A1 pinned toolchain (Node 24.13.1, npm 11.8.0, Python 3.12.10) and the repository Python package importable via `PYTHONPATH`.

From `validation/cm01/p0-cancellation/`:

```text
npm ci --ignore-scripts --no-audit --no-fund
npm run p0
```

The merged executor imports `quickjs-emscripten` from its own module tree, so the documented S1-A1 dependencies must also be present:

```text
cd ../s1a-local
npm ci --ignore-scripts --no-audit --no-fund
cd ../p0-cancellation
npm run p0
```

This installs only gitignored `node_modules/`; no tracked S1-A1 artifact is modified. The runner verifies S1-A1 tracked-file hashes and git status before and after.

Exit code is `0` for PASS, `1` for FAIL, `2` for BLOCKED.

## Hard boundaries honored

- No production Mneme or executor modification.
- No S1-A1 artifact or closure record modification.
- No proposal tool or production memory.
- No Cloudflare Workers, credentials, or live model.
- No enforcement or performance claim.
- No ADR-034 M4 change.
- No corrective implementation.
- No milestone closure.

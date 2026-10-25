# CM-01-P0-01-F1 - MCP Cancellation Correction

**Status:** local implementation and validation complete. **Verdict: PASS** in two independent runs.
**Baseline:** `adf50933d0beac255ac2a134e00ee13d40442302`.
**Scope:** isolated experimental correction and validation. No production, S1-A2, Cloudflare Workers, ADR-034 M4, or dependency upgrade.

## What was corrected

The frozen S1-A1 executor and P0 evidence are not modified. This package contains a **versioned executor** derived from:

```text
validation/cm01/s1a-local/e0/quickjs-executor.mjs
SHA-256 4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313
```

The F1 executor adds:

1. Optional provider context: `fn(args, { signal, callId })`.
2. One `AbortController` per host call, never a shared execution signal.
3. Timeout/cleanup abort of active, unsettled calls only.
4. Explicit `hostSettled` / `deferredSettled` guards to prevent double settlement and post-disposal callbacks.
5. A bounded cancellation drain. The provisional 100 ms grace was measured, then finalized at **50 ms**.
6. Deterministic final statistics: `cancelledCalls`, `cancelledSettled`, `cancelledUnsettled`, `cancelledRejections`, `cancelledLateSuccess`, `drainMs`, and the grace value.

The adapter is new and forwards the signal using the pinned SDK API:

```js
client.callTool({ name, arguments: args }, undefined, { signal });
```

The relay withholds or delays genuine upstream responses. The synthetic MCP server provides a slow async tool that observes cooperative cancellation.

## P0 failure signature vs F1 behavior

| Measurement | Original P0 | Corrected F1 |
|---|---|---|
| MCP client promise | pending after executor timeout and after the window | in flight at the deadline, then rejected within the 50 ms bound |
| Client error | none | `McpError` code `-32001` |
| Cancellation notifications | 0 | exactly 1, matching request id |
| Late withheld response | fulfilled the abandoned request | ignored; request remained rejected |
| Executor cancellation stats | not present | `cancelledCalls: 1`, `cancelledSettled: 1`, `cancelledUnsettled: 0` |
| Original verdict | **FAIL** | unchanged; F1 is a separate correction |

The original P0 FAIL and both raw runs are untouched.

## Measured cancellation bound

**Provisional:** 100 ms. **Calibration:** 16 cancellations across both runs; max 3 ms, min 1 ms, mean 1.875 ms. **Finalized:** 50 ms (16.7x the measured maximum). **Final run:** 16 samples, max 4 ms, mean 1.5625 ms. Calibration summary: `evidence/calibration-100ms.json`. Final measured latency: `evidence/measurements.json`.

## Regression matrix results

Both runs executed the full matrix with fresh processes:

| Check | Result |
|---|---|
| F1-N1-CONTROL-DIRECT | PASS |
| F1-N2-CONTROL-RELAY | PASS |
| F1-T1-TIMEOUT-SETTLES | PASS |
| F1-T2-LATE-NO-REVIVAL | PASS |
| F1-C1-RACE-BEFORE | PASS |
| F1-C2-RACE-BOUNDARY | PASS |
| F1-C3-RACE-AFTER | PASS |
| F1-C3-PARALLEL | PASS |
| F1-R1-SEQUENTIAL | PASS |
| F1-R2-REPEATED | PASS |
| F1-F1-TRANSPORT-CLOSE | PASS |
| F1-F2-TIMEOUT-THEN-CLOSE | PASS |
| F1-A1-VALIDATION | PASS |
| F1-A2-MCP-ISERROR | PASS |
| F1-A3-PROPOSALS | PASS |
| F1-S1-GENUINE-CANCEL-FRAME | PASS |
| F1-S2-SYNTHETIC-CANCEL | PASS |
| F1-P1-CLEANUP | PASS |
| F1-P1-NO-POST-DISPOSAL | PASS |
| F1-NO-UNHANDLED | PASS |

Highlights:

- Normal four-method Code Mode results are byte-identical to direct MCP results for the frozen M4 fixture.
- Timeout cancellation sends exactly one matching notification; completed calls receive zero notifications.
- Parallel and sequential cases cancel only the outstanding request.
- Transport close yields `-32000` with no cancellation; timeout-then-close retains `-32001`.
- The genuine server receives the cancellation frame after its withheld response (F1-S1). The synthetic async server receives cancellation and suppresses its response (F1-S2).
- All relay/upstream/server children exited; no survivors, no unhandled rejections, no post-disposal host settlements.

## Preservation

- S1-A1 tracked digest before/after: `cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57` (unchanged).
- No diff or status change under `validation/cm01/s1a-local/` or `validation/cm01/p0-cancellation/`.
- P0 evidence files match the merged HEAD blobs; P0 verification remains `VERIFIED`.
- Frozen executor hash remains `4b960124...`.
- M4 guard passes before and after.
- Only `validation/cm01/p0-f1/` is new.

## Versions

Node `24.13.1`, npm `11.8.0`, `@cloudflare/codemode` `0.5.5`, `@modelcontextprotocol/sdk` `1.32.2`, `ajv` `8.17.1`, `quickjs-emscripten` `0.32.0`, `zod` `4.6.7`, Python `3.12.10`, `mneme` `0.10.0`, Python `mcp` `2.2.0`.

## Reproduce

From `validation/cm01/p0-f1/`:

```text
npm install --ignore-scripts --no-audit --no-fund
node run-f1.mjs
```

Exit code `0` is PASS; `1` is FAIL.

## Limitations

- Client settlement and cancellation dispatch are proven. Server-side thread termination is **not** claimed.
- The genuine Decision MCP tools are synchronous and fast; in-progress server cancellation is observed only through the synthetic async server.
- MCP cancellation notification delivery is fire-and-forget. Evidence records transport dispatch and server receipt, not an acknowledgement.
- The correction is validation-only; no production adapter, S1-A2, Cloudflare Workers, or ADR-034 M4 work is included.

## Evidence

- `evidence/run1.json`, `evidence/run2.json` - full per-run matrix.
- `evidence/verdict.json` - structured PASS/FAIL, checks, hashes, preservation, P0 comparison.
- `evidence/measurements.json` - final cancellation latency and grace bound.
- `evidence/calibration-100ms.json` - preserved provisional-grace calibration summary.
- `evidence/versions.json` - pinned versions.
- `evidence/raw/` - relay JSONL, child event/stderr logs, harness events, host events, synthetic server logs, per-phase raw output.


# CM-01 S1-A1 — E0 local executor proof

**Status:** E0 only. PASS. No Mneme MCP connection, mutation enforcement, approvals, replay, rollback, production authority, or M4 assets are involved.

## Scope

E0 proves that:

- `@cloudflare/codemode/browser` `createBrowserCodeTool.execute()` runs a fixed async JavaScript function through a custom local QuickJS executor;
- three sequential `await`ed synthetic host calls preserve invocation and result order;
- host errors propagate as execution errors;
- timeout/cancellation is enforced and pending host calls are cleaned up;
- the QuickJS memory limit produces an out-of-memory execution error;
- Node filesystem, network, process, module, and runtime globals are absent from the sandbox.

E0 does **not** prove:

- `CodemodeRuntime`, `McpConnector`, `codemode.search`, `codemode.describe`, approvals, replay, or rollback;
- Mneme MCP connectivity;
- any enforcement or evidence semantics.

## Base and provenance

| Item | Value |
|---|---|
| Current-main base | `942de7b121994647e99e9b862b44cda784c0ae84` |
| S0 source | `9eb4057a290795883076ab05bf11c92038c6ca13` |
| Worktree | `.worktrees/feat-cm01-s1a1-e0-local-executor` |
| Branch | `feat/cm01-s1a1-e0-local-executor` |
| M4 guard | Pass; no M4 path changed or untracked |

The M4 guard checks committed (`BASE...HEAD`), staged, unstaged, and untracked paths against the protected M4 list.

## Pinned dependencies

| Dependency | Version |
|---|---|
| Node.js | `v24.13.1` |
| npm | `11.8.0` |
| `@cloudflare/codemode` | `0.5.5` |
| `quickjs-emscripten` | `0.32.0` |
| `@cloudflare/codemode/browser` | exported by `0.5.5`; no `cloudflare:workers` import |

`ai`, `agents`, MCP SDK, Wrangler, Cloudflare account, Worker Loader, tunnels, and remote hosting are not required for E0.

## Exact commands

From `validation/cm01/s1a-local/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m4-guard
npm run probe:native
npm run e0
```

For a clean reproduction after the lockfile exists:

```text
npm ci --ignore-scripts --no-audit --no-fund
npm run m4-guard
npm run probe:native
npm run e0
```

## Native promise bridging decision

`probe-native-promise.mjs` evaluates native QuickJS promise bridging first:

- three sequential host calls;
- each host call returns a delegated QuickJS promise;
- host completion resolves the promise and calls `runtime.executePendingJobs()`;
- the result and start/end sequence must be `["a", "b", "c"]`.

The probe passed. **Asyncify was not selected.** If the native probe fails, stop rather than silently switching to Asyncify.

## E0 checks

| Check | Evidence |
|---|---|
| `E0-ORDER` | `createBrowserCodeTool.execute()` runs three awaited host calls in order |
| `E0-ERROR` | Host failure at `b` propagates; `c` never runs |
| `E0-TIMEOUT` | 60 ms timeout; pending call cancelled and cleaned up |
| `E0-MEMORY` | 8 MiB QuickJS memory limit produces `out of memory` |
| `E0-GLOBALS` | Node globals are `undefined`; only `codemode`/`globalThis` exist |
| `E0-CLEANUP` | Zero pending deferreds, active host calls, and host timers |
| `E0-REPEAT` | Two fresh order runs match exactly |
| `E0-M4` | M4 guard passes before and after |

## Evidence

- `evidence/e0.json` — structured results, versions, checks, M4 guard, limitations.
- `evidence/raw/e0.log` — raw check/native-probe/version record.

Generated evidence is retained under `evidence/`; `node_modules/` is ignored.

## Security notes

- Node's `vm` is not used.
- The sandbox is QuickJS WASM in the host process, with explicit memory, stack, and interrupt limits.
- No Node `process`, `require`, `fetch`, `Buffer`, `module`, `exports`, `__dirname`, Deno, or Bun globals are exposed.
- Host calls are synthetic only; no credentials, project memory, proposal tools, or Mneme MCP.
- The fixed code is authored for E0; no live model-generated code is executed.

## Stop

E0 stops here. M1–M8 require separate review and authorization.

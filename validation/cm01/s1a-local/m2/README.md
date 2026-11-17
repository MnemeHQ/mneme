# CM-01 S1-A1 — M2 local Code Mode-to-Mneme MCP integration

**Status:** M2 only. PASS. No M3–M8 acceptance tests, proposal tools, production memory, Cloudflare Workers, tunnel, live model, or credentials.

## Scope

M2 proves:

- `@cloudflare/codemode/browser` + the existing E0 QuickJS executor can invoke Mneme’s four read-only Decision MCP methods through a local stdio client;
- the upstream MCP inventory remains exactly six tools;
- the Code Mode adapter exposes only the four read methods;
- MCP JSON input schemas are passed through unchanged and validated at the host boundary;
- sanitized JavaScript method names are stable and collision-free;
- one fixed Code Mode script invokes `decision.get`, `decision.search`, `decision.applicable_to`, and `decision.trace` successfully against synthetic canonical memory;
- proposal methods are not exposed to sandbox code;
- MCP errors and host validation errors propagate instead of becoming empty successes;
  - the MCP error probe deliberately bypasses host validation so a server-side `isError` is exercised through actual Code Mode execution;
  - the normal adapter validates arguments at the host boundary before any MCP call;
- fixture state and M4 assets remain unchanged.

M2 does **not** claim full output parity or enforcement compatibility.

## Reuse

| Item | Reused |
|---|---|
| E0 executor | `../e0/quickjs-executor.mjs` |
| E0 evidence | untouched |
| M1 canonical fixture | `../m1/fixture/canonical/project_memory.json` |
| M1 evidence | untouched |
| M1 empty cwd | `../m1/empty-cwd` |

## Pinned dependencies

| Dependency | Version |
|---|---|
| Node.js | `v24.13.1` |
| npm | `11.8.0` |
| `@cloudflare/codemode` | `0.5.5` |
| `@modelcontextprotocol/sdk` | `1.32.2` |
| `ajv` | `8.17.1` |
| `zod` | `4.6.7` |
| Python | `3.12.10` |
| `mneme-hq` | `0.10.0` |
| Python `mcp` | `2.2.0` |

## Exact commands

From `validation/cm01/s1a-local/m2/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m2
```

The child server command is:

```text
python -m mneme decision-mcp --memory <m1-canonical-fixture> --proposals ""
```

## Checks

| Check | Evidence |
|---|---|
| `M2-UPSTREAM-SIX-1` | Run 1 upstream inventory is exactly six |
| `M2-UPSTREAM-SIX-2` | Run 2 upstream inventory is exactly six |
| `M2-ALLOWLIST` | Adapter contains the four read methods only |
| `M2-NO-COLLISIONS` | Sanitized method names are unique |
| `M2-SCHEMA-PASSTHROUGH` | Adapter schemas hash-identical to upstream schemas |
| `M2-SUCCESS-1` | Four successful read calls in fixed order, typed results |
| `M2-SUCCESS-2` | Same on independent startup |
| `M2-NO-PROPOSAL-METHODS` | `decision_propose` / `decision_propose_batch` are `undefined` in sandbox |
| `M2-MCP-ERROR-PROPAGATES` | Invalid search input reaches MCP and returns `isError`, not empty success |
| `M2-HOST-VALIDATION` | Invalid `record_id` is rejected at host boundary before any MCP call |
| `M2-REPEAT` | Normalized run evidence equal |
| `M2-NO-MUTATION` | Fixture, pre-migration, repo memory, proposal state, empty cwd unchanged |
| `M2-M4` | M4 guard passes before and after |

## Evidence

- `evidence/m2.json` — versions, fixture hashes, both runs, checks, M4 guard.
- `evidence/run1.json` / `run2.json` — full upstream tools, adapter schemas, calls, arguments, responses, errors.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr, including the expected rejected search probe.
- `evidence/commands.txt` — exact commands and observed results.

## Boundaries

No proposal tool was invoked or exposed. No M3–M8 acceptance test was run. No merge or compatibility claim was made.

M2 stops here.

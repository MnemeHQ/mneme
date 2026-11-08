# CM-01 S1-A1 — M3 `decision.get` output parity

**Status:** M3 only. PASS. No M4–M8 acceptance tests, proposal calls, production memory, Cloudflare Workers, tunnel, live model, or credentials.

## Scope

M3 proves that `decision.get(ADR-9901)` returns the same complete normalized structured payload through:

1. the direct Node MCP client, and
2. the local `@cloudflare/codemode/browser` + QuickJS path using the M2 four-method read-only adapter behavior.

M3 does not claim enforcement compatibility, performance, or any result beyond this single retrieval.

## Reuse

| Item | Reused |
|---|---|
| E0 executor | `../e0/quickjs-executor.mjs` |
| E0 evidence | untouched |
| M1 canonical fixture | `../m1/fixture/canonical/project_memory.json` |
| M1 evidence | untouched |
| M2 four-method read-only adapter behavior | same allowlist, schema passthrough, host validation, result handling |
| M2 evidence | untouched |

Only `decision.get` is exercised; the adapter’s other three read methods remain available but unused.

## Comparison contract

- Direct path: `CallToolResult.structuredContent` from `client.callTool`.
- Code Mode path: `ProxyToolOutput.result` from `createBrowserCodeTool.execute`.
- Compared payloads: complete normalized JSON objects, with object keys sorted only for comparison.
- Dropped payload fields: none.
- Excluded only transport-envelope fields: `content`, `structuredContent`, `isError`, `toolResult`.
- Differences are recorded recursively; none were found.

## Canonical identity verification

The returned record was checked against the frozen fixture’s canonical identities:

- `decision_id`: `ADR-9901`
- `version`: `1`
- `version_id` / `decision_version_id`: `dver-3c2da75d06c5a5ce73807f025fc1d5c9`
- `content_digest`: `662dae53252e95830a73cd93cf2fe129a21ffb39e6f3a159073cce860f233650`
- `lifecycle_status`: `active`
- `constraints`: `["no external cache service"]`
- `relationships`: `[]`
- `derived_rule_ids`: `["ADR-9901:FORBID_LITERAL:4e447d86bf0efac6f035d836c80c7584"]`

## Checks

| Check | Result |
|---|---|
| `M3-UPSTREAM-SIX-1` | PASS |
| `M3-UPSTREAM-SIX-2` | PASS |
| `M3-DIRECT-CODE-PARITY-1` | PASS — zero differences |
| `M3-DIRECT-CODE-PARITY-2` | PASS — zero differences |
| `M3-IDENTITY-1` | PASS |
| `M3-IDENTITY-2` | PASS |
| `M3-NO-DROPPED-FIELDS` | PASS |
| `M3-SCHEMA-PASSTHROUGH` | PASS |
| `M3-NO-PROPOSAL-CALLS` | PASS — one `decision.get` call per run |
| `M3-REPEAT` | PASS — normalized evidence equal |
| `M3-NO-MUTATION` | PASS |
| `M3-M4` | PASS |

## Exact commands

From `validation/cm01/s1a-local/m3/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m3
```

The run starts two independent MCP server processes.

## Evidence

- `evidence/m3.json` — versions, hashes, both runs, checks, normalization, M4 guard.
- `evidence/run1.json` / `run2.json` — raw direct and Code Mode envelopes, normalized payloads, recursive differences, adapter calls, fixture identity.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `evidence/commands.txt` — exact commands and observed results.

## Boundaries

No proposal method was invoked. No M4–M8 test was run. No merge or compatibility claim was made.

M3 stops here.

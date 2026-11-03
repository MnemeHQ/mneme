# CM-01 S1-A1 — M8 failure-behavior probes

**Status:** M8 only. PASS. No merge, no S1-A1 closure claim, no M9 tests.

## Probes

| Probe | Result |
|---|---|
| **E1 — typed not-found** | `decision.get("ADR-9999")` → `not_found`; `decision.trace("ADR-9999")` → `trace_not_found`; direct/Code Mode complete payload parity |
| **E2 — host argument validation** | Non-string `record_id` rejected before MCP; zero upstream calls; not classified as `not_found` |
| **E3 — MCP tool rejection** | Invalid search lifecycle filter returned direct MCP `isError`; Code Mode failed with matched MCP-tool rejection classification; test-only validation bypass used |
| **E4 — transport failure** | Disconnected synthetic MCP child produced a transport failure, no result, one attempted upstream call, pending calls `0` |
| **E5 — missing Decision Index** | Section-less memory refused startup with migration prerequisite; no handshake, no fallback, no implicit migration, file unchanged |
| **E6 — executor failure** | Isolated QuickJS timeout failed execution; no result; pending calls `0`; host calls/timers `0` |

## Error classes

- E1 remains successful typed data, not a transport error.
- E2 is host-boundary argument validation, not `not_found`.
- E3 is an MCP tool rejection, not an empty success.
- E4 is a transport failure, not a fabricated decision.
- E5 is a startup/configuration refusal, not a fallback index.
- E6 is an executor timeout, distinct from MCP tool failure.

## Checks

| Check | Result |
|---|---|
| `M8-UPSTREAM-SIX-1` | PASS |
| `M8-UPSTREAM-SIX-2` | PASS |
| `M8-E1-TYPED-NOT-FOUND` | PASS |
| `M8-E2-HOST-VALIDATION` | PASS |
| `M8-E3-MCP-REJECTION` | PASS |
| `M8-E4-TRANSPORT-FAILURE` | PASS |
| `M8-E5-MISSING-INDEX` | PASS |
| `M8-E6-EXECUTOR-FAILURE` | PASS |
| `M8-NO-PROPOSAL-CALLS` | PASS |
| `M8-REPEAT` | PASS — normalized evidence equal |
| `M8-NO-MUTATION` | PASS |
| `M8-M4` | PASS |

## Evidence details

- E1 direct and Code Mode not-found payloads had zero recursive differences.
- E2 error: `Argument validation failed for decision.get`; upstream calls `0`.
- E3 direct `isError: true`; Code Mode result `null`; one upstream call; normal validating adapter preserved for all other probes.
- E4 used `client.close()` to disconnect before the tool response; result `null`; transport error recorded.
- E5 stderr explicitly requested migration:

```text
has no authoritative decision_index section
Preview the migration: mneme decision-index migrate --memory ...
```

The section-less file remained section-less and unchanged.
- E6 reused the E0 QuickJS timeout mechanism; `timedOut: true`, pending `0`.

## Preservation and isolation

- E0–M7, original M4 and M4-F1 evidence unchanged; before/after hashes equal.
- M1 and M4-F1 fixtures unchanged.
- M8 section-less disposable file unchanged.
- Repository memory unchanged.
- Proposal store absent.
- Empty cwd unchanged.
- M4 protection guard: `pass: true`, `violations: []`.
- No proposal tool invoked.
- No production code, ADR, enforcement, canonical memory, or ADR-034 M4 asset changed.

## Exact commands

From `validation/cm01/s1a-local/m8/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m8
```

The run performs two independent iterations.

## Evidence

- `evidence/m8.json` — verdict, versions, fixture hashes, both runs, all checks, preservation hashes, M4 guard.
- `evidence/run1.json` / `run2.json` — raw E1–E6 results, classifications, call counts and cleanup.
- `evidence/run1-stderr.log` / `run2-stderr.log` — normal server stderr.
- `evidence/e4-run*-stderr.log` — disconnected transport stderr.
- `evidence/e5-run*-stderr.log` — section-less startup refusal.
- `evidence/commands.txt` — exact commands and observed results.

M8 stops here. No merge and no S1-A1 closure claim.

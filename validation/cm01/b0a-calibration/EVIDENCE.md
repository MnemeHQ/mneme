# CM-01 B0-A calibration evidence specification

Applies to one run directory written by `calibration.py`. Calibration evidence is **not** B0-A evidence. It is committed only through a separate PR after the run, and it never modifies S1-A1, P0, F1, B0-M or ADR-034 M4 evidence.

## Files

| File | Content |
|---|---|
| `requests.jsonl` | One line per Messages attempt: `seq`, `purpose`, `attempt`, `body_sha256` and the full request body. No headers. |
| `responses.jsonl` | One line per attempt: HTTP status, `request-id`, latency in seconds, transport error class, the verbatim response body (including the raw `usage` object) and the normalized usage record. |
| `ledger.jsonl` | Budget ledger per attempt: input-token bound, worst-case USD, charged USD (actual cost when usage is known, worst case when unknown, 0 for 4xx), cumulative spend, requests used. |
| `mcp.jsonl` | Every genuine Decision MCP call: loop, method, arguments, `isError`, result SHA-256 and byte size, or a rejection record for a non-allowlisted name. |
| `events.jsonl` | `count_tokens` results and the stop record if the run ended early (`budget_cap`, `bound_violation`, `auth_error`, `unexpected_probe_response`). |
| `checks.json` | Run status; metadata (mode, attested workspace spend limit, workspace ID header if used, script caps); budget summary; per-loop turn summaries with UTC send times, tool calls (`genuine_mcp` or `fixed_stub`) and passed-back-content checks; K1-K9 results with their details. |
| `manifest.sha256` | SHA-256 of every file above plus `calibration.py`, `templates.py` and the B0-M fixture. |

## Review procedure (before results are used)

1. Recompute `manifest.sha256`; confirm the harness hashes match the reviewed PR head and the fixture hash is `a996e2aa...1dca`.
2. Confirm no API key appears in any file, and that only `request-id` headers are present.
3. Recompute every normalized total in `responses.jsonl` from the raw `usage` objects, and the K1-K9 results from the turn records.
4. Confirm the budget ledger never exceeds 150 attempts or $25, and that every retry and warm-up is in it. Reconcile the ledger's estimated spend against the provider console for the dedicated workspace, and confirm `checks.json` records the attested workspace spend limit.
5. Confirm every Code Mode stand-in tool result carries `calibration_stub: true, code_executed: false`, and that `mcp.jsonl` contains only the four read methods.
6. Record the outcomes for A2 (structured-output switch, provisional `max_tokens`) and A5 (E-4 invariance) in the D1-C decision register. A FAIL on K1, K3 or K7 blocks the pilot until it is resolved.

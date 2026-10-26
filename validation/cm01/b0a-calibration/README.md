# CM-01 B0-A provider calibration harness (A4)

**Status:** PREPARED, NOT EXECUTED. This harness has run only in dry-run mode (synthetic provider responses, no network). A billable run requires the human owner's explicit authorization after reviewing this code (D1-C register A25). It is calibration only: **not B0-A evidence**, no effect or variance estimate, no pilot or confirmatory scenario, no S1-A2.

Tracker: #640. Register: #667 (A2, A4, A9 rows). Design sources: D1 #655, Erratum 1 #664, D1-P #660, corpus/evaluator #662, D1-H #663.

## What it checks

| Check | Question | Outcome |
|---|---|---|
| K1 | Does every successful response carry complete usage? What do the error probes return? | PASS / FAIL. Error responses without usage are recorded as observed API errors, not failures. |
| K2 | Do the usage categories reconcile? | `thinking_tokens` is approximate and diagnostic only; it is never used to reconcile the primary total. |
| K3 | Is the normalized input total invariant across cache states in tool loops (Erratum E-4)? | PASS only with equal totals across at least two different cache splits; otherwise INCONCLUSIVE. |
| K4 | Do structured outputs work with tool loops and adaptive thinking, for both tool sets? | PASS enables `output_config.format` in both arms; FAIL falls back to evaluator-validated JSON in both arms. |
| K5 | How many input tokens does the structured-output system prompt add? | Estimated with `count_tokens`; actual accounting is always taken from Messages responses. |
| K6 | Grammar compilation: cold vs warm latency per arm and schema | Recorded. "Cold" is valid only if the pair was not compiled in the previous 24 hours. |
| K7 | Echo fields | `model` must equal `claude-sonnet-5-5`; `speed`, `service_tier`, `inference_geo` and the API version are recorded. |
| K8 | Are thinking blocks passed back unchanged accepted? | PASS / FAIL. |
| K9 | Output-size evidence for `max_tokens` | Provisional ceiling = min(128000, 4 x largest representative calibration output), pending review. |

## Request plan (sequential, at most about 62 Messages requests before retries)

1. Four K1 probes: a 16-token cap, `temperature` (expected 400), forced `tool_choice` (expected error), `between_tools` at `xhigh` (expected 400).
2. Six structured-output tool loops: tasks CAL-T5, CAL-T6 and CAL-T8, each in the direct and Code Mode stand-in arms. Each loop's first request is repeated once for K6. Loops are capped at 6 turns.
3. Two plain-JSON loops (CAL-T5, both arms) as the K4 fallback baseline.
4. Four K3 replays: the final requests of two direct loops, resent twice each.
5. Twelve `count_tokens` calls for K5 (not billed; separately capped at 60).

## Boundaries enforced in code

- **No model-generated code is executed.** The Code Mode stand-in tool always returns one fixed result, precomputed from the genuine MCP for that task and marked `calibration_stub: true, code_executed: false`.
- **Genuine Decision MCP, read-only.** A fresh `python -m mneme decision-mcp` child per loop on the frozen B0-M fixture (hash checked at start). Only `decision.get`, `decision.search`, `decision.applicable_to` and `decision.trace` are exposed; any other name is rejected and logged.
- **B0-M is a labeled regression input only.** The calibration tasks are `CAL-*`, not B0-A scenarios. No B0-A corpus exists or is touched.
- **Budget.** Hard caps of 150 Messages attempts and $25, counting every probe, warm-up, replay and retry. Before each attempt the worst-case cost (request bytes plus an 8,000-token allowance for provider-injected text, priced at the highest input rate, plus `max_tokens` at the output rate) must fit in the remaining budget, or the run stops and is recorded. Each response is checked against its input bound; a violation halts the run. Infrastructure retries: at most 2, with fixed 10 s and 30 s backoff, only on 429/5xx/529/network errors. Strictly sequential.
- **Credentials.** The key is read from `ANTHROPIC_API_KEY`, used only in the request header and never written. Every evidence write passes a tripwire that aborts if the key string would appear. Only the `request-id` response header is kept.

## Configuration notes for review

- A2 as ratified: `claude-sonnet-5-5`, `thinking: {type: adaptive, display: omitted}`, `output_config.effort: high`, no sampling parameters, `tool_choice: auto`, non-strict tools, `speed: standard`, `service_tier: standard_only`, non-streaming. The calibration `max_tokens` is 16,000 (a measurement ceiling only).
- `anthropic-version: 2026-10-21` and `Authorization: Bearer` follow the official Messages API example read on 2026-10-26. If either is wrong, the first request fails with 401/400 (not billed) and the run stops.
- **D1-C items surfaced by building this:**
  - Anthropic tool names must match `^[a-zA-Z0-9_-]{1,64}$`, so the dotted MCP names are mapped one-to-one (`decision.get` becomes `decision_get`).
  - Structured outputs require `additionalProperties: false` on every object, so #662's open `rule_payload`/`applicability` objects need explicit per-rule-type shapes. K4 tests the shapes used here.
  - The Code Mode stand-in description differs from the production F1 adapter's, so K5/K6 numbers for the one-tool set are indicative only.

## Running

Dry run (no network, no key):

```powershell
python validation/cm01/b0a-calibration/calibration.py --dry-run --out $env:TEMP\b0a-cal-dry
python -m pytest validation/cm01/b0a-calibration/test_calibration.py -q
```

Live run, **only after explicit authorization**. A dedicated Anthropic workspace with its own spending limit is recommended as an extra safeguard:

```powershell
$env:ANTHROPIC_API_KEY = "<key from your secret store>"
python validation/cm01/b0a-calibration/calibration.py --live --out validation/cm01/b0a-calibration/evidence/run1 --confirm-requests 150 --confirm-usd 25
Remove-Item Env:ANTHROPIC_API_KEY
```

The live command refuses to start unless both confirmations match the frozen caps exactly, the key is set, the B0-M fixture hash matches, and the output directory is new or empty. Evidence layout and review procedure: [EVIDENCE.md](EVIDENCE.md).

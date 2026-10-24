# CM-01 S1-A1 — M6 `decision.trace` parity

**Status:** M6 only. PASS. No M7–M8 acceptance tests, proposal calls, production memory, Cloudflare Workers, live model, or credentials.

## Scope

M6 proves complete deterministic `decision.trace` parity between direct Mneme MCP and the local Code Mode adapter, using the M4-F1 canonical fixture.

## Cases

| Case | Record | Expected |
|---|---|---|
| Active canonical decision | `ADR-9901` | `canonical_trace` with one derived rule |
| Deprecated canonical decision | `ADR-9902` | `canonical_trace` with no derived rules |
| Unknown identifier | `ADR-9999` | `trace_not_found`, type unknown |

All three returned identical complete normalized payloads through direct MCP and Code Mode:

- recursive differences: `0` for every case;
- array order preserved;
- no fields dropped.

## Lineage results

Both canonical traces used exactly:

```text
result_type
canonical_decision_id
canonical_record
derived_rules
declared_test_evidence
missing_links
```

`ADR-9901`:

- complete canonical record matched the fixture;
- one derived rule;
- `rule_id`, `decision_version_id`, `rule_payload` and `applicability` passed through unchanged;
- missing links explicitly reported absent declared evidence and absent enforcement links.

`ADR-9902`:

- complete canonical record matched the fixture;
- `derived_rules: []`;
- no lineage invented;
- missing links explicitly included absent derived rules, absent declared evidence and absent enforcement links.

`ADR-9999`:

```text
result_type: trace_not_found
record_id: ADR-9999
```

It was not classified as a proposal or canonical decision and retained the explicit type-unknown missing link.

Declared test evidence remained empty and was not upgraded into trusted or verified evidence.

## Checks

| Check | Result |
|---|---|
| `M6-UPSTREAM-SIX-1` | PASS |
| `M6-UPSTREAM-SIX-2` | PASS |
| `M6-PARITY-1` | PASS — zero differences all cases |
| `M6-PARITY-2` | PASS — zero differences all cases |
| `M6-ACTIVE-TRACE` | PASS |
| `M6-DEPRECATED-TRACE` | PASS |
| `M6-MISSING-LINKS` | PASS |
| `M6-UNKNOWN` | PASS |
| `M6-DECLARED-EVIDENCE` | PASS |
| `M6-NO-PROPOSAL-CALLS` | PASS — three `decision.trace` calls per run |
| `M6-REPEAT` | PASS — normalized evidence equal |
| `M6-NO-MUTATION` | PASS |
| `M6-M4` | PASS |

## Preservation and isolation

- E0–M5, original M4 and M4-F1 evidence unchanged; before/after hashes equal.
- M1 and M4-F1 fixtures unchanged.
- Repository memory unchanged.
- Proposal store absent.
- Empty cwd unchanged.
- M4 protection guard: `pass: true`, `violations: []`.
- No proposal tool invoked.
- No production code, ADR, enforcement, canonical memory, or ADR-034 M4 asset changed.

## Exact commands

From `validation/cm01/s1a-local/m6/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m6
```

The run starts two independent MCP server processes.

## Evidence

- `evidence/m6.json` — verdict, versions, fixture hashes, both runs, checks, preservation hashes, M4 guard.
- `evidence/run1.json` / `run2.json` — raw direct and Code Mode trace payloads, normalized payloads, zero-difference records, lineage, missing links and unknown handling.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `evidence/commands.txt` — exact commands and observed results.

M6 stops here. M7 and M8 are not started.

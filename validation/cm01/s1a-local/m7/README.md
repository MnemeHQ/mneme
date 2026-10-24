# CM-01 S1-A1 — M7 data-dependent composition

**Status:** M7 only. PASS. No M8 error-class tests, proposal calls, production memory, Cloudflare Workers, live model, or credentials.

## Scope

M7 proves one local Code Mode execution can perform a deterministic, data-dependent chain:

```text
decision.search
    → select ADR-9901 from returned canonical results
    → decision.get using the selected decision_id
    → decision.trace using the decision_id returned by get
```

The downstream `get` and `trace` calls do not hardcode `ADR-9901`; they use IDs extracted from preceding responses.

## One execution

- Code Mode `execute()` invocations: **1**
- Calls inside it: exactly three, in order:

| Seq | Tool | Argument source |
|---|---|---|
| 1 | `decision.search` | fixed query `"cache"` |
| 2 | `decision.get` | `selected.decision_id` from search |
| 3 | `decision.trace` | `get.canonical_decision.decision_id` |

No additional tool calls occurred.

## Selection

The fixed program selected the canonical decision whose:

- `context_scope` includes `"cache"`, and
- `lifecycle_status` is `"active"`.

Exactly one match was found: `ADR-9901`.

## Parity

Direct MCP and Code Mode returned identical complete normalized results for search, get and trace:

- recursive differences: `0`;
- array order preserved;
- no fields dropped.

## Identity consistency

| Field | Value |
|---|---|
| `decision_id` | `ADR-9901` |
| `version_id` | `dver-3c2da75d06c5a5ce73807f025fc1d5c9` |
| `content_digest` | `662dae53252e95830a73cd93cf2fe129a21ffb39e6f3a159073cce860f233650` |
| `derived_rule_ids` | `["ADR-9901:FORBID_LITERAL:4e447d86bf0efac6f035d836c80c7584"]` |

The selected, get and trace identities all matched each other and the M4-F1 fixture.

## Checks

| Check | Result |
|---|---|
| `M7-UPSTREAM-SIX-1` | PASS |
| `M7-UPSTREAM-SIX-2` | PASS |
| `M7-PARITY-1` | PASS — zero differences |
| `M7-PARITY-2` | PASS — zero differences |
| `M7-CALL-SEQUENCE` | PASS — search, get, trace only |
| `M7-ONE-EXECUTE` | PASS — one Code Mode execution |
| `M7-DERIVED-ARGS` | PASS — downstream args derived, no hardcoded ID |
| `M7-IDENTITY` | PASS |
| `M7-NO-PROPOSAL-CALLS` | PASS |
| `M7-REPEAT` | PASS — normalized evidence equal |
| `M7-NO-MUTATION` | PASS |
| `M7-M4` | PASS |

## Preservation and isolation

- E0–M6, original M4 and M4-F1 evidence unchanged; before/after hashes equal.
- M1 and M4-F1 fixtures unchanged.
- Repository memory unchanged.
- Proposal store absent.
- Empty cwd unchanged.
- M4 protection guard: `pass: true`, `violations: []`.
- No proposal tool invoked.
- No production code, ADR, enforcement, canonical memory, or ADR-034 M4 asset changed.

## Exact commands

From `validation/cm01/s1a-local/m7/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m7
```

The run starts two independent MCP server processes.

## Evidence

- `evidence/m7.json` — verdict, versions, fixture hashes, both runs, checks, preservation hashes, M4 guard.
- `evidence/run1.json` / `run2.json` — fixed program, raw direct and Code Mode responses, call logs, normalized results, identity and parity.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `evidence/commands.txt` — exact commands and observed results.

M7 stops here. M8 is not started. No claim is made about fewer model calls, lower latency, or improved enforcement.

# CM-01 S1-A1 — M5 `decision.applicable_to` parity

**Status:** M5 only. PASS. No M6–M8 acceptance tests, proposal calls, production memory, Cloudflare Workers, live model, or credentials.

## Scope

M5 proves that `decision.applicable_to` preserves retrieval/context applicability semantics through the local Code Mode integration, with exact direct-MCP parity.

A retrieval/context match is **not** typed-rule applicability, **not** an enforcement verdict, and **not** permission to mutate a file.

## Cases

| Case | Input |
|---|---|
| Matching context | `context=["cache"]` |
| Opaque path string | `paths=["src/cache.py"]` |
| Empty context | `context=[]`, `paths=[]` |
| Unmatched context | `context=["unrelated"]` |

All four returned identical complete normalized payloads through direct MCP and Code Mode:

- recursive differences: `0` for every case;
- array order preserved;
- no payload fields dropped.

## Result structure

Each successful result contains exactly two separate top-level lists:

```text
proposal_hint_matches
canonical_scope_matches
```

Matching canonical references contain exactly the documented slim fields:

```text
decision_id
version
version_id
statement
lifecycle_status
context_scope
```

No rule selectors, rule evaluation, enforcement verdicts, or invented applicability fields were introduced.

## Matching semantics

- `context=["cache"]` matched `ADR-9901`, whose context scope is `cache`.
- `paths=["src/cache.py"]` matched through the documented opaque path-string substring behavior.
- Empty context produced empty lists.
- Unmatched context produced empty lists.
- Path matching performed no ADR-020 selector or glob evaluation.

Canonical identity remained:

| Field | Value |
|---|---|
| `decision_id` | `ADR-9901` |
| `version` | `1` |
| `version_id` | `dver-3c2da75d06c5a5ce73807f025fc1d5c9` |
| `statement` | `Synthetic M1 cache adapter uses the in-memory backend.` |
| `lifecycle_status` | `active` |
| `context_scope` | `["cache"]` |

## Checks

| Check | Result |
|---|---|
| `M5-UPSTREAM-SIX-1` | PASS |
| `M5-UPSTREAM-SIX-2` | PASS |
| `M5-PARITY-1` | PASS — zero differences all cases |
| `M5-PARITY-2` | PASS — zero differences all cases |
| `M5-SEPARATE-LISTS` | PASS |
| `M5-SLIM-FIELDS` | PASS |
| `M5-NO-TYPED-RULE-DATA` | PASS |
| `M5-MATCHING-CONTEXT` | PASS |
| `M5-OPAQUE-PATH` | PASS |
| `M5-EMPTY-AND-UNMATCHED` | PASS |
| `M5-CANONICAL-IDENTITY` | PASS |
| `M5-NO-PROPOSAL-CALLS` | PASS — four `decision.applicable_to` calls per run |
| `M5-REPEAT` | PASS — normalized evidence equal |
| `M5-NO-MUTATION` | PASS |
| `M5-M4` | PASS |

## Preservation and isolation

- E0–M3, original M4 and M4-F1 evidence unchanged; hashes recorded before and after.
- M1 and M4-F1 fixtures unchanged.
- Repository memory unchanged.
- Proposal store absent.
- Empty cwd unchanged.
- M4 protection guard passed before and after.
- No proposal tool invoked.
- No production code, ADR, enforcement, canonical memory, or ADR-034 M4 asset changed.

## Exact commands

From `validation/cm01/s1a-local/m5/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m5
```

The run starts two independent MCP server processes.

## Evidence

- `evidence/m5.json` — verdict, versions, fixture hashes, both runs, checks, preservation hashes, M4 guard.
- `evidence/run1.json` / `run2.json` — raw direct and Code Mode responses, normalized payloads, zero-difference records, structure, matching and identity.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `evidence/commands.txt` — exact commands and observed results.

M5 stops here. M6–M8 are not started.

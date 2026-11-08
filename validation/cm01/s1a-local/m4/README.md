# CM-01 S1-A1 — M4 `decision.search` parity

**Status:** M4 only. **FAIL** at closure due to the frozen fixture lacking `ADR-9902`. Search parity itself passed for all three cases.

## Result

All three required search cases produced identical complete normalized payloads through direct MCP and Code Mode:

- `query="cache"`
- `query="", canonical_lifecycle_status="active"`
- `query="", canonical_lifecycle_status="deprecated"`

Recursive differences: `0` for each case in both independent runs.

However, M4 closure **fails** because the frozen M1 canonical fixture contains only `ADR-9901`:

```text
fixture decision IDs: ["ADR-9901"]
deprecated search canonical_decisions: []
expected ADR-9902 lifecycle: deprecated
actual ADR-9902: absent
```

M4 requires both `ADR-9901` active and `ADR-9902` deprecated. The fixture cannot be changed under M4’s preservation boundary.

## Checks

| Check | Result |
|---|---|
| `M4-UPSTREAM-SIX-1` | PASS |
| `M4-UPSTREAM-SIX-2` | PASS |
| `M4-PARITY-1` | PASS — all three cases equal |
| `M4-PARITY-2` | PASS — all three cases equal |
| `M4-SEPARATION` | PASS — `proposals` and `canonical_decisions` are distinct arrays |
| `M4-ADR9901-ACTIVE` | PASS — active in query and active-filter results |
| `M4-ADR9902-DEPRECATED` | **FAIL** — absent from fixture and deprecated result |
| `M4-IDENTITY` | **FAIL** — ADR-9902 identity cannot be verified |
| `M4-NO-PROPOSAL-CALLS` | PASS — three `decision.search` calls per run |
| `M4-REPEAT` | PASS — normalized evidence equal |
| `M4-NO-MUTATION` | PASS |
| `M4-M4` | PASS — M4 protection guard |

`ADR-9901` identity, version, content digest and derived rule ID remained unchanged across both paths.

## Blocker

> Frozen M1 canonical fixture contains only ADR-9901; ADR-9902 is absent, so the deprecated lifecycle search returns an empty canonical list. The fixture cannot be changed under M4's preservation boundary.

## Reuse and preservation

- E0 executor and evidence untouched.
- M1 fixture and evidence untouched.
- M2 four-method read-only adapter behavior reused; only `decision.search` was invoked.
- M3 evidence untouched.
- No proposal tool invoked.
- No production code, ADR, canonical memory or ADR-034 M4 asset changed.

## Exact commands

From `validation/cm01/s1a-local/m4/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m4
```

The run starts two independent MCP server processes.

## Evidence

- `evidence/m4.json` — verdict, blocker, versions, fixture hashes, both runs, checks, M4 guard.
- `evidence/run1.json` / `run2.json` — raw direct and Code Mode search responses for all three cases, normalized payloads, recursive differences, call logs, fixture facts, lifecycle and identity checks.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `evidence/commands.txt` — exact commands and observed results.

## Next step

Do not proceed to M5. M4 requires a reviewed fixture decision: either authorize a fixture amendment containing `ADR-9902` or define a new M4-specific fixture. Neither was performed here.

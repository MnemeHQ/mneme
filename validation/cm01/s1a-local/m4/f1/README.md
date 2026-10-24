# CM-01 S1-A1 — M4-F1 corrected search parity

**Status:** M4-F1 only. **PASS.**

This is a new validation result. It does not replace or rewrite the original CM-01 M4 FAIL, whose evidence remains unchanged at:

```text
m4/evidence/m4.json
SHA-256: dde0f195ef6f38e7d239a13c3a2b932b834b8e166a7ba32fe59b0787376878dd
```

## Correction

The original M4 fixture contained only `ADR-9901`, so the deprecated-lifecycle search case could not satisfy the acceptance criterion.

M4-F1 adds a separate M4-specific fixture:

```text
m4/fixture/pre_migration.json
m4/fixture/work/project_memory.json
m4/fixture/canonical/project_memory.json
```

The frozen M1 fixture was not modified or replaced.

The new source fixture contains:

- `ADR-9901`: copied unchanged from the frozen M1 fixture;
- `ADR-9902`: a deprecated decision with no typed rules.

Migration used the existing `mneme decision-index migrate` command on a copy of the new source fixture. `ADR-9902` is present in `decision_index` but absent from the active-only legacy `decisions[]` snapshot, as expected.

## Preflight

Before search parity:

- both `ADR-9901` and `ADR-9902` exist in `decision_index`;
- `ADR-9902` is absent from `decisions[]`;
- `ADR-9901` retains its M1 version ID, content digest and derived rule ID;
- direct `decision.get("ADR-9902")` returns `lifecycle_status: "deprecated"`.

| Fixture | SHA-256 |
|---|---|
| Pre-migration source | `6746f86c7164fbb06ec4d3eb99678dcdc6a96a7b2b55b8d2e5b51ddaf5c57537` |
| Canonical fixture | `b4d83d0cc0f70f442e2a62bd0e527220ae99b07cba1238e39d0ad8c5685d4e7f` |

Canonical identities:

| Decision | Lifecycle | Version ID | Content digest | Derived rule IDs |
|---|---|---|---|---|
| `ADR-9901` | active | `dver-3c2da75d06c5a5ce73807f025fc1d5c9` | `662dae53252e95830a73cd93cf2fe129a21ffb39e6f3a159073cce860f233650` | `["ADR-9901:FORBID_LITERAL:4e447d86bf0efac6f035d836c80c7584"]` |
| `ADR-9902` | deprecated | `dver-1606ff8e8763eddde0d18d18ab72a30a` | `ee82d7d1d19eec5d43fbd5814ba8e6ad9032ea589e66f0da53784c898e72de58` | `[]` |

## Search parity

All three cases produced identical complete normalized payloads through direct MCP and Code Mode:

| Case | Recursive differences |
|---|---|
| `query="cache"` | `0` |
| `query=""`, `canonical_lifecycle_status="active"` | `0` |
| `query=""`, `canonical_lifecycle_status="deprecated"` | `0` |

- Array order preserved.
- No payload fields dropped.
- `proposals` and `canonical_decisions` remained separate.
- `ADR-9901` active and `ADR-9902` deprecated were present in the correct results.
- Canonical identities, version identities, content digests and derived rule IDs matched.

## Checks

| Check | Result |
|---|---|
| `M4F1-LINK-ORIGINAL-FAIL` | PASS |
| `M4F1-PREFLIGHT` | PASS |
| `M4F1-UPSTREAM-SIX-1` | PASS |
| `M4F1-UPSTREAM-SIX-2` | PASS |
| `M4F1-PARITY-1` | PASS |
| `M4F1-PARITY-2` | PASS |
| `M4F1-SEPARATION` | PASS |
| `M4F1-LIFECYCLE` | PASS |
| `M4F1-IDENTITY` | PASS |
| `M4F1-NO-PROPOSAL-CALLS` | PASS |
| `M4F1-REPEAT` | PASS |
| `M4F1-NO-MUTATION` | PASS |
| `M4F1-M4` | PASS |

## Isolation

- M1 fixture and all E0–M3 evidence unchanged.
- Original M4 evidence unchanged.
- Repository memory unchanged.
- Proposal store absent.
- Empty cwd unchanged.
- M4 protection guard passed before and after.
- Only `decision.search` was invoked through the adapter; no proposal tool.

## Exact commands

From `validation/cm01/s1a-local/m4/`:

```text
node f1/run-m4-f1.mjs
```

The run starts two independent MCP server processes.

## Evidence

- `f1/evidence/m4-f1.json` — verdict, correction link, fixture hashes, both runs, checks, M4 guard.
- `f1/evidence/run1.json` / `run2.json` — preflight, raw direct and Code Mode search responses, normalized payloads, differences, call logs, lifecycle and identity.
- `f1/evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `f1/evidence/commands.txt` — exact commands and observed results.
- `m4/fixture/SHA256SUMS` — fixture hashes.

M4-F1 stops here. M5–M8 are not started.

# CI1.2.2 fixture: incomplete evaluation

CI1.2.1 pinned one way to get `evaluation_complete: false`: a target path
outside the policy root. This corpus pins the others an adapter must handle.
Shared rules (classification, contract exit codes, record order) are in the
[index README](../README.md).

The fixture is synthetic. ADR-921 and ADR-922 are not Mneme product
decisions, and nothing here touches the repository's canonical
`.mneme/project_memory.json`.

## Layout (`v1/`)

| Path | Role |
|---|---|
| `adr/ADR-921-*.md` | Global `FORBID_LITERAL` (`--legacy-sync`), no path selectors |
| `adr/ADR-922-*.md` | Scoped `FORBID_LITERAL` (`staging.internal.example`) with `include_paths: [docs/**]` (ADR-020) |
| `project_memory.json` | Canonical memory **generated** from `adr/` through the supported CLI only (below). `v1/` is the policy root |
| `docs/*.md` | Inputs |
| `cases.json` | Case manifest, including both canonical rule identities |
| `expected/*.json` | Golden `mneme.check/v1` payloads, records sorted by `rule_id` |

The two ADRs use different scopes. With the same scope and priority the ADR
import refuses them as an active-active contradiction.

## Regenerating `project_memory.json`

Run from `v1/` against an empty seed. The result must be identical to the
committed file once parsed:

```bash
python -m mneme.cli decision-index migrate --memory project_memory.json --apply
python -m mneme.cli adr import --memory project_memory.json --apply adr
```

The seed is
`{"meta":{"name":"ci1-fixture","description":"CI1.2.2 incomplete-evaluation fixture"},"items":[],"examples":[],"decisions":[]}`.

## Invocation contract

Every case runs from `v1/` under every entry in `query_variants` as:

```bash
python -m mneme.cli check --memory project_memory.json --input <input> --query <q> --top <n> --mode <mode> --adr-dir adr --json [--target-path <path>]
```

The payload (after sorting records) and the exit code must be identical across
the variants, because literal-tier enforcement does not depend on retrieval
ranking (ADR-017).

## Cases

| Case | Target | Mode | ADR-922 | Verdict | `evaluation_complete` | Exit | Classification |
|---|---|---|---|---|---|---|---|
| `complete_pass` | input | strict | APPLIED | PASS | true | 0 | VERIFIED_PASS |
| `complete_fail` | input | strict | APPLIED | FAIL | true | 2 | VIOLATION |
| `unknown_target_is_policy_root` | `.` | strict | UNKNOWN | PASS | **false** | 2 | UNEVALUATED |
| `unknown_in_warn_mode` | `../README.md` | **warn** | UNKNOWN | PASS | **false** | **2** | UNEVALUATED |
| `unknown_with_global_fail` | `../README.md` | strict | UNKNOWN | **FAIL** | **false** | 2 | UNEVALUATED |

What each case pins:

- **`unknown_target_is_policy_root`**: a second UNKNOWN reason. The target
  resolves to the policy root itself, not to an artifact.
- **`unknown_in_warn_mode`**: warn mode maps every complete verdict to exit
  0, but an incomplete evaluation still exits 2. Mode does not hide UNKNOWN.
- **`unknown_with_global_fail`**: ADR-921 is APPLIED and FAILs while ADR-922
  is UNKNOWN. The payload keeps the violation and reports verdict FAIL, but
  the evaluation is incomplete, so the class is UNEVALUATED. An adapter must
  not read UNEVALUATED as "no violation found". Whether this result blocks is
  ADR-033's question. This corpus only pins that the violation is reported.

## Versioning

`v1` is immutable. A change to rule identity derivation, payload shape or any
expected result means adding `v2/`, not editing `v1/`.

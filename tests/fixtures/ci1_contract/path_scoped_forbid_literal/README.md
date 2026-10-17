# CI1.2.1 fixture: path-scoped `FORBID_LITERAL`

A versioned, CI-platform-independent fixture for the CI1 Enforcement Assurance
workstream (see the
[CI1.1 record](../../../../docs/validation/ci1-1-enforcement-assurance-contract-validation-2026-10-16.md)).
Any CI adapter (GitHub Actions, GitLab CI, Jenkins or another) must reproduce
these results by calling the existing `mneme check --json` CLI. The adapter
must not reimplement retrieval, path applicability or verdict logic.

The fixture is synthetic. ADR-901 and ADR-902 are not Mneme product decisions,
and nothing here touches the repository's canonical `.mneme/project_memory.json`.

## Layout (`v1/`)

| Path | Role |
|---|---|
| `adr/ADR-901-*.md` | Source decision. One `FORBID_LITERAL` rule (`install legacy-client`) with `include_paths: [docs/**]` and `exclude_paths: [docs/history/**]` (ADR-020) |
| `adr/ADR-902-*.md` | Retrieval decoy with no enforceable rule. Its vocabulary outranks ADR-901 for storage and caching queries |
| `project_memory.json` | Canonical memory **generated** from `adr/` through the supported CLI only (below). `v1/` is the ADR-020 policy root, because the memory file's parent is the root |
| `docs/`, `src/` | Inputs, checked at their real paths inside the policy root |
| `cases.json` | Case manifest: input, optional target path, mode, expected exit code, expected classification and golden payload |
| `expected/*.json` | Golden `mneme.check/v1` payloads, compared after JSON parsing |

## Regenerating `project_memory.json`

Run from `v1/` against an empty seed. The result must be identical to the
committed file once parsed:

```bash
python -m mneme.cli decision-index migrate --memory project_memory.json --apply
python -m mneme.cli adr import --memory project_memory.json --apply adr
```

The seed is
`{"meta":{"name":"ci1-fixture","description":"CI1.2.1 path-scoped fixture"},"items":[],"examples":[],"decisions":[]}`.

## Invocation contract

Every case runs from `v1/` as:

```bash
python -m mneme.cli check --memory project_memory.json --input <input> --query <q> --top <n> --mode <mode> --adr-dir adr --json [--target-path <path>]
```

Each case runs under every entry in `query_variants`. The payload must be
identical across them, because literal-tier enforcement does not depend on
retrieval ranking (ADR-017), even with `--top 1` and a query that ranks the
decoy first.

## Cases

| Case | Applicability | Verdict | `evaluation_complete` | Exit (strict) | Classification |
|---|---|---|---|---|---|
| `applied_pass` | `APPLIED` (`docs/**`) | PASS | true | 0 | VERIFIED_PASS |
| `applied_fail` | `APPLIED` (`docs/**`) | FAIL | true | 2 | VIOLATION |
| `excluded_by_exclude_selector` | `EXCLUDED` (`docs/history/**`) | PASS | true | 0 | VERIFIED_PASS |
| `excluded_by_no_include_match` | `EXCLUDED` (no include matched) | PASS | true | 0 | VERIFIED_PASS |
| `unknown_target_outside_policy_root` | `UNKNOWN` | **PASS** | **false** | 2 | UNEVALUATED |

Classification describes the result. It is not a blocking policy:

- **VERIFIED_PASS**: the payload parses, `evaluation_complete` is true and the verdict is PASS.
- **VIOLATION**: the payload parses, `evaluation_complete` is true and the verdict is FAIL.
- **UNEVALUATED**: `evaluation_complete` is false, or there is no parseable payload.

Whether UNEVALUATED blocks a merge is an availability-policy question
(ADR-033, proposed, #483). This fixture does not decide it.

**Read `evaluation_complete` before `verdict`.** In the UNKNOWN case the
payload reports `"verdict": "PASS"` while `evaluation_complete` is `false`, and
the exit code is 2, the same code as a strict FAIL. An adapter that reads only
`verdict`, or only the exit code, will misclassify this case (CI1.1 F1). The
fixture pins this current behavior on purpose. Changing it is a contract
change and needs a new fixture version.

## Versioning

`v1` is immutable. A change to rule identity derivation, payload shape or any
expected result means adding `v2/` next to it, not editing `v1/`.

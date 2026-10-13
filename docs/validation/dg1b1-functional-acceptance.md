# DG1B1 Functional Acceptance — GSA-TTS ADR-0028 (Windows-Native Secret Storage)

> One real-repository functional acceptance scenario for **DG1B1 deterministic
> decision applicability** (ADR-031 §4/§6–§8), under the merged
> [DG1B1 charter](../plans/2026-10-08-dg1b1-decision-applicability-charter.md)
> and the [Layer 1 freeze amendment](../architecture/layer1-freeze-e73ff7d.md).
> Evidence is reproducible offline through the committed fixture; it does not
> reimplement resolver logic.

## 1. Pinned source

| Field | Value |
|---|---|
| Repository | `GSA-TTS/agentic-coding-quickstart` |
| Pinned commit SHA | `8e6160c63acc35bd48d0a3844e133ea3ad52a464` |
| Source file | `docs/adr/0028-windows-native-secret-storage.md` |
| Source location | `L1-L12; L106-L140` |
| Reviewed reference | `ref-gsa-agentic-coding-quickstart-005` |
| Source status | `accepted` |

The evidence fixture is
`tests/fixtures/dg1b1_functional_acceptance/gsa_adr_0028_windows_secret_storage.json`,
captured verbatim from the frozen O1A reference corpus. Its `source_evidence`
is content-addressed:

```
sha256(source_evidence) = fb72bb1051e95874b4053203cc4815ebf2f3f996c814778c4276c51d9cdbda87
```

The exact decision sentence the charter cites is present (whitespace-normalized
because the source wraps): *"…gated to Windows hosts (MSYS/MINGW)…"*.

**Source verification.** The frozen corpus records the pinned repository commit
and source file. It was cross-checked **once** against the pinned upstream
revision (`https://raw.githubusercontent.com/GSA-TTS/agentic-coding-quickstart/8e6160c…/docs/adr/0028-windows-native-secret-storage.md`);
the fetched text matches the frozen `source_evidence`. After the fixture was
established the test is network-independent.

**Authority boundary.** O1A classification fields (`normalized_decision`,
`scopes`, `candidate_rule`, …) are research data and are deliberately **not**
used as canonical authority. The canonical decision is constructed explicitly
through Mneme-owned persistence interfaces (the v1→v2 migration transform plus
`set_decision_applicability`), with the pinned source provenance recorded
(`source_type: adr`, `source_locator: docs/adr/0028-windows-native-secret-storage.md`,
`source_revision: 8e6160c63acc35bd48d0a3844e133ea3ad52a464`).

## 2. Scenario

A canonical decision `0028-windows-native-secret-storage` ("acq stores Windows
secrets with the DPAPI-backed `keychain-windows` backend, gated to Windows hosts
(MSYS/MINGW)") with one Mneme-authored typed rule (`FORBID_LITERAL
dpapi-plaintext-export`, test-authored — not O1A-derived). Decision applicability
is assigned through `set_decision_applicability(required_labels=["platform:windows"])`.

Implemented and executed by `tests/test_dg1b1_functional_acceptance.py`
(13 tests). Uses temporary canonical memory only.

## 3. Expected vs actual

| # | Requirement | Expected | Actual (evidence) |
|---|---|---|---|
| F1 | Canonical v1 decision globally eligible | effective, no cause | `effective=('0028-…',) cause=None` ✅ |
| F2 | Explicit v1→v2 migration preserves identities | decision/version/rule/snapshot unchanged | `state=upgrade_to_v2`; `version_id` equal; `content_digest`, `derived_rule_ids`, decisions/versions/rules/snapshot equal; projection equal ✅ |
| F3 | Assign `required_labels=["platform:windows"]` | persisted, feature declared | `required_labels=('platform:windows',) features=['decision_applicability']`; file round-trip ✅ |
| F4 | `platform:windows` | effective | `effective=True cause=None applicability_step='matched'` ✅ |
| F5 | `platform:linux` | ineffective, `not_applicable` | `effective=False cause='not_applicable' applicability_step='not_applicable'` ✅ |
| F6 | no platform label | ineffective, `not_applicable` | `effective=False cause='not_applicable'` ✅ |
| F7 | miscased `Platform:Windows` | ineffective | `effective=False cause='not_applicable'` ✅ |
| F8 | removed applicability | globally effective | validated separate state → `effective=('0028-…',) cause=None` ✅ |
| F9 | superseded lifecycle precedence | `lifecycle_superseded` (not `not_applicable`) | both matching and empty labels → `cause='lifecycle_superseded'` ✅ |
| F10 | snapshot comparison | `governed_scope_changed` | `kinds=('became_ineffective','resolution_cause_changed','governed_scope_changed')` ✅ |
| F11 | deterministic / idempotent replay | stable | `resolve_twice_equal=True`; `upgrade_replay_noop=True bytes_unchanged=True`; re-apply applicability `changed=False` ✅ |
| F12 | runtime projection / enforcement inputs unchanged | identical | `projection_equal=True`; `check` strict exit codes `[2, 2]` (FAIL both) ✅ |

## 4. Schema-migration evidence

`mneme decision-index migrate --to-v2` (the explicit upgrade) on the v1 file:

- schema `mneme.decision-index/v1` → `mneme.decision-index/v2`;
- `semantic_features: []` (no decision gained applicability);
- `decisions`, `versions`, `rules`, and the `decisions[]` compatibility snapshot
  byte-identical (`snapshot_equal=True versions_equal=True rules_equal=True`);
- version identity (`version_id`), `content_digest`, and `derived_rule_ids`
  unchanged; Layer 1 projection identical before and after.

## 5. Resolver traces and cause codes

| Context labels | Status | Cause | `applicability` trace step |
|---|---|---|---|
| `('platform:windows',)` | effective | `None` | `matched` |
| `('platform:linux',)` | ineffective | `not_applicable` | `not_applicable` |
| `()` | ineffective | `not_applicable` | `not_applicable` |
| `('Platform:Windows',)` | ineffective | `not_applicable` | `not_applicable` |

Superseded lifecycle: `('platform:windows',)` → `lifecycle_superseded`;
`()` → `lifecycle_superseded` (lifecycle evaluated before applicability).

## 6. Deterministic replay

Repeated resolution over the same canonical state + context is equal; the v1→v2
upgrade replay on a v2 file is a byte-identical no-op; re-applying the same
applicability reports `changed=False`.

## 7. Runtime non-interference

`project_canonical_index` is identical with and without applicability (the
decision still projects as active). The `mneme check` strict verdict is
identical in both states (exit `2`, `FAIL`) because typed literals are enforced
corpus-wide and no consumer reads applicability yet (DG1F). `MemoryStore` (the
shared runtime loader) exposes the same decision, statement, and rules.

## 8. Compatibility — genuine 0.10.x loader

Executed: a throwaway virtual environment with the published
`mneme-hq==0.10.0`, loading the same decision as v1 and as v2:

```
mneme-hq version: 0.10.0
v1: ACCEPTED records=['0028-windows-native-secret-storage']
v2: REJECTED DecisionIndexPersistenceError: decision_index schema must be 'mneme.decision-index/v1'
```

This is a real
old-binary execution, not a current-code schema check: the 0.10.0 loader accepts
the v1 document and refuses the v2 document at load, satisfying ADR-031 §8's
"binaries at or below 0.10.x cannot read v2 memory".

## 9. Unverified conditions

- **Compatibility execution environment.** The 0.10.0 run used a local throwaway
  venv and the PyPI artifact `mneme-hq==0.10.0` (not hash-pinned). It is evidence
  from a real published loader, but not re-run in CI, and only v1/v2 load
  refusal was exercised.
- **Live-source verification** was performed once over the network against the
  pinned upstream revision; the committed fixture is the reproducible artifact.
- The 0.10.0 compatibility check is not part of the offline pytest suite (it
  requires network + pip); only the F1–F12 functional acceptance is automated.

## 10. Scope / constraints honored

No change to `DecisionRetriever`, `ConflictDetector`, enforcement-consumer
convergence, DG1B2 waivers, schema surface, extension namespacing,
`.mneme/project_memory.json`, or frozen benchmark methodology. Only temporary,
test-scoped canonical memory is written.

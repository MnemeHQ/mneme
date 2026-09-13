# D0 — OSS Decision Index kernel + Layer 1 projection parity (ADR-023)

Implements the D0 milestone of proposed ADR-023 and MnemeHQ/mneme#358: the
canonical decision-layer contract and a deterministic local projection,
proving no observable Layer 1 behavior change. It is architecture
hardening, not a product expansion.

## Exact tested SHA

`cced061ee9a501bdbaf59df71004fb9e269dcafe` (branch
`feat/d0-decision-index-kernel`, based on canonical `main` at
`e057a032abe519d8b877ec1998d625b7b77fb7bc`, which includes ADR-027).
The gate battery and benchmark instrument were executed on that exact
source state. The PR head adds this validation artifact only; no runtime
bytes differ from the tested SHA.

## G1-G9 results

| Gate | Result | Evidence |
|---|---|---|
| G1 Projection parity | PASS | `tests/test_decision_projection.py::test_g1_projection_parity_adr_corpora` (docs/adr: 27 parsed / 17 active; examples/mneme-own-adrs: 5/5 — full `Decision`/`Rule` field equality vs `adrs_to_decisions`) and `test_g1_projection_parity_runtime_decisions` (per-field round trip over `examples/project_memory.json` and `.mneme/project_memory.json`) |
| G2 DecisionRetriever parity | PASS | `test_g2_decision_retriever_parity` + `test_g2_retrieval_parity_with_path_token_queries`: identical ordering, scores, per-field match counts, and top-3 selection for 11 queries over both memories |
| G3 Enforcement parity | PASS | Frozen benchmark fixtures unchanged. `test_g3_frozen_benchmark_parity`, `test_g3_frozen_enforcement_quality_benchmark_parity` (identical verdicts, violation counts, triggers, Layer 1 metrics), `test_g3_strict_verdict_parity_on_violating_and_compliant_inputs`; instrument run: 7/7 PASS, pass rate 100% |
| G4 ConflictDetector parity | PASS | `test_g4_conflict_detector_parity`, `test_g4_scoped_unknown_applicability_is_identical`, `test_g4_detect_raises_identically_on_unknown_applicability`: identical conflicts, violated decision ids, applicability outcomes (APPLIED/EXCLUDED/UNKNOWN), typed-rule matching results |
| G5 Architecture Audit parity | PASS | `test_g5_architecture_audit_parity_repo_memory`, `test_g5_architecture_audit_parity_example_memory`, `test_g5_audit_parity_without_repo_root`: identical per-decision tier/intent/guardrail/evidence linkage and identical summary metrics (Current Protection, Identified Mneme Potential, Protection Gap) |
| G6 Lifecycle parity | PASS | `tests/test_decision_index.py::test_g6_lifecycle_parity_active_superseded_deprecated` (active, superseded-by-link, explicitly superseded, deprecated, proposed fixtures): projected Layer 1 inclusion/exclusion identical to `compile_for_import`; lineage retained in the index without runtime governance |
| G7 No inferred enforcement | PASS | `test_g7_no_inferred_enforcement_from_prose_only_decision`, `test_g7_prose_only_decision_has_no_applicability_trace`: zero invented `Rule`s, no new deterministic FAIL behavior, no applicability trace |
| G8 Source independence | PASS | `test_g8_same_identity_and_equivalent_projection_across_source_locations`: same ADR content at two source locations normalizes to the same canonical identity (`decision_id`, `version`, statement, rationale, constraints, rules) with equivalent Layer 1 runtime output; only the provenance locator differs |
| G9 Non-code safety | PASS | `test_g9_non_code_target_projects_without_inventing_enforcement` (canonical representation succeeds, no path applicability or enforcement rule invented), `test_g9_non_architecture_class_fails_closed`; frozen benchmark behavior unchanged (G3) |

38 new tests total; `1237 passed, 5 skipped` for the full gate battery
(skips are pre-existing and unrelated).

## Exact commands

```text
python scripts/run_test_battery.py gate
python -m pytest tests/test_decision_index.py tests/test_decision_projection.py
python -m mneme.cli benchmark examples/benchmarks/ --memory examples/project_memory.json
```

## Fixtures/tests used

- New: `tests/test_decision_index.py`, `tests/test_decision_projection.py`
  (both registered in the gate manifest of `scripts/run_test_battery.py`
  per the test policy classification invariant — a manifest change only).
- Read-only corpora: `docs/adr/`, `examples/mneme-own-adrs/`,
  `examples/project_memory.json`, `.mneme/project_memory.json`.
- Frozen benchmark suites (unchanged): `examples/benchmarks/`,
  `examples/benchmarks-enforcement-quality/`.

## Limitations

- `version` is the narrow D0 constant `"1"`: the current ADR/compiler data
  carries exactly one immutable version per decision id (supersession
  creates a new id, not a new version). A richer version contract is D1
  scope and was deliberately not invented.
- The canonical record adds two explicit losslessness fields beyond
  ADR-023's minimal field list: `test_evidence` (declared test evidence,
  required for G5 evidence linkage per ADR-024) and an optional
  `updated_at` (runtime records may carry `updated_at != created_at`).
  Both are additive representation, not runtime semantics.
- Lifecycle vocabulary reuses the existing graph projection states
  (`active` / `superseded` / `deprecated` / `inactive`) rather than
  inventing canonical states.
- Same-scope precedence losers are excluded from the corpus-level index:
  the current compiler emits no runtime record for them, and representing
  them as active would fabricate unauthorized governance. D1 hardening.
- The kernel is additive: the runtime continues to consume the existing
  compiler/store path. Switching runtime loading to the kernel is a later,
  separately reviewed step and is not part of D0.
- D0 implements no MCP surface, no DecisionProposal lifecycle, no source
  ingestion adapters, no organizational persistence, and no hosted or
  organizational dependency (explicitly excluded by ADR-023/ADR-027/#362).

## Frozen-boundary attestation

- frozen runtime files behaviorally changed? NO
  (`decision_retriever.py`, `enforcer.py`, `conflict_detector.py`,
  `benchmark.py`, `rule_matcher.py`, `path_selectors.py` untouched)
- benchmark fixtures changed? NO
- runtime semantic delta? NO
- MCP implementation added? NO
- proposal lifecycle added? NO
- hosted/org dependency added? NO

## ADR-023 acceptance evidence

G1-G9 all pass on current canonical `main` with no runtime semantic delta.
This evidence supports moving ADR-023 from `proposed` to `accepted`; the
ADR file's status is intentionally not changed by this PR (that promotion
is a maintainer decision).

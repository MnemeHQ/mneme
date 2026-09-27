# Archlint Reference Decisions — Batch 01 Review

**Repository:** `muhammetsafak/archlint`  
**Pinned commit:** `185837e93565718d8e1ea653236cd70ca0a89e3a`  
**Benchmark batch:** `open_architecture/batch_01`  
**Reference decisions:** `ref-archlint-001` through `ref-archlint-010`  
**Sampling categories:** `clear_explicit` (5/5), `scoped` (5/5)

---

## Selection basis

These 10 candidates were selected from the approved 20-candidate sample (see candidate selection report). The first 5 fall in the `clear_explicit` quota; the next 5 fall in the `scoped` quota. All represent explicitly validated product decisions with direct source grounding in the pinned commit.

---

## Candidate → Reference mapping

| Candidate | Reference ID | Title |
|-----------|--------------|-------|
| archlint-candidate-01 | ref-archlint-001 | Layer declaration via architecture.json |
| archlint-candidate-02 | ref-archlint-002 | Allowed dependency directions (rules) |
| archlint-candidate-03 | ref-archlint-003 | Longest-prefix layer resolution |
| archlint-candidate-04 | ref-archlint-004 | Executable ADR mechanism |
| archlint-candidate-05 | ref-archlint-005 | Coupling metrics on the enforcement graph; SDP derived and optionally gated |
| archlint-candidate-06 | ref-archlint-006 | ADR merge/conflict: union layers & allows, deny authoritative |
| archlint-candidate-07 | ref-archlint-007 | Three-language parsing strategies |
| archlint-candidate-08 | ref-archlint-008 | Same-layer imports always allowed |
| archlint-candidate-09 | ref-archlint-009 | GitHub Actions inline annotation format |
| archlint-candidate-10 | ref-archlint-010 | Bounded-context breach despite layer rule allow |

---

## Source coverage

| Reference | Primary source file | Key functions |
|-----------|---------------------|---------------|
| ref-archlint-001 | `internal/config/config.go` | `Config` struct, `validate()` |
| ref-archlint-002 | `internal/config/config.go` | `Rules` field, `validate()` |
| ref-archlint-003 | `internal/config/config.go` | `LayerOf()` |
| ref-archlint-004 | `internal/adr/adr.go` | `parseFile()` |
| ref-archlint-005 | `README.md` | Coupling metrics & Conway/DDD analysis |
| ref-archlint-006 | `internal/adr/adr.go` | `Ruleset.add()`, `Ruleset.MergeInto()` conflict check |
| ref-archlint-007 | `internal/lang/lang.go`, `golang.go`, `typescript.go`, `python.go` | `init()`, `Imports()`, `Resolve()` per language |
| ref-archlint-008 | `internal/config/config.go` | `Allows()` |
| ref-archlint-009 | `cmd/archlint/main.go` | `emitGitHub()`, `emitMetricsGitHub()`, `resolveFormat()` |
| ref-archlint-010 | `internal/metrics/contexts.go` | `ContextSet.Detect()` |

All source locations verified against pinned commit `185837e93565718d8e1ea653236cd70ca0a89e3a`.

---

## Classification summary

| Field | Value |
|-------|-------|
| **classification** | `prescriptive` (all 10) |
| **decision_domains** | `architecture_structure` (001–010); + `developer_workflow` (004, 009); + `dependency_technology` (006, 007) |
| **decision_purposes** | `constrain`, `standardize`, `define_boundary` (core); + `optimize_quality_attribute` (005) |
| **authority_status** | `explicitly_accepted` (all 10) |
| **lifecycle_status** | `active` (all 10) |
| **enforcement_potential** | `deterministic_rule` (all 10) |

---

## Human review status

| Reference | Status |
|-----------|--------|
| ref-archlint-001 | reviewed |
| ref-archlint-002 | reviewed |
| ref-archlint-003 | reviewed |
| ref-archlint-004 | reviewed |
| ref-archlint-005 | reviewed |
| ref-archlint-006 | unreviewed |
| ref-archlint-007 | unreviewed |
| ref-archlint-008 | unreviewed |
| ref-archlint-009 | unreviewed |
| ref-archlint-010 | unreviewed |

---

## Relationships

| Reference | Relationships |
|-----------|---------------|
| ref-archlint-001 | `[]` |
| ref-archlint-002 | `[]` |
| ref-archlint-003 | `[]` |
| ref-archlint-004 | `[]` |
| ref-archlint-005 | `[]` |
| ref-archlint-006 | `[]` |
| ref-archlint-007 | `[]` |
| ref-archlint-008 | `[]` |
| ref-archlint-009 | `[]` |
| ref-archlint-010 | `[]` |

No `supersedes` / `superseded_by` relationships in this batch. Relationships for 006–010 will be evaluated during their semantic review.

---

## Confidence & validation

| Reference | Confidence | Human validation |
|-----------|------------|------------------|
| ref-archlint-001 | 0.95 | reviewed |
| ref-archlint-002 | 0.95 | reviewed |
| ref-archlint-003 | 0.95 | reviewed |
| ref-archlint-004 | 0.95 | reviewed |
| ref-archlint-005 | 0.90 | reviewed |
| ref-archlint-006 | 0.95 | unreviewed |
| ref-archlint-007 | 0.95 | unreviewed |
| ref-archlint-008 | 0.95 | unreviewed |
| ref-archlint-009 | 0.95 | unreviewed |
| ref-archlint-010 | 0.95 | unreviewed |

Confidence reflects direct source grounding; 005 slightly lower due to multi-flag gating semantics.

---

## Original Nemotron semantic exact-pass for 001–005

**0/5 (0%)** — All five records required semantic corrections per Theo's approved review.

---

## Records amended

**5** (ref-archlint-001 through ref-archlint-005)

---

## Recurring correction themes

1. **Adjacent-decision over-bundling** — Records 001–005 originally included semantics belonging to other decisions (rules entry in 001, same-layer behavior in 002, merge/conflict detail in 004, bounded-context in 005).

2. **Unsupported/overbroad domains and purposes** — `dependency_technology`, `reliability_observability`, `developer_workflow` (005), `enable_migration`, `document_tradeoff`, `require_evidence` removed where not directly source-supported.

3. **Non-frozen relationship type** — `uses_same_graph_as` removed from 005 (not in frozen O1A taxonomy v0.1).

4. **Enforcement scalar correction** — 005 changed from `contextual_guidance` to `deterministic_rule` (best scalar representation for mixed observational + gated behavior).

5. **Evidence/scope precision** — Scopes changed from `repository` to `file_pattern` for `architecture.json`; ADR directory scope clarified as configurable; README evidence trimmed to direct source support.

---

## Files created

```
benchmarks/open_architecture/batch_01/reference_decisions/archlint/
├── ref-archlint-001.jsonl
├── ref-archlint-002.jsonl
├── ref-archlint-003.jsonl
├── ref-archlint-004.jsonl
├── ref-archlint-005.jsonl
├── ref-archlint-006.jsonl
├── ref-archlint-007.jsonl
├── ref-archlint-008.jsonl
├── ref-archlint-009.jsonl
├── ref-archlint-010.jsonl
└── archlint-review.md (this file)
```

---

## Next steps

Remaining 10 candidates (lifecycle_or_supersession 3, ambiguous_or_conflicting 3, enforcement_potential 2, unusual_or_difficult 2) await separate approval for reference decision drafting.
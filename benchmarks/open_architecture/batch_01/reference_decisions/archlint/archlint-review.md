# Archlint Reference Decisions — Batch 01 Review

**Repository:** `muhammetsafak/archlint`  
**Pinned commit:** `185837e93565718d8e1ea653236cd70ca0a89e3a`  
**Benchmark batch:** `open_architecture/batch_01`  
**Reference decisions:** `ref-archlint-001` through `ref-archlint-020`  
**Sampling categories:** `clear_explicit` (5/5), `scoped` (5/5), `lifecycle_or_supersession` (3/3), `ambiguous_or_conflicting` (3/3), `enforcement_potential` (2/2), `unusual_or_difficult` (2/2)

---

## Selection basis

These 20 candidates were selected from the approved 20-candidate sample (see candidate selection report). The first 5 fall in the `clear_explicit` quota; the next 5 fall in the `scoped` quota; 3 fall in `lifecycle_or_supersession`; 3 fall in `ambiguous_or_conflicting`; 2 fall in `enforcement_potential`; 2 fall in `unusual_or_difficult`. All represent explicitly validated product decisions with direct source grounding in the pinned commit.

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
| archlint-candidate-11 | ref-archlint-011 | teams.json current; CODEOWNERS ingestion planned follow-up |
| archlint-candidate-12 | ref-archlint-012 | Static import graph today; runtime-trace correlation later phase |
| archlint-candidate-13 | ref-archlint-013 | JSON config today; YAML support follow-up |
| archlint-candidate-14 | ref-archlint-014 | Metrics default gating contradiction: README vs CLI |
| archlint-candidate-15 | ref-archlint-015 | Unreadable/unparseable/ungoverned inputs skipped silently |
| archlint-candidate-16 | ref-archlint-016 | GitHub annotation severity disagrees with enforcement gating |
| archlint-candidate-17 | ref-archlint-017 | Exit code convention: 0/1/2 shared by check & metrics |
| archlint-candidate-18 | ref-archlint-018 | ADR provenance on violations (file:line attribution) |
| archlint-candidate-19 | ref-archlint-019 | Abstractness (A) as declared proxy (0.0/1.0) not symbol-level |
| archlint-candidate-20 | ref-archlint-020 | Conway Mismatch Index excludes unowned layers |

---

## Source coverage

| Reference | Primary source file | Key functions |
|-----------|---------------------|---------------|
| ref-archlint-001 | `internal/config/config.go` | `Config` struct, `validate()` |
| ref-archlint-002 | `internal/config/config.go` | `Rules` field, `validate()` |
| ref-archlint-003 | `internal/config/config.go` | `LayerOf()` |
| ref-archlint-004 | `internal/adr/adr.go` | `parseFile()` |
| ref-archlint-005 | `README.md` | Coupling metrics & Conway/DDD analysis |
| ref-archlint-006 | `internal/adr/adr.go` | `Ruleset.MergeInto()` conflict check |
| ref-archlint-007 | `internal/lang/golang.go`, `typescript.go`, `python.go` | `Imports()`, `Resolve()` per language |
| ref-archlint-008 | `internal/config/config.go` | `Allows()` |
| ref-archlint-009 | `cmd/archlint/main.go` | `emitGitHub()`, `emitMetricsGitHub()`, `resolveFormat()` |
| ref-archlint-010 | `internal/metrics/contexts.go` | `ContextSet.Detect()` |
| ref-archlint-011 | `README.md` | Conway analysis & ownership |
| ref-archlint-012 | `README.md` | Static vs runtime analysis |
| ref-archlint-013 | `README.md` | Config format (JSON/YAML) |
| ref-archlint-014 | `README.md`, `cmd/archlint/main.go` | Metrics gating behavior |
| ref-archlint-015 | `internal/arch/arch.go` | `BuildGraph()` skip behavior |
| ref-archlint-016 | `cmd/archlint/main.go` | `emitMetricsGitHub()`, gating logic |
| ref-archlint-017 | `README.md`, `cmd/archlint/main.go` | Exit codes, check/metrics exit |
| ref-archlint-018 | `internal/arch/arch.go`, `internal/adr/adr.go`, `cmd/archlint/main.go` | Violation Source, SourceOf, sourceSuffix |
| ref-archlint-019 | `internal/metrics/metrics.go`, `internal/metrics/contexts.go` | Abstractness A, AbstractLayers |
| ref-archlint-020 | `internal/metrics/conway.go` | TeamMap, Conway, Detect |

All source locations verified against pinned commit `185837e93565718d8e1ea653236cd70ca0a89e3a`.

---

## Classification summary

| Field | Value |
|-------|-------|
| **classification** | `prescriptive` (001–013, 015, 017–020); `ambiguous` (014, 016) |
| **decision_domains** | `architecture_structure` (001–003, 005–008, 010, 012, 015, 017–020); `developer_workflow` (004, 009, 011, 014, 016, 017); `dependency_technology` (007, 013); `ownership_boundary` (011, 020) |
| **decision_purposes** | `constrain`, `standardize`, `define_boundary` (core); + `optimize_quality_attribute` (005); + `select` (007, 011, 012, 013); + `standardize` (014, 016) |
| **authority_status** | `explicitly_accepted` (all 20) |
| **lifecycle_status** | `active` (all 20) |
| **enforcement_potential** | `deterministic_rule` (all 20) |

---

## Human review status

| Reference | Status |
|-----------|--------|
| ref-archlint-001 | reviewed |
| ref-archlint-002 | reviewed |
| ref-archlint-003 | reviewed |
| ref-archlint-004 | reviewed |
| ref-archlint-005 | reviewed |
| ref-archlint-006 | reviewed |
| ref-archlint-007 | reviewed |
| ref-archlint-008 | reviewed |
| ref-archlint-009 | reviewed |
| ref-archlint-010 | reviewed |
| ref-archlint-011 | reviewed |
| ref-archlint-012 | reviewed |
| ref-archlint-013 | reviewed |
| ref-archlint-014 | reviewed |
| ref-archlint-015 | reviewed |
| ref-archlint-016 | reviewed |
| ref-archlint-017 | reviewed |
| ref-archlint-018 | reviewed |
| ref-archlint-021 | reviewed |
| ref-archlint-022 | reviewed |
| ref-archlint-023 | reviewed |

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
| ref-archlint-011 | `[]` |
| ref-archlint-012 | `[]` |
| ref-archlint-013 | `[]` |
| ref-archlint-014 | `[]` |
| ref-archlint-015 | `[]` |
| ref-archlint-016 | `[]` |
| ref-archlint-017 | `[]` |
| ref-archlint-017 | `[]` |
| ref-archlint-018 | `[]` |
| ref-archlint-019 | `[]` |
| ref-archlint-020 | `[]` |

No `supersedes` / `superseded_by` relationships in this batch.

---

## Confidence & validation

| Reference | Confidence | Human validation |
|-----------|------------|------------------|
| ref-archlint-001 | 0.95 | reviewed |
| ref-archlint-002 | 0.95 | reviewed |
| ref-archlint-003 | 0.95 | reviewed |
| ref-archlint-004 | 0.95 | reviewed |
| ref-archlint-005 | 0.90 | reviewed |
| ref-archlint-006 | 0.95 | reviewed |
| ref-archlint-007 | 0.95 | reviewed |
| ref-archlint-008 | 0.95 | reviewed |
| ref-archlint-009 | 0.95 | reviewed |
| ref-archlint-010 | 0.95 | reviewed |
| ref-archlint-011 | 0.90 | reviewed |
| ref-archlint-012 | 0.90 | reviewed |
| ref-archlint-013 | 0.90 | reviewed |
| ref-archlint-014 | 0.85 | reviewed |
| ref-archlint-015 | 0.85 | reviewed |
| ref-archlint-016 | 0.85 | reviewed |
| ref-archlint-017 | 0.90 | reviewed |
| ref-archlint-018 | 0.90 | reviewed |
| ref-archlint-019 | 0.85 | reviewed |
| ref-archlint-020 | 0.85 | reviewed |

Confidence reflects direct source grounding; lifecycle/ambiguous records slightly lower due to taxonomy limitations.

---

## Original Nemotron semantic exact-pass for 001–005

**0/5 (0%)** — All five records required semantic corrections per Theo's approved review.

---

## Original Nemotron semantic exact-pass for 006–010

**0/5 (0%)** — All five records required semantic corrections per Theo's approved review.

---

## Original Nemotron semantic exact-pass for 011–015

**0/5 (0%)** — All five records required semantic corrections per Theo's approved review.

---

## Original Nemotron semantic exact-pass for 016–020

**3/5 (60%)** — Records 016, 017, 018 passed; 019, 020 required semantic corrections per Theo's approved review.

---

## Cumulative original exact-pass for Archlint 001–020

**3/20 (15%)** — Three of twenty records passed original semantic exact-pass; seventeen required semantic corrections per Theo's approved review.

---

## Records amended in second batch

**5** (ref-archlint-006 through ref-archlint-010)

---

## Records amended in third batch

**5** (ref-archlint-011 through ref-archlint-015)

---

## Records amended in fourth batch

**2** (ref-archlint-019, ref-archlint-020)

---

## Cumulative records amended

**17** (ref-archlint-001 through ref-archlint-020; 016, 017, 018 passed without amendment)

---

## Records drafted in fourth batch (pending review)

**0**

---

## Recurring correction themes

1. **Adjacent-decision over-bundling** — Records 001–020 originally included semantics belonging to adjacent decisions (rules entry in 001, same-layer behavior in 002, merge/conflict detail in 004, bounded-context in 005, ADR self-contradiction in 006, cross-language consequence in 007, Rules-list semantics in 008, gating terminology in 009, non-frozen relationship in 010, ownership boundary in 011, component scope in 012, config format in 013, gating contradiction in 014, skip behavior in 015, annotation gating mismatch in 016, exit code convention in 017, ADR provenance scope in 018, abstractness proxy in 019, ownership-bounded metric in 020).

2. **Unsupported/overbroad domains and purposes** — `dependency_technology`, `reliability_observability`, `developer_workflow` (005, 009, 011, 013, 014), `deployment_infrastructure` (009), `enable_migration`, `document_tradeoff`, `require_evidence` removed where not directly source-supported.

3. **Invented/non-frozen relationship types** — `uses_same_graph_as` removed from 005; `part_of` removed from 006 and 008; `orthogonal_to` removed from 010 (none in frozen O1A taxonomy v0.1).

4. **Imprecise scope typing** — Scopes changed from `repository` to `file_pattern`/`directory`/`component` for `architecture.json`, `docs/adr`, `contexts.json`, `archlint check`, `archlint metrics`; 007 now uses explicit `file_pattern` per supported extension.

5. **Evidence/provenance precision** — 005 evidence moved to primary README source; 006 trimmed to ADR/config merge; 007 Python regex fixed to exact pinned source; 009 gating terminology removed from normalized_decision/candidate_rule (source comment retained in raw_evidence); 010 non-frozen relationship removed; 011 ownership_boundary domain; 012 component scope for check/metrics; 013 dependency_technology domain; 014 component scope for metrics; 015 prescriptive classification; 014/015 exact source fidelity; 016 annotation vs gating mismatch; 017 component scopes; 018 ADR provenance scope; 019 declared proxy; 020 ownership-bounded metric.

6. **Raw evidence transcription error in 007** — Python regexes corrected to exact pinned source (`pyFrom`, `pyImport` from `internal/lang/python.go`); TypeScript capture groups preserved.

7. **Scope/domain correction in fourth batch** — 019 scope corrected to `contexts.json`; 020 domain corrected to `ownership_boundary` and scope corrected to `archlint metrics` component.

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
├── ref-archlint-011.jsonl
├── ref-archlint-012.jsonl
├── ref-archlint-011.jsonl
├── ref-archlint-012.jsonl
├── ref-archlint-013.jsonl
├── ref-archlint-014.jsonl
├── ref-archlint-015.jsonl
├── ref-archlint-016.jsonl
├── ref-archlint-017.jsonl
├── ref-archlint-018.jsonl
├── ref-archlint-019.jsonl
├── ref-archlint-020.jsonl
└── archlint-review.md (this file)
```

---

## Next steps

All 20 candidates from the approved 20-candidate sample have been drafted and reviewed. The Archlint reference corpus for Batch 01 is complete. Next steps require separate approval for any additional repositories or candidates beyond the approved 20.

---

## Final quota accounting

| Sampling Category | Completed / Total |
|-------------------|-------------------|
| `clear_explicit` | 5 / 5 |
| `scoped` | 5 / 5 |
| `lifecycle_or_supersession` | 3 / 3 |
| `ambiguous_or_conflicting` | 3 / 3 |
| `enforcement_potential` | 2 / 2 |
| `unusual_or_difficult` | 2 / 2 |
| **Total** | **20 / 20** |

---

## Next steps

All 20 candidates from the approved 20-candidate sample have been drafted and reviewed. The Archlint reference corpus for Batch 01 is complete. Next steps require separate approval for any additional repositories or candidates beyond the approved 20.
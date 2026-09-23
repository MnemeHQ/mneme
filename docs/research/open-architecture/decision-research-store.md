# Decision Research Store

## Purpose

The Decision Research Store preserves discovered, inferred, classified, and human-reviewed decision research data.

It is deliberately separate from the Canonical Decision Index.

## Architectural boundary

```text
Decision Research Store
discovered / inferred / experimental
            ↓
      DecisionProposal
            ↓
Canonical Decision Index
accepted / governed / authoritative
            ↓
        Enforcement
```

A research candidate must never become canonical solely because Mneme inferred it.

## Batch 01 storage

Use SQLite initially.

Reasons:

- local and reproducible
- no service dependency
- easy to version and inspect
- sufficient for tens to hundreds of repositories
- schema can evolve rapidly during ontology discovery

Portable JSON or JSONL may be emitted for fixtures, CI, review, and reproducibility.

SQLite is the working research store.

> Pre-O1A3 research databases created against earlier development schemas are not migration-supported. Recreate the local research database before baseline execution if the schema compatibility check fails.

## Future progression

### Current

SQLite.

### Continuous or multi-user research

PostgreSQL.

### Optional later infrastructure

Redis may be introduced for:

- caches
- queues
- worker coordination

Redis must not become the authoritative research corpus.

## Required provenance

Every analysis run should record:

- repository
- repository commit SHA
- Mneme version
- Mneme commit SHA
- benchmark schema version
- taxonomy version
- classifier version
- configuration hash
- timestamps
- run status

Historical runs must not be overwritten.

## Multi-classifier provenance

The store must support several predictions for the same candidate.

A prediction should preserve:

- classifier backend
- classifier version
- model identifier where applicable
- taxonomy version
- output
- confidence
- latency
- cost
- timestamp

Do not overwrite one classifier's output with another.

Classifier disagreement should be queryable and may later be used to prioritize human review.

External hosted classifiers must remain optional so Mneme can preserve local, offline, and no-source-egress deployments.

## Human correction

Machine output must be preserved even after human review.

The store should let us ask:

- which purposes are hardest to classify?
- where is scope most often corrected?
- how often does repository-wide scope become package-specific?
- which decisions are frequently mistaken for descriptive prose?
- where do ontology gaps occur?
- which classifier version performs best on the same human-labelled corpus?
- how has Governing Decision Set F1 changed over time?

Human corrections are a primary output of the research program, not cleanup metadata.

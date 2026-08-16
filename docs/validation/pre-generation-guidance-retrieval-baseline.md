# Pre-generation Guidance Retrieval Baseline

**Date:** 2026-08-13  
**Evaluator:** `python -m mneme.guidance_eval tests/fixtures/guidance_retrieval/cases.json`  
**Retriever state:** unchanged from `c1d29e9`

## Locked inputs

| Artifact | SHA-256 |
|---|---|
| `tests/fixtures/guidance_retrieval/cases.json` | `27B45E547E8B10D8EAE39CB4BAB1488D3822AA4F1B81010D5148379B24FEA261` |
| `tests/fixtures/guidance_retrieval/project_memory.json` | `983BAA775AAF38AB36C5D83CA07379C16F72A931BD7568BBA58D13C25B2C45DD` |

These files are the locked development/holdout evaluation inputs for this
implementation. A scorer change must not edit either hash. A later corpus
revision requires a new version and a new baseline; it must not overwrite this
evidence.

## Unchanged-retriever result

| Gate | Required | Observed | Result |
|---|---:|---:|---|
| Holdout macro recall@3 | >= 0.90 | 1.00 | PASS |
| Safety-critical recall@3 | 1.00 | 0.90 | **FAIL** |
| No-relevance false-injection rate | <= 0.10 | 0.00 | PASS |
| Low-signal injections | 0 | 0 | PASS |

The single failed case is `dev-typed-rule-value`:

```text
prompt:       Use legacy-client
expected:     ADR-INSTALL
retrieved:    none
```

`legacy-client` exists only as the value of a typed `FORBID_LITERAL` rule. The
current `DecisionRetriever` scores decision text, scope, constraints,
anti-patterns, and rationale, but not typed rules. The miss is therefore a
schema-symmetry defect, not a synonym or semantic-search problem.

## Checkpoint decision

Checkpoint 3 is authorized to make one narrow retrieval change: include typed
rule values in deterministic field-weighted scoring. No evidence in this
baseline authorizes stemming, embeddings, learned weights, rationale-weight
changes, K changes, or fixture changes.

The empty-token fallback remains unchanged for existing retriever callers.
Automatic guidance rejects it at the adapter boundary, which is why both
low-signal cases correctly produced no selected decisions.

## Checkpoint 3 result

The retriever now scores typed rule values at `1.5`, matching the existing
constraint and anti-pattern field weight. Selectors do not contribute to task
relevance because they describe eventual artifact applicability.

The locked input hashes remained unchanged. After the repair:

| Gate | Observed | Result |
|---|---:|---|
| Holdout macro recall@3 | 1.00 | PASS |
| Safety-critical recall@3 | 1.00 | PASS |
| No-relevance false-injection rate | 0.00 | PASS |
| Low-signal injections | 0 | PASS |
| Frozen benchmark | 7/7; recall@3 1.00 | PASS |

No other scoring behavior was changed.

# Enforcement-Quality Benchmark Suite

Frozen regression suite for **enforcement false positives and false negatives**,
authorized by [charter #318](../../docs/plans/2026-08-24-benchmark-fpr-charter.md)
and the `[layer1-freeze]` amendment (#319). Motivating defect: #317 — benign
planning prose was FAILed because multi-term legacy anti-patterns fired on any
single term.

## Invocation

```bash
python -m mneme benchmark examples/benchmarks-enforcement-quality \
  --memory examples/benchmarks-enforcement-quality/project_memory.json \
  --json report.json --markdown report.md
```

The fixture memory is part of this frozen suite. Do **not** run this suite
against `examples/project_memory.json`, and do not edit the memory or scenario
files without a charter reference (see §7 of the charter).

## Composition

- 3 violation guards (`guard_*`, `scenario_type: "violation"` explicitly) — measure false
  negatives; a verdict other than PASS means enforcement missed a forbidden
  pattern.
- 4 benign controls (`benign_*`, `scenario_type: "benign"`) — measure false
  positives; a `FALSE_POSITIVE` verdict means Mneme blocked benign work.
- Every scenario declares `expected_exposed_decision_ids`: its governing
  rule must actually be in enforcement scope (positive-score top-K retrieval).
  A clean run without exposure is `WEAK_RETRIEVAL` / uncheckable — never PASS —
  for benign controls, and downgrades an otherwise-clean guard identically.

## Metrics

| metric | definition |
|---|---|
| violation catch rate | `violation_passed / violation_checkable` |
| false-positive rate | `benign_blocked / benign_checkable` where checkable = `PASS_benign + FALSE_POSITIVE` |
| uncheckable | benign scenarios that are MALFORMED or WEAK_RETRIEVAL (excluded from the FPR denominator, always rendered) |

Current baseline at merge: catch rate 3/3, FPR 0/4, uncheckable 0.

## Why TXT fixtures only (expected warnings)

Running this suite emits one `UserWarning` per missing structured sibling
(14 total). This is deliberate: the guards pin the *legacy enforcer* phrase
matcher, which the assertion-DSL verifier does not exercise, and benign
controls must flow through `check_prompt()` — the code under test — rather
than the structured verifier. The canonical suite keeps its JSON siblings;
this suite intentionally does not.

## Scorecard

Record these four signals per meaningful core change:

```text
Violation catch rate   target 100%
False-positive rate    target ~0%   (#317 fixed it from >0%)
Retrieval Recall@3     target 1.00  (canonical suite)
Retrieval Precision@3  advisory     (fixture-shape constrained; see freeze doc)
```

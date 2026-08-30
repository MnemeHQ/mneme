# Enforcement-Quality Benchmark Results

Run against the frozen suite in `examples/benchmarks-enforcement-quality/`,
authorized by [charter #318](../../../docs/plans/2026-08-24-benchmark-fpr-charter.md)
and the `[layer1-freeze]` amendment (#319). See that directory's `README.md`
for suite composition, invocation, and metric definitions.

## Invocation

```bash
python -m mneme benchmark examples/benchmarks-enforcement-quality \
  --memory examples/benchmarks-enforcement-quality/project_memory.json \
  --json report.json --markdown report.md
```

## Results

| Scenario | Type | Verdict | Baseline violations | Enhanced violations |
|---|---|---|---|---|
| benign_awin_programme | benign | PASS | 0 | 0 |
| benign_foo_bar_incomplete | benign | PASS | 0 | 0 |
| benign_governance_docs | benign | PASS | 0 | 0 |
| benign_slug_prose | benign | PASS | 0 | 0 |
| guard_awin_identifier | violation | PASS | 1 | 0 |
| guard_foo_and_bar_compound | violation | PASS | 1 | 0 |
| guard_unreviewed_changes | violation | PASS | 1 | 0 |

## Summary

**Violation catch rate (Layer 2 enforcement):** 3/3 (100%). All three guard
scenarios were caught — the baseline (no Mneme) triggered the forbidden
pattern in each; the Mneme-enhanced response did not.

**False-positive rate:** 0/4 checkable (0%). None of the four benign
controls were blocked. `benign_uncheckable`: 0/4.

**Layer 1 (retrieval, n=3):** mean Recall@3 = 1.00, mean Precision@3 = 1.00,
irrelevant injection rate = 0%.

**By category:**

- **enforcement_quality**: 3/3 PASS

## What this proves and does not prove

**Proves:** on this frozen regression suite, Mneme's enforcement path
correctly blocked all three injected violations and did not block any of the
four benign controls it was run against.

**Does not prove:** false-positive behavior in production codebases, on
scenarios outside this fixed suite, or under adversarial paraphrase. Per the
`[layer1-freeze]` amendment, this suite is a fixed regression control, not an
adversarial or continuously expanding benchmark — see the freeze document's
"Why benchmark expansion is frozen" for that boundary.

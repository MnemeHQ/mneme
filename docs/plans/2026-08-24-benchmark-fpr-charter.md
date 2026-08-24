# Benchmark False-Positive Regression Charter

**Status:** draft — pending review; becomes the active charter for the FPR benchmark-extension work on merge
**Anchor commit:** `be853e29` (#317 phrase-sequence matching on `origin/main`)
**Provides charter basis for:** a subsequent `[layer1-freeze]` amendment of [layer1-freeze-e73ff7d.md](../architecture/layer1-freeze-e73ff7d.md) §Benchmark Methodology ("Why benchmark expansion is frozen", "Categories covered") and §Suite-level metrics, under Amendment Procedure 3(b), referencing **this merged charter**.

**Required sequence:** this charter merges first → the `[layer1-freeze]` amendment PR references it → only then does behavioral/benchmark implementation land. Per freeze §Amendment Procedure 4, the implementation cannot precede the freeze amendment.

---

## 1. Context

PR #317 fixed a real dogfood defect: benign planning prose was FAILed because
multi-term legacy anti-patterns fired on any single term inside the
retrieval-gated tier. The canonical benchmark did not move before or after
(#317): all seven shipped scenarios are violation scenarios, so the benchmark
proves "we did not lose enforcement" but cannot express "we became less likely
to block good work."

The enforcement false-positive rate is therefore unmeasured. This charter
authorizes the narrow benchmark extension that measures it, and nothing else.

The freeze (§Why benchmark expansion is frozen) forbids adding adversarial,
paraphrase, or known-good-behavior scenarios **silently**, because doing so to
move a headline number is overfitting. This document is the explicit
authorization path that freeze demands: the scenarios below pin behaviors that
regressed in the field, as permanent regression controls — not as metric
improvement targets.

## 2. Authorized changes — exactly this

1. **A separate enforcement-quality regression suite** may live alongside the
   canonical suite (separate directory root, dedicated frozen fixture memory),
   containing two scenario partitions:
   - **violation** scenarios — measure false negatives (a miss = undetected
     forbidden pattern);
   - **benign** scenarios — measure false positives (a block = benign content
     blocked).
2. **`scenario.json["scenario_type"]`: `"violation"` | `"benign"`** is an
   authorized benchmark-methodology addition. Absent means `violation`
   internally; an **unknown value is `MALFORMED`** (a typo such as
   `"bening"` must fail loudly, never fall back to violation semantics).
   Every existing fixture omits the field and is therefore unaffected.
3. **A sixth verdict, `FALSE_POSITIVE`**, defined only for benign scenarios:
   the enhanced side produced ≥1 violation against benign content. Benign
   scenarios with zero violations are `PASS`. Violation-scenario verdict logic
   (PASS / FAIL / WEAK / WEAK_RETRIEVAL / MALFORMED triggers) is untouched.
4. Runner/report/CLI code may implement the above, additively — with one hard
   boundary: **canonical legacy output stays byte-identical**. New fields
   (`scenario_type`, exposure, the partitioned scorecard:
   `violation_passed`, `violation_checkable`, `benign_total`,
   `benign_blocked`, `benign_checkable`, `false_positive_rate`,
   `benign_uncheckable`) are emitted **only** for scenarios that explicitly
   opt in by declaring `scenario_type`. Absent-`scenario_type` results are
   treated as violation internally but render exactly as before, so existing
   canonical terminal, Markdown, and JSON output is byte-for-byte unchanged.
   This follows the v1.1 additive-JSON precedent without touching frozen
   output.
5. Fixture set: the initial enforcement-quality suite consists of **seven
   scenarios — three violation guards + four benign controls** — each
   traceable to the #317 incident regressions or the matcher contract they pin.
6. **Exposure contract** — `scenario.json["expected_exposed_decision_ids"]`
   for benign scenarios: the decision IDs whose governing rules must be in
   actual enforcement scope (present in the runner's positive-score top-K
   retrieval set, i.e. the retrieval-gated tier) before a benign PASS is
   meaningful. This field is an authorized methodology addition that
   deliberately does **not** participate in Layer 1 metrics: it is recorded on
   a separate per-result field (e.g. `exposure`), never inside the `layer1`
   objects, so Recall/Precision/injection aggregates are untouched. A benign
   scenario whose expected exposed decision is absent from enforcement scope
   is `WEAK_RETRIEVAL` / uncheckable — never `PASS` — preventing a
   coincidental 0% FPR when the governing rule was never actually applied.
   Violation scenarios may optionally use the same field with identical
   semantics; existing canonical fixtures do not.

## 3. Frozen — explicitly unchanged

- **Canonical seven fixtures**: byte-identical; canonical suite count stays 7;
  `examples/benchmarks/reports/RESULTS.md` stays as written.
- **Historical 7/7 headline** remains the canonical-suite Layer 2 result. The
  benign suite never merges into that headline; the two suites are reported
  separately, always.
- **Retrieval methodology**: scoring formula, weights, stopwords, tiebreak,
  K=3, and the `governed` Layer 1 aggregation filter. Benign scenarios must
  declare no `expected_protected_decision_ids`; they are then excluded from
  Layer 1 means exactly as id-less scenarios are today, so Recall@3 /
  Precision@3 / injection rate cannot move through this extension.
- **Five-verdict semantics for violation scenarios** and the assertion DSL.
- **Determinism discipline**: canned content, stable sort, no live model.

## 4. Metric authority

| metric | definition | role |
|---|---|---|
| violation catch rate | `violation_passed / violation_checkable` where checkable = `PASS_violation + FAIL_violation` | authoritative — must stay 1.00 |
| **false-positive rate** | `benign_blocked / benign_checkable` where checkable = `PASS_benign + FALSE_POSITIVE` (all exposed) | authoritative — target 0 |
| uncheckable counts | benign scenarios ending MALFORMED or WEAK_RETRIEVAL (exposure miss) | visibility only — see §5 |

**Denominator rule:** FPR is computed over **checkable benign scenarios
only**: evaluated, exposure-satisfied `PASS_benign + FALSE_POSITIVE`. A
MALFORMED or exposure-missed (`WEAK_RETRIEVAL`) benign scenario must not lower
the denominator and must not silently disappear: both are counted and rendered
in every report as uncheckable.

**Report partition rule:** the enforcement-quality suite holds 3 violation +
4 benign scenarios; generic legacy aggregates (`passed`, `pass_rate`,
"violations caught") must never render across the combined set. Authoritative
rendering is the pair above — violation catch rate and false-positive rate —
in terminal, Markdown, and JSON output. Existing legacy JSON keys may remain
for compatibility, but must not be used to label benign PASSes as "violations
caught".

## 5. CLI edge — decided here, not accidentally later

Today only verdict `FAIL` makes `mneme benchmark` exit 1 (`cli.py`
`has_failures`). This charter decides:

- **`FALSE_POSITIVE` exits 1.** Blocking benign content is a failing benchmark
  condition; that is the entire point of the metric.
- **`MALFORMED` remains exit-0 suite-wide.** Exit-code semantics are part of
  the frozen methodology; changing them wholesale is out of scope here. The
  silent-degradation risk is instead covered by (a) mandatory rendering of the
  uncheckable count, and (b) the merge-blocking signal below: any MALFORMED
  scenario in any shipped suite blocks the implementation PR, and any future
  PR introducing one is blocked by the ported integrity tests.

## 6. Merge-blocking invariants (implementation PR and successors)

1. Canonical suite runs **byte-identically**: same 7 verdicts, same Layer 1
   numbers, same explanations shape, and byte-for-byte unchanged terminal,
   Markdown, and JSON output (legacy fixtures emit no `scenario_type`,
   exposure, or partitioned scorecard fields — see §2.4). Any diff in
   canonical output blocks.
2. Any modification to a canonical fixture file blocks.
3. Enforcement-quality suite at merge time: catch rate 3/3, FPR 0/4, **every
   benign scenario exposure-satisfied** (its `expected_exposed_decision_ids`
   present in enforcement scope). Later PRs: any new FALSE_POSITIVE, any
   caught-rate drop, or any benign scenario turning WEAK_RETRIEVAL /
   uncheckable blocks.
4. Any MALFORMED scenario in any shipped suite blocks.
5. A benign PASS without a satisfied exposure contract is invalid by
   construction and cannot occur; if the runner ever emits one, that is an
   implementation defect and blocks.
6. Report output partitions violation and benign results per §4; combined
   "violations caught" rendering across both partitions blocks.
7. `pytest` green; `mneme check --mode warn` clean against the governance
   source.

## 7. Purpose boundary

This extension exists for **regression visibility after observed dogfood
evidence** (#317 lineage). It does not authorize: metric-improvement work,
generalization or distribution claims, tuning against the new suite, adding
scenarios beyond incident-traceable regressions or documented governance gaps
(anti-inflation criterion carried over from the Step 3C charter §3), or any
change to the frozen list in §3. New benign/guard scenarios require their own
charter reference to the incident or gap they pin.

## 8. Exit criteria

Sequence gate: the `[layer1-freeze]` amendment PR referencing this merged
charter lands **before** any behavioral/benchmark implementation.

Charter satisfied when: runner/report/CLI implement §2 (including the exposure
contract) within §3–§6; the enforcement-quality suite ships frozen with
provenance documented in its README (invocations, metric definitions, scorecard
template, and per-scenario `expected_exposed_decision_ids` with provenance);
canonical suite is byte-identical; full test suite green; scorecard recorded
once in the implementation PR description (violation catch rate, FPR,
uncheckable count, recall@3, precision@3, injection rate).

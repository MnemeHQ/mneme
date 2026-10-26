# CM-01-B0-A D1-S — Independent Statistical Review

**Status:** documentation-only REVIEW; no preregistration freeze, model calls, or benchmark execution.
**Date:** 2026-10-25
**Issue:** #657; parent #640.
**Source:** D1 resolution #655, squash-merged at 4b8471149d49f6f4a2a4ddfd0d3601d59355c337.

## Review verdict

This review must be interpreted together with the **merged, still-unratified D1 Erratum 1** (PR #664): E-1 redefines T5–T8 workloads; E-2 changes failure attribution; E-3 requires symmetric broker routing; E-4 distinguishes cache-hit variance from token accounting completeness. These amendments remain subject to D1-C parameter approval.

The D1 formulation is mathematically coherent as a *planning approximation*, not evidence of an adequately powered benchmark. The independent experimental unit is a distinct scenario, never an individual model turn or repeated sample of the same prompt.

Primary scenario log ratio: `ell_s = mean_r log(C[s,r]/D[s,r])` for fixed, paired R trials. Family estimand: `theta = (1/4) sum_f mean_s ell_s` for T5-T8, with token benefit `Delta=1-exp(theta)`. Independently resample scenario clusters within each family, preserving all paired repetitions and 1/4 family weights. Source usage must be complete for every planned pair or the study is inconclusive unless a higher-priority hard gate failed.

The corrected null is `theta >= theta0 = log(1-delta_material)`; the planned effect is `theta1=log(1-delta_planning)`, where `delta_planning > delta_material`; hence `gamma=theta0-theta1>0`. The approximate equal-N sample-size formula is:

`N_approx=ceil((z_(1-alpha)+z_(1-beta))^2 * sum_f sigma_f^2 / (16*gamma^2))`

This is **not** the achieved power of the actual finite-cluster bootstrap trial. Near the 15% null boundary, power to exceed the material threshold is near alpha, not 80%.

## Review findings to resolve before D1-C

1. **Planning effect:** Approve delta_planning separately from the 15% materiality threshold. Prefer ratifying the plausible planning effect and sensitivity set *before pilot*, rather than choosing a favorable pilot effect to make N convenient. If pilot-selection is chosen instead, its exact rule and limitations must be preregistered.
2. **Repetition selector:** Freeze a finite allowable set of R values and a deterministic rule using pilot-estimated between-scenario and within-scenario variation. Repeated runs are not independent scenarios.
3. **Sample-size selector:** Freeze a conservative upper-variance method, allocation/quotas per T5-T8 family, the minimum genuinely independent scenario count, and any finite enrollment cap. N and R remain UNKNOWN without pilot data.
4. **Bootstrap coverage:** Prespecify simulations or defensible analytic checks of the actual stratified scenario-cluster percentile-bootstrap decision rule: false positive frequency at the null boundary and conditional power under the approved planning effect. Specify PRNG/seed, 10000 bootstrap draws (proposed), quantile convention, cluster minima and failure rules. No outcome-driven change of interval method.
5. **Outcome precedence (Erratum 1 E-2):** Harness/authority/security/cleanup failure in either arm and treatment-attributable fabricated identity are zero-tolerance FAILs. Non-fabricated wrong/missing identity and format errors in either arm feed a prespecified paired correctness non-inferiority interval, rather than automatically failing the entire study. Its margin, per-arm reliability floor and decisive-outcome probability must be approved; incomplete token usage remains INCONCLUSIVE absent higher-precedence FAIL. No complete-case replacement, post-hoc suppression or successful-only token averages.
6. **Latency:** One paired scenario-level log latency ratio and one-sided cluster interval, with full specified startup/cleanup window in both arms. Passing latency noninferiority is a conjunctive gate, not a second opportunity to claim benefit.
7. **Meaning of power:** A prospective 80% token-test power target is conditional on correctness, token-record completeness and latency passing, unless independent joint power/reliability assumptions justify the overall rate. Do not equate planned N with overall test power.
8. **Boundary equalities:** Freeze exact strict/non-strict comparisons for benefit, no-benefit and latency intervals at the equality points.


## Erratum E-1 statistical alignment — required before any pilot

The four primary workload families now represent: T5 one trace; T6 trace-predicate filtering of m ≥ 3 candidates including zero-match and all-match bins; T7 a seed-trace → path-dependent applicability → target-trace chain; T8 a k ≥ 2 trace fan-out. The estimand can retain 1/4 weighting **only if** the human owner and statistics reviewer prospectively declare that each workload type represents equal benchmark importance, not equal frequency in real repositories. Record the resulting target population and the sensitivity analysis under alternative plausible workload frequencies as secondary/descriptive; never choose weights using observed confirmatory benefit.

Freeze m/k bins, T6 zero/partial/all-match quotas, T7 chain adequacy and approved scenario distribution before pilot. If any family is structurally unachievable or collapses to an equivalent workload under actual MCP transports, do not retain four-family claims or reuse an unadjusted N: amend the protocol before pilot, update family variance/power logic and keep old results separate.

E-2 paired correctness non-inferiority uses per-scenario correct-answer fractions and an independently validated scenario-cluster bound on C-D. Preapprove `margin_correct` and the reliability floor **before pilot**, account for missed provider-usage pairs, and report projected *decisive-outcome* probability in addition to conditional token-test power. Hard containment and treatment-attributable fabrication remain distinct FAIL classes. No pilot effect/variance, correctness margin, weights or model-run outcome is inferred here.

## Zero-model-call verifier examples (specification only)

- Equal token volumes yield a 0% point benefit.
- Artificial 20% reduction across complete pairs yields a 20% point benefit; this is not an observed improvement.
- Repeat observations are kept within scenario clusters and never used as independent bootstrap draws.
- Unequal family sample counts do not change family weight 1/4.
- Seeded Type-7 bootstrap quantiles and monotonic log-ratio transformation reproduce exact test fixtures.
- Code Mode fabrication of a canonical identity never present in a genuine MCP result yields FAIL even with fewer tokens. Other incorrect identities enter the paired correctness gate; if its confidence interval is insufficient or the reliability floor is breached, they cannot yield BENEFIT.
- Missing provider request usage yields INCONCLUSIVE unless a higher failure occurred.
- Latency CI crossing the 1.20 margin yields INCONCLUSIVE.
- Cancel/cleanup leak yields FAIL.
- A plan effect equal to the threshold cannot be used to claim 80% statistical power.

## Recommendation

**READY for independent statistics design review only.** Formal D1-C remains BLOCKED until threshold/planning effect, alpha/power, pilot variance, R/N algorithms, cluster-bootstrap coverage, reviewer and analysis hash are approved. No B0-A implementation or API call is authorized. B0-M retains its separate mechanical PASS/VERIFIED status.

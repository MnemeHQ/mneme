# CM-01-B0-A - D1-C Readiness Decision Register

**Status:** WORKING REGISTER FOR DECISION - documentation only. **No decision is recorded as made here. Not a preregistration. Authorizes no implementation, calibration call, corpus or host build, pilot, confirmatory run, B0-A execution or S1-A2 work.**
**Date:** 2026-10-26. **Tracker:** [#640](https://github.com/MnemeHQ/mneme/issues/640).
**Sources (merged `main`):** D0 #654 `8060b9bc`; D1 #655 `4b847114`; D1 Erratum 1 #664 `862dce39` (proposed, unratified); D1-P #660 `d9868399`; D1-S #661 `eb198efc`; corpus/evaluator #662 `648e32e5`; D1-H #663 `c7782dcf`.

How to read: **Proposed** values are carried from the merged documents with a one-line reason. **TBD** means there is no supporting evidence, so no value is proposed. **Phase A** decisions must be made before any pilot. **Phase B** items can only be finalized after pilot variance exists; their *method* is fixed in Phase A. Owner roles other than the human owner are currently unassigned (A24).

## Phase A - decide before the pilot

| # | Parameter | Proposed value - justification | Existing commitment | Owner | Blocks until decided |
|---|---|---|---|---|---|
| A1 | Provider, immutable snapshot, endpoint/region, API and SDK versions | **TBD, human choice.** Criteria: documented stable snapshot ID; complete usage on success, tool, failure and incomplete responses; identical tool calling in both arms. No comparative evidence supports picking a provider. | D1 §5.5; #660 §4 (BLOCKED) | Human owner + model/usage reviewer | A2-A6, calibration, pilot |
| A2 | Decoding: temperature, reasoning/effort, speed/tier mode, max tokens | Fixed and identical in both arms; record effective defaults. Model settings are the main uncontrolled token driver. | D0 §8; #660 §4 (BLOCKED) | Model/usage reviewer | Calibration, pilot |
| A3 | Response mode | **Non-streaming.** Anthropic streamed usage is cumulative, so per-event summing double-counts (C2). | #660 §4 prefers non-streaming | Model/usage reviewer | Token mapping (A4) |
| A4 | Token mapping and live calibration scope | Adopt the #660 per-provider mapping. Authorize a **minimal, separately approved** calibration set to verify null fields, failure-path usage and the E-4 cache reconciliation. Call count and budget TBD. | D1 §3; #660 §§2-3; E-4 | Human owner (authorization) + model/usage reviewer | Primary metric validity, pilot |
| A5 | Cache policy | Identical configuration in both arms; disable where the provider supports it; otherwise rely on E-4 invariance with the reconciliation check. | D1 §3.2 as amended by E-4 | Model/usage + statistics reviewers | A4, latency (A18) |
| A6 | API budget and credential custody | Key only in the trusted orchestrator, never in the guest. Budget amount TBD. | D1 §7.4; #663 §4.5 | Human owner | Any billable call |
| A7 | Materiality threshold `delta_material` | **15% total-token reduction (baseline).** A judgment of practical significance, not data-derived; proposed in D0 and carried unchanged by D1. | D0 §5; D1 §4.2 (proposed) | Human owner + statistics reviewer | A9, power plan, D1-C |
| A8 | One-sided alpha / power target | **0.05 / 0.80.** Conventional; power is conditional on the gates passing (#661 finding 7). | D1 §5.3 (proposed) | Statistics reviewer + human owner | Power plan |
| A9 | Planning effect `delta_planning` | **Value TBD.** Method proposed: ratify a pre-pilot sensitivity set strictly above 15% (#661 finding 1's preference). A pilot-informed rule is allowed only if preregistered with its limits. | D1 §5.3; #661 finding 1 | Statistics reviewer + human owner | N_f (B3); D1-C |
| A10 | Decision-boundary equalities | Adopt D1 as written: BENEFIT `Delta_L >= 0.15`; NO-BENEFIT `Delta_U < 0.15`; latency pass `L_U < 1.20`, fail `L_L > 1.20`. D1 already states them, so freezing them closes #661 finding 8. | D1 §§4.2-4.3 | Statistics reviewer | Analysis code |
| A11 | Interval method | Stratified scenario-cluster percentile bootstrap, `B = 10000`, type-7 quantiles on the **`Delta` scale**, PRNG and seed fixed pre-pilot. Coverage and power simulation specified at the null boundary and the smallest allowed `N_f` (C3). | D1 §2.5; #661 finding 4 | Statistics reviewer | Analysis code, B4 |
| A12 | Family weights | Equal 1/4 across T5-T8, **only** with a declaration that the four workload types matter equally to the benchmark; alternative weightings reported as a secondary sensitivity analysis. | D1 §2.2; E-1.3; #661 E-1 alignment | Human owner + statistics reviewer | Estimand, D1-C |
| A13 | Correctness margin `margin_correct` | **TBD, no evidence.** Method fixed: paired non-inferiority on per-scenario correct fractions with a cluster bound on C-D. | E-2.2, E-2.3 | Human owner + statistics reviewer | Pilot |
| A14 | Per-arm reliability floor | **TBD, no evidence.** | E-2.2, E-2.3 | Human owner + statistics reviewer | Pilot |
| A15 | Minimum probability of a decisive outcome | **TBD.** Recommend fixing the threshold before the pilot so it is not set after seeing pilot rates; E-2.3 allows it up to D1-C. | E-2.3 | Human owner + statistics reviewer | Confirmatory authorization |
| A16 | Retry policy | 0 answer retries; 2 infrastructure retries with fixed backoff. Avoids confounding from answer repair. | D1 §8.3 (proposed) | Protocol/statistics reviewer + human owner | Harness spec |
| A17 | Order and concurrency | Paired randomized arm order, concurrency 1, fixed seed. | D0 §3; D1 register | Statistics reviewer | Harness spec |
| A18 | Latency guardrail and timing window | 1.20 non-inferiority margin, with start/end events frozen. Spans include Code Mode host start-up and the broker hop in both arms. Ratify only after candidate-runtime start-up latency is measured (C1). | D1 §4.3; E-3.2 | Statistics + security reviewers, human owner | BENEFIT route |
| A19 | `R` and `N_f` selector algorithms | `R` from a finite allowed set by a deterministic rule; `N_f` from the D1 §5.3 formula with a conservative upper variance bound; a minimum `N_f` justified by coverage simulation (C3); finite enrollment cap. Values are Phase B. | D1 §§5.3-5.4; #661 findings 2-3 | Statistics reviewer | B1-B4 |
| A20 | Corpus structure and quotas | E-1 families. Bins for `m >= 3` and `k >= 2`; T6 `c` bins zero/partial/all-match; applicability populated; only `p_T6` and the T7 seed disclosed; 5-token Jaccard 0.60/0.80. **Quotas and counts TBD.** | E-1; D1 §6.4; #662 §§2-7 | Corpus reviewer + statistics reviewer | Corpus build |
| A21 | Pilot design | Scenarios disjoint from confirmatory, labeled PILOT; selection rule and eligible bank approved before the pilot. **Pilot size TBD.** | D1 §5.2; #662 §8 | Statistics reviewer + human owner | Pilot authorization |
| A22 | Restricted host | Container or microVM **TBD**; seccomp/AppArmor/cgroup profile; `pids.max` measured for the pinned Node/F1 image (C1); adapter `inventory` is a hash-pinned `tools/list` snapshot; one broker configuration for both arms; limits sized at corpus freeze. | D1 §7; E-3; #663 §§3-5, 10 | Security reviewer | Host build, red team, pilot |
| A23 | Incident stops and evidence retention | Adopt D1 §7.6 / #663 §7 stop rules. Retention period and access control TBD. | D1 §§7.6, 9.5; #663 §§7-8 | Security/evidence reviewer + human owner | Pilot |
| A24 | Independent reviewer roles | Separate model/usage, statistics, corpus/evaluator, security and outcome reviewers. **Unassigned.** | D1 §9.3; register | Human owner | Every approval above |
| A25 | Stage authorizations | Separate explicit approvals for: calibration calls, corpus/evaluator implementation, host build and red team, pilot. | D1 §11; #662 §11; #663 §12 | Human owner | Each stage |

## Phase B - finalize only after pilot variance is measured

| # | Item | Method fixed in | Owner | Blocks |
|---|---|---|---|---|
| B1 | `sigma_f` per family (between- vs within-scenario split, upper bound) | A19 | Statistics reviewer | B3 |
| B2 | `delta_planning`, only if the pilot-informed rule was chosen in A9 | A9 | Statistics reviewer + human owner | B3 |
| B3 | `N_f` per family and `R` | A19 | Statistics reviewer | Confirmatory manifest |
| B4 | Coverage/power simulation results; projected decisive-outcome probability against A15 | A11, A15 | Statistics reviewer | D1-C |
| B5 | Confirmatory scenario set, by randomized selection from the approved bank | A20, A21 | Corpus reviewer | D1-C |
| B6 | Broker numeric limits from frozen-corpus maximum result sizes | A22 | Security reviewer | Confirmatory run |
| B7 | Analysis code hash, manifest hashes, immutable D1-C document | All of A | Human owner | Confirmatory authorization |

## Carry-forward findings (resolved inside D1-C; original PRs not reopened)

| # | Finding | Source | Lands in |
|---|---|---|---|
| C1 | "PID limit 1" is infeasible for the Node-based F1 executor, because threads count against `pids.max`. Use a measured `pids.max` and explicit `clone`/`clone3` seccomp handling; measure start-up latency per candidate runtime. | #663 §4.3 | A18, A22 |
| C2 | Provider usage metadata: Anthropic `thinking_tokens` is a re-tokenized approximation (never use it for reconciliation); record `speed`, `inference_geo` and the API version header; take only terminal cumulative usage from streams. | #660 §§1-2 | A2, A3, A4 |
| C3 | Statistics: type-7 quantiles are taken on the `Delta` scale (not invariant under the log transform); coverage simulation must include the smallest allowed `N_f`; report the NO-BENEFIT operating characteristic. | #661 verifier list, finding 4 | A11, A19 |
| C4 | Naming: the #662 filename and #658 title say "d1-c" for the corpus track, while D1 §5.5 uses D1-C for the preregistration. Merged files stay as recorded; the D1-C document declares "D1-Corpus" as the alias for the corpus track. | #662, #658 | D1-C header |

**Unchanged:** D1-C remains BLOCKED. No implementation, pilot, model/API call, B0-A or S1-A2 is authorized. B0-M remains a mechanical PASS/VERIFIED only, with no model-efficiency claim.

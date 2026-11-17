# CM-01-B0-A - D1 Protocol Resolution Proposal

**Status:** PROPOSAL FOR REVIEW - **not accepted, not frozen, not preregistered, and not authorized for execution**.

**Date:** 2026-10-25  
**Workstream:** CM-01, parallel optional orchestration interoperability; [tracker #640](https://github.com/MnemeHQ/mneme/issues/640).  
**Design baseline:** `8060b9bc318e0a0cb206d0cc9d3e6833977e367c` (D0 proposal PR #654 squash merge; roadmap reconciliation PR #653 at `8250aa09cfedf99b392ccabff597beca1b4d2055`).  
**D0 proposal:** PR #654, reviewed head `6220b482f7f12260b284bcca571abee52a2efbc6`, squash-merged at `8060b9bc318e0a0cb206d0cc9d3e6833977e367c`.  
**Predecessors:** S1-A1 PR #627; P0-01 FAIL PR #633 (`adf50933`); F1 PASS / VERIFIED PR #642 (`f8591102`); B0-M PASS / supplemental VERIFIED PR #650 (`34d75bec`).

This document resolves, as far as possible without new measurements, the eight D1 areas left open by the D0 review. It is a design-resolution proposal, not a protocol freeze. It does not authorize a model/API call, pilot, confirmatory run, benchmark implementation, production integration, new MCP capability, B0-A execution or S1-A2 work.

Where a value depends on unavailable evidence, the value is marked **TBD** or **BLOCKED**. This document does not invent variance, sample size, model availability, cost or security results.

## 1. Governing constraints

- **ADR-017:** retrieval is context; enforcement remains outside this benchmark. No enforcement, fail-closed or protection claim follows from B0-A.
- **ADR-022:** any eventual evidence or implementation record uses a task branch, PR and squash merge. This proposal is documentation-only.
- **ADR-023:** the Decision Index and the Mneme runtime projection are the only authoritative source of applicable canonical decisions. B0-A must not create a second resolver, fabricated trace, rule or evidence.
- **ADR-027:** the genuine upstream inventory remains exactly six tools. Both model arms expose or allow only the four read methods: `decision.get`, `decision.search`, `decision.applicable_to`, `decision.trace`. `decision.propose` and `decision.propose_batch` are never available to the model.
- **F1 reuse:** the merged F1 executor, adapter and cancellation semantics are used read-only and hash-pinned. F1 files, S1-A1, P0, B0-M and ADR-034 M4 evidence are immutable.
- **B0-M separation:** B0-M is a mechanical regression and smoke corpus. Its 24 deterministic decisions and eight fixed task examples are not B0-A confirmatory evidence.
- **No production path:** no Workers, hosted control plane, production mutation, new production dependency, changed MCP authority or S1-A2 implementation. A validation-only container runtime is permitted for the restricted host; it must not enter production.
- **No model call authority:** no model/API call is authorized by D1. A separately approved pilot authorization is required first.

## 2. Primary estimand

### 2.1 Units and notation

- A **scenario** `s` is one frozen task instance: corpus fixture, prompt, tool-visible inputs, required answer schema and expected answer. It belongs to exactly one family `f` in `{T5, T6, T7, T8}` for the primary analysis.
- A **repetition** `r = 1..R` is one paired randomized run block for the same scenario, with one direct-arm execution and one Code Mode execution in separate fresh model conversations and separate fresh MCP children.
- `D[s,r]` is the primary token total for the direct execution.
- `C[s,r]` is the primary token total for the Code Mode execution.
- `ell[s,r] = log(C[s,r] / D[s,r])` is the paired log token ratio. Negative values favor Code Mode.
- `R` is fixed and equal for every scenario in the confirmatory design. The value of `R` is a D1 parameter (**TBD**).

The independent sampling unit is the scenario, not a repetition and not an individual model turn. Repetitions estimate within-scenario measurement variation; they do not increase the number of independent scenarios.

### 2.2 Family-balanced estimand

For a complete scenario `s`, define the scenario-level log ratio as the equal-weight mean over its repetitions:

```text
ell_s = (1 / R) * sum_{r=1..R} log(C[s,r] / D[s,r])
```

For each family `f`, with `N_f` complete scenarios:

```text
ellbar_f = (1 / N_f) * sum_{s in family f} ell_s
```

The primary estimand is the equal-family-weighted mean log ratio:

```text
theta = (1/4) * sum_{f in {T5,T6,T7,T8}} E[ellbar_f]
```

The reported improvement is:

```text
Delta = 1 - exp(theta)
```

`Delta` is the estimated proportional reduction in total model tokens for Code Mode relative to direct MCP. A positive `Delta` favors Code Mode.

Each of T5-T8 receives weight `1/4`, regardless of how many scenarios or repetitions that family contributes. A family with fewer scenarios therefore gives more weight per scenario; that is intentional in the family-balanced estimand and must be disclosed.

### 2.3 Repeated executions

- `R` is fixed before confirmatory execution and is the same for every scenario.
- `ell_s` averages repetitions equally on the log scale. This is a geometric mean of token ratios, not an arithmetic mean of percentages.
- Repetitions are never resampled as if they were independent scenarios.
- If `R` must differ by scenario, the design must be re-preregistered. This proposal does not permit variable `R` in the primary analysis.

### 2.4 Missing pairs

The primary analysis population is every planned confirmatory scenario. A scenario is **complete** only when every planned repetition has both arms, valid correctness status and complete provider token usage.

- No imputation, winsorization, trimming, substitution or complete-case selection is allowed for the primary verdict.
- If any planned scenario is incomplete, `BENEFIT` and `NO-BENEFIT` are impossible. The outcome is `FAIL` if a hard gate failed, otherwise `INCONCLUSIVE`.
- A complete-case estimate may be reported descriptively, clearly labeled non-verdict.
- If any family has fewer than two complete scenarios, the clustered interval is not estimable and the outcome is `INCONCLUSIVE`.

### 2.5 One-sided confidence interval

The interval is a **stratified cluster bootstrap by scenario**, preserving the paired observations and all repetitions.

- Resample scenarios with replacement independently within each family, keeping all `R` paired repetitions for each selected scenario.
- Keep the equal family weights `1/4` in every bootstrap replicate.
- Use `B = 10000` bootstrap replicates, a fixed seed and the analysis code hash recorded before confirmatory execution. `B` and the seed are protocol parameters; changing them after data is prohibited.
- Compute the bootstrap distribution of `Delta`.
- Use the Hyndman-Fan type 7 quantile for `Q(p)`: sort the `B` values ascending, set `h = (B - 1) * p + 1`, and linearly interpolate between the values at `floor(h)` and `ceil(h)`.
- One-sided 95% lower bound: `Delta_L = Q(0.05)`.
- One-sided 95% upper bound: `Delta_U = Q(0.95)`.

The percentile bootstrap is the primary interval. If the interval is unstable or a family is too small, the result is `INCONCLUSIVE`; no alternative interval may be selected after inspecting confirmatory outcomes.

### 2.6 Deterministic analysis pseudocode

```text
INPUT:
  ledger: every planned scenario and repetition with
          family, scenario_id, arm, tokens, correctness, usage_complete
  R: fixed repetitions per scenario
  B: 10000
  seed: preregistered
  delta_material: approved threshold (proposed 0.15)

STEP 1 - validate ledger
  for each planned scenario s:
      require exactly R valid pairs
      require complete provider usage for both arms in every pair
      require correctness status for every pair
  if any planned scenario is incomplete:
      record reason
      result.complete = false
  if any family has fewer than 2 complete scenarios:
      result.complete = false

STEP 2 - point estimate
  for each complete scenario s:
      ell[s] = mean over r of log(C[s,r] / D[s,r])
  for each family f:
      ellbar[f] = mean of ell[s] for s in f
  theta_hat = mean of ellbar[T5..T8]
  Delta_hat = 1 - exp(theta_hat)

STEP 3 - stratified cluster bootstrap
  for b in 1..B:
      for each family f:
          sample N_f scenarios with replacement from complete scenarios in f
          retain all R pairs for each sampled scenario
          ellbar_star[f] = mean of ell[s] for sampled scenarios
      theta_star[b] = mean of ellbar_star[T5..T8]
      Delta_star[b] = 1 - exp(theta_star[b])

STEP 4 - bounds
  Delta_L = quantile_type7(Delta_star, 0.05)
  Delta_U = quantile_type7(Delta_star, 0.95)

STEP 5 - classify using Section 4
  emit ledger, estimates, bounds, exclusions, code hash and seed
```

### 2.7 Secondary and descriptive analyses

Secondary/descriptive outputs, with no alternative verdict route:

- input, output, reasoning and cache token components;
- model request/turn count;
- model-visible intermediate-result bytes and any approved pinned-tokenizer estimate;
- genuine MCP method/argument/result counts;
- end-to-end and component latency;
- correctness and failure distributions;
- T1-T4 negative-control overhead;
- cancellation/cleanup outcomes;
- raw distributions, outliers and unfavorable examples.

Secondary results cannot be promoted to the primary endpoint after observation. No multiplicity-adjusted secondary claim is planned.

## 3. Token accounting

### 3.1 Primary token total

The primary unit is the **total provider-reported model tokens consumed by one arm execution**. It is the sum over every model API request in that execution, including every turn, retry and model-generated code request, of the provider's non-overlapping reported token categories.

The normalized total must include, exactly once:

- input/prompt tokens, including system prompt, task objective, tool schemas, conversation history, host-injected instructions and tool results;
- output/completion tokens, including model-generated code, tool-call arguments, final answer and any provider-reported reasoning tokens not already included in output;
- prompt-cache read tokens, if reported separately;
- prompt-cache write/creation tokens, if reported separately;
- any other provider-reported model-processing token category that is part of the provider's total.

The mapping from provider fields to the normalized total is frozen per model snapshot. It must be verified against at least one provider response and recorded. If provider fields overlap or the mapping is ambiguous, the execution is usage-incomplete and the verdict is `INCONCLUSIVE`.

Tool schemas and system prompts are not subtracted. They are part of the intervention's input cost and are recorded separately by byte/digest.

### 3.2 Caching

The primary metric counts token volume, not billed cost. Cached tokens are included at their reported token counts; they are not discounted.

- Disable provider prompt caching where the provider supports a symmetric disable setting.
- If caching cannot be disabled symmetrically, both arms must use the same caching policy, and cache read/write categories must be complete and symmetric.
- If cache behavior cannot be made symmetric, or cannot be fully reported, the primary verdict is `INCONCLUSIVE`.
- Do not compare different cache regimes and call the difference an efficiency effect.

A cost analysis would be a separate endpoint with provider pricing and is **not** made here.

### 3.3 Retries and failed requests

- Every model API request counts, including retries and requests that later fail.
- Tokens consumed by a failed or retried request are included when the provider reports them.
- If usage for any request in a planned execution is missing, the execution is usage-incomplete; no local tokenizer estimate may replace it in the primary metric.
- Secondary pinned-tokenizer estimates may be reported, clearly labeled, but cannot produce a primary verdict.

### 3.4 Missing usage and verdict

Any of the following makes the primary metric non-computable:

- missing input/output/usage record for any model request;
- missing reasoning/cache category that the approved mapping requires;
- incomplete streamed response usage;
- provider total that cannot be reconciled to its categories;
- token report that includes non-model or host operations.

A non-computable primary metric yields `INCONCLUSIVE` (or `FAIL` if a higher-precedence hard gate failed). It never yields `BENEFIT` or `NO-BENEFIT`.

### 3.5 Exclusions from the token total

The primary total excludes:

- MCP server compute;
- local QuickJS/container CPU or memory;
- harness, evaluator, logging or evidence processing;
- network transport bytes;
- wall-clock latency;
- cost or projected cost.

Those are separate descriptive measurements or gates.

## 4. Outcome classification

### 4.1 Hard gates

The following gates are mandatory. A hard-gate failure yields `FAIL` regardless of token improvement:

- **G-AUTH:** no proposal, mutation, unknown or non-allowlisted MCP method; only the four read methods.
- **G-IDENTITY:** exact required canonical identities, versions, version IDs, content digests, scopes, derived rule IDs and declared evidence; no fabricated or omitted required field.
- **G-FORMAT:** valid frozen answer JSON with all required fields; malformed or truncated final output is a failure unless the predeclared retry policy recovers it.
- **G-SECURITY:** restricted-host containment, no unauthorized network/filesystem/process/secret access, and OS-level termination verified.
- **G-CLEANUP:** no leaked child, relay, server or container; no unhandled rejection; no outstanding request after bounded drain; valid cancellation notification.
- **G-LATENCY:** no material latency regression beyond the approved guardrail.

A single identity, authority, security or cleanup failure in a planned confirmatory execution is a study `FAIL`; it is not averaged away. This zero-tolerance rule is proposed for approval; if reviewers prefer a nonzero predeclared reliability threshold, it must be fixed before pilot and cannot be relaxed after data.

### 4.2 Material-effect threshold

The proposed materiality floor is:

```text
delta_material = 0.15   (15% total-token reduction)
```

This is **proposed, not ratified**. It must be approved before confirmatory execution. If it is changed after any confirmatory data are observed, the study is `INCONCLUSIVE`; a new preregistration is required.

`BENEFIT` requires the one-sided 95% lower bound `Delta_L >= delta_material`.

`NO-BENEFIT` requires the one-sided 95% upper bound `Delta_U < delta_material`. This is evidence against a material improvement at the approved threshold; it is not proof of zero effect.

If `Delta_L < delta_material <= Delta_U`, the result is `INCONCLUSIVE`.

### 4.3 Latency guardrail

Latency is a mandatory non-inferiority gate, not a second efficiency claim.

- For each paired execution, `L[s,r] = latency_CodeMode / latency_Direct`.
- Use the same scenario-level, family-balanced and cluster-bootstrap procedure on `log(L)`.
- Non-inferiority margin: `1.20` (20% regression), proposed for approval.
- Pass: one-sided 95% upper bound `L_U < 1.20`.
- Fail: one-sided 95% lower bound `L_L > 1.20`.
- Otherwise: `INCONCLUSIVE`.

Latency begins when the harness starts preparing the arm execution and ends after final answer and cleanup. Per-run host/image startup is included for Code Mode because it is part of the treatment; pre-trial environment preparation and image pulls are recorded separately. The exact start/end events must be frozen in the preregistration.

### 4.4 Decision table

| Outcome | Required conditions | Precedence |
|---|---|---|
| `FAIL` | Any G-AUTH, G-IDENTITY, G-FORMAT (unrecovered), G-SECURITY or G-CLEANUP failure; latency lower bound `L_L > 1.20`; protocol violation. | Highest. Even if tokens improve. |
| `INCONCLUSIVE` | No `FAIL`, but any planned pair incomplete; any usage incomplete; any family `< 2` complete scenarios; CI not estimable; sample/power/precision insufficient; threshold or latency guardrail not ratified; unresolved environment drift; latency guardrail interval inclusive of the margin. | Before benefit/no-benefit. |
| `BENEFIT` | No `FAIL`; no `INCONCLUSIVE` condition; all hard gates pass; `Delta_L >= delta_material`; latency pass. | After gates. |
| `NO-BENEFIT` | No `FAIL`; no `INCONCLUSIVE` condition; all hard gates pass; `Delta_U < delta_material`; latency pass. | After gates. |

There is no fifth outcome and no "trend toward benefit" classification. A favorable point estimate with an uncertain interval is `INCONCLUSIVE`.

### 4.5 Multiplicity and stopping

- One primary hypothesis only; no alpha adjustment for the primary.
- The latency guardrail is a mandatory non-inferiority gate. `BENEFIT` requires both primary and latency conditions; no alternative PASS route exists.
- No optional stopping, no peeking, no post-hoc threshold change and no promotion of a secondary result.
- Operational stop rules for security incidents, provider outage, data corruption or credential exposure must be predeclared. A stopped study is `FAIL` or `INCONCLUSIVE` as applicable; raw evidence is retained.

## 5. Sampling and power

### 5.1 Prospective design

- Independent unit: distinct scenario.
- Fixed repetitions: `R` per scenario, equal across the confirmatory design.
- Families: T5-T8 primary; T1-T4 negative controls outside the primary endpoint.
- Allocation: equal `N_f` scenarios per primary family for simplicity and family balance. Unequal allocation is a new protocol decision and must be preregistered.
- No numeric `N_f` or `R` is asserted here. Both are **TBD** until pilot variance and the approved parameters exist.

### 5.2 Pilot

A pilot is required before confirmatory sample-size determination. It is not confirmatory evidence.

- Pilot scenarios are distinct from confirmatory scenarios and never reused.
- Pilot measurements are labeled `PILOT` and excluded from the confirmatory verdict.
- The pilot may calibrate instrumentation, token-report completeness, host behavior and variance. It may not be used to tune prompts or scoring on confirmatory scenarios.
- The pilot protocol, model snapshot, corpus generator, security host, endpoint, threshold and analysis code are frozen before pilot execution.
- After the pilot, only the pre-specified power calculation may set `N_f` and `R`. Any change to endpoint, threshold, scenarios or evaluator requires a new preregistration and invalidates the prior confirmatory plan.
- The pilot itself requires a separate, explicit model/API authorization. It is **not authorized** by this proposal.

### 5.3 Prospective power formula

The power calculation must be for the actual decision rule: demonstrate that the true improvement is **greater than the material threshold**, not merely greater than zero. The old zero-centered formula is not sufficient.

Let:

```text
theta = log(C / D)                              (negative favors Code Mode)
theta0 = log(1 - delta_material)                (null boundary: improvement = material threshold)
theta1 = log(1 - delta_planning)                (true planning effect; delta_planning > delta_material)
gamma = theta0 - theta1                         (positive effect gap above the threshold)
```

`delta_planning` is a separately approved planning effect strictly above `delta_material`. It is **not chosen here**, must be fixed before confirmatory execution, and must not be selected to make the sample size convenient or changed after confirmatory data are observed. If `delta_planning <= delta_material`, the study is at or below the null boundary, where rejection probability is at most `alpha` (5% at the boundary), not the intended power; no finite `N` is claimed and D1 remains blocked.

Let `sigma_f` be the standard deviation of the planned scenario-level log ratio `ell_s` within family `f`, after the fixed `R` repetitions are averaged. The pilot estimates between-scenario and within-scenario residual variance separately, then derives the `sigma_f` appropriate to the planned `R`; it does not treat repetitions as independent scenarios. Let `z_a = z_{1-alpha}` for one-sided `alpha` and `z_b = z_{1-beta}` for power `1-beta`.

For equal `N` scenarios per family and equal family weights, the approximate variance of `theta_hat` is:

```text
Var(theta_hat) = (1/16) * sum_f (sigma_f^2 / N)
```

The one-sided test rejects the null boundary when the upper confidence bound satisfies `theta_U < theta0`, equivalently when the lower improvement bound exceeds `delta_material`. At true effect `theta1`, the approximate power is:

```text
power = Phi( gamma / SE - z_a )
```

`Phi` is the standard normal cumulative distribution function.

Setting `power = 1 - beta` gives `SE = gamma / (z_a + z_b)`. The prospective equal-`N` plan is therefore:

```text
N = ceil( ((z_a + z_b)^2 * sum_f sigma_f^2) / (16 * gamma^2) )
```

with a minimum of two complete scenarios per family for the cluster interval. Two is a computability floor, not an adequacy claim; the approved power plan determines the real `N`.

The pilot must estimate `sigma_f` with a predeclared method that separates between-scenario variance from within-scenario residual variance and derives the scenario-level value for the planned `R`. Use a conservative upper confidence bound for `sigma_f`, not the pilot point estimate, so the plan is not optimistically underpowered. The pilot may inform `delta_planning`, but the pilot effect estimate is not confirmatory evidence and cannot be used to tune the endpoint or threshold. The formula is a planning approximation; the confirmatory analysis remains the scenario-cluster bootstrap. If the pilot cannot estimate `sigma_f` adequately, D1 remains blocked and no `N` is claimed.

Proposed, not ratified: one-sided `alpha = 0.05`, power `0.80`, `delta_material = 0.15`. `delta_planning` is **TBD** and strictly greater than `delta_material`. These values are approval items; none is used to claim power or a numeric sample size in this document.

### 5.4 Repetitions

`R` controls within-scenario measurement error. It does not increase independent scenario count.

- Choose `R` from pilot precision analysis with a predeclared method before confirmatory execution.
- `R` must be equal across confirmatory scenarios.
- Increasing `R` cannot compensate for too few independent scenarios; the power formula uses scenario-level `ell_s`.
- No `R` value is asserted here.

### 5.5 Confirmatory freeze

Before any confirmatory run, a separate D1-C preregistration must freeze:

- exact model snapshot, endpoint, region, parameters and tool-use mode;
- token mapping and caching policy;
- `delta_material`, `delta_planning`, `alpha`, power target, `N_f`, `R`, seed and analysis code;
- corpus, scenario list, prompts, expected answers, evaluator and hashes;
- security host image/config and red-team results;
- exclusions, retries, stop rules and reviewer roles.

No confirmatory run is authorized by this proposal.

## 6. Scenario construction and corpus adequacy

### 6.1 B0-M is not B0-A

B0-M's 24 synthetic decisions, eight fixed examples, hashes and expected answers are a mechanical regression/smoke corpus. They are not the B0-A confirmatory corpus and may not be promoted into B0-A evidence. B0-M can be used only as an explicitly labeled regression check outside the B0-A endpoint.

### 6.2 Corpus requirements

The B0-A corpus is a separately generated, synthetic, non-production Decision Index fixture. It must include enough decisions and relationships to support the frozen scenario families:

- multiple scopes and overlapping scopes;
- active, superseded, deprecated and inactive lifecycle states;
- multiple versions where the scenario requires version identity;
- derived rules, test evidence and explicitly missing lineage links;
- search result cardinalities from unique to ambiguous;
- nonapplicable near-matches and misleading but nonapplicable terms;
- T5-T8 scenarios where a later call's argument depends on an earlier tool result;
- no production, customer, credential or private repository data.

The generator, seed, schema and output must be checked in and hashed. The corpus may not be edited after the confirmatory freeze.

### 6.3 Scenario families and quotas

| Family | B0-A role | Required feature |
|---|---|---|
| T1 | Negative-control / overhead | Unique stable decision ID |
| T2 | Negative-control / overhead | Search-result identity |
| T3 | Negative-control / overhead | Scope-based retrieval |
| T4 | Negative-control / overhead | Rule/evidence lineage, including missing links |
| T5 | Primary multi-step | Search result determines later ID |
| T6 | Primary multi-step | Lineage query depends on search |
| T7 | Primary multi-step | Scope/lifecycle filtering then get/trace |
| T8 | Primary multi-step | Multiple candidates and compact projection |

The primary endpoint uses T5-T8 only. T1-T4 can fail correctness/authority/security gates and are reported descriptively; they do not enter the primary token estimand.

### 6.4 Measurable adequacy checks

Before freezing the confirmatory corpus, all of the following must pass:

1. **Exact uniqueness.** Canonicalized prompt + parameters + expected answer is unique by SHA-256. Zero exact duplicates.
2. **Near-duplicate control.** Normalize each scenario's model-visible prompt and parameters with Unicode NFKC, lowercase and whitespace collapse; tokenize on whitespace and form 5-token shingles. For every unordered pair of confirmatory scenarios, compute Jaccard `J = |A intersect B| / |A union B|` on the shingle sets. Jaccard is symmetric; higher values mean greater similarity. Acceptance is: `J < 0.60` pass; `0.60 <= J < 0.80` requires documented corpus-reviewer approval with rationale; `J >= 0.80` reject and do not freeze. Exact duplicates are always rejected. The `k=5` shingle size and the `0.60`/`0.80` thresholds are proposed for approval and must be ratified before corpus freeze; otherwise D1 remains blocked. Separately, any scenario or expected answer that is identical or near-identical to a B0-M example is rejected; B0-M is not a B0-A source.
3. **Answer leakage.** Expected decision IDs, version IDs, content digests, rule IDs and evidence selectors do not appear in the prompt, tool descriptions or model-visible context unless the task explicitly requires them.
4. **Multi-step dependency.** For T5-T8, a deterministic structural check proves that at least one later-call argument is determined by an earlier tool result and is not fully present in the prompt.
5. **Diversity quotas.** Predeclared minimum counts cover scopes, lifecycle states, cardinality bins, lineage-present/absent cases, active/inactive filters and ambiguity. The actual quotas are **TBD** pending corpus design.
6. **Ground-truth independence.** Expected answers are derived from the frozen corpus by a deterministic evaluator implemented and reviewed separately from the corpus generator. No LLM judge. The evaluator has tests for projections, ordering, missing fields and not-found behavior.
7. **Pilot/confirmatory separation.** Scenario IDs and hashes are disjoint; pilot scenarios are never reused or relabeled as confirmatory.
8. **B0-M exclusion.** B0-M scenarios are absent from the confirmatory manifest and cannot enter the primary ledger.
9. **Synthetic provenance.** The corpus contains no production or private data; all source fields are synthetic.
10. **Hash freeze.** Corpus, scenario list, prompts, expected answers, evaluator, generator, environment and analysis code have SHA-256 entries in a frozen manifest before any confirmatory run.

Any failed check blocks D1-C. This proposal does not claim any corpus is adequate; adequacy is **BLOCKED** until the corpus exists and is reviewed.

### 6.5 Scenario count

The number of decisions, scenarios per family and repetitions is **not chosen here**. It follows from the approved power plan after the pilot. B0-M's 24 decisions do not establish that count.

## 7. Security threat model and restricted host

### 7.1 Assets and threats

Assets: model API credentials, the trusted orchestrator, the Decision MCP server and fixture, evidence logs, the host OS, other workloads and the integrity of the benchmark.

Threats from model-generated Code Mode source:

- reading or writing host files;
- network access or data exfiltration;
- process creation, privilege escalation or container escape;
- secret/environment access;
- infinite loops, memory/CPU/PID exhaustion or output flooding;
- calling unauthorized MCP methods or proposal/mutation tools;
- oversized or malicious MCP arguments/results;
- tampering with evidence or cancellation state;
- prompt injection or instruction smuggling through tool results, corpus text or generated output;
- exploiting a QuickJS/runtime vulnerability;
- denial of service against the harness or provider.

The in-process QuickJS experiment is **not** a hardened hostile-code boundary. F1 proves client cancellation and settlement, not OS-level termination, hardened isolation or cross-platform security.

### 7.2 Trust boundaries

- **Trusted orchestrator:** model API client, task prompts, evidence writer, MCP client, authorization decisions.
- **Restricted executor:** disposable process/container running the pinned F1 executor/adapter and model-generated code. It is untrusted.
- **MCP broker:** trusted narrow bridge that accepts only four read methods, validates arguments and forwards to the genuine MCP. It runs outside the guest.
- **Decision MCP server:** genuine pinned Mneme server, read-only fixture, no proposal store.
- **Provider:** external model API; not trusted for local isolation; its usage reporting is evidence input.

### 7.3 Smallest concrete host architecture

Use one disposable Linux container (or equivalent VM) per Code Mode execution. The direct arm does not execute model-generated code and does not use the guest.

The guest must have:

- read-only root filesystem, non-root UID/GID, no general host mounts (only a dedicated broker socket or VM channel) and a small no-exec tmpfs;
- no network namespace or egress; the only channel is a Unix-domain socket or VM channel to the trusted broker;
- dropped Linux capabilities, `no_new_privs`, a deny-by-default seccomp profile and AppArmor/SELinux confinement;
- PID, mount and user namespaces; cgroup v2 CPU, memory, PID and wall-clock limits;
- no model API credentials, no host environment, no SSH/cloud tokens and no repository checkout;
- output, stderr and log size limits;
- one execution per container; no reuse across arms, scenarios or runs.

The trusted broker:

- exposes exactly `decision.get`, `decision.search`, `decision.applicable_to` and `decision.trace`;
- rejects `decision.propose`, `decision.propose_batch`, unknown methods, extra authority fields and oversized results;
- validates arguments against the pinned upstream schemas;
- forwards to the genuine Decision MCP with a read-only fixture and no proposal store;
- records method, arguments hash, result identity/size and caller execution ID;
- has a per-execution call quota and timeout.

### 7.4 F1 reuse unmodified

The merged F1 `quickjs-executor.mjs` and `adapter.mjs` are used read-only and hash-pinned. The adapter receives a broker-backed client; the broker shim is validation-only and does not modify F1. The executor runs inside the restricted guest with its memory/stack/time limits plus host limits. No F1 file is edited.

The model API calls remain in the trusted orchestrator. The guest has no provider credentials and no direct network path.

### 7.5 Cleanup and termination

On completion, timeout, cancellation or incident:

- terminate the entire cgroup/container process tree with an OS-level signal;
- wait for exit and verify no surviving process, container or mount;
- remove the guest filesystem and temporary artifacts;
- record exit code/signal, duration, resource peaks and cleanup evidence;
- preserve evidence outside the guest before disposal.

Client-side cancellation alone is not accepted as termination proof.

### 7.6 Incident stop conditions

Stop the trial and preserve evidence on any of:

- unauthorized method or argument;
- network, filesystem, process or secret access attempt;
- seccomp/AppArmor/cgroup violation;
- container/runtime escape signal;
- resource-limit breach;
- missing or corrupted evidence;
- credential exposure;
- unexpected host or image drift.

Classify as `FAIL` unless the stop is an external provider/infrastructure event, in which case the affected pairs are incomplete and the outcome is `INCONCLUSIVE`.

### 7.7 Independent demonstration required before pilot

The security host is **not demonstrated** by this proposal. Before any pilot, an independent security reviewer must approve and witness:

- the threat model and container/broker design;
- network isolation and no-egress tests;
- filesystem read/write and mount denial;
- process creation and privilege-escalation denial;
- absence of credentials/environment secrets in the guest;
- seccomp/AppArmor/cgroup enforcement;
- infinite-loop, memory, PID and output-flood termination;
- OS-level termination and no surviving children;
- broker allowlist, schema validation and proposal denial;
- evidence integrity and redaction;
- F1 executor/adapter hash verification;
- a red-team suite with malicious model-code samples.

Until then, no model-generated Code Mode code may be executed in B0-A.

## 8. Failure accounting

### 8.1 Attempt ledger

Every attempted execution is recorded, including successful, wrong, malformed, failed, timed-out, cancelled, truncated and retried attempts. No trial is deleted.

Each attempt records: scenario/repetition/arm, order, seed, model snapshot/config, prompt/tool-schema hashes, provider request/response IDs, token categories, usage completeness, generated-code hash, MCP method/arguments/result, final answer, evaluator result, latency spans, failure class, retry history, host/container evidence and cleanup result.

### 8.2 Failure classes and handling

| Class | Handling |
|---|---|
| Wrong/missing/fabricated canonical identity | `FAIL`; retain attempt; no efficiency claim. |
| Malformed or schema-invalid final answer | `FAIL` unless a predeclared retry recovers it; all tokens counted. |
| Failed tool call (`isError`, invalid args) | Retry only under the fixed policy; if unresolved or repeatedly invalid, `FAIL`; all tokens counted. |
| Unauthorized/proposal/mutation method | Immediate `FAIL`; security/protocol incident. |
| Transport/provider error | Fixed infrastructure retry; if unresolved, pair incomplete; `INCONCLUSIVE` unless a hard gate failed. |
| Timeout | Host terminates; attempt retained; no valid final answer means correctness failure; tokens to termination included if reported; otherwise usage-incomplete. |
| Truncated output | Invalid answer; `FAIL` unless recovered by the fixed policy; tokens counted. |
| Missing/partial token usage | Primary metric non-computable; `INCONCLUSIVE`; no local estimate. |
| Cleanup/termination failure | `FAIL`. |
| Security violation | `FAIL`; stop run. |
| Provider outage/environment drift | Affected pairs incomplete; `INCONCLUSIVE`; no substitution. |

### 8.3 Retry policy

Proposed for approval, identical for both arms:

- `max_answer_retries = 0` for confirmatory scoring; one model answer attempt per arm/trial.
- `max_infrastructure_retries = 2` only for provider 5xx, transport reset or rate-limit responses, with a fixed backoff and recorded attempts.
- No retry may change the prompt, tools, scenario, model parameters or scoring.
- Every infrastructure retry's tokens are counted; if usage is missing, the execution is usage-incomplete.
- If the initial attempt plus the two allowed infrastructure retries still fails, the pair is incomplete; no silent replacement.

`max_answer_retries = 0` avoids answer-repair confounding and keeps the comparison single-shot. If reviewers prefer a nonzero answer-retry allowance, it must be fixed before pilot and applied symmetrically; it cannot be selected after seeing results.

### 8.4 No artificial efficiency

- Failed or timed-out executions cannot be dropped to lower token totals.
- Token statistics cannot be conditioned on successful runs.
- A failure that lowers token use still counts in the ledger and, if it triggers a hard gate, yields `FAIL`, not `BENEFIT`.
- Missing pairs make `BENEFIT` and `NO-BENEFIT` impossible.
- No winsorization, trimming or reweighting of failures.

## 9. Evidence and reproduction requirements

### 9.1 Per-trial evidence

- scenario/task ID and hashes;
- arm, randomized order, run block and seed;
- immutable model/provider snapshot and parameters;
- system prompt, tool schema, task prompt and wrapper hashes;
- provider request IDs, response IDs, usage categories and completeness;
- model turns, generated-code hash and final answer;
- MCP method, arguments, result identity/size and correlation ID;
- correctness/evaluator result and mismatch detail;
- latency spans and timing events;
- failure/retry/timeout/cancellation records;
- host/container image digest, limits, isolation evidence and cleanup;
- storage of raw transcript with secrets redacted and original usage counters retained.

### 9.2 Aggregate evidence

- frozen corpus, scenario list, expected answers, evaluator and generator;
- environment lockfiles and container image digest;
- model configuration and token mapping;
- randomization seed and analysis script;
- model-usage ledger;
- raw logs and host evidence;
- distributions, point estimate, bootstrap replicates and confidence bounds;
- verdict, exclusions and failure ledger;
- pilot versus confirmatory manifests;
- SHA-256 evidence manifest and additive errata policy.

### 9.3 Independent verification

A reviewer separate from implementation must:

- reconstruct exact correctness from raw evidence;
- reconstruct token totals from provider usage and verify the category mapping;
- recompute the paired family-balanced effect and clustered interval from the frozen ledger;
- verify inclusion/exclusion, cluster structure, seed, analysis code and absence of endpoint switching;
- confirm all failures and missing pairs are represented;
- reproduce the deterministic harness and an independently approved subset of model trials;
- confirm the security host evidence and no unauthorized methods;
- sign an outcome record.

Model text need not be byte-identical; do not claim full statistical reproduction from non-deterministic text. Deterministic harness and analysis reproduction plus raw-evidence reconstruction are the requirement.

### 9.4 Reproduction scope

The independent verifier may re-run a subset of model trials only after a separate model/API authorization and budget. The subset size, selection method and acceptance criteria must be predeclared. Reproduction failure yields `INCONCLUSIVE`, not an improvised replacement.

### 9.5 Privacy and retention

- Use synthetic corpus and no production/private data.
- Provider credentials never enter evidence.
- Redact secrets and sensitive headers; retain usage counters and request metadata.
- Define retention period, access control and immutability before pilot.
- Preserve original records; corrections are additive errata, never silent rewrites.

## 10. Authorization register

The table is the D1 parameter register. "Proposed" means the value or method is recommended here but not ratified. "Blocked" means the value cannot be fixed without missing evidence or explicit human authorization. No row is silently accepted.

| Parameter | Proposed value | Source of evidence | Reviewer | Approval state | Blocker |
|---|---|---|---|---|---|
| ADR-017/023/027 boundaries | Retrieval-only, canonical index, six-tool upstream, four read methods | Accepted ADRs | Architecture owner | Accepted | None |
| F1 executor/adapter reuse | Read-only, hash-pinned, unmodified | Merged F1 evidence | Architecture owner | Accepted | None |
| B0-M separation | Mechanical regression only, not B0-A corpus | B0-M merged evidence | Human owner | Accepted | None |
| Production/S1-A2 | No production, no S1-A2 | Task constraints and ADRs | Human owner | Accepted | None |
| Primary estimand | Family-balanced scenario log token ratio | This proposal | Statistics reviewer | Proposed | Independent stats review |
| Repetition aggregation | Equal-weight geometric mean, fixed `R` | This proposal | Statistics reviewer | Proposed | `R` approval |
| Family weights | Equal 1/4 for T5-T8 | This proposal | Statistics reviewer | Proposed | Stats review |
| Confidence interval | Stratified cluster bootstrap, `B=10000`, type 7, fixed seed | This proposal | Statistics reviewer | Proposed | Stats review and seed freeze |
| Token total definition | All non-overlapping provider categories, cached tokens included | Provider documentation | Statistics/model reviewer | Proposed | Provider usage mapping |
| Cache policy | Disable if symmetric; otherwise symmetric and fully reported | Provider capability | Model/statistics reviewer | Proposed | Symmetric capability evidence |
| Material threshold | 15% total-token reduction | D0 proposal | Human owner/statistics | Proposed | Human approval |
| Planning effect | TBD; strictly greater than the material threshold | Pilot/statistics | Statistics/human owner | Blocked | No approved `delta_planning` |
| Alpha / power | One-sided 0.05 / 80% | This proposal | Statistics reviewer | Proposed | Human approval |
| `N_f` / decisions / `R` | TBD | Pilot variance | Statistics reviewer | Blocked | No pilot data |
| Pilot protocol | Separate, non-confirmatory, disjoint scenarios | This proposal | Statistics/human owner | Blocked | Explicit pilot authorization |
| Scenario corpus | New synthetic corpus, not B0-M | This proposal | Corpus reviewer | Blocked | Corpus not built/frozen |
| Corpus quotas/diversity | Checklist in Section 6 | This proposal | Corpus reviewer | Proposed | Corpus review |
| Duplicate/leakage thresholds | Exact duplicates reject; 5-token Jaccard `J >= 0.80` reject; `0.60 <= J < 0.80` review; `J < 0.60` pass | This proposal | Corpus reviewer | Proposed | Threshold approval |
| Ground-truth evaluator | Independent deterministic implementation | This proposal | Corpus/statistics reviewer | Blocked | Implementation/review |
| Pilot/confirmatory hashes | Required | This proposal | Evidence reviewer | Blocked | Corpus/evaluator freeze |
| Security host architecture | Disposable container + broker + F1 in guest | Section 7 | Security reviewer | Proposed | Design review |
| Container/seccomp/cgroup config | TBD | Security build | Security reviewer | Blocked | Build and red-team evidence |
| MCP broker allowlist | Four read methods; reject proposals | ADR-027 | Security/architecture reviewer | Proposed | Implementation/test |
| Credential custody | API key only in trusted orchestrator | Section 7 | Security reviewer | Proposed | Review |
| Cleanup/termination | OS-level cgroup/container kill and verification | Section 7 | Security reviewer | Proposed | Red-team proof |
| Incident stop rules | Section 7.6 | This proposal | Security/human owner | Proposed | Approval |
| Retry policy | 0 answer retries; 2 infrastructure retries | This proposal | Protocol/statistics reviewer | Proposed | Human approval |
| Randomization/order | Paired arm-order randomization, concurrency one, fixed seed | This proposal | Statistics reviewer | Proposed | Seed/preregistration |
| Stop rules | No optional stopping; predeclared security/provider/data stops | This proposal | Statistics/security reviewer | Proposed | Approval |
| Analysis code/seed | Frozen script and seed before confirmatory run | This proposal | Statistics reviewer | Blocked | Code freeze |
| Pilot size | TBD | Pilot design | Statistics reviewer | Blocked | Approval and variance plan |
| Latency guardrail | 20% non-inferiority, one-sided 95% bound | This proposal | Statistics/human owner | Proposed | Approval |
| Model provider/snapshot | TBD | Procurement/pilot | Model owner | Blocked | Explicit human authorization |
| Endpoint/region/parameters | TBD | Provider docs | Model owner | Blocked | Authorization |
| API budget/credentials | TBD | Finance/owner | Human owner | Blocked | Authorization |
| Tokenizer for secondary estimates | TBD | Provider documentation | Statistics reviewer | Blocked | Model selection |
| Independent reviewer roles | Separate implementation, corpus, statistics, security and outcome reviewers | This proposal | Human owner | Blocked | Assignment |
| Evidence retention/storage | Immutable, redacted, access-controlled | This proposal | Security/evidence reviewer | Proposed | Approval |
| External validity | One model snapshot and one corpus; no general claim | This proposal | Human owner | Accepted limitation | None |
| Pilot execution | Not authorized | Section 11 | Human owner | Blocked | Explicit pilot authorization |
| Confirmatory execution | Not authorized | Section 11 | Human owner | Blocked | D1-C freeze and authorization |
| D1 preregistration | Separate immutable document and hash | This proposal | Human owner | Blocked | See Section 11 |

Register categories:

- **Fixed by accepted architecture or merged evidence:** ADR-017/023/027 boundaries, six-tool inventory, four read methods, F1 reuse, B0-M separation, and the prohibition on production/S1-A2 work.
- **Decidable by this design, subject to review:** estimand, aggregation, family weights, interval method, token-total mapping, outcome rules and precedence, retry policy, corpus checks, restricted-host design and evidence requirements.
- **Requires new evidence:** provider usage/caching behavior, pilot variance, `N_f`, `R`, achieved power, corpus adequacy, evaluator results, security red-team results and reproduction subset behavior.
- **Requires explicit human authorization:** model provider/snapshot, endpoint/region/parameters, API budget and credentials, materiality threshold, alpha/power, latency guardrail, restricted-host approval, reviewer roles, pilot execution and confirmatory execution.

## 11. D1 readiness recommendation

### 11.1 What this proposal resolves

- The primary estimand, repetition aggregation, family weighting and clustered interval procedure.
- The primary token-total definition, cache treatment and missing-usage verdict.
- The outcome table, one-sided bounds, material threshold, equivalence rule, latency guardrail and precedence.
- The threshold-relative prospective power formula and the requirement that pilot variance and an approved planning effect, not invention, determine `N_f` and `R`.
- The corpus separation, measurable adequacy checks, symmetric 5-token Jaccard near-duplicate rule and freeze requirements.
- The threat model, smallest restricted-host architecture, F1 reuse rule and pre-pilot security demonstrations.
- The failure taxonomy, retry policy and no-artificial-efficiency rules.
- The evidence, reproduction and authorization register.

### 11.2 What remains blocked

D1 preregistration is **BLOCKED** by:

1. **Model authority:** no approved provider snapshot, endpoint, parameters, credentials or budget.
2. **Token evidence:** provider usage/caching categories and mapping are not yet verified.
3. **Statistical evidence:** no pilot variance and no approved `delta_planning`, so `N_f`, `R` and achieved power are not known.
4. **Corpus evidence:** no B0-A corpus, scenario list, evaluator or adequacy review exists yet.
5. **Security evidence:** no restricted host is built, red-teamed or independently reviewed.
6. **Human approvals:** `delta_material`, `delta_planning`, alpha/power, retry policy, latency guardrail and reviewer roles are not ratified.
7. **Pre-registration:** no immutable D1-C document, hashes and analysis code have been frozen.

### 11.3 Recommendation

- **D1 resolution proposal:** READY for architecture, statistics, corpus and security review.
- **D1 preregistration:** **BLOCKED**. Do not freeze or authorize the pilot.
- **B0-A pilot/confirmatory execution:** NOT AUTHORIZED.
- **B0-A implementation or model/API call:** NOT AUTHORIZED.
- **S1-A2:** undefined and blocked.
- **Model-efficiency claim:** none. B0-M remains a mechanical PASS/VERIFIED result and provides no model-efficiency evidence.

The next gate is a read-only D1 review of this proposal. It must resolve the authorization register rows marked Blocked, approve the statistical and security parameters, build and independently verify the B0-A corpus/evaluator and restricted host, and then create a separate D1-C preregistration. Only after that separate authorization may a pilot be considered.

## 12. Immutable references

- S1-A1: PR #627.
- P0 original cancellation **FAIL**: PR #633 (`adf50933`).
- F1 isolated cancellation **PASS**, independently **VERIFIED**: PR #642 (`f8591102`). F1 does not prove server-thread termination or hardened isolation.
- B0-M mechanical **PASS**, 39/39 in two sequential executions in one Node process; supplemental **VERIFIED**, 98/98: PR #650 (`34d75bec`).
- B0-M fixture: `a996e2aa5c2d41bf8a75293c8d60adebf9ab89eb59caea926fbccf97297a1dca`.
- B0-M tasks: `7aaa196a72b52726ea6db7e46db612c6a6abc0f2bf7f3d5f3a13be2822e163b6`.
- B0-M original evidence manifest: `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`.
- B0-M supplemental record: `70afd4272fce2ba1e35e3ea78332b84175f41153139e384c2e51eff357614708`.
- F1 executor: `0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1`.
- F1 adapter: `3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c`.
- F1 relay: `536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5`.
- F1 runner: `55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830`.
- F1 harness: `3b2a7591614dd19532e3d7a5064e403ea4d58e73e73e305009b9d67385ba8076`.
- Frozen S1-A1 executor: `4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313`.
- D0 design proposal: PR #654, reviewed head `6220b482f7f12260b284bcca571abee52a2efbc6`, squash-merged at `8060b9bc318e0a0cb206d0cc9d3e6833977e367c`.

All cited experimental claims are prior results. No B0-A model-mediated trial has been run.

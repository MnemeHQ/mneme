# CM-01-B0-A — Model-Mediated Decision MCP / Code Mode Benchmark Design

**Status:** PROPOSAL FOR REVIEW — **not accepted, not frozen, not preregistered, and not authorized for execution**.
**Date:** 2026-10-25
**Workstream:** CM-01, parallel optional orchestration interoperability; [tracker #640](https://github.com/MnemeHQ/mneme/issues/640).
**Design baseline:** `8250aa09cfedf99b392ccabff597beca1b4d2055` (roadmap reconciliation PR #653, squash merged).
**Predecessors:** S1-A1 PR #627; original P0-01 FAIL PR #633; independently verified F1 PASS PR #642 (`f8591102`); model-free B0-M PASS PR #650 (`34d75bec`).

This document **proposes**, but does not adopt, the B0-A experimental design. It does not authorize a model/API call, new integration, production dependency, code execution, or any modification to frozen results. A separately approved and immutable preregistration must precede confirmatory scoring. The earlier B0 comparative-protocol discussion was not committed or preregistered; do not retroactively claim it was.

## 1. Research question and decision

**Question:** Relative to exposing four read-only Decision MCP tools directly to the **same model**, does allowing that model to compose the same tools through the merged F1 Code Mode execution surface reduce model-mediated orchestration effort **without loss of exact decision correctness, reliability, or acceptable latency**?

- **H0:** no material efficiency advantage.
- **H1:** Code Mode has a predeclared, material model-token advantage on data-dependent read-only tasks and clears all non-inferiority/identity gates.
- **H2:** Code Mode incurs equivalent or greater cost/latency, fails correctness or reliability, or does not justify its additional interface.
- A valid **NO-BENEFIT** result is expected to be reported without tuning the thresholds after observation.

**Decision enabled by B0-A:** whether a *separate* portable reference-integration evaluation is worth authorizing. B0-A never makes Code Mode a default, a production integration, an enforcement layer, or a second resolver.

## 2. Authority and implementation invariants

- **ADR-017:** retrieval is context; deterministic enforcement stays outside the benchmark.
- **ADR-023:** the Decision Index and Mneme projection are the only authoritative source of applicable canonical decisions. No second resolver, fabricated trace, rule or evidence.
- **ADR-027:** the genuine upstream MCP inventory remains exactly six tools: `decision.get`, `decision.search`, `decision.applicable_to`, `decision.trace`, `decision.propose`, and `decision.propose_batch`. **Both model arms expose or allow only the first four read methods**. Any attempted proposal/mutation/authority call is an immediate protocol failure.
- **ADR-022:** any eventual source or evidence record uses a separate branch, PR and squash merge.
- Existing direct MCP, CLI, hook and CI remain usable without Code Mode.
- The B0-A harness must call the *genuine* pinned Decision MCP, not a mocked retrieval engine; any additional corpus is a frozen synthetic input to Mneme, never a replacement resolver.
- Use the merged F1 executor/adapter **read-only and hash-pinned**. Never edit S1-A1, P0, F1, B0-M or ADR-034 M4 evidence or alter their verdicts.
- In-process QuickJS has **not** been certified as a hostile-code security boundary. Before any model-generated Code Mode source is executed, approve a bounded disposable process/container host, no host secrets in the guest, only four allowlisted MCP methods, bounded CPU/memory/time, and verified termination/cleanup. F1 proves client cancellation/settlement, **not** server-thread termination, hardened sandbox isolation or cross-platform timing.
- No Cloudflare Workers or production adapter inference from this study.

## 3. Interventions, unit and arms

| Aspect | D — direct MCP control | C — Code Mode treatment |
|---|---|---|
| Model | Same exact immutable provider snapshot | Same snapshot |
| User objective and required answer schema | Identical | Identical |
| Read authority | Genuine Mneme Decision MCP | Same MCP through pinned F1 adapter |
| Model-visible functions | Four direct read-only methods | One Code Mode function exposing those four methods to generated code |
| Execution | Model issues read tool calls and processes intermediate results | Model generates bounded source to chain/filter reads in Code Mode |
| Final output | Frozen machine-readable JSON schema | Same schema |
| Allowed feedback and recovery | Equivalent bounded, measured retries | Equivalent bounded, measured retries |
| Hidden sources / prefilled answers | None | None |

**Intervention:** the orchestration/tool interface. Differences in function descriptions, wrapper instructions, code-generation tokens and protocol envelopes are inherent intervention overhead and must be recorded, token-counted and disclosed — not secretly adjusted to favor either arm.

**Independent sampling unit:** a distinct, frozen **task scenario** (corpus/query/context/expected answer), not merely a repeated inference on the same T5 query. Trial repetition estimates within-scenario stochastic variation; it cannot increase the count of independent scenarios.

A **pair** is one scenario, one randomized run block, executed once per arm with separate fresh model conversations and MCP children. Randomize arm order within each block; run concurrency one and record order, clock, model request IDs and provider responses. Never transfer intermediate context, model history or computed answers between arms.

## 4. Task families and corpus validity

Retain the B0-M **family definitions**, not its eight fixed examples as sufficient confirmatory coverage:

| Family | Role in B0-A | Required feature |
|---|---|---|
| T1 single get | Negative-control / overhead | Unique stable decision ID |
| T2 single search | Negative-control / overhead | Search-result identity |
| T3 single applicability | Negative-control / overhead | Scope-based retrieval |
| T4 single trace | Negative-control / overhead | Rule and evidence lineage, including explicitly missing links |
| T5 search → get | Primary multi-step stratum | Search result determines later ID |
| T6 search → trace | Primary multi-step stratum | Lineage query depends on search |
| T7 applicability → get → trace | Primary multi-step stratum | Scope and lifecycle filtering |
| T8 filter/compose | Primary multi-step stratum | Multiple candidate decisions and compact projection |

B0-M's **24 synthetic decisions** are suitable as an inherited mechanical regression/smoke corpus, **not** evidence of B0-A dataset size, model difficulty or statistical power. Do not recycle its eight fixed expected answers as confirmatory observations.

Before confirmatory execution:
1. Construct and freeze multiple *distinct* scenarios per family from a separately reviewed synthetic corpus, with varied scopes, lifecycle status, result cardinalities, version/lineage links, misleading but nonapplicable matches, empty/partial traces and selection ambiguity resolved by explicit task rules.
2. Ensure multi-step scenarios actually require reading intermediate tool output to select subsequent calls; do not leak IDs, target digests or expected answers in the model prompt.
3. Derive ground truth using the frozen canonical fixture and an independently reviewed deterministic evaluator. Hash the input, ground truth, transformations, scenario/task prompts and evaluator **before** any confirmatory run.
4. Freeze a **pilot** subset and a distinct, disjoint **confirmatory** subset, stratified by family; the pilot can calibrate instrumentation/variance, but cannot tune prompts or scores on confirmatory instances.
5. Record corpus construction, checks for duplicate/easy marker leakage, cardinalities, difficulty, and scenario sampling. Corpus adequacy remains **unresolved pending review**; no chosen count is silently considered approved.

## 5. One primary endpoint — proposal for approval

**Proposed primary endpoint:** percent reduction in **total provider-reported model tokens per scenario** (input + output across *all* model API requests, including model-generated code, retries and any final answer), evaluated across T5–T8. Record provider-specific reasoning, prompt-cache read/write and token categories separately. Do not combine provider usage with an incompatible local tokenizer estimate. Model usage reporting must be complete and symmetrically available for both arms; otherwise the trial is **INCONCLUSIVE**.

For each paired scenario/run block, compute:

`r = tokens_CodeMode / tokens_Direct`; analyze `log(r)`.

Aggregate with **equal weight to each of T5–T8 families**, not weight proportional to whichever family has more repetitions. The effect is `1 - exp(mean weighted log(r))`. Report the direction, magnitude and a cluster-aware confidence interval resampling **scenario identities**, maintaining paired observations, family strata and run blocks. Do not resample individual model-turn rows as independent trials.

**Proposed practical material-effect floor for review (NOT ratified):** ≥15% total-token reduction. A confirmatory **BENEFIT** would require the one-sided 95% confidence bound to support an improvement of **at least** 15%, not merely a reduction greater than zero. The threshold and CI method must be independently approved *before* looking at confirmatory data. If the design cannot support a defensible interval, use **INCONCLUSIVE**, not a favorable point estimate.

This is one primary hypothesis only. Do not promote an attractive secondary result to the primary result after observing data.

**Secondary/descriptive (not alternative PASS routes):** total input/output token components, number of model API requests/turns, model-visible intermediate-result context bytes and pinned-tokenizer estimates, genuine MCP request count, end-to-end and component latency, answer format validity, correctness, error recovery, cancellation/cleanup, and separate T1–T4 negative-control overhead. Report raw distributions, outliers and failure examples, including unfavorable ones. No model/API usage projections or extrapolated savings enter the primary verdict.

## 6. Sampling, power, and stop rules

The previously discussed **8 families × 2 arms × 6 repeats** is **provisional only** and does not establish adequate independent scenario sampling.

Proposed locked path:
1. Select and pin the provider/model snapshot, model parameters, tool-use mode, tool schemas, tokenizer, environment and retry policy.
2. Approve a small, separately tagged **non-confirmatory pilot** using *distinct pilot scenarios* in both arms. All pilot measurements must be labeled `PILOT` and excluded from the confirmatory verdict.
3. From pilot variability in *paired log token ratios at scenario level*, compute the scenario-level sample-size / power plan for the preapproved 15% threshold (or a separately ratified threshold); account for hierarchical scenario/repeat clustering and the predeclared one-sided error rate. Report assumptions, feasible precision and sensitivity. Repetitions are not substitutes for independent scenarios.
4. Freeze **N unique scenarios per family, repetitions per scenario, the randomization seed, fixed maximum retries, all exclusion/timeout rules, confidence method and analysis script** in a new immutable preregistration before running any confirmatory trial.
5. Run the exact preregistered grid, with no optional stopping, per-arm prompt tuning or post-hoc threshold changes. Every attempted trial — completed, wrong, timed out, or otherwise invalid — is retained and counted.
6. A changed model snapshot, incomplete provider token reporting, irreproducible inputs, or meaningful environment drift invalidates/inconclusively labels affected pairs; never quietly substitute a model alias or drop inconvenient cases.

**Open parameters requiring approval:** model provider and immutable snapshot; permitted model API resource cap and credentials custody; corpus/scenario count; pilot size; target power; repeats; token category accounting; final 15% threshold; CI implementation; latency guardrail and test plan. No B0-A pilot or confirmatory run is authorized by this document.

## 7. Correctness, reliability and latency gates

These gate efficiency rather than being traded away for fewer tokens.

**Exact correctness:** deterministic exact match for selected canonical decision IDs, versions, version IDs, content digests, applicable scopes, derived rule IDs and declared evidence links **as requested by the task**; explicit missing fields must not be fabricated. Any wrong/fabricated canonical identity, unauthorized proposal/mutation call, or manufactured evidence is an **experimental FAIL** and cannot be omitted from the efficiency population.

**Functional completion:** valid frozen answer JSON with all required fields. Every attempted task, including failures and retries, counts in the outcome ledger. Do not condition token statistics only on successful trials.

**Reliability:** no leaked child/relay/server process, unhandled rejection, post-disposal callback, outstanding request after the specified bounded drain, or invalid cancellation notification. Require the separately preregistered fault matrix (not-found, invalid arguments, transport close, timeout/cancel and recovery) to pass; report it separately from efficiency.

**Latency:** wall-clock span including model requests, tool execution and necessary cleanup is the operational metric; record connection/setup/teardown separately and explicitly declare whether a cold-start total is a secondary. Proposed guardrail: treatment must not show a material latency regression beyond **+20%** against paired direct MCP, with an independently approved interval/precision rule. A disputed or underpowered guardrail is **INCONCLUSIVE**, not silently PASS.

If any mandatory identity, contract or cleanup gate fails, report **FAIL** even if tokens improve.

## 8. Fairness, privacy, and host controls

- Fresh stateless conversation and fresh MCP child per arm/trial. No across-arm reuse of task answers or cached transcripts.
- Same system/task objective, response schema, model snapshot, temperature/decoding settings, region, request timeout, bounded retry allowance and machine; document unavoidable arm-specific tool instructions and hash both. No model fallback.
- Randomized paired arm order; warm-up/pilot outside confirmatory scoring; concurrency one; capture timing using a monotonic clock.
- Provider caching disabled where supported, otherwise record complete cache-hit/read/write metrics and prespecify handling. Enforce a symmetric configuration; never silently compare different caching regimes.
- The host enforces a *four-method* call allowlist in both arms even though the genuine upstream registry has six methods. Abort/flag any unexpected tool access. Validate arguments using the upstream schemas; no proposal or mutation tools are available to the model.
- Model-generated source executes only in the separately reviewed restricted host described in `2. Keep provider credentials outside guest, do not give guest file/network/process globals, cap work/memory/time, and record explicit process cleanup. These controls are prerequisites to authorization, **not currently demonstrated guarantees**.
- Redact tokens/secrets in stored provider transcripts while retaining original usage counters, request metadata, secure evidence hashes and exact evaluator inputs; never commit credentials.
- Detect logging blind spots (e.g. B0-M inbound initialize not captured) and record limitations rather than asserting complete transcripts.

## 9. Evidence, independence and provenance

**Per attempted trial:** scenario and task hashes; arm and run seed; provider snapshot/config; system/tool/schema/prompt hashes; model requests, response IDs, usage categories, number of turns and generated code hash; MCP method/arguments/result identity; structured final answer and evaluator mismatch; timing spans; failures/retries/timeouts/cancellations; process and resource cleanup.

**Aggregate package:** frozen corpus, scenario assignment, ground truth, evaluator, environment lockfiles, model configuration, randomization and analysis script; model-usage ledger; raw logs; distributions/CI; verdict; identity/source/hash manifest; declared pilot versus confirmatory separation.

**Independent verification:** a reviewer separate from implementation independently reconstructs correctness, token totals and paired effects from raw evidence, checks all trial inclusion/exclusion and cluster structure, confirms no endpoint switching, and reproduces the deterministic harness and an independently approved subset of model trials. Model text need not be byte-identical; do not call that full statistical reproduction. Preserve the original record plus additive errata if any errors are found.

**Outcomes, mutually exclusive:**
- `BENEFIT`: all gates pass and the one preregistered primary-effect CI clears the approved material improvement floor.
- `NO-BENEFIT`: all gates pass and the evidence excludes a material improvement at approved precision (not merely a nonsignificant test).
- `FAIL`: correctness, tool authority, security execution boundary, cleanup/cancellation, or prespecified latency failure; preserve all raw runs.
- `INCONCLUSIVE`: uncertain interval, underpowered sample, irreproducible run, unverified/partial model usage, snapshot drift, or unresolved evidence.
- Mechanical B0-M PASS remains a separate result and cannot be promoted into a B0-A benefit.

**Closure:** independent verification + human approval of the exact frozen protocol and outcome record in a dedicated PR. Closure never authorizes S1-A2, production integration, Workers or changed MCP authority.

## 10. Authorization gates and immediate next step

| Gate | Deliverable | Allowed now? |
|---|---|---|
| D0 — draft design | Review this document against accepted ADRs and B0-M | **Yes — documentation only** |
| D1 — freeze readiness | Resolve open model/corpus/statistics/security parameters; approve a separate preregistration and hashes | **Not yet** |
| P — model-mediated pilot | Model API instrumentation, restricted host and non-confirmatory pilot | **Not authorized** |
| C — confirmatory | Independently review pilot/power, then freeze and execute the sampled trial grid | **Not authorized** |
| V — independent outcome review | Recompute results and record BENEFIT/NO-BENEFIT/FAIL/INCONCLUSIVE | **Not authorized** |
| I — portable integration evaluation | Separate architecture/integration decision **only after** defensible measured benefit | **Not authorized** |

**Recommended next task after this documentation PR:** a read-only D1 design review resolving the proposed primary metric, 15% materiality floor, scenario adequacy, sample-size method, security isolation plan and single model selection. Do not start instrumentation or call the model until that independent gate is explicitly authorized.

## 11. Frozen historical references

- S1-A1 compatibility: PR #627.
- P0 original cancellation **FAIL**: PR #633 (`adf50933`).
- F1 isolated cancellation **PASS**, independently **VERIFIED**: PR #642 (`f8591102`). F1 client settlement does not prove server-thread termination.
- B0-M mechanical **PASS**, 39/39 in two sequential executions in one Node process; independent supplemental **VERIFIED**, 98/98: PR #650 (`34d75bec`).
- B0-M 24-decision fixture: SHA-256 `a996e2aa5c2d41bf8a75293c8d60adebf9ab89eb59caea926fbccf97297a1dca`.
- B0-M task definitions: SHA-256 `7aaa196a72b52726ea6db7e46db612c6a6abc0f2bf7f3d5f3a13be2822e163b6`.
- B0-M original evidence manifest: `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`.
- B0-M supplemental record: `70afd4272fce2ba1e35e3ea78332b84175f41153139e384c2e51eff357614708`.

All cited experimental claims are *prior* results; **no B0-A model-mediated trial has yet been run**.

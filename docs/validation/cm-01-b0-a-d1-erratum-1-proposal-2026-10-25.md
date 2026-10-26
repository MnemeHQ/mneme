# CM-01-B0-A - D1 Erratum 1 Proposal

**Status:** PROPOSED ERRATUM FOR REVIEW - **not accepted, not frozen, not preregistered, and not authorized for execution**.

**Date:** 2026-10-25  
**Workstream:** CM-01, parallel optional orchestration interoperability; [tracker #640](https://github.com/MnemeHQ/mneme/issues/640).  
**Amends (additively):** D1 protocol resolution proposal, PR #655, squash-merged at `4b8471149d49f6f4a2a4ddfd0d3601d59355c337` (`docs/validation/cm-01-b0-a-d1-protocol-resolution-proposal-2026-10-25.md`).  
**Related open proposals:** #660 (D1-P token accounting), #661 (D1-S statistics), #662 (corpus/evaluator), #663 (D1-H restricted host).  
**Governing architecture:** ADR-017, ADR-022, ADR-023, ADR-027.

This erratum is additive. It does not edit the merged D1 document, which stays as recorded (D1 Section 9.5: corrections are additive errata, never silent rewrites). Where this erratum and D1 conflict, the erratum is a **proposal** to replace the cited D1 text in the eventual D1-C preregistration. It takes effect only if it is reviewed and accepted. It does not authorize a model/API call, corpus build, evaluator implementation, host build, pilot, confirmatory run, B0-A execution or S1-A2 work. No experimental result, verdict or historical evidence (S1-A1, P0, F1, B0-M, ADR-034 M4) is changed.

Errata E-1 to E-4 come from the 2026-10-25 independent review of #660-#663 posted on [#640](https://github.com/MnemeHQ/mneme/issues/640). Every transport claim below was checked against `mneme/decision_mcp.py` and `mneme/decision_index_service.py` at `main` `4b847114`.

## E-1. Primary task families must have a transport-verified information dependency

**Amends:** D1 Section 6.3 (family table, rows T5-T8), Section 6.4 check 4, Section 2.1 (scenario definition); D0 Section 4 family table.

### E-1.1 Finding

D1 describes T5-T8 by *call sequence* ("search result determines later ID", "repeated get"). Against the genuine Decision MCP, none of T5-T8, as currently scored, actually needs a second dependent call:

- `decision.search` returns `canonical_decisions` as full `canonical_record_to_transport` records: `decision_id`, `version`, `version_id`, `content_digest`, `lifecycle_status`, `context_scope`, `test_evidence`, `relationships`, `derived_rule_ids` and the remaining record fields.
- `decision.get` returns the same `canonical_record_to_transport` record. For canonical decisions it never adds information beyond search.
- An empty `query` matches every record (`DecisionIndexService.search`: "An empty query matches everything"). One `decision.search` call with an optional `canonical_lifecycle_status` filter therefore returns every canonical record field for the whole fixture.
- `decision.trace` (canonical) returns `canonical_record` (the same full record), `declared_test_evidence` (equal to the record's `test_evidence`), `missing_links` (derived only from whether `derived_rules` and `test_evidence` are empty, plus a constant `enforcement_links` entry), and `derived_rules`.
- The only canonical data available from no tool except `decision.trace` is **`rule_payload` and `applicability`** inside the `derived_rules` objects (`rule_to_transport`). Search does not index rule payloads or rule applicability, and `decision.applicable_to` matches `context_scope` only, never rule applicability.
- The other rule fields can be derived from the search record:
  - `rule_type` is encoded in the `rule_id` string (`<decision_id>:<RULE_TYPE>:<hash>`, `decision_index_persistence.rule_id_of`);
  - `sequence` equals the position in the record's ordered `derived_rule_ids` (the trace integrity check requires the two orders to match);
  - rule `lifecycle_status` is inherited from the owning decision (`CanonicalRuleRecord`, `mneme/decision_index.py`);
  - `decision_version_id` always equals the record's `version_id`, because canonical rules are loaded only from the active version (`rules_by_version[active_version_id]`) and carried-forward bindings are re-stamped with the new version's ID.

### E-1.1a Validation evidence (read-only probe)

On 2026-10-25 the frozen B0-M fixture (`a996e2aa...`, 24 decisions, 20 rules) was loaded through the genuine `DecisionIndexService` and serialized with the genuine `decision_mcp` transport functions. No MCP process ran, no model was called, and nothing was written. Results:

| Check | Result |
|---|---|
| `search("")` canonical results equal the index record count | 24/24 |
| `get` record identical to the search record | 24/24 |
| Trace `canonical_record` identical to the search record | 24/24 |
| Trace `declared_test_evidence` equal to the record's `test_evidence` | 24/24 |
| Trace `missing_links` reproducible from record fields alone | 24/24 |
| Rule `rule_type` present in `rule_id`; `sequence` equal to position | 20/20; 20/20 |
| Rule `lifecycle_status` and `decision_version_id` / `decision_version` equal to the record's | 20/20 each |
| Rule `rule_payload.value` found in any search-returned text field | 0/20 |
| Rule `applicability` non-empty | 0/20 (B0-M rules are all globally applicable) |

The B0-M fixture is used only to confirm transport behavior. It is not B0-A data (D1 Section 6.1). The last row is why the B0-A corpus must populate `applicability` (E-1.2 item 1).

The B0-M-derived expected-answer schemas (T5 get projection, T6 trace projection with `derived_rule_ids` and `declared_test_evidence`, T7 `get`/`trace`, T8 identity `items`) contain only record fields. So every primary scenario is answerable from a single `decision.search` result. That defeats D1 Section 6.4 check 4, and the primary endpoint would not measure multi-step orchestration.

**Correction to the earlier review:** the #662 review comment suggested `applicable_to -> get` and `search -> trace` (via `declared_test_evidence` / `missing_links`) as remedies. Both still allow a one-call solution through `search("")`, because `declared_test_evidence` and canonical `missing_links` can be derived from the search record. The first draft of this erratum also overstated the trace-only fields: rule `lifecycle_status` and `decision_version_id` can be derived as well. Only `rule_payload` and `applicability` are trace-only (E-1.1a). This erratum replaces both earlier suggestions.

### E-1.2 Proposed rule: information dependency, not call sequence

For every primary scenario (T5-T8):

1. **Trace-only field requirement.** For each decision the task selects or tests, the expected answer, or the selection that produces it, must depend on `rule_payload` or `applicability`. No other rule field satisfies this requirement (E-1.1). Corpus generator constraints:
   - (a) every primary-family decision has at least one derived rule;
   - (b) rule `applicability` is populated with non-empty `include_paths` (and `exclude_paths` where the family needs them) at the quotas approved at corpus review; global (empty) applicability stays in the corpus as a declared bin;
   - (c) rule payload values and applicability path strings never appear in any record field that `decision.search` returns (`statement`, `rationale`, `constraints`, `anti_patterns`, `targets`, `context_scope`, source-evidence locators) or in any model-visible prompt;
   - (d) applicability path strings are synthetic and unique to the corpus.
2. **Selection dependency.** The identity of every selected decision must be determined by an earlier tool result under the frozen task rule, and must not be present in, or derivable from, the model-visible prompt (#662 Section 7.3, after the normalization in E-1.4).
3. **Mechanical non-solvability check.** A deterministic validator computes the union of all results obtainable *without* `decision.trace` (including `decision.search` with an empty query under every lifecycle filter, and `decision.applicable_to` over every declared scope) and proves the expected answer cannot be produced from that union. A scenario that fails this check is rejected at corpus review.
4. **Sequences are reference, not enforced.** The "reference sequence" is descriptive. Both arms may use any sequence of the four allowed read methods, including a full `search("")` dump. Strategy, call count and result bytes are recorded as secondary measurements. A dump strategy is not a protocol violation, and is part of what the interface comparison measures.

### E-1.3 Proposed family table (replaces D1 Section 6.3 rows T5-T8)

Under the information-dependency rule, every primary task reduces to "obtain candidates (or a full dump), trace some decisions, project". Families that differ only in selection tool or projection breadth are therefore the same workload. In particular, the selection-based T5/T6/T7 of the first draft of this erratum were all one select plus one trace. The families are instead defined along the three properties that drive orchestration cost:

- **fan-out `k`:** the number of `decision.trace` calls the information requires;
- **filtering ratio:** traced decisions per decision in the final answer;
- **dependency depth:** the number of sequential steps where a later argument or selection depends on an earlier result.

| Family | Workload | Reference sequence | `k` | Filtering ratio | Depth | Required answer content |
|---|---|---|---|---|---|---|
| T5 single-target lookup | One decision selected by record fields (marker or scope + lifecycle, explicit tie rule) | `search` or `applicable_to` -> `trace` | 1 | 1 | 2 | Identity (`decision_id`, `version_id`, `content_digest`), `derived_rule_ids`, each rule's `rule_payload` and `applicability`, `missing_links` |
| T6 trace-predicate filter | Candidate set of `m >= 3` decisions selected by record fields; answer is the subset whose rule `applicability.include_paths` contains a given exact path string (may be empty) | select -> `trace` x `m` | `m` | `m` / answer size (high) | 2 | Sorted `decision_id` list of the matching subset plus `count` |
| T7 chained dependency | Trace decision A; a path from A's rule `applicability.include_paths` (selected by an explicit task rule) is the `paths` argument to `applicable_to`, which selects decision B; trace B | `trace(A)` -> `applicable_to(paths=[p])` -> `trace(B)` | 2 | 1 | 3 | `selected_id` (B), B's identity, each B rule's `rule_payload` and `applicability`, `missing_links` |
| T8 fan-out compose | `k >= 2` decisions selected by record fields and a task rule; every selected decision is reported | select -> `trace` x `k` | `k` | 1 (low) | 2 | Items ordered by `decision_id`, each with identity and every rule's `rule_payload` and `applicability` |

Constraints for these families:

- `m` (T6) and `k` (T8) are fixed per scenario, drawn from bins approved at corpus review, and recorded in the manifest. They are covariates, not free parameters.
- T6 matching is exact string membership in `include_paths`. It never uses glob, prefix or ADR-020 selector semantics, so the evaluator does not re-implement ADR-020 applicability, which would be a second resolver under ADR-023.
- In T7, `applicable_to(paths=[p])` must yield exactly one B after the lifecycle filter and the explicit tie rule; the corpus validator proves this. The decision A is identified in the prompt (T7 starts from a known ID, like T4). The dependency check proves that `p` comes only from A's trace and that B is not derivable from the prompt. The `applicable_to` step uses the genuine MCP matching (case-insensitive substring of a scope hint in a supplied path). Expected answers for T7 therefore require double-entry ground truth: replay against the genuine pinned MCP agreeing with the independent evaluator. Any disagreement blocks freeze.
- A dump strategy cannot bypass T6, T7 or T8, because the predicate, chain argument or reported values depend on trace-only fields.
- T5 is kept as the minimal multi-step baseline. The statistics reviewer must confirm, before the pilot, that equal weighting across these four workload types is the intended estimand (D1 Section 2.2), or re-specify the weights.

T1-T4 negative controls are unchanged. They include no trace-only requirement, except that the T4 lineage projection adds `missing_links` (below).

Every lineage projection (T4, T6, T7 trace) must include `missing_links` in fixture order. Omitting or fabricating a missing link is an identity failure. This closes the gap where D1 Section 6.2 requires missing-link cases but the B0-M-derived schemas do not score them.

### E-1.4 Leakage normalization (amends D1 Section 6.4 check 3)

Prompt-leakage and selection-dependency checks run after Unicode NFKC normalization, casefolding and removal of the separators `- _ . : /` and whitespace, matching the case-insensitive substring semantics of `decision.search`. Decision IDs must not be derivable from markers or scope strings. B0-M's marker convention (`marker_adr-b0-005` encodes `ADR-B0-005`) is prohibited for B0-A.

## E-2. Hard-gate attributability

**Amends:** D1 Section 4.1 (zero-tolerance paragraph), Section 4.4 (`FAIL` row), Section 8.2 (first two rows).

### E-2.1 Finding

D1 Section 4.1 makes any single G-IDENTITY or G-FORMAT failure in **any** planned confirmatory execution a study `FAIL`, including direct-arm (control) executions and T1-T4 controls. D0 Section 9 defines `FAIL` as a property of the treatment. Model output is stochastic, so the probability that no execution fails is `(1 - p)^E`. For example, `E = 480` T5-T8 executions at `p = 0.01` gives about `0.008`. A control-arm error would then produce `FAIL` and say nothing about Code Mode.

### E-2.2 Proposed gate classes

| Class | Gates | Arms | Rule |
|---|---|---|---|
| Harness integrity | G-AUTH (executed or brokered non-allowlisted method), G-SECURITY, G-CLEANUP, protocol violation, evidence loss | Both | Any single occurrence -> study `FAIL` (unchanged zero tolerance). These invalidate the harness, whichever arm triggers them. |
| Treatment-attributable fabrication | A Code Mode final answer containing a canonical identity value (ID, version ID, digest, rule ID, evidence selector/hash) that appears in **no** genuine MCP result of that execution | Code Mode | Any single occurrence -> study `FAIL` (zero tolerance kept for the treatment). |
| Answer correctness | G-IDENTITY (non-fabricated wrong or missing values) and G-FORMAT | Both | Paired non-inferiority, defined below. No single-execution `FAIL`. |

**Correctness non-inferiority (proposed; margin TBD):** for each scenario, `c_s(arm)` is the fraction of the `R` executions with a fully correct answer. Using the same family-balanced stratified cluster bootstrap as D1 Section 2.5 on `c_s(C) - c_s(D)`:

- `FAIL` if the one-sided 95% upper bound is below `-margin_correct` (Code Mode materially less correct);
- `INCONCLUSIVE` if the interval includes `-margin_correct`;
- pass otherwise.

Fabrication in the direct arm is reported as a descriptive reliability measure. It is not a study `FAIL`, because it is not caused by the treatment.

**Reliability floor (proposed; value TBD):** if either arm's overall correct-answer rate is below a predeclared floor, the comparison cannot be interpreted and the study is `INCONCLUSIVE`.

D1 Section 8.4 is unchanged: token totals include every execution, correct or not. No success-conditioned token statistic is allowed.

### E-2.3 Pilot requirement (adds to D1 Section 5.2)

The pilot must estimate, per arm, the identity, format, fabrication and usage-incompleteness rates. The power report must include the projected probability of a decisive outcome (`BENEFIT` or `NO-BENEFIT`), counting the D1 Section 2.4 missing-pair rule and these gates. D1-C must state the minimum acceptable probability before confirmatory authorization. `margin_correct` and the reliability floor are human-approval items fixed before the pilot.

## E-3. Direct-arm broker symmetry

**Amends:** D1 Section 7.2 and Section 7.3 ("The direct arm does not execute model-generated code and does not use the guest"); aligns with D0 Section 8 ("The host enforces a four-method call allowlist in both arms").

### E-3.1 Finding

D1 and #663 put Code Mode calls through a trusted broker with an allowlist, schema validation, call quotas, argument and result-size limits and timeouts. Neither specifies the direct-arm path. If only Code Mode goes through the broker, limits and timeouts can change results or add latency in one arm only. That biases correctness, tokens and latency.

### E-3.2 Proposed rule

- Direct-arm tool calls issued by the trusted orchestrator go through **the same broker implementation and configuration** as Code Mode calls: identical four-method allowlist, upstream-schema validation, quotas, size limits, timeouts and audit records. The direct arm still uses no guest.
- The broker result-size limit must be at least the largest genuine result obtainable from the frozen corpus. That includes `decision.search` with an empty query (the full-dump result size from E-1.2) and `decision.applicable_to` over all scopes. The limit is verified at corpus freeze and recorded in the freeze manifest.
- A broker limit breach is a harness-integrity event (E-2.2), never a silent truncation, in either arm.
- Latency spans in both arms include the broker hop. Broker overhead is recorded separately as a descriptive measurement.

## E-4. Cache invariance of the primary token total

**Amends:** D1 Section 3.2 (third bullet: "If cache behavior cannot be made symmetric ... the primary verdict is `INCONCLUSIVE`") and the corresponding rows of D1 Section 4.4 and Section 10.

### E-4.1 Finding

Under the documentary provider mappings in #660, checked against the official references on 2026-10-25:

- Anthropic Messages: "Total input tokens in a request is the summation of `input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens`."
- OpenAI Responses: `input_tokens` includes `input_tokens_details.cached_tokens` and `cache_write_tokens` as breakdowns.

In both cases the normalized input total counts every prompt token exactly once, whether it was served from cache, written to cache or processed uncached. Cache state moves tokens between categories but leaves the primary total unchanged. Asymmetric or uncontrollable cache hits change billed cost and latency. They do not change the primary token-volume endpoint, as long as every required category is reported.

### E-4.2 Proposed rule

- **Primary token endpoint:** cache-hit variation, including provider-automatic caching that cannot be disabled, does **not** make the primary metric non-computable. The primary metric is non-computable (`INCONCLUSIVE`) only under the existing D1 Section 3.4 conditions: a missing or null required category, an irreconcilable total, or an overlapping mapping.
- **Configuration symmetry is still required:** identical cache settings (enable/disable, breakpoints, TTL) in both arms, frozen per snapshot.
- **Invariance check:** the frozen mapping includes a reconciliation in which repeated identical prompt prefixes yield equal normalized input totals across cache states. A failed reconciliation makes the mapping unverified and blocks the pilot.
- **Latency guardrail:** per-arm cache-hit/read/write volumes are reported. Cache-hit asymmetry is a declared latency covariate, handled descriptively under D1 Section 4.3. It is not a new verdict route.
- If a selected provider's mapping is ever *not* invariant (for example, cached tokens are excluded from the reported totals), this relaxation does not apply, and D1 Section 3.2 governs as originally written for that snapshot.

## E-5. Register changes (proposed rows for the D1 Section 10 register)

| Parameter | Proposed value | Approval state | Blocker |
|---|---|---|---|
| Primary family definitions | E-1 information-dependency rule; families by fan-out, filtering ratio and dependency depth | Proposed | Corpus and statistics review |
| Trace-only fields | `rule_payload` and `applicability` only (E-1.1, E-1.1a) | Proposed | Corpus/evaluator review |
| Rule applicability population | Non-empty `include_paths` at approved quotas; global bin retained; no leakage into searchable text | Proposed | Corpus review |
| `m` / `k` bins (T6/T8) | TBD | Blocked | Corpus review and pilot |
| Equal weighting across workload types | 1/4 each, unless re-specified before pilot | Proposed | Statistics reviewer |
| T7 double-entry ground truth | Genuine-MCP replay must agree with the independent evaluator | Proposed | Corpus/evaluator review |
| Lineage `missing_links` scoring | Required in every trace projection | Proposed | Corpus/evaluator review |
| Gate classes | E-2.2 three-class model | Proposed | Human owner + statistics review |
| `margin_correct` | TBD | Blocked | Human approval before pilot |
| Per-arm reliability floor | TBD | Blocked | Human approval before pilot |
| Decisive-outcome probability minimum | TBD | Blocked | Pilot estimates + human approval |
| Direct-arm broker path | Same broker and configuration as Code Mode | Proposed | Security/architecture review |
| Broker result-size limit | At least the frozen corpus maximum, including the full-dump result | Proposed | Corpus freeze measurement |
| Cache treatment for primary metric | Invariant volume; symmetric configuration; reconciliation check | Proposed | Provider calibration (#660) |

## E-6. Status

- **Erratum 1:** PROPOSED for architecture, statistics, corpus and security review.
- **Effect on #662:** the corpus/evaluator specification should adopt E-1 before its T-family contracts are accepted.
- **Effect on #663:** the restricted-host review should adopt E-3.
- **Effect on #660:** the provider record should carry the E-4 reconciliation.
- **D1-C preregistration:** **BLOCKED**, as in D1 Section 11.2, plus the new blocked rows in E-5.
- **B0-A pilot, confirmatory execution, implementation or model/API call:** NOT AUTHORIZED.
- **S1-A2:** undefined and blocked.
- **Model-efficiency claim:** none. B0-M remains a mechanical PASS/VERIFIED only.

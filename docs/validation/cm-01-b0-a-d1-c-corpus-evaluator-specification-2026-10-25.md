# CM-01-B0-A D1-Corpus - Synthetic Scenario Corpus and Independent Evaluator Specification

**Status:** PROPOSAL FOR REVIEW - **not built, not frozen, not accepted, and not authorized for execution**.

**Date:** 2026-10-25  
**Issue:** #658; parent #640.  
**D0 design:** PR #654, squash-merged at `8060b9bc318e0a0cb206d0cc9d3e6833977e367c`.  
**D1 resolution:** PR #655, squash-merged at `4b8471149d49f6f4a2a4ddfd0d3601d59355c337`.  
**Governing architecture:** ADR-017, ADR-022, ADR-023 and ADR-027.

This document specifies the B0-A synthetic scenario corpus and the independent deterministic answer evaluator. **D1-Corpus is the corpus workstream; it is not the separate D1-C frozen preregistration.** It does not build them, freeze them or select final counts. No model/API call, benchmark run, production change, new MCP method, B0-A pilot, confirmatory execution or S1-A2 work is authorized.

B0-M remains a mechanical regression corpus only. Its 24 decisions, eight fixed examples, expected answers and hashes are not B0-A confirmatory data.

## 1. Required separation of ownership

The corpus generator and the answer evaluator must be separate implementations with separate review ownership.

| Artifact | Owner | Must not do |
|---|---|---|
| Corpus generator | Corpus author | Compute the evaluator's answer logic or consume model outputs |
| Scenario manifest builder | Corpus author | Share private expected-answer helpers with the evaluator |
| Ground-truth evaluator | Independent evaluator author | Import generator-private answer logic or accept model text loosely |
| Corpus reviewer | Independent reviewer | Approve its own generated corpus |
| Statistics reviewer | Independent reviewer | Approve a corpus without the D1 power/N constraints |
| Security reviewer | Independent reviewer | Treat the corpus as trusted code |

The evaluator may read the frozen canonical fixture and the scenario manifest. It must not import the generator module or reuse a generator helper that produces expected answers. Both implementations may use the accepted canonical identity algorithms from `mneme` to construct or verify fixture identities; the evaluator's projection and comparison logic must be independently written and tested.

## 2. Corpus model

### 2.1 Fixture requirements

The B0-A corpus is a new synthetic Decision Index fixture. It must contain:

- `decision_index` with schema `mneme.decision-index/v2`;
- canonical decisions with stable `decision_id`;
- one or more versions per decision where the scenario requires version identity;
- lifecycle states `active`, `superseded`, `deprecated` and `inactive`;
- context scopes with overlapping and non-overlapping coverage;
- typed `FORBID_LITERAL` rules with explicit decision/version lineage;
- declared test evidence selectors and hashes, including empty cases;
- deliberate missing lineage links for `decision.trace`;
- decision relationships where useful for lineage scenarios;
- a compatibility snapshot only as required by the existing Mneme fixture format;
- no production, customer, credential or private-repository data.

The fixture must be accepted unchanged by the genuine pinned Decision MCP. It must not be generated or rewritten by the MCP during a run.

### 2.2 Deterministic generator inputs

The generator must be deterministic and versioned. Proposed inputs:

```text
generator_version
seed
decision_count                 (TBD; must support N_f plus pilot)
versions_per_decision_policy   (TBD)
lifecycle_distribution         (TBD)
scope_graph                    (TBD)
rule_density                   (TBD)
evidence_density               (TBD)
missing_lineage_density        (TBD)
relationship_density           (TBD)
ambiguity_bin_distribution     (TBD)
```

No numeric value in this list is approved. Populate rule `applicability.include_paths` at approved quotas, retain a global/empty-applicability bin, keep path strings/payloads out of the searchable record, and include zero/partial/all-match T6 bins plus T8 k-size bins. Counts follow the approved D1 power plan and corpus review, not a convenience target. The generator must emit a manifest of its inputs, seed, version and output hashes.

### 2.3 Canonical identity fields

Every scenario's expected answer uses only identity fields defined by the accepted Decision Index model:

- `decision_id`;
- `version` and `version_id`;
- `content_digest`;
- `lifecycle_status`;
- `context_scope`;
- `derived_rule_ids`;
- declared test-evidence selectors and hashes;
- task-requested projection fields.

The evaluator must not invent identity values, infer a missing digest or accept a plausible-looking substitute.

## 3. T1-T8 scenario contracts — aligned with D1 Erratum 1 E-1

The [merged, still-proposed D1 Erratum 1](./cm-01-b0-a-d1-erratum-1-proposal-2026-10-25.md) (#664) supersedes the old B0-M-derived T5–T8 contracts **for this proposal**. Task sequences below are *descriptive*, never enforced: both arms may issue any of the four permitted read calls, including `decision.search(query="")`. Every primary scenario requires information that genuinely appears only inside canonical `decision.trace` `derived_rules[].rule_payload` or `derived_rules[].applicability`, proven by the mechanical non-solvability check in `3.2.

| Family | Model-visible initial input | Reference operation strategy (not mandated) | Required answer and test dimension |
|---|---|---|---|
| T1 | Stable decision ID | `get` | Original identity projection (negative control) |
| T2 | Unique marker and lifecycle filter | `search` | Canonical IDs and count (negative control) |
| T3 | Scope context | `applicable_to` | Canonical IDs and count (negative control) |
| T4 | Stable decision ID | `trace` | Lineage projection **including `missing_links`** (negative control) |
| T5 single target | Marker/scope and lifecycle, no derived target ID | candidate retrieval → `trace` once | Selected identity plus full rule payload/applicability and `missing_links`; one required trace |
| T6 trace-predicate filter | Record-defined candidate set of `m >= 3` and explicitly disclosed predicate path `p_T6` | retrieve candidates → `trace` each; exact membership test | IDs of all candidates with a rule whose `applicability.include_paths` contains `p_T6` (exact string membership), sorted, plus count. Zero/partial/all-match bins |
| T7 chained dependency | Declared starting decision A ID; target B hidden | `trace(A)` → `applicable_to(paths=[p from A])` → `trace(B)` | Selected B plus its identity, rule payloads/applicability and `missing_links`; genuine context-scope matching, depth three |
| T8 fan-out compose | Candidate retrieval criteria without selected answer IDs | retrieve candidates → `trace` `k >= 2` selected decisions | Sorted items with identity, all rules' payloads and applicability; fan-out |

T5 has one required trace, T6 has `m >= 3` required traces with filtered fraction `phi=(m-c)/m`, T7 has two traces with the second target depending on A's previously retrieved applicability and the genuine `applicable_to` result, and T8 has `k >= 2` required traces with no output filtering. The T6 `c` bins (zero, partial, all matches), `m` and T8 `k` sizes and family quotas are **unapproved**, fixed before pilot. `p_T6` is the sole permitted *prompt-disclosed applicability path*: the prompt must not disclose candidate membership or any expected answer ID. The T7 seed A is the sole permitted prompt-disclosed starting decision ID among primary tasks; its derived path and answer target B are not disclosed.

T6 tests exact membership in the raw `include_paths` list; **no ADR-020 glob or selector resolution is performed by the evaluator**. T7 uses genuine MCP `applicable_to` behavior for its path-dependent context-scope selection, and its expected answer requires double-entry ground truth (`6.2). T1–T4 are negative controls outside the primary benefit estimand; they still contribute to the approved correctness and integrity gates. Equal family weights of 1/4 are **proposed pending statistics/human approval** under Erratum E-1 and E-2.

### 3.1 Proposed exact output schemas

The private answer evaluator must accept only the family-specific closed schema frozen before execution. The following proposal **replaces** the old B0-M-derived identity-only outputs and must be ratified before any corpus or D1-C freeze:

```text
T1 get:
  { decision_id, version, version_id, content_digest,
    lifecycle_status, context_scope, derived_rule_ids }
T2 / T3:
  { canonical_ids: [string, ... sorted ascending], count: integer }
T4 full lineage:
  { canonical_decision_id, version, version_id, content_digest,
    derived_rule_ids, declared_test_evidence: [ { selector, sha }, ... ],
    missing_links: [string, ... fixture order] }
T5:
  { decision_id, version_id, content_digest, derived_rule_ids,
    derived_rules: [ { rule_id, rule_payload, applicability }, ... ordered ],
    missing_links: [string, ... fixture order] }
T6:
  { canonical_ids: [string, ... sorted ascending], count: integer }
T7:
  { selected_id, decision_id, version_id, content_digest,
    derived_rules: [ { rule_id, rule_payload, applicability }, ... ordered ],
    missing_links: [string, ... fixture order] }
T8:
  { items: [ { decision_id, version_id, content_digest,
    derived_rules: [ { rule_id, rule_payload, applicability }, ... ordered ] },
    ... sorted by decision_id] }
```

All rule payload/applicability objects are compared recursively and exactly to the genuine frozen trace output. Arrays retain frozen order unless explicitly declared sorted; `canonical_ids` and T8 `items` sort ascending by raw Unicode code point of `decision_id` (no locale collation). Each schema is closed: wrong type, omitted/fabricated field, extra field, wrong value, or wrong required order fails evaluation. Missing, extra or fabricated `missing_links` are scored. Fixture-derived example identities and answers must not appear in any model-visible schema illustration.

### 3.2 T5–T8 information-dependency and leakage proof

For each proposed primary scenario the deterministic verifier must:

1. Retrieve the actual serialized non-trace observation set from the **pinned genuine MCP**: `decision.search(query="")` under every permitted lifecycle filter, `get` of visible IDs, `applicable_to` over all declared scopes and every explicitly disclosed prompt parameter (including `p_T6` and the seed A ID). The union must lack the trace-only data required to compute the expected answer or selected subset.
2. Prove that the model-visible prompt, schemas and rendered request (after NFKC, Unicode casefolding and deletion of `- _ . : /` and whitespace for identity-leak checks) do not disclose derived target IDs, candidate-to-path membership, any relevant rule payload or applicability, or T7's chained path. Only `p_T6` and T7 seed A may be supplied where explicitly declared.
3. Prove T5's answer requires one trace, T6's exact predicate requires traces for all `m` candidates (including zero-match), T7's path must be produced by `trace(A)` and yield exactly one B through genuine applicability, and T8 requires each of its `k` selected traces. Show that counterfactually removing the requisite trace output prevents full scoring or changes the correct answer.
4. Reject scenarios where rule payloads or undisclosed applicability values leak into model-visible prompts, task examples or tool metadata, or where any applicability value (including the disclosed T6 predicate `p_T6`) is repeated in searchable canonical record text/source locators such that a non-trace result suffices. T6 may disclose `p_T6` **only** as the declared query parameter, never disclose candidate membership, and must verify that `search(p_T6)` and `applicable_to(paths=[p_T6])` cannot identify membership.
5. Confirm unique deterministic ground truth with a genuine pinned-MCP replay and independently checked answer projection (`6.2). Do **not** independently implement a runtime decision resolver or invent authority.
6. Retain failure logs, per-tool field-availability evidence and a verifiable dependency graph. No reference call sequence may be required of either arm; a `search("")` dump is allowed and measured.

Failure of any requirement rejects the scenario before corpus freeze. This is a specification only; no validator or red-team/model call is claimed to exist.

## 4. Scenario schema and manifest

Each scenario is a frozen JSON object. Proposed minimum fields:

```json
{
  "scenario_id": "b0a-t5-0001",
  "family": "T5",
  "corpus_sha256": "...",
  "task_sha256": "...",
  "prompt": "...",
  "params": {},
  "expected": {},
  "required_fields": [],
  "dependency_graph": [],
  "search_cardinality": 1,
  "applicable_cardinality": 0,
  "lifecycle_bin": "active",
  "scope_bins": [],
  "rule_presence": true,
  "evidence_presence": false,
  "missing_lineage": false,
  "ambiguity_bin": "unique",
  "leakage_checks": {},
  "duplicate_checks": {},
  "pilot_or_confirmatory": "confirmatory"
}
```

The manifest is an ordered list of scenarios plus a SHA-256 manifest of all scenario objects, prompts, expected answers, corpus, generator version and evaluator version. Scenario order is frozen before execution and never selected by model output.

### 4.1 Model-visible projection — required data-flow boundary

The scenario manifest above is a **private orchestration/evaluator artifact**, not a model prompt. In particular, `expected`, `dependency_graph`, `leakage_checks`, `duplicate_checks`, oracle-derived identities, fixture paths and reviewer records are **never** supplied to either model arm. The host MUST build a separately serialized, allowlisted `model_task_payload` consisting only of:

- user-facing task objective/prompt and explicitly permitted input parameters;
- the same frozen required-final-answer JSON schema and task-operation constraints for both arms;
- arm-specific tool interface descriptions (four direct read tools or one Code Mode interface) whose differences are included in the measured intervention.

The `model_task_payload` MUST be generated from a dedicated projection schema, **not** by serializing the full scenario and deleting known secret fields. The prompt, system/developer instructions, tool definitions, model-facing wrapper and submitted request body must be inspected as a whole, after all interpolation, before dispatch. The expected-answer record and evaluator/oracle only enter the trusted scorer **after** the model response. Genuine MCP tool results may legitimately disclose identities retrieved at runtime; the prohibition is on advance disclosure through scenario metadata or prompts. Explicit IDs for T1/T4 and T7 seed A remain allowed; T6's exact predicate path p_T6 may also be disclosed. All derived/answer target IDs and T7's chained path remain withheld until genuine MCP results.

**Mandatory preflight (synthetic, no model/API call):** place a unique secret canary only in the private `expected`/oracle metadata of a test scenario; render both Direct and Code Mode model-facing requests; assert that the canary and all forbidden metadata keys are absent from every request component and tool description. Assert that any attempt to pass the full scenario object, any unknown projection key, or a leaked derived target `record_id` for T5-T8 fails closed (except the explicitly declared T7 seed A). Preserve projection-schema hash, rendered-request hashes, allowlist tests and leakage-verifier results. These are specifications for future tests, **not** completed evidence. The model-facing projection is distinct from the actual Decision MCP fixture, which remains available only through the genuine MCP read methods. Prohibit real fixture-derived answer examples in shared schema text; perform normalization-aware (NFKC, casefold, separator-insensitive) leakage validation.

## 5. Corpus adequacy and coverage

The corpus must be adequate for the approved D1 power plan, not merely large. Adequacy is a review decision, not a count invented here.

### 5.1 Required coverage dimensions

- **Family coverage:** T1-T8 present; T5-T8 have at least the approved `N_f`.
- **Scope coverage:** every declared scope appears in applicable and non-applicable scenarios; overlap cases exist.
- **Lifecycle coverage:** active, superseded, deprecated and inactive records appear in retrieval and filter scenarios.
- **Cardinality coverage:** unique, small, medium and ambiguous search/applicable result sets, with bins approved before freeze.
- **Version coverage:** single-version and multi-version decisions where version identity matters.
- **Lineage coverage:** rule-present, rule-absent, evidence-present, evidence-empty and missing-link traces.
- **Ambiguity coverage:** deterministic task rules resolve selection ambiguity; no scenario depends on model guesswork.
- **Negative controls:** unique IDs and simple searches produce low expected overhead and detect gross interface regressions.

### 5.2 Quotas

Quotas are **TBD** pending:

- approved `N_f` per T5-T8 family from the pilot power plan;
- approved pilot and confirmatory counts;
- approved diversity bins;
- approved minimum number of decisions per scope/lifecycle/cardinality bin;
- approved enrollment cap.

No fixed decision count is asserted. A corpus that cannot satisfy the approved power plan fails adequacy regardless of total size.

### 5.3 Complexity measures

Record per scenario and aggregate:

- number of decisions visible to search/applicability;
- number of candidate decisions before filtering;
- number of rules and evidence records;
- number of missing lineage links;
- number of scopes and lifecycle transitions;
- expected tool-call sequence length;
- prompt and tool-schema token counts (secondary measurement only);
- dependency depth.

The corpus review must show that T5-T8 are materially data-dependent and not reworded T1-T4 tasks.

## 6. Ground-truth evaluator specification

### 6.1 Evaluator principles

- Deterministic; no LLM judge.
- Exact match on the task-requested identity fields.
- No fuzzy matching, plausible-ID acceptance, order-insensitive comparison where order is specified, or silent coercion.
- Inputs: frozen scenario, frozen expected answer, frozen corpus, raw model final answer.
- Output: `PASS` or `FAIL`, mismatch path, expected and actual values, and an evaluator version hash.
- The evaluator must be independently implemented and reviewed.

### 6.2 Ground-truth consistency acceptance

- 100% of frozen expected answers must be independently re-derived from the frozen corpus by the evaluator or a reviewer-owned oracle and match field-for-field.
- Every expected field must trace to the genuine pinned MCP fixture and serialized outputs; no expected value may come from model output or generator-private convenience logic. For search and applicability membership (especially T7), a deterministic genuine-MCP replay and the independently written evaluator projection must agree exactly; disagreement blocks freeze. The evaluator is a cross-check/scorer, **never** a replacement runtime resolver under ADR-023.
- A reviewer must re-derive a predeclared sample of scenarios without using generator-private helpers.
- Mutation coverage must show that changing any required identity field causes evaluator failure.
- Any mismatch between generator expected output and independent derivation blocks corpus freeze.

### 6.3 Required self-tests

The evaluator test suite must include at least:

- correct expected answer for each family;
- wrong decision ID;
- wrong version or version ID;
- wrong content digest;
- wrong lifecycle status;
- wrong context scope;
- wrong derived rule ID;
- wrong declared evidence selector/hash;
- omitted or fabricated `missing_links` entry;
- T6 predicate case where `c=0`, partial or all candidates match, with exact `include_paths` membership;
- T7 correct seed A but wrong trace-derived path or wrongly selected B;
- fabricated missing field;
- missing required field;
- extra field where the schema forbids extras;
- wrong ordering for T8;
- empty and partial results;
- not-found and trace-not-found behavior;
- malformed JSON;
- truncated answer;
- wrong canonical record type;
- ambiguous selection at the task-rule boundary;
- property/mutation tests for identity-field comparison.

The evaluator must fail closed on unknown output shapes.

### 6.4 Independence evidence

The evaluator review must record:

- source hash and version;
- author and independent reviewer;
- test results;
- differences from generator answer logic;
- any shared Mneme identity algorithm dependency and why it is acceptable;
- a mutation report showing that each expected field is checked.

## 7. Duplicate and leakage controls

### 7.1 Exact duplicates

Canonicalize prompt + params + expected answer and hash it. Any exact duplicate in the confirmatory set is rejected.

### 7.2 Near-duplicates

Normalize model-visible prompt and params with Unicode NFKC, lowercase and whitespace collapse. Tokenize on whitespace, form 5-token shingles, and compute symmetric Jaccard `J = |A intersect B| / |A union B|` for every unordered confirmatory scenario pair.

Proposed, not ratified:

- `J < 0.60`: pass;
- `0.60 <= J < 0.80`: documented corpus-reviewer approval required;
- `J >= 0.80`: reject.

Shared boilerplate alone is not a reason to pass a near-duplicate. Report both the raw Jaccard and a boilerplate-stripped Jaccard. If a high raw value is solely shared task-template boilerplate, remove or parameterize that boilerplate, rerun both the exact and near-duplicate checks, and retain the raw finding and stripped finding in the rejection/exception report. Never waive the threshold; a stripped pair at or above the reject tier is still rejected. Every `0.60`-`0.80` exception requires a reviewer rationale, and the final confirmatory set must have zero pairs at or above `0.80`.

### 7.3 Answer leakage

For every scenario:

- expected decision IDs, version IDs, digests, rule IDs and evidence selectors must not appear in prompt or tool descriptions unless the task explicitly requires the ID;
- no derived/answer-target argument may be pre-filled in the prompt for T5-T8 (T7 seed A and T6 predicate p_T6 are the only declared input exceptions);
- no expected answer may be recoverable from a prompt-only string match;
- the information-dependency proof in Section 3.2 and the model-visible projection in Section 4.1 must pass;
- the model must not receive a hidden answer file, prior transcript or evaluator output.

### 7.4 B0-M overlap

Exact or near-duplicate overlap with B0-M scenarios, prompts or expected answers is rejected. B0-M may be run only as a separate labeled regression check.

## 8. Pilot and confirmatory separation

- Pilot and confirmatory scenario IDs and hashes are disjoint.
- The pilot manifest is frozen before pilot execution; the confirmatory manifest is frozen before confirmatory execution.
- Pilot scenarios are never relabeled or reused as confirmatory.
- Pilot results may calibrate variance/instrumentation but may not tune confirmatory prompts, expected answers, thresholds or evaluator logic.
- Confirmatory scenario **selection rule and eligible scenario bank** must be approved before any pilot model call. The final number and identities of confirmatory scenarios may be frozen **after the non-confirmatory pilot** only via the predeclared variance-to-`N_f` calculation, fixed eligibility rules and an independent randomized selection seed, without inspecting confirmatory outcomes. The final confirmatory manifest and its hashes must be frozen **before the first confirmatory model call**. No pilot scenario may be reused.
- The confirmatory corpus is not regenerated after confirmatory data are observed.

## 9. Hashes, rejection evidence and sign-off

The freeze manifest must include SHA-256 values for:

- corpus fixture;
- generator source and version;
- generator inputs/seed;
- scenario manifest;
- prompts and tool-visible inputs;
- expected answers;
- evaluator source/version and tests;
- environment/lockfiles used to run the deterministic generator/evaluator;
- pilot and confirmatory manifests;
- duplicate/leakage reports;
- corpus and evaluator reviewer records.

Every rejected scenario, duplicate pair, leakage finding and quota exception retains a reason and evidence. Rejections are not silently deleted.

Required sign-off before any freeze proposal:

- corpus author;
- independent corpus reviewer;
- independent evaluator author/reviewer;
- statistics reviewer confirming `N_f` feasibility;
- human owner confirming authorization and scope.

## 10. Unresolved parameter register

| Parameter | Proposed value/state | Required evidence/approval |
|---|---|---|
| Decision count | TBD | Approved `N_f`, pilot/confirmatory counts, coverage quotas |
| Versions per decision | TBD | Corpus design review |
| Lifecycle distribution | TBD | Coverage review |
| Scope graph | TBD | Coverage review |
| Rule density | TBD | Coverage review |
| Evidence density | TBD | Coverage review |
| Missing-link density | TBD | Trace coverage review |
| Ambiguity bins | TBD | Task-rule review |
| T6 m / c bins, disclosed p_T6 | TBD; one disclosed predicate allowed | Prepilot corpus quota/leakage approval |
| T8 k bins | TBD | Fan-out quota review |
| E-1 1/4 family weights | Proposed, not accepted | Independent statistics/human decision |
| Search/applicable cardinality bins | TBD | Coverage review |
| Near-duplicate thresholds | 5-token Jaccard, 0.60/0.80 proposed | Corpus review and approval |
| Evaluator implementation | TBD | Separate implementation and test review |
| Evaluator language/runtime | TBD | Environment freeze |
| Generator seed | TBD | Pre-freeze manifest |
| Pilot/confirmatory counts | TBD | D1 power plan and approval |
| Reviewer identities | TBD | Human assignment |
| Freeze authorization | BLOCKED | Human approval |

## 11. Readiness

- **Corpus/evaluator specification:** READY for review as a design proposal.
- **Corpus build/freeze:** NOT AUTHORIZED.
- **Evaluator implementation:** NOT AUTHORIZED.
- **B0-A pilot/confirmatory execution:** NOT AUTHORIZED.
- **D1-C preregistration:** BLOCKED.
- **S1-A2:** undefined and blocked.

This document does not claim a frozen corpus, evaluator, ground truth, adequacy result or statistical power. No model/API call or benchmark execution was performed.

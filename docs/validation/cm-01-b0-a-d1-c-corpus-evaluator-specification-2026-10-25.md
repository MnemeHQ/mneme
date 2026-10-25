# CM-01-B0-A D1-C - Synthetic Scenario Corpus and Independent Evaluator Specification

**Status:** PROPOSAL FOR REVIEW - **not built, not frozen, not accepted, and not authorized for execution**.

**Date:** 2026-10-25  
**Issue:** #658; parent #640.  
**D0 design:** PR #654, squash-merged at `8060b9bc318e0a0cb206d0cc9d3e6833977e367c`.  
**D1 resolution:** PR #655, squash-merged at `4b8471149d49f6f4a2a4ddfd0d3601d59355c337`.  
**Governing architecture:** ADR-017, ADR-022, ADR-023 and ADR-027.

This document specifies the B0-A synthetic scenario corpus and the independent deterministic answer evaluator. It does not build them, freeze them or select final counts. No model/API call, benchmark run, production change, new MCP method, B0-A pilot, confirmatory execution or S1-A2 work is authorized.

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

No numeric value in this list is approved. Counts follow the approved D1 power plan and corpus review, not a convenience target. The generator must emit a manifest of its inputs, seed, version and output hashes.

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

## 3. T1-T8 scenario contracts

| Family | Model-visible input | Required operations | Required output | Data-dependency contract |
|---|---|---|---|---|
| T1 | Stable decision ID | `decision.get` | Identity projection | None; single step |
| T2 | Unique text marker and lifecycle filter | `decision.search` | Canonical IDs and count | Search only |
| T3 | Scope context | `decision.applicable_to` | Canonical IDs and count | Scope retrieval only |
| T4 | Stable decision ID | `decision.trace` | Lineage and declared evidence | Trace only |
| T5 | Marker and lifecycle filter | `search`, then `get` | Identity projection | Later `record_id` must be selected from search output |
| T6 | Marker and lifecycle filter | `search`, then `trace` | Lineage projection | Later `record_id` must be selected from search output |
| T7 | Scope context | `applicable_to`, lifecycle filter, `get`, `trace` | Selected ID plus get/trace projections | Selection requires scope/lifecycle output; get and trace use that selection |
| T8 | Query and lifecycle filter | `search`, filter, then repeated `get` | Ordered identity items | Selected IDs must come from search output and rule presence |

T1-T4 are negative controls and do not enter the primary token estimand. They remain mandatory correctness/authority/security gates.

### 3.1 Exact output schemas

The evaluator accepts only these frozen shapes. Extra fields are rejected where the schema says closed; ordering is exact where specified.

```text
T1 / T5 get projection:
  { decision_id, version, version_id, content_digest,
    lifecycle_status, context_scope, derived_rule_ids }

T2 / T3:
  { canonical_ids: [string, ... sorted ascending], count: integer }

T4 / T6 trace projection:
  { canonical_decision_id, version, version_id, content_digest,
    derived_rule_ids,
    declared_test_evidence: [ { selector, sha }, ... ] }

T7:
  { selected_id,
    get: <T1 get projection>,
    trace: <T4 trace projection> }

T8:
  { items: [ { decision_id, version, content_digest,
               derived_rule_ids }, ... ] }   // sorted by decision_id
```

Within each projection, `context_scope`, `derived_rule_ids` and `declared_test_evidence` preserve frozen fixture order; `canonical_ids` and T8 `items` are sorted ascending by `decision_id`. No field may be normalized into an approximate match. Missing required fields, extra fields in a closed object, wrong types, wrong order where required, or wrong identity values are failures.

### 3.2 T5-T8 data-dependency proof

For every T5-T8 scenario, a deterministic structural validator must prove:

1. the later request argument (typically `record_id`) is absent from the prompt, tool descriptions and model-visible context;
2. the argument is not derivable from a stable rule stated in the prompt;
3. the argument is produced by the earlier tool result under the frozen task algorithm;
4. removing or corrupting the earlier tool result makes the scenario unsolvable or changes the selected identity;
5. no alternative valid sequence selects a different canonical answer;
6. the scenario has exactly one expected final projection under the task rules.

The validator records a dependency graph and a counterfactual result. A scenario without a proven dependency fails corpus review.

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
- Every expected field must trace to a canonical fixture field; no expected value may come from model output or generator-private convenience logic.
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
- no later-call argument may be pre-filled in the prompt for T5-T8;
- no expected answer may be recoverable from a prompt-only string match;
- the dependency proof in Section 3.1 must pass;
- the model must not receive a hidden answer file, prior transcript or evaluator output.

### 7.4 B0-M overlap

Exact or near-duplicate overlap with B0-M scenarios, prompts or expected answers is rejected. B0-M may be run only as a separate labeled regression check.

## 8. Pilot and confirmatory separation

- Pilot and confirmatory scenario IDs and hashes are disjoint.
- The pilot manifest is frozen before pilot execution; the confirmatory manifest is frozen before confirmatory execution.
- Pilot scenarios are never relabeled or reused as confirmatory.
- Pilot results may calibrate variance/instrumentation but may not tune confirmatory prompts, expected answers, thresholds or evaluator logic.
- Confirmatory scenario selection is fixed before any model call.
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

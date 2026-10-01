# O1A Open Architecture Benchmark Methodology

## Objective

Evaluate whether Mneme can identify and correctly apply software architecture decisions from real repositories.

The benchmark separates five problems:

1. decision discovery
2. decision understanding
3. authority and lifecycle
4. scope and applicability
5. Governing Decision Set retrieval

## Decision representation

Each candidate should preserve:

- source evidence
- normalized decision
- classification
- domain
- purpose
- authority
- scope
- lifecycle
- relationships
- enforcement potential
- confidence
- human validation

## Decision classification

Primary classification:

- prescriptive
- advisory
- descriptive
- historical
- ambiguous

## Decision domains

`decision_domain` is multi-label.

Initial values:

- architecture_structure
- dependency_technology
- api_interface
- data_contract
- integration_eventing
- persistence
- security_privacy
- deployment_infrastructure
- reliability_observability
- performance_scalability
- testing_quality
- compatibility_versioning
- migration_evolution
- ownership_boundary
- developer_workflow
- compliance
- cost_resource
- other

## Decision purposes

`decision_purpose` is multi-label.

Initial values:

- constrain
- standardize
- select
- prohibit
- require
- allocate_ownership
- define_boundary
- preserve_compatibility
- manage_risk
- enable_migration
- deprecate
- freeze
- create_exception
- require_evidence
- optimize_quality_attribute
- document_tradeoff
- other

Domain answers what the decision concerns.

Purpose answers what the decision does.

## Authority

Initial authority states:

- candidate
- explicitly_accepted
- superseded
- rejected
- unknown

Authority evidence must be retained separately from the normalized decision.

## Scope

Scope types:

- repository
- service
- package
- directory
- file_pattern
- component
- api
- dependency
- other

A decision may have multiple scope expressions.

## Lifecycle

Lifecycle states:

- active
- superseded
- deprecated
- temporary
- unknown

Preserve:

- `supersedes`
- `superseded_by`
- `effective_date`
- `expiration_if_any`

## Relationships

Initial relationship types:

- requires
- prohibits
- depends_on
- refines
- conflicts_with
- supersedes
- exception_to

## Enforcement potential

Initial classes:

- deterministic_rule
- contextual_guidance
- warning
- block
- not_mechanically_enforceable
- unknown

Classification of enforcement potential is not itself permission to enforce.

## Applicability scenarios

Each scenario represents a proposed software change.

A scenario contains:

- path
- component
- change type
- dependency context
- API context
- technology context
- free-form context
- expected governing decisions
- Mneme governing decisions

Several decisions may govern one change.

## Headline metric

The most important product metric is **Governing Decision Set F1**.

For a proposed change:

- Precision: of the decisions Mneme returned, how many actually govern the change?
- Recall: of all decisions that should govern the change, how many did Mneme retrieve?
- F1: harmonic mean of precision and recall.

Do not collapse the benchmark into one overall score.

## Additional metrics

Measure:

- decision discovery precision and recall
- prescriptive intent precision, recall, and F1
- domain precision, recall, and F1
- purpose precision, recall, and F1
- scope accuracy
- authority accuracy
- lifecycle accuracy
- relationship accuracy
- enforcement classification accuracy

## Classifier backend comparison

The benchmark must support multiple classifier backends without changing the benchmark ontology.

Every prediction should retain backend identity, version, confidence, latency, and cost where measurable.

Compare classifiers against the same human-reviewed candidate set.

Also record:

- calibration against human labels
- false-positive rate
- false-negative rate
- escalation rate
- backend disagreement

Classifier confidence must not be assumed to be calibrated across backends.

Probabilistic classifiers may assist interpretation. They must not directly establish canonical authority or replace deterministic enforcement.

## Error taxonomy

Record at least:

- MISSED_SOURCE
- NOT_A_DECISION
- WRONG_INTENT
- WRONG_DOMAIN
- WRONG_PURPOSE
- WRONG_AUTHORITY
- WRONG_SCOPE
- WRONG_LIFECYCLE
- MISSED_SUPERSESSION
- MISSED_RELATIONSHIP
- FALSE_APPLICABILITY
- MISSED_APPLICABILITY
- WRONG_RULE_DERIVATION
- AMBIGUOUS_HUMAN_LABEL
- ONTOLOGY_GAP

`ONTOLOGY_GAP` is especially important during O1A because the initial taxonomy is provisional.

## Batch 01 sample design

Per repository, aim for 20 manually reviewed decisions:

- 5 clear explicit decisions
- 5 scoped decisions
- 3 lifecycle or supersession decisions
- 3 ambiguous or conflicting decisions
- 2 decisions with enforcement potential
- 2 unusual or difficult cases

Also create 10 realistic proposed-change scenarios per repository.

Batch 01 total:

- 5 repositories
- 100 validated decisions
- 50 applicability scenarios

## Batch 01 Staged Benchmark Protocol

To decouple discovery errors from semantic evaluation and prevent candidate explosion and artificial zero-overlap in retrieval, Batch 01 is structured into three discrete stages:

```text
Repository Sources
       ↓ (discover_sources + HeuristicExtractor)
Stage A: Dynamic Discovery Spans (cand-*) ──[Span Match]──> Evaluated vs. Frozen Reference Decisions (ref-*)
                                                                       │
Stage B: Semantic Classification (800 tasks) <─────────────────────────┘ (Frozen Reference Decisions ref-*)
       ↓
Stage C: Governing Decision Set (DecisionRetriever) ──────> Evaluated vs. Pinned Scenarios (ref-*)
```

### Stage A — Discovery

- **Input**: Pinned repository sources at frozen commit SHAs.
- **Execution**: Existing `discover_sources` followed by existing `HeuristicExtractor`.
- **Output**: Dynamic `cand-*` `ExtractedCandidate` evidence spans.
- **Identity**:
  - `cand-*` is dynamic discovery identity.
  - `ref-*` is frozen benchmark ground-truth identity.
  - Identities are never rewritten or treated as equal.
- **Deterministic discovery match**:
  A dynamic candidate $C$ matches a frozen reference $R$ iff:
  1. $C$ source path matches one of $R$'s source-file components, AND
  2. $C$ line interval has non-empty intersection with one of $R$'s line intervals for that source-file component.
  - No semantic or LLM matching is permitted.
  - No empirical Intersection over Reference (IoR) or Intersection over Candidate (IoC) threshold is used for match gating.
- **Primary metrics**:
  $$\text{Discovery Recall} = \frac{\text{number of frozen reference decisions overlapped by } \ge 1 \text{ candidate}}{\text{all frozen reference decisions}}$$
  $$\text{Discovery Precision} = \frac{\text{number of extracted candidates overlapping } \ge 1 \text{ frozen reference decision}}{\text{all extracted candidates}}$$
- **Edge semantics**:
  - **$1 \to N$ (One candidate matching multiple references)**: Candidate counts once for precision; every overlapped reference counts independently for recall.
  - **$N \to 1$ (Multiple candidates matching one reference)**: Each evidence-bearing candidate participates normally in precision; the reference counts once for recall.
  - **Undiscovered source types (`MISSED_SOURCE`)**: References in undiscovered source types (e.g. source code files not reached by markdown discovery) remain in the recall denominator and are counted as misses; they must not be silently excluded.
  - **Discontinuous / multi-file references**: Represented as the union of their `(source_path, line_interval)` components.
  - IoR and IoC may be recorded as diagnostic indicators of extraction breadth and fragmentation, but MUST NOT determine true positive or false negative status in Batch 01.

### Stage B — Semantic Classification

- **Population**: Exactly the frozen 100 human-reviewed reference decisions (20 per repository). Dynamic 5,459-candidate heuristic extraction output is NOT the classifier baseline population.
- **Tasks**: Exactly the eight frozen semantic tasks per decision (`decision_classification`, `domains`, `purposes`, `authority`, `scope`, `lifecycle`, `relationships`, `enforcement_potential`).
- **Expected logical task count**: $100 \times 8 = 800$ logical classifier tasks (provider retries may produce additional HTTP attempts).
- **ClassifierTask mapping**:
  - `candidate_id` = `reference_decision_id`
  - `repository_identifier` = `repository`
  - `repository_commit_sha` = `repository_commit_sha`
  - `source_path` = `source_file`
  - `source_location` = `source_location`
  - `raw_statement` = `raw_evidence`
  - `source_context` = `raw_evidence`
  - `taxonomy_version` = `0.1`
- **Evidence invariance**: The exact same frozen evidence must be supplied to every classifier backend and on every rerun. Predictions are compared directly against the frozen human labels.

### Stage C — Governing Decision Set (GDS)

- **Input**: Classified representation of the same frozen reference decisions, preserving `ref-*` as `DecisionCandidate.candidate_id`.
- **Per repository**: Exactly 20 reference decisions and 10 applicability scenarios.
- **Projection**: Project `ref-*` `DecisionCandidate` records through the existing frozen projection (`project_candidate_to_decision`); use the existing frozen `DecisionRetriever` unchanged under the `score_gt_zero` policy.
- **Evaluation**: Predicted decision IDs and expected scenario IDs are both `ref-*`. Compute existing GDS precision, recall, and F1. GDS must not directly compare `cand-*` IDs with `ref-*` IDs.

## Scenario Identity and Provenance

The benchmark distinguishes two scenario identities:

1. **Frozen Batch 01 Scenario Corpus Identity**:
   `2ff8751955fd64a33316aca6692dc803`
   - Deterministic content hash of all 50 canonical scenarios across the five repositories.
   - Remains stored in `baseline.yaml` under `scenario_corpus.content_hash`.
2. **Per-Repository Execution Subset Identity**:
   - Deterministic content hash of the actual 10 scenarios evaluated for a given repository.
   - Remains stored in `RunMetadata.scenario_content_hash`.

`RunMetadata.scenario_content_hash` is not redefined, and `RunMetadata` is not modified. The future Batch 01 harness will bind global benchmark provenance outside the frozen `RunMetadata` contract using a research-only batch provenance envelope containing, at minimum:
- `baseline_id`
- `baseline_configuration_hash`
- `reference_corpus_hash`
- `scenario_corpus_hash`
- per-repository `RunMetadata` records

## Frozen Baseline Identities

- `semantic_mneme_sha`: `3673c36855fb1e30d46942ce826c50be4888df5e`
- `reference_corpus` content hash: `0455bd66aae52551c35b37a63c2d185f` (100 decisions, 20/repo)
- `scenario_corpus` content hash: `2ff8751955fd64a33316aca6692dc803` (50 scenarios, 10/repo)

## Core Research Boundary

Benchmark research data is strictly experimental and never canonical project authority. No inferred candidate or reference decision is automatically promoted into the Canonical Decision Index.

## Baseline integrity

Do not improve Mneme's semantic behaviour partway through Batch 01.

Run all five repositories on one frozen build first.

Record weaknesses instead of correcting them during the baseline.

After baseline completion:

1. inspect failures
2. identify ontology and product gaps
3. decide changes
4. rerun against the same pinned repository SHAs

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

## Baseline integrity

Do not improve Mneme's semantic behaviour partway through Batch 01.

Run all five repositories on one frozen build first.

Record weaknesses instead of correcting them during the baseline.

After baseline completion:

1. inspect failures
2. identify ontology and product gaps
3. decide changes
4. rerun against the same pinned repository SHAs

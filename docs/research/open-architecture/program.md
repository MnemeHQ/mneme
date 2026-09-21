# Mneme Open Architecture Project

## Purpose

The Mneme Open Architecture Project is a product-learning and developer-adoption program for studying how software architecture decisions are expressed, scoped, related, superseded, applied, and eventually enforced.

The program asks:

> Can Mneme reconstruct, understand, and correctly apply the architectural decisions governing a software change?

## Strategic loop

```text
Public repository analysis
        ↓
Decision Index learning
        ↓
Maintainer verification
        ↓
Decision MCP
        ↓
Contributor / agent usage
        ↓
Enforcement evidence
        ↓
Enterprise learning and adoption
```

The strategic asset is not a centralized public database of other projects' decisions. It is Mneme's accumulated understanding of how technical decisions work in real software systems.

## Milestones

### O1A — Open Architecture Benchmark

Create a reproducible benchmark across real repositories.

Initial Batch 01 target:

- 5 repositories
- 100 manually validated decisions
- 50 applicability scenarios

Primary outputs:

- baseline performance
- failure taxonomy
- ontology gaps
- representative failure cases

### O1B — Maintainer-verified Decision Index

For selected repositories:

- run the Architecture Audit
- create provisional DecisionProposal candidates
- ask maintainers to accept, modify, or reject
- preserve corrections as product-learning evidence

### O1C — Public Decision MCP

Expose accepted project decisions through Decision MCP so contributors and coding agents can query:

- `decision.search`
- `decision.get`
- `decision.applicable_to`
- `decision.trace`

### O1D — Enforcement experiments

Test whether accepted architectural decisions can prevent or redirect architecture-breaking agent actions before code is generated or shipped.

## Research and authority boundary

An inferred statement is not an authoritative decision.

```text
discovered intent
→ candidate decision
→ DecisionProposal
→ human / maintainer acceptance
→ canonical decision
```

Research evidence must never silently promote itself into project authority.

## OSS and enterprise are complementary

OSS is especially useful for:

- technical architecture semantics
- scope
- applicability
- public decision lifecycle
- agent integration
- contributor workflows

Enterprise design partners are required for:

- organizational authority
- waivers and exceptions
- confidential constraints
- compliance
- approval chains
- temporary policy
- ownership
- regional and business constraints

Both streams should feed the same Decision Index and enforcement model.

## Semantic classification backends

O1A must not assume a single semantic classifier.

Treat classification as an interchangeable research component:

```text
SemanticClassifier
├── local/default
├── external/optional
└── reference classifier
```

External classifiers may assist discovery, triage, ranking, and semantic interpretation. They must not directly establish canonical authority or replace deterministic enforcement.

Human-reviewed O1A labels remain the benchmark reference.

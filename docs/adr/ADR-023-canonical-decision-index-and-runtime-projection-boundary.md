---
id: ADR-023
title: "Canonical Decision Index and Runtime Projection Boundary"
status: proposed
priority: foundational
date: 2026-09-11
scope: decision_index.runtime_projection
---

# ADR-023: Canonical Decision Index and Runtime Projection Boundary

**Status:** Proposed  
**Date:** 2026-09-11  
**Deciders:** Theo Valmis

---

## Context

Mneme currently models `mneme.schemas.Decision` as the primary runtime unit for
project-scoped architectural governance. A runtime Decision carries the decision
statement, rationale, retrieval scope, legacy constraints and anti-patterns,
mechanically enforceable typed rules, provenance paths, timestamps, and lifecycle
status.

That model is appropriate for the current Layer 1 wedge: architectural governance
for AI-assisted software development. It should not become the implicit permanent
schema for every organizational decision Mneme may eventually represent.

The longer-term architecture must preserve the possibility of decisions whose
consequences apply to software architecture, infrastructure, security, data,
operations, procurement, compliance, or other workstreams without assuming that
every decision:

1. originates in an ADR;
2. applies to a source-code path;
3. can be mechanically enforced;
4. ends in a code mutation; or
5. should be represented directly by the current runtime `Decision` object.

At the same time, the current runtime is validation-sensitive. ADR-017 separates
retrieval from enforcement. ADR-019 requires explicit typed rules rather than
inferred enforcement. ADR-020 keeps applicability at the rule level. The current
roadmap also prioritizes external validation of the architecture wedge over broad
platform expansion.

This ADR therefore establishes a canonical decision-layer boundary without
changing current retrieval, enforcement, conflict-detection, Audit, or benchmark
behavior.

---

## Decision

### 1. The Decision Index is the canonical decision layer

Mneme distinguishes between organizational decision records and runtime
representations used by a specific governance surface:

```text
organizational sources
        |
        v
canonical Decision Index
        |
        v
runtime projection
        |
        v
existing Mneme architecture runtime
```

The **Decision Index** is the canonical machine-readable representation of
organizational decisions.

The existing `mneme.schemas.Decision` remains the **Layer 1 architecture runtime
projection**. It is not the universal enterprise decision schema.

### 2. Canonical decisions are source-independent

A canonical decision must not depend on the source format in which it was
recorded. ADRs are the validated source type for D0. Future verified sources may
include documents, tickets, policies, meeting records, messages, or explicit
Mneme-native decision capture.

Source adapters normalize source material into the canonical decision model.
They do not implement enforcement semantics.

### 3. Decision identity is stable and versioned

Every canonical decision has a stable `decision_id` independent of source file
location. Moving or renaming a source does not create a logically new decision.

A decision may have multiple immutable versions. The active version is resolved
explicitly rather than inferred from source modification time.

### 4. Decisions and rules are separate entities

A decision records organizational intent. A rule is one possible
machine-operational expression derived from that intent.

A decision may have zero, one, or many rules. A decision with no rule remains a
valid decision.

No prose decision automatically becomes an enforcement rule. Mechanical
enforcement continues to require an explicit rule type with specified semantics.
For Layer 1, `FORBID_LITERAL` remains governed by ADR-019.

### 5. Decision scope and rule applicability are distinct

The Decision Index may record organizational relevance such as repository,
system, component, service, workstream, process, or policy domain. This is
**decision scope**.

Decision scope does not silently become enforcement applicability.

For current typed architectural rules, path applicability remains owned by the
rule through ADR-020 `include_paths` / `exclude_paths` semantics.

```text
decision scope != typed-rule applicability
```

Future runtimes may define other applicability contracts, but those require
explicit architecture decisions.

### 6. Canonical lifecycle may include non-authoritative states

The current runtime supports `active`, `superseded`, and `deprecated`.

The canonical layer may later need non-authoritative states such as `discovered`
or `proposed` for historical decision reconstruction. Those states do not project
into active Layer 1 governance.

```text
discovered -> no active runtime governance
proposed   -> no active runtime governance
active     -> eligible for runtime projection
superseded -> retained for lineage
deprecated -> retained for lineage
```

Discovery is not authorization.

### 7. The canonical logical model is storage-independent

D0 defines a logical contract, not a database technology.

Conceptually:

```text
CanonicalDecisionRecord
    decision_id
    version
    decision_class
    statement
    rationale
    lifecycle_status
    owner
    decided_at
    context_scope[]
    targets[]
    constraints[]
    source_evidence[]
    relationships[]
    derived_rule_ids[]
```

For D0, the only validated `decision_class` is `architecture`.

The Decision Index may be represented with ordinary deterministic file-backed
records. This ADR does not require a graph database, vector database, ORM,
hosted service, or SaaS control plane.

### 8. Provenance is first-class but does not create authority

Canonical decisions should be traceable to source evidence, conceptually:

```text
DecisionSourceEvidence
    source_id
    source_type
    source_locator
    source_revision
    observed_at
    evidence_hash
    verification_status
```

The intended authority chain is:

```text
evidence exists
    -> decision discovered
    -> decision verified
    -> decision becomes authoritative
```

Future extraction from enterprise knowledge must preserve that boundary. LLM
identification of decision-like language must never silently create active policy.

### 9. Decision relationships form a logical graph

Relationships are explicit records independent of storage technology.

D0 requires compatibility with:

- `supersedes`
- `derived_from`

Future relationships may include `depends_on`, `conflicts_with`, `refines`, or
`implements`, but they gain no operational semantics merely by being representable.

The existing `ConflictDetector` is not repurposed for decision-to-decision graph
analysis. A future decision-consistency component must be a separate surface.

### 10. Rules retain explicit decision lineage

A canonical rule is traceable to the decision version from which it derives:

```text
CanonicalRuleRecord
    rule_id
    decision_id
    decision_version
    rule_type
    rule_payload
    applicability
    lifecycle_status
```

For Layer 1, projection of rules must reproduce the existing `Rule` model and
semantics exactly.

### 11. `mneme.schemas.Decision` is a runtime projection

The initial architecture projection maps canonical architecture decisions into
the existing runtime shape:

```text
decision_id              -> Decision.id
statement                -> Decision.decision
rationale                -> Decision.rationale
context_scope            -> Decision.scope
constraints              -> Decision.constraints
legacy anti-pattern data -> Decision.anti_patterns
derived Layer 1 rules    -> Decision.rules
source provenance        -> Decision.source_path
lifecycle                -> Decision.status
timestamps               -> created_at / updated_at
```

`memory_path` remains runtime storage provenance. It does not define canonical
organizational identity.

Ownership, generic targets, rich provenance, relationships, and other canonical
fields need not appear in the Layer 1 runtime object unless a later ADR gives
them runtime semantics.

### 12. Projection must preserve current behavior

For the existing ADR corpus:

```text
existing ADR compiler -> current Decision[]

must be behaviorally equivalent to

existing ADR corpus -> canonical Decision Index -> Layer 1 projection -> Decision[]
```

Behavioral equivalence includes current decision IDs, text, rationale, scope,
constraints, anti-patterns, typed rules, selectors, lifecycle state, provenance
needed by policy-source exemptions, retrieval ranking, enforcement verdicts,
ConflictDetector results, Architecture Audit classifications, and frozen benchmark
results.

### 13. Retrieval remains a relevance concern

ADR-017 remains unchanged.

`DecisionRetriever` continues to answer which runtime decisions are useful
context for a query. It does not become the Decision Index query engine and its
score does not determine whether an explicit deterministic rule is enforced.

### 14. `ConflictDetector` remains a runtime output evaluator

The current `ConflictDetector` evaluates generated output against supplied
runtime decisions. It is not a general decision-graph contradiction detector.

A future `DecisionConsistencyAnalyzer` or equivalent must be introduced
separately if Mneme needs to detect contradictory active decisions.

### 15. Architecture Audit remains a Layer 1 projection consumer

The Architecture Audit continues to classify architectural decision protection
using the existing Protected / Mneme-ready / Requires modelling / Guidance
semantics and existing formulas.

D0 changes the conceptual source of identity, not Audit scoring:

```text
Decision Index decision_id
        -> runtime Decision.id
        -> Architecture Audit assessment
```

### 16. Future enforcement evidence uses the same identity chain

D0 establishes the identifiers required for future evidence without adding a new
evidence store:

```text
source evidence
    -> decision
    -> decision version
    -> rule
    -> applicability
    -> enforcement event
```

Future exceptions or bypasses may attach to the same chain. This ADR does not
introduce exception runtime behavior.

### 17. External consumers may read the Decision Index without owning it

The Decision Index is intended to be consumable by multiple tools while remaining
Mneme-owned authority.

A future **read-only Decision MCP surface** is an allowed projection/consumer
interface. It is distinct from the currently deferred generic hosted MCP/HTTP
control plane.

A Decision MCP surface may expose operations conceptually equivalent to:

```text
get_applicable_decisions(repo, files, change)
get_decision(decision_id)
get_architecture_constraints(scope)
get_protection_status(decision_id)
get_enforcement_evidence(change_or_event_id)
explain_block(event_id)
```

The exact protocol contract requires a separate implementation decision after D0.

An external review system may consume this information to improve review or
analysis. It must not become necessary for Mneme enforcement, decide decision
authority, or replace Mneme lifecycle/rule semantics.

The preferred dependency direction is:

```text
Mneme Decision Index -> external consumers
```

not:

```text
external consumer knowledge store -> Mneme authority
```

A CodeRabbit integration is a suitable future reference consumer because
CodeRabbit currently supports custom MCP context during review, but CodeRabbit is
not part of the canonical architecture and is never required for Mneme to work.

### 18. External knowledge integrations do not replace Mneme ingestion

Context platforms may already connect to systems such as Confluence, Jira,
Notion, Slack, monitoring systems, and other MCP sources. Mneme should not assume
those platforms expose a general reusable data API from which the Decision Index
can be constructed.

Mneme owns decision identification, authority, lifecycle, scope, rule compilation,
deterministic enforcement, and evidence. Source ingestion remains a Mneme
boundary or uses explicitly validated source adapters.

This avoids making another product the authority or mandatory ingestion layer for
Mneme decisions.

### 19. Non-code decisions may be representable without becoming Layer 1 support

The canonical model must not assume that all targets are files or repositories.
A future organizational decision may be structurally representable while having
no Layer 1 projection or enforcement rule.

```text
representable != supported != enforceable
```

D0 validates architectural decisions only.

---

## D0 validation gates

D0 is accepted only if it proves compatibility with the current runtime.

### G1 — Projection parity

For the canonical current ADR corpus, compare current compiler output with
Decision-Index-projected runtime output across all behaviorally relevant
`Decision` and `Rule` fields.

**Required:** PASS.

### G2 — `DecisionRetriever` parity

Run existing retrieval fixtures/queries over current and projected decisions.
Require identical ordering, scores, per-field match counts, and top-K selection.

**Required:** PASS.

### G3 — Enforcement parity

Run the frozen enforcement benchmark against projected decisions with unchanged
fixtures. Require identical verdicts.

**Required:** PASS.

### G4 — `ConflictDetector` parity

Run current conflict-detection regressions against current and projected decisions.
Require identical conflicts, decision IDs, applicability outcomes, and typed-rule
matching results.

**Required:** PASS.

### G5 — Architecture Audit parity

Run `mneme audit` over the same repository state before and after projection.
Require identical decision sets, protection tiers, summary metrics, and evidence
linkage.

**Required:** PASS.

### G6 — Lifecycle parity

For active, superseded, and deprecated ADR-backed decisions, require identical
Layer 1 inclusion/exclusion behavior.

**Required:** PASS.

### G7 — No inferred enforcement

Project an active canonical decision containing rationale, scope, and constraints
but no explicit typed rule. Require no invented `Rule` and no new deterministic
FAIL behavior.

**Required:** PASS.

### G8 — Source-independence fixture

Represent the same synthetic architecture decision through two equivalent source
fixtures, normalize both to the same canonical identity, and require equivalent
runtime projection.

This is a D0 fixture only; it does not add a production source adapter.

**Required:** PASS.

### G9 — Non-code safety fixture

Represent a canonical decision with a non-code target and no Layer 1 rule. Require
canonical representation to succeed without inventing path applicability or an
enforcement rule, and require frozen benchmark behavior to remain unchanged.

**Required:** PASS.

---

## D0 implementation boundary

The first implementation milestone after this ADR is limited to:

- canonical logical models;
- architecture runtime projection;
- current ADR -> canonical adapter;
- deterministic identity/version handling needed by the adapter;
- projection parity tests;
- DecisionRetriever parity tests;
- ConflictDetector parity tests;
- Audit parity tests; and
- frozen enforcement benchmark parity.

Likely module boundaries are conceptually:

```text
mneme/decision_index.py
mneme/decision_projection.py
```

Exact filenames may change during implementation review. The architectural
boundary may not.

D0 must introduce no behavioral modification to:

```text
mneme/decision_retriever.py
mneme/enforcer.py
mneme/conflict_detector.py
mneme/benchmark.py
mneme/rule_matcher.py
mneme/path_selectors.py
```

Existing benchmark fixtures must not be rewritten to make D0 pass.

If D0 requires a behavioral change to one of those surfaces, it has exceeded its
charter and requires a separate architecture decision.

---

## Explicit non-goals

D0 does not implement:

- Slack or Teams ingestion;
- email ingestion;
- generic enterprise semantic search;
- automatic decision extraction or approval;
- a graph or vector database;
- new retrieval scoring;
- new rule types;
- generic organizational enforcement;
- non-code action interception;
- decision-conflict inference;
- exception workflows;
- a hosted enterprise control plane;
- cross-repository governance;
- team policy synchronization;
- the Decision MCP server itself; or
- a CodeRabbit integration.

The Decision MCP server and CodeRabbit reference-consumer validation are explicit
follow-on candidates once D0 proves the canonical projection boundary.

---

## Consequences

### Positive

- The current architecture wedge can continue without hard-coding the runtime
  `Decision` object as Mneme's permanent enterprise model.
- Decision identity, provenance, lifecycle, relationships, rules, and future
  evidence have an explicit canonical home.
- ADR-017's retrieval/enforcement separation becomes a property of the larger
  architecture rather than a local implementation detail.
- External systems can consume authoritative decisions without becoming their
  owner.
- A future Decision MCP interface can make the Index useful to review systems and
  other agents without requiring bespoke integrations into every consumer.
- Existing code-review/context platforms may remain complementary rather than
  becoming Mneme ingestion dependencies.

### Negative / accepted trade-offs

- D0 adds an architectural layer that initially provides no new user-visible
  capability.
- The same architectural decision exists in canonical and runtime forms, so
  parity tests become mandatory.
- Source-independent identity and versioning introduce concepts that are not
  required by today's local-repo runtime alone.
- MCP and non-ADR ingestion remain follow-on work rather than being bundled into
  the foundational change.

---

## Relationship to existing ADRs

- **ADR-017 — Enforcement Scope Is Independent of Retrieval Scope:** unchanged
  and strengthened. Retrieval remains relevance; deterministic enforcement does
  not depend on ranking.
- **ADR-018 — Introduced-Delta Enforcement at the Edit Gate:** unchanged. D0 does
  not change which bytes are evaluated.
- **ADR-019 — Typed Literal Rule Contract:** unchanged. D0 does not infer rules
  from decision prose.
- **ADR-020 — Explicit Path Applicability for Typed Rules:** unchanged. Decision
  scope does not replace rule selectors.
- **ADR-022 — Main Is PR and Squash Only:** all D0 implementation remains subject
  to existing repository governance.

---

## Relationship to the roadmap

The active product wedge remains project-scoped architectural governance for
AI-assisted software development.

D0 is a foundational architecture direction, not a broad enterprise product
expansion. Current external-validation work remains necessary.

The intended technical sequence after D0 is:

```text
D0  Canonical Decision Index + runtime projection parity
D1  Decision lifecycle/provenance/relationship hardening where required
D2  Read-only Decision MCP consumer surface
D3  Reference consumer validation (CodeRabbit is a candidate)
D4  Additional source adapters only where evidence justifies them
```

This sequence intentionally prioritizes the Mneme-owned decision model and
enforcement layer over rebuilding every context integration already available in
adjacent platforms.

---

## Acceptance criterion

ADR-023 is satisfied when:

1. the canonical Decision Index contract is implemented for architecture
   decisions;
2. the current ADR corpus can be represented canonically;
3. projection reproduces existing Layer 1 runtime semantics;
4. G1-G9 pass;
5. no frozen retrieval, enforcement, ConflictDetector, Audit, or benchmark
   behavior changes; and
6. no additional enterprise decision class is promoted to supported status.

Until those conditions pass, the Decision Index is an architecture contract, not
a replacement runtime.

---

## Decision summary

Mneme will treat organizational decisions as a canonical, source-independent,
versioned decision layer. The existing `Decision` object remains the
architecture-runtime representation rather than becoming the universal schema.

Decisions may exist without enforceable rules. Rules remain explicit, typed, and
deterministic. Decision scope does not silently become rule applicability.
Retrieval, applicability, and enforcement remain separate concerns. Historical
discovery cannot silently create authoritative governance.

External systems may consume Mneme decisions, including through a future
read-only Decision MCP interface, but they do not own decision authority or
become required for Mneme enforcement.

This establishes the Decision Index as a first-class strategic architecture
primitive while preserving the validated architectural-governance wedge.
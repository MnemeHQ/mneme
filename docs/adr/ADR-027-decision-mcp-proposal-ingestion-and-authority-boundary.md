---
id: ADR-027
title: "Decision MCP Proposal Ingestion and Authority Boundary"
status: proposed
priority: high
date: 2026-09-12
scope: decision_index.mcp
---

# ADR-027: Decision MCP Proposal Ingestion and Authority Boundary

**Status:** Proposed  
**Date:** 2026-09-12  
**Deciders:** Theo Valmis

---

## Context

ADR-023 establishes the canonical Decision Index and allows a future Decision MCP
consumer surface while preserving Mneme-owned decision authority. Its initial MCP
framing is read-only.

The Decision Index also needs a safe producer boundary. External architecture
systems can identify candidate architectural decisions that should enter Mneme for
review without becoming authoritative merely because an external tool emitted
them.

Candidate producers include architecture agents, architecture-document tooling,
EventCatalog, migration-analysis tools, Confluence/document sources, and other
human- or AI-authored systems.

The desired flow is:

```text
external system
    -> proposes architectural decision
    -> Mneme records proposal + provenance
    -> human reviews / accepts through Mneme authority controls
    -> canonical Decision Index entry created
    -> Architecture Audit evaluates governability
    -> rules / applicability / enforcement / evidence remain Mneme-owned
```

This requires a write capability at the MCP boundary without turning MCP ingestion
into authority or enforcement.

---

## Decision

### 1. Decision MCP supports consumers and non-authoritative producers

The first Decision MCP contract may support both retrieval and proposal ingestion.

The MCP sits over the canonical Decision Index. It is not a second decision store
and does not own lifecycle or enforcement semantics.

```text
Decision producers
        |
        v
Decision Index MCP
        |
        v
Proposal / canonical Decision Index
        |
        v
Audit / modelling
        |
        v
Rule + applicability
        |
        v
Enforcement
        |
        v
Evidence
```

Consumer tools use the same MCP boundary in the opposite direction to retrieve
Mneme-owned decisions and context.

### 2. Proposal state is distinct from canonical decision lifecycle

A proposal is a candidate record, not an authoritative decision.

Minimum proposal lifecycle:

```text
proposed -> accepted -> canonical Decision created
proposed -> rejected
```

A proposal MUST NOT be enforceable.

`accepted` describes the result of a Mneme authority step. It does not grant an
external producer permission to perform acceptance.

Canonical decision lifecycle remains governed separately by the Decision Index and
existing lifecycle contracts.

### 3. Generic producers cannot create Active governance

A producer may submit candidate decision text, rationale, provenance, scope hints,
architecture context, and relationships to known decisions.

A generic producer may not:

- create an Active/enforced canonical decision directly;
- mark a decision Protected;
- activate enforcement;
- create a typed rule merely by assertion;
- fabricate verified evidence;
- bypass human/Mneme review;
- create exceptions;
- supersede an Active decision outside normal Mneme lifecycle controls; or
- mutate canonical history invisibly.

MCP ingestion is not enforcement.

This preserves ADR-017's separation between retrieval/context and deterministic
enforcement and ADR-019's requirement for explicit typed rules.

### 4. P0 producer operation: `decision.propose`

`decision.propose` submits one candidate architectural decision.

Conceptual inputs:

```text
title
statement
rationale
source
    producer_name
    producer_type
    source_reference
    external_source_id?
    source_version_or_commit?
scope_hints?
architecture_context?
related_decision_ids?
```

Conceptual result:

```text
proposal_id
proposal_status
match_or_deduplication_information
canonical_decision_id_if_known
warnings_requiring_human_review
```

The initial state of a newly created proposal is always `proposed`.

### 5. P0 producer operation: `decision.propose_batch`

`decision.propose_batch` submits multiple candidate decisions originating from one
architecture/design output.

Each candidate receives its own proposal identity. Shared source provenance may be
represented once and referenced deterministically by each proposal.

Batch submission does not create batch authority: every proposal remains
independently reviewable and non-enforceable.

### 6. P0 retrieval operations

The initial MCP contract should also define:

```text
decision.get
decision.search
decision.applicable_to
decision.trace
```

`decision.get` retrieves a proposal or canonical decision by stable ID and may
return lifecycle/proposal state, version, provenance, scope, linked rules, linked
enforcement points, and evidence summary where those links exist.

`decision.search` searches supported proposal/canonical metadata and text. Search
may be textual or semantic, but search ranking is retrieval/context only and has
no deterministic enforcement authority.

`decision.applicable_to` returns decisions relevant/applicable to a supplied
repository/path/component/context for retrieval and context loading. It must not
redefine ADR-020 typed-rule applicability semantics.

`decision.trace` returns the deterministic lineage currently known:

```text
Decision
    -> Rule
    -> Scope / applicability
    -> Enforcement point / Test
    -> Evidence
```

A partial trace is valid. Missing links must be explicit rather than fabricated.

### 7. Acceptance is not a generic producer MCP mutation

P0 does not expose generic producer operations equivalent to:

```text
decision.accept
decision.activate
decision.supersede
decision.create_exception
```

Human review/acceptance occurs through a Mneme-owned authority surface defined
separately from generic producer submission.

When a proposal is accepted, Mneme must:

- assign or use a stable canonical decision ID;
- create the initial canonical decision version;
- retain the originating proposal;
- retain source provenance and producer relationship; and
- never silently overwrite an existing canonical decision.

### 8. Proposal ingestion is idempotent

External systems will resend source data.

The producer contract must support a stable source key conceptually equivalent to:

```text
source_system
+ source_document
+ external_decision_id
+ source_version
```

Repeated submission of the same source/version must not create duplicate
proposals.

Changed content/source versions create a new proposal or version candidate rather
than silently mutating history.

Semantic similarity may flag likely duplicates for human review. Similarity alone
must never auto-merge proposals or canonical decisions.

### 9. Proposal provenance is first-class

Every proposal must retain enough provenance to answer:

- where did this candidate decision originate?
- which producer/system created it?
- which document/output/repository did it come from?
- what source version or commit produced it?
- when was it proposed?
- was it AI-generated, human-authored, or imported?

Proposal provenance is informational. Trusted execution/evidence attestation is a
separate concern governed by ADR-024/ADR-025 and must not be inferred from producer
claims.

### 10. The producer does not need Mneme enforcement schemas

Producer systems submit decision intent, rationale, source context, and optional
scope hints. They are not required to understand Mneme's internal rule model,
Audit tier mechanics, enforcement points, or evidence schema.

Mneme remains responsible for Audit classification, modelling, rule compilation,
rule applicability, enforcement, and evidence.

### 11. First compatibility test uses a generic architecture producer

The first producer-workflow validation should use
`sagarika29/ai-system-architect` as a reference producer.

Target flow:

```text
AI System Architect
    -> generates architecture
    -> extracts candidate architecture decisions
    -> decision.propose_batch
    -> Mneme returns proposal IDs / matches / warnings
    -> human reviews / accepts via Mneme authority surface
    -> canonical decisions created
    -> Architecture Audit evaluates accepted decisions
    -> Protected / Mneme-ready / Requires modelling / Guidance
```

No Sagarika-specific adapter or semantics belong in the Decision Index/MCP core.
The test is whether a generic producer can use the contract.

### 12. OSS and organizational boundaries remain separate

This ADR defines protocol and authority semantics, not hosted enterprise
infrastructure.

A local OSS implementation may expose local proposal ingestion and retrieval over
the Decision Index kernel.

This ADR does not require the OSS core to implement:

- organization-wide Decision Index persistence;
- cross-repository aggregation;
- multi-source organizational reconciliation;
- RBAC/SSO or multi-tenant governance;
- organization-wide policy synchronization; or
- a hosted enterprise control plane.

Those remain separate architecture/product boundaries.

### 13. D0 remains unchanged

ADR-027 does not expand D0 / issue #358.

D0 remains exclusively responsible for proving:

```text
ADR corpus
    -> OSS Decision Index kernel
    -> existing Layer 1 runtime projection
    -> identical observable behavior
```

No MCP implementation is added to D0.

---

## P0 operations

```text
decision.propose
decision.propose_batch
decision.get
decision.search
decision.applicable_to
decision.trace
```

The exact MCP schemas, transport details, error contracts, authorization model, and
persistence mechanism require implementation validation after D0.

---

## Deferred from the first MCP release

Unless separately justified, defer:

- proposal amend/update operations;
- source-system webhooks;
- automatic document watching;
- Confluence-specific writeback;
- automatic acceptance;
- exception creation;
- supersession mutations over MCP;
- evidence submission from arbitrary producers;
- trusted CI/test attestation through producer claims; and
- generic graph traversal APIs.

The P0 identity/provenance contracts should allow these to be introduced later
without changing the authority boundary.

---

## Consequences

### Positive

- Mneme can become a common decision layer for both decision-producing and
  decision-consuming tools.
- Architecture tools can contribute candidate decisions without understanding
  Mneme's enforcement internals.
- Proposal provenance and idempotency are explicit from the first producer
  contract.
- External AI systems cannot silently turn generated text into active policy.
- Sagarika, EventCatalog, migration tools, document systems, and future agents can
  converge on one producer protocol rather than bespoke core integrations.

### Negative / accepted trade-offs

- The MCP is no longer strictly read-only, increasing authorization and persistence
  requirements for its proposal path.
- Proposal state must be modelled separately from canonical decision lifecycle.
- Deduplication can identify candidates but still requires human judgment for
  semantic duplicates.
- Acceptance requires a separate Mneme-owned authority surface rather than a
  convenient generic MCP mutation.

---

## Relationship to existing ADRs

- **ADR-017:** unchanged. Search/retrieval/proposal ingestion does not determine
  deterministic enforcement.
- **ADR-019:** unchanged. Producer text never becomes a typed rule implicitly.
- **ADR-020:** unchanged. Producer scope hints do not become rule applicability
  without explicit Mneme modelling.
- **ADR-023:** extended only for the Decision MCP boundary. Its read-only consumer
  framing is superseded by this proposal-capable but non-authoritative MCP
  contract. D0 and canonical/runtime projection requirements remain unchanged.
- **ADR-024 / ADR-025:** proposal provenance must not be confused with declared or
  trusted test-execution evidence.
- **ADR-026:** Architecture Audit tier semantics remain authoritative after a
  proposal has been accepted into canonical decision governance.

---

## Validation requirement before implementation promotion

A Decision MCP implementation should not be promoted until tests prove at least:

1. proposals cannot project into active enforcement before acceptance;
2. repeated identical source/version submissions are idempotent;
3. changed source versions do not silently mutate proposal history;
4. producer scope hints do not become typed-rule applicability automatically;
5. producer text does not create typed rules automatically;
6. producer-supplied evidence cannot be represented as trusted evidence merely by
   assertion;
7. retrieval operations do not alter enforcement semantics; and
8. the Sagarika reference workflow succeeds without producer-specific core code.

---

## Related

- ADR-023 — Canonical Decision Index and Runtime Projection Boundary
- ADR-024 — Declared Test Evidence Ingestion
- ADR-025 — Trusted Test Execution Attestation
- ADR-026 — Audit Tier Semantics and Mneme Potential
- GitHub issue #358 — D0 OSS Decision Index kernel
- GitHub issue #362 — Decision Index MCP consumer + proposal-ingestion contract

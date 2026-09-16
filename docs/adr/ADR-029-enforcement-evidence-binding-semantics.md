---
id: ADR-029
title: "Enforcement Evidence Binding Semantics"
status: accepted
priority: foundational
date: 2026-09-16
scope: enforcement.evidence_binding
---

# ADR-029: Enforcement Evidence Binding Semantics

**Status:** Accepted
**Date:** 2026-09-16
**Deciders:** Theo Valmis

---

## Context

Mneme's Audit tiers (ADR-026) classify **Protected** from configured,
deterministically linkable enforcement material — an installed typed
`FORBID_LITERAL` rule, verified CI linkage, or (reserved) trusted test
evidence. Runtime observation is deliberately not required: an installed
rule is objective enforcement evidence regardless of whether a real
workflow has since tripped over it.

That leaves a gap. A control can run successfully while proving nothing
about the architectural decision it is claimed to govern:

- it may evaluate a different change or input;
- it may apply a different rule;
- it may fall outside the relevant applicability scope (ADR-020);
- it may produce an outcome unrelated to the architectural constraint;
- it may run at a point where the decision was not actually being made;
- the rule configuration in force may differ from the one the evidence
  claim assumes.

Therefore "observed" must never become a simple boolean — neither inside
the runtime nor as a future evidence channel. Evidence must be capable of
proving a chain conceptually equivalent to:

```
decision or constraint
  → enforcement control
  → rule / configuration / version
  → exact change, input, or action evaluated
  → applicability result
  → allow or reject outcome
  → provenance
```

Only evidence with sufficient binding across that chain supports the
claim that a specific decision was observed being enforced.

The runtime already emits most of the raw material for this chain.
`RuleEvaluation` (ADR-020 applicability trace) carries per-rule decision
identity, rule identity, applicability outcome, selector, and input path;
`Violation` binds decision, rule, trigger, and path; `EnforcementResult`
carries the verdict. What is missing is subject binding, configuration
binding, and control provenance — and, before any of that is implemented,
the *semantics* that say which bindings must hold for an observation to
count.

ADR-023 §16 already reserves the identity chain `decision → decision
version → rule → applicability → enforcement event` for exactly this
purpose. ADR-024 and ADR-025 established the evidence philosophy for test
evidence: exact binding, fail closed, claims distinguished from
verification, no caller-manufactured trust. This ADR applies the same
philosophy to runtime enforcement observation, and freezes the semantics
that later milestones (D1 identity hardening, P0 traceability) must
implement.

## Decision

### 1. Three evidence concepts — not three statuses, not new tiers

Mneme distinguishes three evidence concepts for a decision's protection:

1. **Configured and validated protection.** The deterministic control
   exists, is linked to the decision, and its enforcement behavior has
   been mechanically validated (`protection.validate_proposal`
   semantics). This is today's Protected substrate; runtime observation
   is NOT required for it, ever.

2. **Execution observed.** There is evidence that the control executed.

3. **Relevant enforcement observed.** There is evidence that the control
   actually evaluated the relevant subject/action under the relevant
   decision/rule, with applicability APPLIED, and produced an
   attributable allow/reject result, with provenance.

These are **independent evidence dimensions over the existing enforcement
trace**, plus a derived completeness level — not a new lifecycle enum and
not Audit tiers. A run can be execution-observed without being
relevantly-enforcement-observed; both remain true simultaneously rather
than one replacing the other.

### 2. Binding dimensions (fail closed)

"Relevant enforcement observed" requires ALL of the following bound to
the SAME evaluation. Each dimension must be positively established; any
missing or mismatched dimension keeps the evidence at or below
execution-observed, annotated, never upgraded:

| # | Dimension | Bound when |
|---|---|---|
| 1 | control / provenance | the enforcement surface is identified, with Mneme version |
| 2 | subject | the exact evaluated text/change/action is bound |
| 3 | decision | the decision being claimed is the one evaluated |
| 4 | rule | the specific rule/control under that decision is identified |
| 5 | applicability | the rule was APPLIED under ADR-020 semantics |
| 6 | outcome | an attributable allow/reject result is recorded for that rule |

Invariants:

- `APPLIED`, `EXCLUDED`, and `UNKNOWN` applicability are never collapsed
  into "control ran". An EXCLUDED evaluation is execution-observed, never
  relevantly-enforcement-observed for that rule. UNKNOWN remains the
  operational failure it is today.
- Evidence fails closed: incomplete binding never upgrades to relevant.
- Mismatched binding (different subject digest, path, selector, rule
  version, or configuration) is stale/mismatched evidence: fail closed.
- Binding is established by deterministic identifiers only. No LLM, no
  fuzzy matching, no filename similarity, no coverage inference — the
  same anti-fuzzy stance as ADR-024.

### 3. The existing trace is the carrier

Runtime enforcement observation extends the existing per-rule trace
(`RuleEvaluation`, `Violation`, `EnforcementResult`) rather than
introducing a parallel event model, a new event system, or hosted
telemetry. The applicability trace already answers dimensions 3–5 inside
a run; later work adds what it cannot yet answer (subject, configuration,
provenance).

### 4. Identity representation is deliberately deferred to D1

This ADR freezes **which bindings must hold**, not **how identifiers are
represented**. Four identity slots are named abstractly:

- **decision identity** — canonical decision id plus version
  (ADR-023 §3/§10), not merely the runtime `Decision.id`;
- **rule/control identity** — the specific rule under that decision
  (ADR-023 §10 anticipates a stable canonical `rule_id`);
- **subject/action identity** — the exact evaluated change;
- **configuration identity** — which rule configuration was in force.

The runtime's current surrogate identifiers — `rule_index` +
`rule_value`, and content digests of the policy memory — are useful
implementation probes but **MUST NOT be committed as the long-term public
evidence identity** before D1 settles canonical decision identity,
decision versioning, and stable rule identity. Committing them earlier
would bake a temporary identifier into the traceability chain. Until D1
lands, no public evidence schema is committed.

### 5. Frozen architectural invariants

- Protected / Mneme-ready / Requires modelling / Guidance remain the
  Audit tiers; no fifth tier is created.
- Observed execution is not required for deterministic protection to
  count as configured and Protected.
- An installed control merely existing is not evidence that it has
  governed a particular real action.
- A control merely executing is not evidence that it evaluated the
  relevant action.
- Evidence fails closed when the binding between decision, control,
  subject, and outcome is incomplete.
- Audit remains passive and offline by default; runtime observation
  never changes an Audit tier.
- No caller-supplied field may manufacture trusted evidence (the
  ADR-024 trust-boundary rule applies to enforcement evidence verbatim).
- ADR-024 declared test evidence and ADR-025 trusted attestation remain
  their own channels; this ADR does not touch their states or boundaries.
- No enterprise infrastructure, hosted services, or new event system.

### 6. Required scenario semantics

| Scenario | Configured/validated | Execution observed | Relevant enforcement observed |
|---|---|---|---|
| A. Rule installed; validation proves it blocks prohibited content | yes | no | no |
| B. Runtime executes; relevant rule EXCLUDED by path applicability | yes | yes | no |
| C. Runtime evaluates the decision/rule against the exact action; APPLIED; attributable allow/reject recorded | yes | yes | yes |
| D. A CI/test control ran; coverage of the claimed subject/decision unprovable | (external channel) | yes, of that control | no |
| E. Evidence binds a different SHA, path, selector, action, or rule version | yes | yes | no — stale/mismatched, fail closed |

### 7. Explicit non-goals for this decision

- No persistence, no evidence store, no decision log (P1).
- No schema, API, payload, or CLI change (P0 binding, after D1).
- No event architecture, no hosted telemetry, no new control surfaces.
- No implementation of ADR-025 trusted attestation (pilot-gated,
  unchanged).
- No new rule types, no Decision Index storage redesign, no
  proposal/authority changes.

## Consequences

### Positive

- The configured/validated vs execution-observed vs relevantly-enforced
  distinction is frozen before any carrier or storage exists, so D1 and
  P0 implement against stable semantics instead of retrofitting them.
- The "control ran against the wrong thing" case has a deterministic,
  fail-closed answer once binding lands.
- Premature identity bake-in is prevented: the evidence contract's
  identifier slots stay abstract until D1A/D1 settle canonical identity
  and versioning.

### Negative / accepted trade-offs

- No user-visible capability changes in this step; the evidence model is
  not yet consumable anywhere.
- Interim tooling must not improvise binding claims before the binding
  implementation exists; "observed" claims made by anything other than
  the bound trace are unsupported.
- The future public evidence contract is intentionally undefined here;
  ADR-023's projection-parity style gates (G1–G9) are the template for
  the later P0 acceptance criteria.

## Decision summary

Mneme distinguishes configured-and-validated protection, execution
observation, and relevant enforcement observation as independent binding
dimensions over the existing enforcement trace, with a derived,
fail-closed completeness level — not a new status enum, not Audit tiers.
Relevant enforcement observation requires control, subject, decision,
rule, applicability, and outcome to be bound to the same evaluation.
Identifier representations are deliberately deferred to D1; the runtime's
surrogate identifiers must not become the long-term evidence identity.
No persistence, schema commitment, or attestation work happens here.

## Related

- ADR-017: Enforcement Scope Is Independent of Retrieval Scope
- ADR-019: Typed Literal Rule Contract
- ADR-020: Explicit Path Applicability for Typed Rules
- ADR-023: Canonical Decision Index and Runtime Projection Boundary (§3, §10, §16)
- ADR-024: Declared Test-Evidence Ingestion for the Architecture Audit
- ADR-025: Trusted Test-Execution Attestation (Deferred)
- ADR-026: Audit Tier Semantics and Mneme Potential
- ADR-027: Decision MCP Proposal Ingestion and Authority Boundary

---
id: ADR-023
title: "Audit Tier Semantics and Mneme Potential"
status: accepted
priority: foundational
date: 2026-09-11
scope: audit.tier_semantics
---

# ADR-023: Audit Tier Semantics and Mneme Potential

**Status:** Accepted
**Date:** 2026-09-11
**Deciders:** Theo Valmis

---

## Context

The P1.2 Architecture Protection Audit (ADR-017 lineage, frozen in
`docs/plans/p1-2-architecture-audit-redesign.md`) classified each decision
into Protected / Mneme-ready / Requires modelling / Guidance from the
*shape* of the record: a decision was protection-relevant only when its
`anti_patterns` or `no X`-shaped `constraints` fields were populated. The
decision text itself was never consulted for intent.

The first real Design Partner diagnostic (sagarika29/ai-system-architect,
"PASS WITH ISSUES") demonstrated two P0 defects:

1. **Tier classification was overly dependent on record shape.**
   Byte-identical architectural decision text changed tier from Guidance
   to Requires Modelling when a structured constraint ("no empty
   descriptions") was added. The tier therefore reflected which fields
   happened to be populated rather than what the architectural decision
   means.

2. **"Identified Mneme Potential" was biased toward what the current rule
   engine can trivially encode.** A low-value single-token anti-pattern
   (`seamless`) became Mneme-ready via `FORBID_LITERAL`, while higher-value
   architectural boundaries (reject invalid output contracts, reject blank
   input, fail closed on invalid architecture output) could not become
   Mneme-ready under the same narrow rule model and were excluded from the
   metric entirely. The percentage could read as "architectural value
   Mneme can protect" while actually meaning "records compatible with
   current rule types".

The enforcement loop itself (Audit → candidate rule → Protect → Validate →
strict-mode refusal) worked correctly and must not be weakened.

## Decision

### Tier semantics

The four tiers are redefined semantically (the audited unit is the
*documented statement* — the decision text — plus its compiled
enforcement material):

- **PROTECTED** — a documented architectural decision for which Mneme has
  deterministically linked evidence that the decision is currently
  enforced: a typed `FORBID_LITERAL` rule, or external CI evidence whose
  failure is deterministically linked to detecting the forbidden token.

- **MNEME_READY** — a documented architectural decision that can be
  represented faithfully by an existing Mneme rule type, with sufficient
  scope/applicability information to activate it without inventing missing
  architectural intent: an explicit literal prohibition (single-term
  anti-pattern, single-term "no X" constraint, or an equivalently explicit
  quoted term ban stated by the decision text).

- **REQUIRES_MODELLING** — a documented architectural decision that
  appears deterministically enforceable in principle, but Mneme does not
  yet have an adequate rule type, sufficient structured scope, or another
  required representation mechanism.

- **GUIDANCE** — a documented statement that is primarily advisory,
  explanatory, aspirational, preference-based, or inherently
  judgment-dependent and should not currently be represented as
  deterministic enforcement.

### Intent classification (structure invariance)

Intent (deterministic vs guidance) is judged from the decision text:

- prescriptive language (obligation, requirement, prohibition — `must`,
  `never`, `reject`, `fail closed`, `forbidden`, `enforce`, `validate`,
  leading `No X` headlines) makes a decision protection-relevant
  regardless of which structured fields are populated;
- advisory language (`prefer`, `consider`, `should`, `can`, `where
  practical`, `judgment`, `tradeoffs`) marks the statement guidance, and
  no structured field can upgrade it;
- structured prohibition fields remain documented enforcement material
  for decisions whose text is not advisory, preserving the frozen
  Mneme-ready guardrail derivation for every pre-existing record shape.

**Invariant:** adding syntactic structure or a constraint field MUST NOT,
by itself, change a decision from Guidance to Requires Modelling or
Mneme-ready. Classification derives from the meaning/capability
relationship, not record shape. Both classifiers are conservative:
prescriptive markers never fire on advisory wording, absent markers
default to guidance, and prose prohibitions that need interpretation are
never literalized from text alone (no repository- or partner-specific
vocabulary is special-cased).

### Identified Mneme Potential

```
Identified Mneme Potential = (M + R) / PR × 100%
```

- **Numerator:** active decisions classified Mneme-ready (M) or Requires
  Modelling (R) — decisions whose documented meaning is deterministically
  enforceable in principle and not yet enforced.
- **Denominator:** PR = Protected (P) + Mneme-ready (M) + Requires
  Modelling (R) — active, protection-relevant decisions only. Guidance is
  excluded from numerator and denominator.

**Reading of the metric.** Under these definitions Identified Mneme
Potential is the **unprotected deterministic opportunity**: it is
numerically identical to the Protection Gap (`(M + R) / PR`) by
construction, and the exact complement of Current Protection
(`Potential = 100 − Current Protection`). It is NOT an independent second
metric, and user-facing output must not present Current Protection and
Identified Mneme Potential as two separate findings. The
`identified_mneme_potential_pct` field is retained in `mneme.audit/v1`
for compatibility. A future, genuinely distinct metric may express
immediately protectable coverage as `(P + M) / PR`, with
Requires-modelling reported as the product gap. No subjective
"importance" weights are introduced.

### Compatibility

`mneme.audit/v1` is unchanged: same schema string, same summary fields,
same per-decision fields. CLI, Protect behavior, enforcement/refusal
semantics, and runtime enforcement (`assess_governability`, `check_prompt`)
are unchanged. Classification remains deterministic for identical inputs.

## Consequences

- Deterministic architectural requirements with no structured fields no
  longer fall to Guidance; they surface as Requires Modelling and enter
  the protection-relevant denominator, so the audit honestly distinguishes
  "deterministic but already protected" vs "deterministic and
  representable now" vs "deterministic but requiring richer modelling" vs
  "actual guidance".
- A text-stated quoted term ban ("must not use the term `seamless`") is
  now Mneme-ready and activatable without a structured field; the
  proposed guardrail and the classification share the same derivation
  (`_proposed_literal_tokens`).
- Mneme's own audit summary changes for decisions whose text is
  prescriptive but previously shape-classified as Guidance (for example
  encoding enforcement); those records now report Requires Modelling.
  Historical release-validation records (v0.7.0) are snapshots and are
  not recomputed.
- The Mneme Potential percentage rises on corpora containing
  deterministic boundaries that today's rule model cannot yet encode;
  that is the intended honest reading, with the M/R split and Current
  Protection showing what is immediately actionable.
- Known limitations remain: intent classification is a conservative
  lexical model, not full semantic parsing; constraint-level decomposition
  (one decision → multiple constraints) is still deferred; test-evidence
  ingestion as a verified enforcement channel is the next planned P1 task
  and is intentionally out of scope here.

## Related

- ADR-017: Enforcement Scope Is Independent of Retrieval Scope
- ADR-019: Typed Literal Rule Contract
- ADR-020: Explicit Path Applicability for Typed Rules
- P1.2 redesign plan (original freeze):
  `docs/plans/p1-2-architecture-audit-redesign.md`
- Design Partner diagnostic repository (read-only fixture):
  `sagarika29/ai-system-architect`

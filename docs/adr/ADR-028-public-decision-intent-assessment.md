---
id: ADR-028
title: "Public Decision-Intent Assessment API"
status: accepted
priority: normal
date: 2026-09-13
scope: audit.public_intent_api
---

# ADR-028: Public Decision-Intent Assessment API

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** Theo Valmis

## Context

ADR-026 defines how Audit judges a decision's intent: advisory/qualified
wording is Guidance even when it contains prescriptive words (`must`,
`never`, `enforce`); unequivocal prescriptive wording is deterministic;
absent markers default to Guidance; structured fields never upgrade
Guidance by themselves (structure invariance); installed typed-rule
enforcement outranks prose intent entirely.

That derivation currently lives in two module-private lexical helpers in
`mneme.enforcer` (`_is_prescriptive_text`, `_is_advisory_text`) with the
precedence combination (`prescriptive or documented_enforcement) and not
advisory`) applied inside `_assess_protection`.

The first real external consumer — the Architecture Audit backend
(mnemehq-site), which discovers candidate decisions from ordinary Markdown
architecture documentation — needs to ask ADR-026's intent question per
statement before classification, and reached for those private helpers.
Consuming module-private names across repositories is not a supportable
production contract: the helpers carry no stability guarantee, and
exporting the two booleans raw would push ADR-026's precedence
combination out to every call site, inviting divergent second
implementations of the semantics.

## Decision

Expose one public, text-only intent primitive in `mneme.enforcer`:

```python
DecisionIntent = Literal["prescriptive", "advisory", "neutral"]

@dataclass(frozen=True)
class DecisionIntentAssessment:
    intent: DecisionIntent   # authoritative ADR-026 verdict, precedence applied

def assess_decision_intent(text: str) -> DecisionIntentAssessment
```

Contract:

- **Only the authoritative answer is exposed.** ADR-026 makes precedence
  authoritative: for unenforced prose, advisory wording wins over
  prescriptive markers. The returned `intent` therefore already carries
  the precedence decision, and the dataclass exposes exactly that one
  field. Raw lexical-marker booleans (a "contains prescriptive words"
  flag) stay private: exposing them would create a second interpretation
  surface where a consumer checks the raw marker instead of the verdict —
  recreating the shape-vs-meaning bug ADR-026 fixed. Raw marker
  information remains private unless a demonstrated consumer requirement
  appears.
- **One canonical implementation.** The public function calls the same
  private lexical helpers `assess_protection` uses. The private helpers
  remain implementation details; they are not renamed, underscore-stripped,
  or re-implemented.
- **Consumers MUST use the public Mneme semantic API rather than
  reimplementing decision-intent classification.** Semantic changes remain
  owned by Mneme Core and reach consumers through versioned Mneme
  releases; external code that re-derives intent semantics (including from
  raw lexical markers) is unsupported and will silently diverge from the
  canonical assessor.
- **Text-only by construction.** Structured fields (anti-patterns,
  constraints, typed rules) are never consulted — ADR-026 structure
  invariance forbids structure upgrading intent, and the text+structure
  combination (documented enforcement material) remains internal to
  `_assess_protection`. Quoted-term-ban guardrail derivation likewise
  stays with `assess_protection` / `propose_literal_rule`; the intent API
  reports only the text verdict. The well-known equivalence between this
  API's verdict and `assess_protection`'s intent holds only for the
  text-only fixture (no structured enforcement material, no installed
  typed rules) and is pinned by tests as such, never as a global
  invariant.
- **Pure and passive.** Deterministic output for identical input; no
  repository access, no network or LLM calls, no state mutation, no rule
  creation, no evidence inference.
- **Additive.** No change to retrieval, `ConflictDetector`, `check_prompt`
  enforcement, typed-rule semantics, path applicability, benchmark
  fixtures or results, `mneme.audit/v1`, or any existing
  `assess_protection` classification.

Consumers replace private imports:

```python
# before (unsupported)
from mneme.enforcer import _is_prescriptive_text, _is_advisory_text
# after (supported)
from mneme.enforcer import assess_decision_intent
```

## Consequences

- External consumers (the Audit backend's document-discovery channel) get
  a supported, deterministic intent boundary; the cross-repo API surface
  contains no private names.
- ADR-026 semantics remain in exactly one place. Any change to intent
  semantics lands in the markers/`_assess_protection` and flows to both
  internal and public consumers simultaneously.
- The primitive is intentionally narrower than `assess_protection`: it
  answers the text question only. Callers needing tiers, guardrails, or
  evidence continue to use `assess_protection` and `propose_literal_rule`.
- Nothing here licenses discovery or auto-governance: Mneme remains
  governance-first (Layer 1 freeze discipline); this API exposes intent
  assessment of text the caller already has, it does not discover,
  generate, or enforce anything.

## Related

- ADR-026: Audit Tier Semantics and Mneme Potential (the semantics this
  API exposes; no semantic amendment)
- ADR-017: Enforcement Scope Is Independent of Retrieval Scope
- ADR-019: Typed Literal Rule Contract
- ADR-027: Decision MCP Proposal Ingestion and Authority Boundary
  (adjacent external-boundary decision; numbering continuity)
- Layer 1 freeze: `docs/architecture/layer1-freeze-e73ff7d.md`

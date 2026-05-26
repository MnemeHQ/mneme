---
id: ADR-014
title: "Harness-Complementary Positioning Vocabulary"
status: accepted
priority: normal
date: 2026-05-16
scope: positioning.harness_vocab
---

# ADR-014: Harness-Complementary Positioning Vocabulary

> Note: this ADR was originally numbered ADR-011 and was renumbered to ADR-014
> during the 2026-05-26 legacy-ADR normalization pass (see PR following
> [issue #139](https://github.com/TheoV823/mneme/issues/139)). The original
> ADR-011 number now belongs to "Knowledge-graph content architecture";
> this ADR's content is unchanged except for cross-references to the renumbered
> external-platform-presence ADR (now ADR-013).

**Status:** Accepted
**Date:** 2026-05-16
**Deciders:** Theo Valmis

---

## Context

Wave 1 of the harness-engineering ontology rollout established the runtime stack
as the default frame for talking about where Mneme sits in an autonomous agent
system. Three surfaces now carry that frame as canonical content:

- `site/insights/harness-engineering-still-needs-governance/` — the hub article
  arguing that harness engineering and architectural governance are distinct
  layers that run side by side.
- `site/concepts/governance-infrastructure/` — the five-layer runtime stack
  (Models → Harnesses → Execution systems → Governance infrastructure →
  Verification / enforcement), with governance highlighted as a separate layer.
- `site/concepts/governance-propagation/` — the execution-surfaces enumeration
  (source code, branch names, commit messages, PR titles, tags, CI config,
  deployment artifacts, generated configuration, agent-produced documentation),
  arguing governance must propagate across every surface the agent writes to,
  not only source code.

The framing exists at the article and concept-page level, but the vocabulary is
not yet codified as a positioning rule. Without a written decision, future
contributors can drift the framing back toward "memory," "RAG," "context layer,"
or "coding assistant tooling" without violating any explicit constraint.

This ADR is the vocabulary lock. It is additive — it does not supersede ADR-001,
it constrains the language used to express ADR-001's positioning.

---

## Decision

### 1. Canonical layer names (the runtime stack)

The runtime stack is the default abstraction for any Mneme surface that
positions the product in an autonomous agent system. The canonical layer names
and their order are:

1. **Models** — candidate output, generation, probability over tokens.
2. **Harnesses** — tool orchestration, retries, planning loops, context
   lifecycle.
3. **Execution systems** — long-running loops, sessions, memory, continuity
   infrastructure.
4. **Governance infrastructure** — decision graph, precedence, pre-generation
   enforcement, propagation across surfaces. **This is Mneme's layer.**
5. **Verification / enforcement** — tests, builds, deploy-time checks,
   deterministic verdicts.

These names must be used verbatim when surfacing the stack. Reordering, renaming,
or collapsing layers is non-compliant.

### 2. Harness-complementary framing

Mneme is positioned as **complementary to harnesses, not as a harness, a memory
layer, or a context-management tool.** The canonical phrasing is some variant
of:

> Harnesses coordinate execution. Mneme enforces architectural intent. They
> run side by side.

Adapt wording to fit the surrounding voice; do not copy the sentence verbatim
across pages. Integration pages must read as "we work alongside this harness,"
not "we replace this tool's memory."

### 3. Prohibitions

The following positioning frames are explicitly non-compliant with this ADR
and must not appear in new content surfaces (insights articles, concept pages,
integration pages, marketing copy, external platform copy):

- Positioning Mneme as **memory** — "AI memory," "persistent memory,"
  "memory layer," "memory store," or "memory for agents." See ADR-001 §
  "Against Generic Memory Tools." If memory must be discussed, frame it as
  *structured architectural decision memory with enforcement semantics*.
- Positioning Mneme as a **RAG alternative** or **RAG replacement** — Mneme
  does not compete with retrieval-augmented generation in the general sense.
  It enforces pre-generation constraints; that is a different layer.
- Positioning Mneme as **prompt engineering** or a **prompt-enhancement
  layer** — pre-generation enforcement is not prompt tuning.
- Positioning Mneme as **coding assistant tooling** — it is not a feature of
  Claude Code, Cursor, Copilot, or any other harness; it is a separate layer
  every harness can query.
- Positioning Mneme as an **agent context layer** — context injection is one
  surface Mneme operates on, not what Mneme is.

### 4. Compliance rule

Any new content surface that mentions an agent runtime, harness, model, or
generation step must use the runtime-stack vocabulary as the default frame.
Any deviation must be explicitly justified inline (for example, when comparing
Mneme to a specific memory product, the surface may use that product's
vocabulary to draw the contrast, provided the conclusion returns to the
runtime-stack frame).

The hub article at `/insights/harness-engineering-still-needs-governance/`
and the runtime-stack section on `/concepts/governance-infrastructure/` are
the canonical references. When in doubt, copy phrasing from there.

---

## Consequences

- Existing content that predates Wave 1 may not yet use the runtime-stack
  frame. This ADR is forward-looking; retrofits land as separate PRs rather
  than as part of this decision.
- The `/architecture/` and `/works-with/` surfaces, refreshed in Wave 2,
  are bound by this ADR as soon as it lands.
- Awesome-list and directory submissions (ADR-013, external platform
  presence) inherit the prohibitions in §3 implicitly — the existing copy
  variants in ADR-013 already conform, but future variants must.

---

## Related

- **ADR-001** — Mneme HQ Positioning and Messaging Rules. This ADR is the
  vocabulary lock that operationalises ADR-001 for the post-Wave-1 surface
  set; it does not supersede ADR-001.
- **ADR-004** — Brand Name (Mneme HQ). Brand-level naming is governed there;
  this ADR governs how the product is *positioned*, not what it is *called*.
- **ADR-006** — Insights Article SEO Requirements. New insights articles
  must satisfy ADR-006 *and* this ADR. The two are independent gates.
- **ADR-013 (external platform presence)** — locks external copy variants.
  New variants must conform to the prohibitions in §3 above.
- `docs/plans/2026-05-16-wave-2-ontology-followups.md` — the Wave 2 plan
  this ADR completes.
- `site/insights/harness-engineering-still-needs-governance/` — canonical
  reference for runtime-stack phrasing.

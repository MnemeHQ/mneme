# ADR-011: Knowledge-graph content architecture for /concepts/ and /insights/

**Status:** Accepted
**Date:** 2026-05-15
**Deciders:** Theo Valmis

---

## Context

The `/concepts/` and `/insights/` sections of mnemehq.com are the public surface
of Mneme's conceptual worldview. As both sections have grown, two structural
risks have emerged:

1. **Drift toward "blog archive" semantics.** Without an explicit content
   architecture, every new page is just another node added to a flat list.
   That weakens semantic clustering, weakens AI Overview extraction, and
   gradually erodes the conceptual-authority positioning that ADR-001
   established.
2. **Asymmetric value of cross-links.** A concept page that points to
   five insight essays is signalling something different than an essay that
   points to five concept pages. Treating both directions the same flattens
   the meaning out of the graph.

The decisions in this ADR codify the content architecture that emerged through
2026-05-15. They make the structure explicit so it survives future content
additions instead of needing to be re-derived each time.

---

## Decisions

### 1. `/concepts/` is the canonical-definitions namespace; `/insights/` is the applied-arguments namespace

The two paths carry different roles, and content must respect the boundary:

- **`/concepts/<slug>/`** — canonical definitions, primitives, properties,
  and outcomes. Abstraction-first. Each page is a stable reference.
  Tier-tagged (primitive / property / outcome / failure / context).
- **`/insights/<slug>/`** — applied arguments and ecosystem consequences.
  Each post takes one or more concepts and develops what they imply
  operationally. Insights point back to concepts; they do not redefine
  them.

Content that would blur the boundary (a "concept page" that is really an
opinion essay, or an "insight" that is really a definitional stub) is rejected
or recategorized.

### 2. Cross-references between the two namespaces are asymmetric by design

On a concept page, the cross-reference panel is **Related operational
essays** — points only to `/insights/*`.

On an insight page, the cross-reference panel is **Related governance
concepts** — points only to `/concepts/*`.

The asymmetry is the point. Each direction frames the destination
differently: an essay deepens a concept; a concept anchors an essay. The
component (`.related-panel`) is shared; the label and target set are
direction-specific.

### 3. The `.related-panel` is the canonical cross-link component

Cross-references are always rendered as the rich card list — title plus
one-line description per item, accent-arrow hover, list-style group — not
as a bare hyperlink list. The 1-line description is required.

Bare `<h2 id="related-reading">` lists with `<ul>` of `<a>` tags are
deprecated; new content uses `.related-panel`. Existing pages may retain
the old pattern until migrated.

The same component renders identically on demos, compare pages, and the
benchmark page, but with destination always being `/concepts/*` from those
surfaces.

### 4. The concept layer has three tiers plus a failure rail

Concepts are organized into:

- **Outcomes** — what governance achieves (architectural-governance,
  governance-infrastructure)
- **Properties** — what governance does (governance-before-generation,
  deterministic-enforcement, governance-propagation, multi-agent-continuity,
  enforcement-provenance)
- **Primitives** — what governance is built from (architectural-compiler,
  verification-contracts, precedence-semantics)
- **Failure rail** — what accumulates without governance (ai-agent-drift,
  architectural-drift)
- **Context** (adjacent) — surrounding terms (ai-native-sdlc,
  agentic-development, decision-continuity)

Every concept page declares its tier in the concept-graph adjacency table
(private, per ADR-002). The `/concepts/` hub diagram renders the three tiers
plus failure rail explicitly.

### 5. Authority scoring (private; runs locally)

The graph health analyzer (`scripts/graph_metrics.py`) emits a weighted
inbound score per concept. Weights:

| Source category | Weight | Rationale |
|---|---:|---|
| benchmark | 5 | Empirical grounding |
| demo | 3 | Proves the concept exists in code |
| use-case | 3 | Proves the concept solves a real problem |
| integration | 3 | Proves the concept is enforceable |
| compare | 2 | Competitive positioning |
| concept | 2 | Semantic mesh density |
| works-with | 2 | Distribution surface |
| insight | 1 | Abundant; counted but lowest |

The score is internal telemetry. Public pages do not display authority scores.
Weights may evolve; changes require updating this ADR.

### 6. Knowledge-graph governance artifacts live in the private repo

Per ADR-002, the canonical adjacency table
(`concepts-graph.json`), the coverage matrix, and the graph-health baseline
reports are Category 3 artifacts. They live in
`mneme-growth-ops` (or equivalent private store), not the public repo. Only
the analyzer script and the rendered HTML live publicly.

---

## Consequences

**Positive:**

- New concept and insight pages have a clear template to inherit. The
  authoring decision is "which namespace?" first, not "how should this look?".
- Cross-references reinforce the worldview every time a page is read.
- The graph is measurable. Drift in the graph (orphan concepts, falling
  authority scores, deteriorating mesh density) becomes a visible signal,
  not a vague concern.
- Phase 2 of the knowledge-graph roadmap has a concrete contract to
  implement (the multi-category metadata block extends `.related-panel`).

**Negative / accepted trade-offs:**

- The asymmetric cross-reference pattern is more discipline than a flat
  "related reading" list. Authors must remember which direction they are
  in.
- The concept-tier taxonomy may need extension as new categories emerge
  (e.g., a tier for "governance economics"). This ADR will be revised then.
- Two parallel ADR-010 files currently exist in the repo (collision pre-
  existing). This ADR does not resolve that; flagged as a separate cleanup.

---

## How this is enforced

1. **`scripts/seo_check.py`** already validates per-page metadata and
   structure. Extended to recognize `.related-panel` as a valid cross-link
   pattern.
2. **`scripts/graph_metrics.py`** measures inbound/outbound counts,
   orphan flags, and authority scores. Re-run after each phase of the
   roadmap; drift surfaces as a metric delta.
3. **Manual review** at PR time — any new concept or insight page must
   include the appropriate `.related-panel` and respect the namespace
   boundary. The PR description should cite this ADR if the new page
   establishes new graph edges.

---

## Related

- ADR-001 — Positioning and messaging. This ADR is the structural
  implementation of the conceptual positioning that ADR-001 established.
- ADR-002 — Repo boundary and internal tooling. Determines which graph
  artifacts are public vs private.
- ADR-003 — Site publishing guidelines.
- ADR-006 — Insights article SEO and schema requirements. Applies in
  addition to this ADR for `/insights/*` pages.
- ADR-012 (next) — Conceptual-authority discipline. Codifies the
  glossary-resistance and naming rules that protect concept-page quality.

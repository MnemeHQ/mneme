# ADR-012: Conceptual-authority discipline for /concepts/, /insights/, and recurring frames

**Status:** Accepted
**Date:** 2026-05-15
**Deciders:** Theo Valmis

---

## Context

ADR-001 established Mneme's positioning as the architectural-governance layer
for AI-assisted development. ADR-011 codified the content architecture that
implements that positioning structurally. This ADR codifies the *editorial
discipline* that protects the moat — the rules that keep concept pages from
drifting into glossary stubs, keep recurring frames coherent, and keep
diagrams behaving as infrastructure evidence rather than ornament.

These rules emerged from the 2026-05-15 knowledge-graph buildout. They are
durable. Without explicit codification, future content will pull toward
generic SEO patterns (short definitional pages, keyword expansion, marketing
diagrams) that have measurably weaker compounding effects than the existing
abstraction-first treatment.

---

## Decisions

### 1. No glossary behavior in `/concepts/`

The concept of a "glossary" — short definitional entries — is structurally
incompatible with conceptual-authority positioning. Every concept page must
pass these tests:

- **Length floor.** Body content ≥ 1000 words. A concept that cannot sustain
  1000 words is either not a real concept or needs merging with an adjacent
  one.
- **Abstraction-first naming.** No concept titled after a feature, a tool,
  or a product surface. `MnemeCheck CLI`, `Hook Configuration`,
  `Cursor Rules Format` do not belong in `/concepts/`. They may belong in
  `/docs/` or `/integrations/`.
- **Argument density.** Each concept page must contain at least one explicit
  contrast claim ("X is not Y, because…"), not just a definition. The
  contrast is what produces semantic clustering with the rest of the graph.
- **No SEO-stub pages.** Topical expansion that would dilute conceptual
  authority is rejected even if it would rank. Concept pages do not exist
  to harvest queries; they exist to anchor entity associations.

A page that fails any of these tests is rejected, deepened, or merged.

### 2. The "X is not governance" frame is a recurring series, not a one-off

The series currently comprises four posts: memory · prompts · review ·
observability. The framing is deliberate: each post takes a category that
the AI tooling market commonly conflates with governance and explains why
the conflation is structural. The series produces semantic reinforcement
that no individual post could.

Rules for the series:

- Every entry must be a `/insights/X-is-not-governance/`-shaped post (full
  trilogy template — lede, contrast block, pull-quotes, FAQ JSON-LD,
  `.related-panel` linking to the relevant concept primitives).
- Every new entry must explicitly cross-link to the existing three (or
  however many) so the series compounds.
- Candidate entries for future expansion: `Tracing is not governance`,
  `Linting is not governance`, `Documentation is not governance`. Not all
  candidates will ship; the bar is whether the conflation is real and
  structural, not whether it would rank.
- The series is positioned in the insights index under the `Thought
  Leadership` tag and listed adjacently in `CollectionPage.hasPart`.

### 3. Diagrams are infrastructure evidence, not decoration

Mneme diagrams behave as part of the conceptual specification. Rules:

- **Canonical primitives are reused, not redrawn.** Four diagrams are
  designated canonical: governance propagation, enforcement checkpoints,
  provenance chain, architectural drift cascade. New pages that need these
  topics embed the existing primitive; they do not introduce variants.
  The roadmap (private) defines which primitive lives on which concept
  page.
- **Visual conventions.** All diagrams share colour tokens
  (`--accent` for active, `--teal` for secondary, `--border2` for neutral),
  glyph ordering (top = outcomes, bottom = primitives), and label
  typography (DM Mono for metadata, Inter for nodes). Deviation requires
  updating this ADR.
- **Diagrams must parse as valid SVG and be mobile-readable.** Inline SVG
  is the current pattern; assets in `/assets/diagrams/` may be introduced
  in Phase 3 of the roadmap if reuse needs warrant it.
- **No ornamental illustrations.** A diagram exists to make a structural
  claim legible. If the claim can be made better in prose, the prose wins
  and the diagram is removed.

### 4. The four flagship concept pages carry extra weight

The four highest-authority concepts (as measured by
`scripts/graph_metrics.py`, weighted) are designated **flagship canonical
references**:

- Governance Infrastructure
- Verification Contracts
- Governance Before Generation
- Architectural Governance

Flagships have stricter rules:

- ≥ 4 internal links to other concepts
- ≥ 3 internal links to insights
- ≥ 2 internal links to demos
- ≥ 1 internal link to a benchmark (or to a benchmark scenario citation
  if the benchmark page hasn't published the relevant assertion yet)
- ≥ 2 diagrams (at least one canonical primitive)
- Full `TechArticle` + `DefinedTerm` JSON-LD
- ≥ 1500 words

Flagships are the pages other pages cite. They are updated continuously,
not snapshotted. Their authority scores set the upper bound for the rest
of the graph.

### 5. Concept ↔ benchmark reinforcement is a first-class requirement

Every concept that can be empirically measured must cite the benchmark
assertion that grounds it. Where the benchmark data does not yet exist,
the concept page cites the **benchmark scenario** that would produce it,
so the citation slot is visible even before numbers publish.

This rule applies most strictly to flagships (per decision 4) but extends
to any concept where benchmark grounding is possible. It exists because
conceptual authority without empirical grounding is rhetoric; the
benchmark bridge is what differentiates Mneme from adjacent conceptual
work.

### 6. The conceptual worldview is recurring and consistent

Across all `/concepts/`, `/insights/`, and `/architecture/` pages,
Mneme uses a stable vocabulary and recurring contrast frames. Authors
do not invent new terms when an existing concept covers the territory.
Specifically:

- Use "decision corpus", not "memory store" or "rules file".
- Use "verification contract", not "test case" or "assertion".
- Use "governance propagation", not "rule sync" or "config distribution".
- Use "drift", not "regression" or "tech debt" (in the AI-coding sense).
- Use "enforcement", not "validation" or "checking" (when speaking of
  the governance layer).

Synonym creep weakens entity reinforcement. New terminology requires
explicit consideration and, if accepted, an ADR amendment.

---

## Consequences

**Positive:**

- Concept pages remain durable references rather than rotating content.
  Citations and AI-Overview extraction stabilize over time.
- Recurring frames (the "X is not governance" series; the contrast
  primitives in the body of each concept page) compound semantically.
- Flagships become the natural targets for inbound links from the rest
  of the ecosystem — investor decks, conference talks, external citations,
  community posts.
- Concept-to-benchmark grounding is a defensible authority signal that
  conceptual-only competitors cannot match without doing the engineering
  work.

**Negative / accepted trade-offs:**

- Some topics that would make decent SEO targets (e.g., "What is a hook?",
  "Cursor rules format") will not be published as concept pages. They
  belong in `/docs/` or `/integrations/`.
- The terminology lock-in (decision 6) requires editorial discipline at
  authoring time. Marketing-driven term creep is the most common failure
  mode for this kind of discipline; the safeguard is PR review citing
  this ADR.
- Flagship pages require continuous maintenance. They are not "ship and
  forget."

---

## How this is enforced

1. **`scripts/seo_check.py`** — already validates word count and h2 structure.
   Concept pages flagged below the 1000-word floor surface as warnings.
2. **`scripts/graph_metrics.py`** — surfaces the flagship pages as the
   top-5 by authority. Drift in the ranking is a flag.
3. **PR review** — new concept pages must cite this ADR if introducing
   new terminology or breaking the abstraction-first naming rule.
4. **Annual review** — the canonical-primitive set and the recurring frames
   are reviewed annually. Additions or removals require an ADR amendment.

---

## Related

- ADR-001 — Positioning and messaging. This ADR is the editorial discipline
  that protects the positioning.
- ADR-002 — Repo boundary and internal tooling. Determines that the
  weighted-authority telemetry is private.
- ADR-006 — Insights article SEO and schema requirements. Applies in
  addition to the rules here.
- ADR-011 — Knowledge-graph content architecture. The structural
  counterpart to this ADR's editorial discipline.

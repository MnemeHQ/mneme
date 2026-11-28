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
>
> Amended 2026-09-25 (positioning-only): aligned with ADR-001's category change
> to "the decision and control layer for agentic software development." The
> five runtime-stack layer names are unchanged and still used verbatim; layer 4
> now describes Mneme as the decision and control layer that provides governance
> infrastructure, rather than naming governance as Mneme's identity. The
> harness-complementary framing and every §3 prohibition are unchanged.
>
> Amended 2026-11-26 (positioning-only): admits **Decision Engineering** as
> discipline vocabulary (§5): the discipline of discovering, formalising,
> distributing, enforcing and verifying the engineering decisions that AI
> coding agents must follow in agentic software development. It names an
> engineering practice, not Mneme's category and not a runtime-stack layer.
> Engineering decision governance is named as the resulting capability, with
> its semantics from ADR-031 unchanged. The five layer names, the
> harness-complementary framing and every §3 prohibition are unchanged, and no
> runtime behaviour, architecture, freeze or integration-status change is
> made. This extends the 2026-10-12 site decision, which adopted only
> "engineering decision governance" and left Decision Engineering unlocked
> (mnemehq-site
> `docs/site/scope-briefs/2026-10-07-business-type-and-decision-governance.md`).

**Status:** Accepted
**Date:** 2026-05-16
**Amended:** 2026-09-25 · 2026-11-26
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
4. **Governance infrastructure** — decision graph, applicability, precedence,
   pre-generation enforcement, propagation across surfaces. **Mneme operates
   here as the decision and control layer for agentic software development:**
   it carries approved engineering decisions across harnesses and execution
   systems, determines which apply to a change, and enforces what can be
   enforced deterministically. "Governance infrastructure" is the layer's
   canonical name and the capability it delivers; it is not Mneme's category
   name (ADR-001).
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

A category-led variant is also canonical:

> Harnesses coordinate execution. Mneme is the decision and control layer
> that carries the same approved decisions across them.

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
  surface Mneme operates on, not what Mneme is. Saying Mneme turns decisions
  *into* agent context (alongside deterministic enforcement and decision-linked
  results) is permitted; naming context as Mneme's category is not.

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

### 5. Discipline vocabulary: Decision Engineering (amendment 2026-11-26)

This section admits one discipline term. It is positioning vocabulary only.
The Decision Engineering lifecycle and comparisons between engineering
disciplines describe engineering practices, not runtime architecture. They do
not replace, rename, reorder or extend the canonical runtime stack defined in
section 1.

#### 5.1 Canonical definition

Use this sentence verbatim wherever the term is defined:

> Decision Engineering is the discipline of discovering, formalising,
> distributing, enforcing and verifying the engineering decisions that AI
> coding agents must follow in agentic software development.

#### 5.2 Disambiguation

The disambiguation is a separate statement. It is required wherever the term
is defined, and must not be merged into the definition sentence.

"Decision engineering" already has established meanings, and Mneme did not
coin the term:

- **Decision intelligence.** Decision-intelligence research and platforms
  (for example Gartner's decision-intelligence research and the literature
  associated with Lorien Pratt) use "decision engineering" for engineering how
  business decisions are made, and that work also covers operationalising
  those decisions, not only making them.
- **Technical decision-making.** *Decision Engineering* by Grygoriy Gonchar
  (Manning, early access) is a method for engineers making architecture and
  technology choices. It covers documenting decisions and following through
  on their implementation, and it addresses AI, including AI-assisted
  development.
- **History.** Decision analysis uses the term for structured decision
  making, and IBM research used "architectural decision engineering" for
  collaborative architectural decision making (ADkwik, SEKE 2007).

Because both of the first two meanings already include putting decisions into
practice, the distinction is not "they make decisions, Mneme makes them hold".
Mneme's sense is distinguished by its object and mechanism: the
**machine-actionable representation, effective resolution, enforcement and
verification of engineering decisions across autonomous execution
environments** (AI coding agents, their harnesses and CI). Surfaces that
define the term must name decision intelligence and the Manning book, and
must not state or imply that Mneme coined, invented or owns the term.

#### 5.3 Stages

The discipline has five stages:

1. **Discover** — find the engineering decisions that already govern a
   system, explicit or implicit.
2. **Formalise** — state each decision with its scope, applicability and
   lifecycle, and derive deterministic rules where the decision allows it.
3. **Distribute** — deliver the decisions that apply to a change to the
   agents and tools making it.
4. **Enforce** — evaluate changes against those decisions at supported
   control points.
5. **Verify** — establish, with evidence, that a change conforms to the
   applicable decisions.

The stages are iterative, not a one-way pipeline: enforcement and
verification findings feed back into discovery and formalisation, and a
decision can be revised or superseded and pass through the stages again.

**Verify means conformance, not correctness or attestation.** Verify checks
that a change conforms to the decisions that apply to it. It does not judge
whether a decision is correct, and it is not trusted execution attestation:
ADR-025 (trusted test execution attestation) is Proposed, not accepted.

**Authority is cross-cutting, not a sixth stage.** Acceptance (a human
accepting or rejecting a proposed decision), precedence, supersession and
effective resolution (which decisions govern a given context) apply across
all five stages. Do not present authority as a separate stage. Describing
it does not imply that authenticated organisational authority exists: Mneme
records identities as claims, not authenticated principals, and RBAC, SSO,
directory and enterprise-policy authority sit outside DG1 (ADR-031 §6).

Other stage lists (for example an eight-stage lifecycle that adds authority,
evidence and evolution as separate stages) are not canonical.

#### 5.4 Roles of the terms

| Term | Role |
|---|---|
| **Decision Engineering** | The discipline (this section). |
| **Engineering Decision Governance** | The resulting capability: decisions that govern deterministically and explainably. Its semantics are ADR-031 (DG1), unchanged by this amendment. Completing the stages does not by itself guarantee it. |
| **The decision and control layer for agentic software development** | Mneme's commercial category, per ADR-001. Unchanged. |
| **Architectural Drift Prevention** | The first use case (ADR-001, ADR-013). |
| **Mneme** | Implements supported aspects of the discipline, starting with architectural decisions (§5.6). |

Write that Decision Engineering produces engineering decision governance,
never the reverse, and never treat the two terms as synonyms. Engineering
decision governance keeps the meaning ADR-031 gives decision governance:
effective resolution, governance change and evidence identity.

#### 5.5 Position among disciplines

Decision Engineering is a peer of prompt engineering, context engineering and
harness engineering in agentic software development. Canonical contrast,
adapted to the surrounding voice:

> Prompt engineering shapes what an agent is asked. Context engineering
> shapes what it knows. Decision Engineering shapes which engineering
> decisions it must respect, and checks that it did.

The disciplines are peers, not a sequence in which Decision Engineering
replaces the others, and the discipline list is not the runtime stack: do
not render Decision Engineering as a sixth §1 layer, or map the disciplines
onto the §1 layers. Standing alongside prompt engineering does not make Mneme
prompt engineering: the §3 prohibition stands.

#### 5.6 Mneme's current support, qualified

Product facts below were checked against release `v0.11.0` and `main` at
`39ab6a59` (2026-11-28). The CHANGELOG and the cited ADRs remain the source
of truth; this table does not upgrade any capability claim, and surfaces
must follow ADR-001 Claim Levels for each stage.

| Stage | Shipped | Qualifications |
|---|---|---|
| Discover | Architecture Audit discovers *candidate* decisions from Markdown architecture docs; `assess_decision_intent` classifies statement intent (ADR-028, 0.8.0) | Candidate decisions, not reconstructed decisions. `mneme research open-architecture` (0.10.0) is research-only and unvalidated. |
| Formalise | `mneme adr import`; typed rules (`FORBID_LITERAL`, ADR-019, with ADR-020 path applicability; `FORBID_NUMERIC_ABOVE`, ADR-034, 0.11.0); canonical Decision Index persistence (ADR-030, 0.10.0); canonical decision applicability under `mneme.decision-index/v2` (DG1B1, 0.11.0) | The Decision Index persists decisions; it does not formalise arbitrary intent. |
| Distribute | Decision MCP (`mneme decision-mcp`, 0.9.0: get, search, applicable_to, trace, non-authoritative proposals) and pre-generation context on supported integrations | MCP retrieval relevance is not authoritative resolution (ADR-031 §1). |
| Enforce | Hooks on supported integrations, `mneme check` and CI gates, for deterministic typed rules | `FORBID_NUMERIC_ABOVE` is supported rule evaluation through the whole-file `mneme check --source-file` audit; it is not equivalent to `FORBID_LITERAL` edit-gate enforcement, and other incomplete inputs report it unevaluated. A Claude Code pre-write check for a `Write` of a new `.py` file (G2-1, `--proposed-new-file`) is implemented in 0.11.0, but it has not passed independent validation and no enforcement claim is made for it. |
| Verify | CI re-check at merge; canonical `rule_id` and `decision_version_id` in `mneme check --json` (DG1E, 0.11.0); declared test evidence (ADR-024, 0.8.0) | Conformance only. Trusted attestation (ADR-025) is Proposed. |
| Authority (cross-cutting) | Human acceptance of proposed decisions (`mneme decision accept / reject`, ADR-027, 0.9.0); precedence by priority and explicit `supersedes`, with ADR `date` no longer precedence authority (DG1P, 0.11.0); DG1 library (0.11.0): effective-decision resolver, governance change resolution, canonical applicability, canonical evidence identity | Recorded identities are claims, not authenticated. The `mneme check --applicability-preview` output is non-authoritative. Enforcement consumers have not converged on DG1: in 0.11.0 nothing in retrieval or enforcement consumes the resolver, and on `main` only three reporting consumers do (DG1F-C3a, unreleased). Waivers (DG1B2a) are merged on `main` but unreleased, as records and explanations only; no enforcement consumer acts on them, and waiver-aware enforcement (DG1B2b) is deferred. |

#### 5.7 Rules of use

- **Where it may appear.** Thesis and concept pages, and external thought
  leadership (articles, talks, LinkedIn), always under the same
  disambiguation (§5.2) and positioning restrictions as this section.
- **Where it may not appear.** Never on the homepage, and never as Mneme's
  category, tagline or hero term. ADR-001's category ("the decision and
  control layer for agentic software development") is unchanged; any move of
  the term onto the homepage or into the category needs an ADR-001
  amendment first.
- Mneme supports or applies the discipline. Do not write that Mneme "is"
  Decision Engineering, "invented" or "coined" it, or is "the Decision
  Engineering platform".
- Capability claims about each stage follow ADR-001 Claim Levels and §5.6:
  name what ships for that stage, and mark planned or research-only work as
  such.
- Not admitted by this amendment as defined terms: "Architectural Decision
  Engineering" (may be cited as the 2007 research usage only),
  "Architecture-Driven Development", "decision enforcement" and "decision
  evidence" as named disciplines. Decision governance, or engineering
  decision governance, as a commercial or product category is rejected
  (ADR-001).

#### 5.8 What this amendment does not change

This amendment introduces no runtime behaviour, architecture, Layer 1
freeze, enforcement, retrieval, schema or integration-status change. The §1
layer names and order, the §2 framing, the §3 prohibitions, the §4
compliance rule, ADR-013 and ADR-031 are unchanged.

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
- Decision Engineering (§5) may appear on thesis and concept pages and in
  external thought leadership with its canonical definition and its
  disambiguation, never on the homepage or as the category. Site rules for
  where and how it appears live in mnemehq-site `PUBLISHING.md` (ADR-016),
  which must cite this amendment. The §5.6 support table is a dated
  snapshot; when a cited capability changes status, update the table or
  defer to the CHANGELOG.

---

## Related

- **ADR-001** — Mneme HQ Positioning and Messaging Rules. This ADR is the
  vocabulary lock that operationalises ADR-001 for the post-Wave-1 surface
  set; it does not supersede ADR-001. As amended 2026-09-25, ADR-001 defines
  the category (decision and control layer); this ADR defines where that
  layer sits in the runtime stack.
- **ADR-004** — Brand Name (Mneme HQ). Brand-level naming is governed there;
  this ADR governs how the product is *positioned*, not what it is *called*.
- **ADR-006** — Insights Article SEO Requirements. New insights articles
  must satisfy ADR-006 *and* this ADR. The two are independent gates.
- **ADR-013 (external platform presence)** — locks external copy variants.
  New variants must conform to the prohibitions in §3 above.
- **ADR-031** — Decision Governance Semantics (DG1). §5 names engineering
  decision governance as the capability that Decision Engineering produces
  and takes its semantics from ADR-031 unchanged.
- **ADR-025** — Trusted Test Execution Attestation (Proposed). §5 keeps
  Verify to conformance and makes no attestation claim.
- `docs/plans/2026-05-16-wave-2-ontology-followups.md` — the Wave 2 plan
  this ADR completes.
- `site/insights/harness-engineering-still-needs-governance/` — canonical
  reference for runtime-stack phrasing.

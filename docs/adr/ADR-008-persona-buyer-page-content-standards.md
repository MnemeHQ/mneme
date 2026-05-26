---
id: ADR-008
title: "Persona / Buyer-Page Content Standards"
status: accepted
priority: normal
date: 2026-05-10
scope: site.persona_pages
---

# ADR-008: Persona / Buyer-Page Content Standards

**Status:** Accepted
**Date:** 2026-05-10
**Deciders:** Theo Valmis

---

## Context

The site has a `/for/<role>/` family of persona-targeted landing pages:

- `/for/cto/` — CTOs and VP Engineering
- `/for/platform/` — Platform and DevEx teams
- `/for/principal-engineer/` — Staff and Principal Engineers

Initial drafts of `/for/cto/` mixed audiences: it spoke to senior leadership at the top
(throughput vs. review capacity, architectural debt) but switched to engineering primitives
mid-page — YAML examples, `mneme check --mode strict` invocations, `.cursor/rules/mneme.mdc`
file paths, and a five-step technical pipeline that an SLT reader has no reason to engage
with.

The CTAs were also wrong for the audience. The CTO page led with "View on GitHub" — a
hand-on-keyboard CTA in a hero that targets a hand-on-budget reader.

This ADR establishes content standards for `/for/<role>/` pages and routes audiences to
the right primitives.

---

## Decisions

### 1. Audience-appropriate primitives

**CTO / VP Engineering pages** (`/for/cto/`)

- No code blocks, no YAML, no command-line invocations, no per-tool config filenames
  (`.cursor/rules/`, `CLAUDE.md`, etc.).
- Frame in: review capacity, architectural debt, headcount efficiency, vendor consolidation,
  audit posture, throughput-without-debt, time-to-decision-continuity.
- A "Business Outcomes" section with explicit ROI framing is required.

**Platform / DevEx pages** (`/for/platform/`)

- May include configuration patterns (precedence resolution, three-tier rollout, scope syntax),
  and one or two short YAML or rules-file snippets where they clarify the rollout shape.
- Frame in: tool consolidation, multi-agent surface coverage, governance-as-code, rollout
  staging, override governance.

**Staff / Principal pages** (`/for/principal-engineer/`)

- May include code-level primitives (hook intercept points, decision-record schema fields,
  CI gate behaviour). The audience writes and reviews this layer.
- Frame in: decision-once-enforced-forever, repeated-review-comment elimination, override
  observability, structural integrity across sessions.

### 2. CTA discipline by role

CTAs route to the next sensible step for that audience.

| Role page | Hero primary | Hero ghost | Footer primary | Footer ghost |
|---|---|---|---|---|
| CTO | `Talk to the founder` → `/contact/` | `See use cases` → `/use-cases/` | `Talk to the founder` → `/contact/` | `See the roadmap` → `/roadmap/` |
| Platform | `View on GitHub` (acceptable) or `Talk to the founder` | `See integrations` → `/integrations/` | role-appropriate | role-appropriate |
| Principal | `View on GitHub` (acceptable) | `Read the rationale` → `/insights/architectural-governance-across-heterogeneous-ai-coding-agents/` | role-appropriate | role-appropriate |

**Hard rule:** the CTO page does not link to GitHub from any CTA in the body. (Footer
nav-links to `/github` are fine — those are universal site chrome, not CTAs.)

### 3. Mid-document Roadmap CTA on long persona pages

Persona pages over ~1,000 words must include a single mid-document CTA panel pointing to
`/roadmap/`, placed between the body sections and the final CTA footer. Pattern:

```html
<div class="mid-cta-wrap">
  <div class="mid-cta">
    <p class="mid-cta-text"><strong>Where this is going.</strong> [one-sentence framing]</p>
    <a href="/roadmap/" class="btn-ghost">See the roadmap →</a>
  </div>
</div>
```

The CSS for `.mid-cta-wrap` / `.mid-cta` lives inline on the page until the site adopts a
shared stylesheet.

### 4. Visible breadcrumbs on every persona subpage

Every `/for/<role>/` subpage and the `/for/` hub itself must render a visible breadcrumb
nav above the hero, in addition to the JSON-LD `BreadcrumbList` mandated by ADR-003 §9.
Format:

```html
<nav class="breadcrumb" aria-label="Breadcrumb">
  <a href="/">Home</a><span class="sep">/</span><a href="/for/">For</a><span class="sep">/</span><span aria-current="page">For CTOs</span>
</nav>
```

Visible breadcrumbs are required on `/for/` because the persona pages are deep in the IA
and frequently entered from cold paid-search; without them readers have no orientation
back to the hub.

### 5. Required structural sections for `/for/cto/`

The CTO page must contain, in order:

1. Hero (eyebrow, h1, subhead, byline, CTA group)
2. **The Problem** — review capacity vs. AI throughput
3. **Why Existing Approaches Don't Scale** — comparison table
4. **How It Works** (high-level, three paragraphs maximum, no engineering primitives per §1)
5. **Business Outcomes** — ROI cards (senior eng hours, throughput-without-debt, governance
   consolidation, audit posture)
6. Mid-document Roadmap CTA (per §3)
7. **Proof** — deterministic enforcement, test coverage, citations
8. CTA footer

---

## Rationale

- **Audience drift kills conversion.** The reader who lands on `/for/cto/` from a cold
  LinkedIn click does not stay through a YAML block. They scroll to ROI or they leave.
- **CTAs are a contract with intent.** "View on GitHub" tells a reader "we expect you to
  read code now." For a CTO, that is the wrong contract. `/contact/` matches their intent.
- **Roadmap-as-trust.** A public roadmap is the strongest trust signal an early-stage
  governance vendor can offer to an SLT buyer; surfacing it mid-document prevents the
  reader from having to reach the footer to find it.
- **Visible breadcrumbs** are user-facing IA, not just an SEO artifact. JSON-LD breadcrumbs
  satisfy crawlers; visible breadcrumbs satisfy humans.

---

## Consequences

- The `style.classes` rule in `scripts/seo_check.py` enforces the layout invariants but
  cannot enforce the content invariants in this ADR. Content review for persona pages is
  a manual step at publish time.
- New persona pages (e.g. `/for/security-leadership/`) inherit the same standards.
- Edits to `/for/cto/` that re-introduce engineering primitives (YAML, command-line,
  per-tool config filenames) are reverted on review.

---

## Related

- ADR-001: Positioning and Messaging
- ADR-003: Site Publishing Guidelines (especially §8–§11 on hub pages, breadcrumbs, CSS hygiene)
- ADR-006: Insights Article SEO and Schema Requirements
- `scripts/seo_check.py` — `style.classes` rule and breadcrumb checks

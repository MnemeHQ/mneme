---
id: ADR-015
title: "Report-Anchored Insight Titles and Entity Front-Loading"
status: accepted
priority: normal
date: 2026-05-30
scope: site.insights_seo.report_titles
---

# ADR-015: Report-Anchored Insight Titles and Entity Front-Loading

**Status:** Accepted
**Date:** 2026-05-30
**Deciders:** Theo Valmis

---

## Context

A subset of insights articles are built on a **named external artifact** — a published
report, study, framework, playbook, or named system (e.g. Datadog's *State of AI Engineering
Report*, METR's productivity studies, the *SPACE Framework*). People search for these by their
exact name. The article that intercepts that query wins traffic the new domain cannot yet win on
authority alone.

Search Console evidence (5–28 May 2026, `searchconsole.searchdata_url_impression` BigQuery export,
`https://mnemehq.com/` property) showed the mechanism clearly:

- `/insights/datadog-state-of-ai-engineering-governance-crisis/` was the **single best-performing
  article** — 54 impressions at avg position **6.8** — and it ranked for `datadog state of ai
  engineering` (pos ~7–8). Its `<title>` and `<h1>` front-load the verbatim report name.
- Other report-anchored articles ranked far deeper because they led with editorial phrasing and
  **buried the searchable entity** in the meta or after a colon (e.g. the METR studies surfaced only
  in the meta; "SPACE Framework" sat after "Quantifying GitHub Copilot's Impact:").
- On a new, low-authority domain, **timeliness + exact-name match is the one wedge that beats
  authority.** Front-loading the named artifact is how we take it.

ADR-006 already mandates the *technical* SEO scaffolding (meta tags, JSON-LD, breadcrumbs, sitemap
inclusion) for every insights article. It does **not** govern the *editorial* title pattern for
report-anchored pieces. This ADR fills that gap.

---

## Decision

### 1. Classify the article first

Apply this pattern **only** to articles whose spine is a named, searchable external artifact:
a report, study, survey, framework, playbook, or named system (with a year if the name carries one).

**Do NOT apply it** to original-concept or POV pieces, even if they cite a report in passing. Forcing
a report name onto an original argument misrepresents it and dilutes the concept terms we are trying
to own (see ADR-012, Conceptual Authority Discipline). A report cited as a *supporting stat* does not
make the article report-anchored — judge by what the piece is *about*.

### 2. Front-load the verbatim searchable entity

For a report-anchored article, the article's `<title>` and `<h1>` must **lead with the exact,
searchable artifact name**, before any editorial angle, so it survives Google's ~60-char title
truncation and matches the query verbatim.

- Good: `METR's AI Productivity Studies: Why AI Coding Feels Fast but Measures Slow`
- Good: `The SPACE Framework: Measuring GitHub Copilot's Real Productivity Impact`
- Good: `Datadog's State of AI Engineering Report Quietly Confirms the Governance Crisis`
- Avoid: `The Productivity Paradox: …` (editorial term first, named entity absent)
- Avoid: `Quantifying GitHub Copilot's Impact: What the SPACE Framework…` (entity after the colon)

Editorial readability is still required — pair the entity with the angle (`<entity>: <hook>`), don't
ship a bare keyword.

### 3. Keep the entity consistent across every title-bearing field

The named entity string must be **identical** across all of these (the Datadog winner keeps
`<title>` and `<h1>` identical):

1. `<title>` (keeps the ` — Mneme HQ` suffix; the others do not)
2. `<h1>`
3. `og:title`, `twitter:title`
4. JSON-LD `Article`/`TechArticle` `headline`
5. JSON-LD `BreadcrumbList` final `ListItem` `name`
6. **Inbound internal anchor text** — the card title + `ItemList` name in `site/insights/index.html`,
   and any related-essay `rel-card` / cross-link on sibling pages

Repetition across title = h1 = schema = anchors is what compounds entity association for Google and
LLM retrieval.

### 4. Lead the meta description with source + a hard number

The `description` (and the matching `og:description` / `twitter:description`, which must be unified to
one string) leads with the source and a concrete figure from the artifact, then pivots to the Mneme
governance angle. Numbers must be **verified against the article body**, not assumed.

- Example: `METR's developer-productivity studies found experienced engineers felt faster with AI yet
  measured 19% slower. Closing that perception–measurement gap is the governance problem.`

### 5. OG card headline leads with the same entity

OG cards use bespoke short headlines (not the verbatim `<title>`), rendered from
`site/og-<slug>.html` via `scripts/generate_og_images.py` (ADR-007). The OG headline must lead with
the same named entity (e.g. `The SPACE Framework & GitHub Copilot`, `METR and the AI Productivity
Paradox`). Every report-anchored article needs its own `og-<slug>.html` template **and** a
`TEMPLATE_MAP` entry — do not let a page inherit a generic or wrong OG image.

### 6. Do not retrofit the pattern onto non-qualifying pages

Leaving an original-concept piece (e.g. "The AI ROI Problem", "Memory Is Not Governance") with its
concept-first title is correct, not an oversight.

---

## Publishing checklist (report-anchored articles only — additive to ADR-006)

- [ ] Article is genuinely spine-anchored on a named report/study/framework/playbook/system
- [ ] `<title>` and `<h1>` front-load the **verbatim** searchable entity name (+ year if applicable)
- [ ] Entity string identical across title, h1, og:title, twitter:title, JSON-LD headline, breadcrumb name
- [ ] Inbound anchors updated (insights index card + `ItemList` name; sibling rel-cards / cross-links)
- [ ] meta = og:description = twitter:description (one unified string), leading with source + a **verified** number
- [ ] `og-<slug>.html` template leads with the entity, has a `TEMPLATE_MAP` entry, renders the correct page/URL
- [ ] Counter-check: this is NOT an original-concept piece being forced into the pattern

---

## Rationale

- **Verbatim-name front-loading** maximizes query-document match for the one class of query a
  low-authority domain can win: the exact named artifact.
- **Cross-field consistency** turns each article into a single, repeated entity signal that compounds
  category/terminology ownership across Google and LLM retrieval.
- **Source + number in the meta** raises CTR and gives AI crawlers an extractable, attributable claim.
- **Classification discipline** protects the original-concept terms Mneme is separately trying to own
  (ADR-012) from being overwritten by third-party report names.

---

## Consequences

- Report-anchored articles take a few extra minutes (entity audit + 6-field sync + OG template).
- The pattern is a **wedge, not a moat** — it works until domain authority and internal-link equity
  build; it does not replace them.
- Editorial judgment is required at classification time; the line between "report-anchored" and
  "concept piece that cites a report" is a human call, documented per-article in the PR.
- First applied 2026-05-30 to `productivity-paradox-perception-vs-measurement` (METR) and
  `github-copilot-space-framework` (SPACE Framework). Already-compliant at that date: Datadog,
  Snowflake (*AI Data Engineering Report*), Microsoft (*Agentic Transformation Playbook*),
  AI Peer Review Study, and `ai-native-engineering-intent-debt` (*State of AI-Native Engineering 2026*).

---

## Related

- ADR-006: Insights Article SEO and Schema Requirements (technical scaffolding this builds on)
- ADR-007: OG Image Generation (`scripts/generate_og_images.py`, `og-<slug>.html` templates)
- ADR-012: Conceptual Authority Discipline (protects original concept terms — the counterweight)
- `site/insights/datadog-state-of-ai-engineering-governance-crisis/` — the reference implementation

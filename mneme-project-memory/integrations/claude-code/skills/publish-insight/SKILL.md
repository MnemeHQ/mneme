---
name: publish-insight
description: |
  Author and publish a Mneme HQ insight article end to end. Use when asked to
  "write an insight", "publish an article", "scope an article", turn a ChatGPT
  "Post-*" scope thread into a page, or react to a report / launch / paper with
  a governance-angle article. Encodes the SEO patterns, the publishing contract,
  internal-link mesh, funnel, and accessibility so a new insight is born compliant.
---

# publish-insight — author + register a Mneme insight, correctly, first time

The canonical contract is `docs/site/insight-publishing-contract.md` and
`scripts/check_insights.py` (the gate). This skill is the *generation* procedure;
the validator is the *enforcement*. Follow both.

## 1. Scope + SEO intent

- Lead the `<title>`, `<h1>`, and meta with a **recognizable entity** (report
  name + year, vendor, paper, launch, OSS project), then pivot to the governance
  interpretation. Avoid abstract category-only titles (good for LinkedIn, weak
  for SEO).
- **Report response?** Lead title/H1/meta with `[Report Name] [Year]`, add an
  early `What [Report] Shows` H2, plant the report's own vocabulary in the body
  and FAQ, and nest the source as `isBasedOn` → `Report` in the TechArticle
  JSON-LD. Otherwise use the entity-anchor pattern.
- Read the source(s) in full and use **verified** facts/stats only; do not
  attribute anecdotes to unverifiable named people — generalize them.
- One authoritative **outbound reference** (`target="_blank" rel="noopener"`),
  cited once.

## 2. Overlap check (do this before writing)

Grep `site/insights/*/index.html` for the theme. If a close article exists
(especially same source/report), either pick a genuinely differentiated angle
or **update the existing page** instead of shipping a near-duplicate. Shipping a
near-duplicate is a failure.

## 3. Write — clone the scaffold

Copy a recent exemplar (`site/insights/ai-coding-agent-verification-tax/`
standard, or `bcg-ai-era-operating-models-governance/` for report-response).
Keep the `<style>`, global `<nav>`, site `<footer>`, and trailing `<script>`
blocks **byte-identical** (nav-footer-check + sticky-nav-check are strict).
Efficient method for a batch: write one golden file, `Copy-Item` to the other
slug dirs, then Edit only the per-article regions (title, meta, JSON-LD,
breadcrumb label, `<article>` body). A 5-line Read of a copy satisfies Edit's
read-precondition for whole-file edits.

Body structure: eyebrow + `<h1>` + `.article-lede` + byline; `<h2>` sections;
`.callout`; `.gov-table`; an `<ol>` Record/Retrieve/Check/Reject/Return loop
where it fits; 4-item FAQ (`<details>`); two `.related-panel` asides (concepts +
essays); `.article-footer` with `.cta-block`.

CTA ladder (order matters — highest-intent first): the `.cta-block` leads with
`<a href="/pilot/" class="btn-primary">Request a pilot &rarr;</a>` as its primary;
demote demo/GitHub to inline text links (`style="display:inline-block;
margin-right:1.25rem;color:var(--accent);font-family:'DM Mono',monospace;
font-size:0.85rem;text-decoration:none;"`). The newsletter subscribe `<aside
aria-label="Mneme HQ newsletter">` goes **below** the `.cta-block` (nurture for
the not-yet-ready reader — never above the pilot CTA).

## 4. The three quality rules check_insights now enforces

- **Accessible links (HARD):** include `.article-body a { color: #8be0c8;
  text-decoration: none; border-bottom: 1px solid rgba(139,224,200,0.4);
  transition: border-color 0.15s; } .article-body a:hover { border-bottom-color:
  #8be0c8; }`. Teal (not the lime `--accent`/CTA colour), underlined (WCAG 1.4.1
  — never colour alone), ~12.6:1 on `#0c0c0d`.
- **Mesh (WARN, aim ≥3 inbound):** cross-link 3–4 existing insights + 3–4
  concepts in the body/related panels, AND add a reciprocal `related-essays`
  `<li>` *into* each neighbour article pointing back, matching that file's own
  related-list format. A page reachable only from the hub is under-meshed.
- **Funnel (WARN):** include at least one contextual bottom-funnel link
  (`/demo/`, `/pilot/`, or `/use-cases/...`) in the body/CTA, beyond the GitHub
  CTA and global nav — especially on buyer-intent (report/cost) pieces.

## 5. Register (every item; check_insights gates them)

1. `site/sitemap.xml` — add `<url><loc>https://mnemehq.com/insights/<slug>/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>`.
2. `site/insights/index.html` — add the `<a class="insight-card-link">` card in the right `cards-grid` **and** a matching `{"@type":"Article",...}` entry in the CollectionPage `hasPart` (both checked independently).
3. OG image — add a tuple to `TEMPLATES` + `NEW_MAP_ENTRIES` in `scripts/ensure_og_coverage.py`, run it, then render **only the new slug(s)** (a temp Playwright loop or a narrowed `TEMPLATE_MAP`) — never the full `generate_og_images.py`. Confirm `site/insights/<slug>/og.png` exists.
4. Head: canonical, `og:image` + `twitter:image` → the article-local `og.png`; `<nav class="breadcrumb-nav">` (3 items); BreadcrumbList JSON-LD (positions 1/2/3, exact item URLs); TechArticle JSON-LD (url == canonical, non-empty headline; `isBasedOn` Report for report responses).

## 6. Validate, then PR

Run `python scripts/check_insights.py` (must exit 0; read its WARN lines and
close the mesh/funnel gaps), plus `check_nav_footer.py`, `check_sticky_nav.py`,
`check_encoding.py` (save UTF-8, no BOM, preserve CRLF). Branch `site/...`,
squash-merge with a taxonomy-compliant title. Merge order matters if a deploy
tooling fix is in flight (see the deploy notes); the live deploy submits changed
URLs to IndexNow on success.

## Anti-slop

Match the house voice: concrete, declarative, short sentences, specific worked
examples (the BillingService ADR). No "in today's fast-paced world", no
furthermore-chains, no em-dash-as-connective-tissue overuse. Two-quotes-max from
any copyrighted source; paraphrase practitioner quotes.

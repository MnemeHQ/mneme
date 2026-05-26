---
id: ADR-007
title: "OG Image Generation for Social Sharing"
status: accepted
priority: normal
date: 2026-05-06
scope: site.og_images
---

# ADR-007: OG Image Generation for Social Sharing

**Status:** Accepted  
**Date:** 2026-05-06  
**Deciders:** Theo Valmis

---

## Context

Every page on `mnemehq.com` needs an `og:image` for LinkedIn, Twitter/X, and Slack previews.
Without page-specific images, LinkedIn auto-pulls a random screenshot or the shared `og.png`,
which is skewed, off-brand, or irrelevant to the page being shared.

Problems with the previous approach:
- Single `og.png` used across all pages — no page-level relevance
- LinkedIn's link preview picked the benchmarks/100% graphic, which looked distorted
- No documented process for generating or updating OG images

---

## Decision

Each page gets its own OG image at `<page-path>/og.png`, generated from a source HTML template.

### Source templates

All OG source files live in `site/` and are named `og-<slug>.html`:

```
site/og-homepage.html
site/og-use-cases-gen.html
site/og-coding-assistant-governance.html
site/og-legacy-codebase-memory.html
site/og-security-compliance-guardrails.html
site/og-data-platform-governance.html
site/og-design-system-governance.html
site/og-multi-agent-workflow-governance.html
site/og-founder.html
site/og-contact.html
site/og-roadmap.html
site/og-insights.html
site/og-insights-prompt-engineering.html
site/og-insights-code-review.html
site/og-insights-rag.html
site/og-insights-cursor.html
site/og-for-cto.html
site/og-for-platform.html
site/og-for-principal.html
```

### Output PNGs

Each template is rendered at exactly **1200×630px** and saved as `og.png` co-located with its page:

```
site/og.png                                                     ← homepage
site/use-cases/og.png
site/use-cases/coding-assistant-governance/og.png
... (one per page)
```

### Design system

All OG images must follow the site design language:

| Property | Value |
|---|---|
| Dimensions | 1200 × 630 px (exact — no skew, no letterbox) |
| Background | `#0c0c0d` |
| Accent | `#c8f060` |
| Text | `#e8e8ec` |
| Muted | `#88889a` |
| Heading font | Instrument Serif (italic accent word in `#c8f060`) |
| Body font | DM Mono |
| Grid | `rgba(200,240,96,0.04)` at 60px |
| Logo text | **"Mneme HQ"** — never "Mneme" |
| Logo position | Top-left, always visible |

### Generation process

Run `scripts/generate_og_images.py` to regenerate all PNGs from the HTML templates.
Requires: `playwright` Python package and a running local HTTP server on port 8765
(or the script starts one automatically).

### og:image tag convention

Every `index.html` must have both:
```html
<meta property="og:image" content="https://mnemehq.com/<path>/og.png" />
<meta name="twitter:image" content="https://mnemehq.com/<path>/og.png" />
```

Pages without a page-specific image (e.g. `privacy/`) use `https://mnemehq.com/og.png`.

### Deploy

OG PNGs are included automatically — `scripts/deploy_site.py` walks `site/` recursively
and uploads every file. No manual manifest updates required.

---

## Consequences

- Adding a new page requires: create `og-<slug>.html`, run `scripts/generate_og_images.py`, deploy
- OG HTML source files are committed to the repo alongside the PNGs they generate
- LinkedIn caches OG images aggressively — use the LinkedIn Post Inspector to force a refresh:
  `https://www.linkedin.com/post-inspector/`

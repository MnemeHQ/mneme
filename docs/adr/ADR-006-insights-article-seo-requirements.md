# ADR-006: Insights Article SEO and Schema Requirements

**Status:** Accepted  
**Date:** 2026-05-06  
**Deciders:** Theo Valmis

---

## Context

Insights articles on mnemehq.com are the primary GEO (Generative Engine Optimization) and SEO
surface for Mneme. For AI crawlers (Perplexity, ChatGPT, Gemini) to cite these articles correctly,
and for Google to show rich breadcrumb results, each article page must carry a complete set of
structured data and meta tags.

The initial four articles launched without breadcrumb navigation, Article JSON-LD schema,
`article:*` Open Graph properties, or a mobile hamburger menu. This ADR documents the required
checklist and makes it a publishing gate.

---

## Decisions

### 1. Required meta tags for every insights article

Every `site/insights/<slug>/index.html` must include all of the following in `<head>`:

```html
<!-- Core -->
<title>[Article Title] — Mneme HQ</title>
<meta name="description" content="[150–160 char description]" />
<meta name="robots" content="index, follow" />
<link rel="canonical" href="https://mnemehq.com/insights/<slug>/" />
<meta name="author" content="Theo Valmis" />

<!-- Open Graph (article type) -->
<meta property="og:type" content="article" />
<meta property="og:site_name" content="Mneme HQ" />
<meta property="og:title" content="[Article Title]" />
<meta property="og:description" content="[same as meta description]" />
<meta property="og:url" content="https://mnemehq.com/insights/<slug>/" />
<meta property="og:image" content="https://mnemehq.com/og.png" />
<meta property="article:published_time" content="YYYY-MM-DDT00:00:00Z" />
<meta property="article:author" content="https://mnemehq.com/founder/" />
<meta property="article:section" content="Engineering" />

<!-- Twitter / X -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="[Article Title]" />
<meta name="twitter:description" content="[same as meta description]" />
<meta name="twitter:image" content="https://mnemehq.com/og.png" />
```

### 2. Required JSON-LD structured data

Every article page must include a `<script type="application/ld+json">` block with both
`BreadcrumbList` and `Article` types in a `@graph` array:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "BreadcrumbList",
      "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://mnemehq.com/"},
        {"@type": "ListItem", "position": 2, "name": "Insights", "item": "https://mnemehq.com/insights/"},
        {"@type": "ListItem", "position": 3, "name": "[Article Title]", "item": "https://mnemehq.com/insights/<slug>/"}
      ]
    },
    {
      "@type": "Article",
      "headline": "[Article Title]",
      "description": "[meta description]",
      "url": "https://mnemehq.com/insights/<slug>/",
      "datePublished": "YYYY-MM-DD",
      "dateModified": "YYYY-MM-DD",
      "author": {"@type": "Person", "name": "Theo Valmis", "url": "https://mnemehq.com/founder/"},
      "publisher": {"@type": "Organization", "name": "Mneme HQ", "url": "https://mnemehq.com/", "logo": {"@type": "ImageObject", "url": "https://mnemehq.com/logo-v2.png"}},
      "image": "https://mnemehq.com/og.png",
      "mainEntityOfPage": "https://mnemehq.com/insights/<slug>/"
    }
  ]
}
```

### 3. Visual breadcrumb navigation

Every article page must render a visible breadcrumb trail immediately below the sticky nav,
before the article content:

```html
<nav aria-label="Breadcrumb" class="breadcrumb-nav">
  <ol class="breadcrumb">
    <li><a href="/">Home</a></li>
    <li><a href="/insights/">Insights</a></li>
    <li aria-current="page">[Article Title]</li>
  </ol>
</nav>
```

CSS class names `.breadcrumb-nav` and `.breadcrumb` must match the shared stylesheet.

### 4. Hub CollectionPage update

When a new article is published, `site/insights/index.html` must be updated to:
- Add a card for the article in the grid
- Add the article to the `hasPart` array in the hub's `CollectionPage` JSON-LD
- Add the article URL to `site/sitemap.xml`

### 5. Mobile hamburger menu

All article pages must include the mobile hamburger nav (matching `site/insights/index.html`).
Article pages without a hamburger button and the associated JS/CSS fail the mobile usability check.

---

## Publishing checklist

Before merging a new insights article, verify all of the following:

- [ ] `<title>` ends with ` — Mneme HQ`
- [ ] `<meta name="description">` present, 150–160 chars
- [ ] `<link rel="canonical">` matches the slug URL exactly
- [ ] `<meta name="author">` = `Theo Valmis`
- [ ] `og:type` = `article`
- [ ] `article:published_time` set to actual publish date
- [ ] `article:author` set to `/founder/` URL
- [ ] `article:section` = `Engineering`
- [ ] BreadcrumbList JSON-LD present with correct 3-item path
- [ ] Article JSON-LD present with all required fields
- [ ] Visual breadcrumb nav renders below sticky nav
- [ ] Mobile hamburger button and JS present
- [ ] Card added to `site/insights/index.html` grid
- [ ] Article added to hub's `hasPart` JSON-LD
- [ ] URL added to `site/sitemap.xml`
- [ ] Post-deploy: URL returns 200 (verified by `scripts/deploy_site.py` automatically)

---

## Rationale

- **BreadcrumbList** enables Google's breadcrumb rich result in SERPs
- **Article JSON-LD** gives AI crawlers (Perplexity, ChatGPT Plugins, Gemini) a structured
  extraction target for author, date, and headline — critical for attribution in AI-cited answers
- **`article:published_time`** affects recency signals in Google News and AI retrieval ranking
- **`article:section`** improves topical classification for both Google and AI index
- **Visual breadcrumb** improves page navigation UX and reinforces the structured data signal

---

## Consequences

- New insights articles take ~5 extra minutes to publish (checklist completion)
- Automated deploy (`scripts/deploy_site.py`) handles the sitemap verification gate;
  manually adding to sitemap and hub JSON-LD remains a human step
- Retroactively applied to the first four articles on 2026-05-06

---

## Related

- ADR-003: Site Publishing Guidelines
- `site/insights/` — all article pages
- `site/sitemap.xml` — canonical URL list
- `scripts/deploy_site.py` — post-deploy verification

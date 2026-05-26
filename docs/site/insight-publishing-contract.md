# Insight publishing contract

Adding a new article under `site/insights/<slug>/index.html` is **not enough on its own**. The publishing pipeline does not auto-discover new articles. Each one requires explicit registration in four places. CI enforces this via `scripts/check_insights.py` (see `.github/workflows/check-insights.yml`).

## What the contract requires

For every `site/insights/<slug>/index.html`, the following must all be true:

**Registration**

1. **Sitemap entry** — a `<url><loc>https://mnemehq.com/insights/<slug>/</loc>...</url>` block in [`site/sitemap.xml`](../../site/sitemap.xml).
2. **Insights hub card** — an `<a href="/insights/<slug>/" class="insight-card-link">...</a>` card on [`site/insights/index.html`](../../site/insights/index.html).
3. **Local OG image** — `og.png` co-located in the article directory: `site/insights/<slug>/og.png`.
4. **OG meta tags resolve** — both `<meta property="og:image">` and `<meta name="twitter:image">` in the article must point to a PNG file that actually exists under `site/`.
5. **At least one incoming internal link** — at least one other HTML file under `site/` must link to `/insights/<slug>/`. The hub card from check (2) satisfies this; reciprocal links from related articles are recommended for SEO depth.

**Breadcrumb**

6. **Visible breadcrumb nav** — `<nav class="breadcrumb-nav">` block with exactly three `<li>` items: `Home` linking to `/`, `Insights` linking to `/insights/`, and the current page (no `<a>` or `aria-current="page"`).
7. **BreadcrumbList JSON-LD** — a `schema.org` `BreadcrumbList` entry whose `itemListElement` has 3 items at positions 1, 2, 3 with `item` URLs matching `https://mnemehq.com/`, `https://mnemehq.com/insights/`, and `https://mnemehq.com/insights/<slug>/`.

**Article schema**

8. **TechArticle/Article JSON-LD** — exactly one `schema.org` `TechArticle` (or `Article`) entry with `url` matching `https://mnemehq.com/insights/<slug>/` and a non-empty `headline`.

**Hub schema**

9. **CollectionPage hasPart entry** — the slug must appear in the `hasPart` array of the `CollectionPage` JSON-LD on the hub. The visible card (check 2) and the hub `hasPart` entry can drift independently and are both consumed by search engines; both must be present.

## How to register a new insight

After writing `site/insights/<slug>/index.html`, do the following before opening the PR:

### 1. OG image

Add three entries to `scripts/ensure_og_coverage.py`:

- `TEMPLATES` — a `(filename, tag, heading, font_size, subtitle, url_path)` tuple. Choose a short `og-insights-<short-slug>.html` filename.
- `NEW_MAP_ENTRIES` — maps the template filename to the output `og.png` path (e.g. `"og-insights-<short-slug>.html": "insights/<slug>/og.png"`).
- `HTML_FIXES` is only needed if the article points at the generic site OG instead of its own. Articles whose `og:image` already points to the correct article-local PNG do not need an entry here.

Then run:

```bash
python scripts/ensure_og_coverage.py     # materializes the template and patches TEMPLATE_MAP
python scripts/generate_og_images.py     # renders all og.png files via Playwright
```

`generate_og_images.py` requires `playwright` and a chromium install (`pip install playwright && playwright install chromium`).

### 2. Sitemap

Append a `<url>` block to `site/sitemap.xml`:

```xml
<url>
  <loc>https://mnemehq.com/insights/<slug>/</loc>
  <changefreq>monthly</changefreq>
  <priority>0.8</priority>
</url>
```

### 3. Insights hub card and `hasPart`

Add a card to `site/insights/index.html` in the most thematically appropriate `cards-section` (e.g. `governance-problem`, `ai-native`, `market-context`). Mirror the structure of neighboring cards: eyebrow tag, read time, `<h3>` title, summary `<p>`, and the `read-pill` footer.

**Also append a matching entry to the `hasPart` array** in the `CollectionPage` JSON-LD block at the top of the file. The visible card and the `hasPart` entry are checked independently — both are required.

```json
{"@type": "Article", "name": "Your Title", "url": "https://mnemehq.com/insights/<slug>/"}
```

### 4. Breadcrumb and article schema

Every article must include:

- A visible `<nav class="breadcrumb-nav">` block with three items: `Home -> Insights -> article`.
- A `BreadcrumbList` JSON-LD entry in `<head>` whose `itemListElement` mirrors the visible breadcrumb.
- A `TechArticle` (or `Article`) JSON-LD entry in `<head>` with `url` matching the article's canonical URL and a non-empty `headline`.

The existing article template under any recent `site/insights/<slug>/index.html` (for example, [`why-context-alone-doesnt-prevent-architectural-drift`](../../site/insights/why-context-alone-doesnt-prevent-architectural-drift/index.html)) is the canonical reference — copy its `<head>` JSON-LD and breadcrumb-nav block and substitute slug + title + headline.

### 5. Internal links

The hub card from step 3 already satisfies the "at least one incoming internal link" requirement. For SEO depth, also add reciprocal cross-links from thematically related insights (the article's own `related-essays` panel links outward; the reciprocal inward links are the high-value pairing).

## Running the check locally

```bash
python scripts/check_insights.py
```

Exit code is `0` if every article is fully registered, `1` if any check fails. Error messages name the failing slug and condition, e.g.:

```
  my-new-article/
    - Missing sitemap entry for site/insights/my-new-article/
    - Missing og.png for site/insights/my-new-article/
    - Missing breadcrumb nav block in my-new-article: expected <nav class="breadcrumb-nav"> with Home -> Insights -> article
    - BreadcrumbList JSON-LD missing from my-new-article
    - TechArticle/Article JSON-LD missing from my-new-article: add a schema.org TechArticle entry with url and headline
    - Missing hub CollectionPage hasPart entry for my-new-article: add {"@type": "Article", "name": "<title>", "url": "https://mnemehq.com/insights/my-new-article/"} to the hasPart array in site/insights/index.html
    - No incoming internal links found for my-new-article
```

## CI behavior

`.github/workflows/check-insights.yml` runs `check_insights.py` on every PR that touches any of:

- `site/insights/**`
- `site/insights/index.html`
- `site/sitemap.xml`
- `scripts/**`

A failing check blocks the PR.

## What the publishing scripts do not do

- They do **not** auto-discover new articles.
- They do **not** auto-create OG templates from article HTML.
- They do **not** auto-insert sitemap entries.
- They do **not** auto-insert insights hub cards.
- They do **not** auto-insert reciprocal cross-links.

The deploy workflow (`.github/workflows/deploy-site.yml`) only uploads changed files via the cPanel API and purges the Cloudflare cache. It performs no content generation.

If automation for any of the above is desired in the future, it should be implemented as an additional script invoked from CI on a separate workflow — not bolted onto deploy.

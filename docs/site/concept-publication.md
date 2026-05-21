# Concept Publication Runbook

Reference checklist for publishing a new concept page to `/concepts/`. Run the
validator in step 7 before opening the PR.

---

## 1. Create the concept page

Create `site/concepts/{slug}/index.html`.

- Slug is lowercase kebab-case matching the concept's canonical URL segment.
- Include all required `<head>` metadata: `<title>`, `<meta name="description">`,
  `<link rel="canonical">`, `og:*` and `twitter:*` tags,
  `article:published_time` (ISO 8601, e.g. `2026-05-21T00:00:00Z`).
- Include the Schema.org `DefinedTerm` JSON-LD block.
- Link back to the hub: breadcrumb `Concepts → {Concept Name}`.
- Add at least one related-concept link in the body (see step 5).

OG image: the publishing script generates `og.png` automatically — do not create
it by hand.

---

## 2. Add the concept card to site/concepts/index.html

Open `site/concepts/index.html`. Find the correct section grid
(`Core concepts`, `Systems concepts`, or `Adjacent concepts`).

Append the card inside the grid's `<div class="concepts-grid" role="list">`:

```html
<a href="/concepts/{slug}/" class="concept-card" role="listitem">
  <div class="card-top">
    <span class="card-num">{NN}</span>
    <div>
      <div class="card-title">{Concept Name}</div>
    </div>
  </div>
  <p class="card-desc">{One-sentence description matching the page's meta description.}</p>
  <span class="card-arrow">&rarr;</span>
</a>
```

Rules:
- `card-num` is a sequential two-digit display label within its section. It is
  decorative — the validator does not check numbering. Keep it consistent with
  neighbouring cards.
- `card-desc` must match (or closely paraphrase) the `<meta name="description">`
  on the concept page. This is the value the validator will eventually use for
  generation (Phase 2).
- Do not change the section a concept belongs to without updating the hub intro
  copy and the SVG diagram caption if relevant.

---

## 3. Add the JSON-LD hasPart entry

In the same file (`site/concepts/index.html`), find the `"hasPart"` array inside
the `CollectionPage` block (around line 202). Add one entry:

```json
{"@type": "DefinedTerm", "name": "{Concept Name}", "url": "https://mnemehq.com/concepts/{slug}/"}
```

- `name` must match the `<title>` on the concept page (before the ` — Mneme HQ` suffix).
- Append the new entry at the end of the array. The existing array is not
  alphabetical; do not attempt to re-sort it.
- Do not add a trailing comma to the last entry.

---

## 4. Update the SVG knowledge graph (if applicable)

The SVG diagram in `site/concepts/index.html` (lines ~280–405) is **editorial**.
Not every concept belongs in it. Before adding a node, decide:

**Add an SVG node if** the concept occupies a structural position in the
primitives → properties → outcomes architecture, or belongs in the failure rail.

**Omit from SVG if** the concept is contextual, adjacent, or definitional without
a fixed tier. Instead, add its slug to `docs/site/svg-omitted.txt` (one slug per
line, no trailing slash) so the validator treats the omission as intentional.

If you add a node:
- Follow the tier conventions: `cmap-card-primitive` (teal border),
  `cmap-card` (neutral), `cmap-card-outcome` (accent border), `cmap-card-fail`
  (red dashed).
- Add flow lines (`<line class="cmap-flow">`) connecting the new node to its
  tier neighbors.
- Update the diagram-level `<desc id="cmap-desc">` to mention the new node
  in the overall description.
- Update the `<figcaption>` if the overall diagram narrative changes.
- Refer to `docs/contributing/diagram-conventions.md` for color roles and
  accessibility requirements.

---

## 5. Add related-concept cross-links

On the new concept page, add at least one `<a href="/concepts/{related-slug}/">`
link to a conceptually adjacent concept. The reciprocal link on the related page
is strongly encouraged but not required for publication.

On the related concept page(s), add a cross-link back where it reads naturally.
Prefer linking from the "related concepts" section or an inline reference in
the body prose.

---

## 6. Update sitemap and internal link audit

Open `site/sitemap.xml`. Add a `<url>` block for the new concept:

```xml
<url>
  <loc>https://mnemehq.com/concepts/{slug}/</loc>
  <changefreq>monthly</changefreq>
  <priority>0.8</priority>
</url>
```

Then do a quick internal link audit:
- Search the site for any existing pages that reference the new concept by name
  but do not link to it. Add links where the prose already calls it out.
- Check the hub intro copy (`site/concepts/index.html` lines ~273–277). If the
  new concept warrants a mention there, update it.

---

## 7. Run the validator before opening the PR

```bash
python scripts/check_concepts.py
```

Exit code 0 = clean. Any non-zero exit means there is actionable drift:

| Code | Meaning |
|------|---------|
| 1 | ERROR — pages missing cards, cards missing JSON-LD, or JSON-LD pointing to absent pages |
| 2 | WARN only — concepts without SVG nodes not listed in svg-omitted.txt |

Fix all ERRORs before opening the PR. WARNs about SVG omission may be resolved
by either adding the node or adding the slug to `docs/site/svg-omitted.txt`.

The validator is also a good smoke-check after any bulk edit to the hub — run it
whenever you touch `site/concepts/index.html`.

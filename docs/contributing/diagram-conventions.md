# Mneme HQ — Diagram Conventions

Contributor reference for the canonical diagram primitives used across `/concepts/`,
`/insights/`, `/demo/`, and `/compare/`. New diagrams must follow these
conventions; bespoke per-page SVGs are no longer how we add visual
infrastructure.

The four canonical primitives live in `site/assets/css/diagrams.css`, each
embedded on its canonical concept-page home:

- `.mneme-diagram--propagation` — fan-out from a compiled corpus to consumers — `/concepts/governance-propagation/`
- `.mneme-diagram--checkpoints` — lifecycle enforcement checkpoints — `/concepts/governance-before-generation/`
- `.mneme-diagram--chain` — backward citation chain (verdict → ADR) — `/concepts/enforcement-provenance/`
- `.mneme-diagram--cascade` — compounding drift over sessions — `/concepts/architectural-drift/`

---

## Markup contract

Every primitive uses this wrapper:

```html
<figure class="diagram-figure">
  <div class="mneme-diagram mneme-diagram--<kind>" role="img"
       aria-labelledby="X-diag-title X-diag-desc">
    <p id="X-diag-title" class="mneme-diagram__title">Visible title</p>
    <p id="X-diag-desc" class="mneme-diagram__sr-desc">Long description for AT</p>
    <!-- primitive-specific markup -->
  </div>
  <figcaption class="diagram-caption">One-line argument summary.</figcaption>
</figure>
```

- The visible title can be any element (`<h2>`, `<h3>`, `<h4>`, or `<p>` / `<div>`).
  Pick whatever fits the page's document outline. Use a heading element only when
  the diagram occupies a heading slot in the page hierarchy; use `<p>` when it sits
  inside a section as an illustration. The class and ARIA wiring stay constant
  regardless.
- **ARIA labelling:** the inner `<div role="img">` carries `aria-labelledby`
  pointing at both the visible title id and the sr-only description id. The outer
  `<figure>` does NOT use `aria-labelledby` — it derives its accessible name
  natively from `<figcaption>`. This avoids duplicate announcements in screen
  readers.
- `.mneme-diagram__sr-desc` is screen-reader-only.
- `.diagram-figure` and `.diagram-caption` chrome is shared with the legacy
  SVG diagrams and must not be modified.

---

## Color roles

Every node belongs to exactly one role. Roles are documented choices on top
of the existing theme tokens (`--accent`, `--teal`, etc.). No new `:root`
variables are introduced.

| Role | Stroke / border | Fill | Used for |
|---|---|---|---|
| **Source** | `--teal` | `rgba(139, 224, 200, 0.05)` | Origin of truth: ADR, decision, intent. |
| **Active** | `--accent`, 1.5px | `rgba(200, 240, 96, 0.05)` | Compiled, on-path, governance-touched. |
| **Gate** | `--accent` | solid `--accent`, dark text | Hard enforcement points only. Reserved. |
| **Neutral** | `--border2` | `--surface` | Passive consumers / endpoints. |
| **Muted** | `--border`, dashed | `--surface` | Drift, divergence, observation-only. |

Solid accent fills are reserved for genuine hard enforcement gates (CI merge
check, pre-tool-use hook). Do not use solid accent for general active-path
nodes.

---

## Typography

- **Eyebrow** (one per primitive): DM Mono, 0.68rem, uppercase, letter-spacing
  0.08–0.1em, color `--muted`.
- **Node title**: Inter, 0.85rem, weight 600, color `--text`.
- **Node sub-label**: DM Mono, 0.66–0.7rem, color `--muted` (or the role
  color when the sub-label is itself a verdict / output).
- **Caption**: stays on the shared `.diagram-caption` class — do not restyle.

If the 0.66rem sub-label fails contrast or feels visually weak, raise the
size; do not introduce new colors.

---

## Connectors

- 1–1.5px borders or pseudo-elements, color-matched to the role.
- No diagonal lines. Fan-outs use a vertical bus + horizontal stubs.
- Arrow glyphs use literal `→` `←` `↑` `↓` characters (not images), so they
  are selectable, indexable, and accessible.

---

## Accessibility

- `role="img"` on the wrapper.
- `aria-labelledby` references both visible title and screen-reader-only
  description IDs.
- All visible text is real HTML, not images or SVG `<text>`.
- DOM order matches visual reading order at all widths.
- WCAG AA contrast at smallest type sizes.
- No keyboard interaction, no focus order. Primitives are static.
- No information by color alone: every role-tinted node has a textual label.

---

## Motion

None. No transitions, no hovers, no animations.

---

## Responsive

- Test widths: 360px, 640px, 768px, 1024px+.
- Collapse breakpoint: `@media (max-width: 640px)`.
- No horizontal scroll. No overflow on `.mneme-diagram`.
- Truncation that loses meaning is a bug; raise the breakpoint or restructure.

---

## CSS scoping invariant

Every selector in `diagrams.css` must either:

1. Be scoped under `.mneme-diagram`, or
2. Target a class that only appears inside `.mneme-diagram` markup.

No bare element selectors, no global resets. The `.mneme-diagram` wrapper is
the firewall against style bleed into the rest of the page.

---

## No invented capabilities

Every node label must correspond to a real Mneme surface, integration page,
or product feature. If a label cannot be sourced, reword it generically
("Source decision," "Example ADR") or drop it. ADR identifiers must be real
IDs from `docs/adr/` — no fake `ADR-NNNN` placeholders.

---

## Adding a new diagram

1. Check if an existing primitive fits. If so, embed it (markup + stylesheet
   link). Do not author new CSS.
2. If a new shape is needed, prefer extending an existing primitive over
   creating a new one. Discuss before adding a fifth primitive.
3. New CSS must follow the scoping invariant and use existing theme tokens.

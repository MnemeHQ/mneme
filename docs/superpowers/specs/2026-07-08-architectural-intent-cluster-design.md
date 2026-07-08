# Design: "Maintaining architectural intent, agent-first" cluster consolidation

**Date:** 2026-07-08
**Branch:** `site/architectural-intent-cluster`
**Origin:** Bing grounding report — strongest grounding theme is *"Maintaining architectural intent, agent-first workflow."* Report recommended building a 6-page cluster around it.

## Key finding that reframes the task

All 6 titles the report proposed already have strong live pages. Building them fresh would cannibalize existing pages for the same queries. The raw content is ~95% published. What is missing is the **cluster signal**: a dedicated landing surface carrying the winning phrase, and a tight reciprocal internal mesh so search engines and LLMs read the ~9 pages as one authoritative cluster.

Mapping of report titles to existing pages:

| Report's proposed title | Existing page(s) |
|---|---|
| Agent-first IDEs need architectural invariants | `agent-first-ides-need-architectural-invariants` (exact) |
| Why Cursor Rules are not enough for architectural intent | `mneme-vs-cursor-rules` |
| AI coding agents and architecture drift | `why-context-alone-doesnt-prevent-architectural-drift`, `constraint-decay-coding-agents-architectural-governance` |
| Architectural guardrails for agent-first engineering teams | `ai-coding-agent-guardrails` (flagship) |
| What breaks when AI agents lose project intent | `ai-native-engineering-intent-debt`, `shared-memory-is-not-shared-intent` |
| How to maintain architectural intent with AI coding agents | *(no dedicated how-to — this is the one real gap)* |

## Goal (user-confirmed)

Do **both**: build the cohesion layer (hub + mesh) **and** write the one genuinely missing how-to page. No duplicate thesis pages.

## Scope

### 1. New topic hub — `/insights/topics/architectural-intent/`

- **Title / H1 / URL** carry the winning phrase: **"Maintaining Architectural Intent in Agent-First Workflows."** This gives Bing an exact-match landing node it lacks today (the theme is currently split across the `architectural-governance` and `ai-coding-agents` hubs).
- **Cornerstone (user-confirmed):** the new how-to page, co-anchored by `agent-first-ides-need-architectural-invariants`.
- **Curated supporting set** — the existing pages that *are* this theme:
  - `agent-first-ides-need-architectural-invariants`
  - `models-are-temporary-architectural-intent-is-not`
  - `mneme-vs-cursor-rules`
  - `why-context-alone-doesnt-prevent-architectural-drift`
  - `constraint-decay-coding-agents-architectural-governance`
  - `ai-coding-agent-guardrails`
  - `ai-native-engineering-intent-debt`
  - `shared-memory-is-not-shared-intent`
- **Scaffold:** clone an existing hub (`topics/architectural-governance/index.html`, 862 lines). Keep global `<nav>`, `<footer>`, `<style>`, sticky-nav `<script>` byte-identical (nav-footer-check + sticky-nav-check are strict). Rewrite only: `<title>`, meta, CollectionPage JSON-LD (`hasPart` = the 9 members), BreadcrumbList JSON-LD, `<h1>`, `.hub-intro`, and the card grid.
- Hubs are auto-discovered by `check_insights.py` (`index_surfaces()` iterates `topics/`), so the new hub registers as an approved index surface with no validator change.

### 2. The gap page — `/insights/how-to-maintain-architectural-intent-with-ai-coding-agents/`

- **Distinct how-to intent** (all existing pages are thesis / report-response; none is a practical guide). This is the one non-cannibalizing new page.
- Clone a recent article exemplar (`ai-coding-agent-verification-tax/`). House voice: concrete, declarative, no "bottleneck", no em-dash-as-connective-tissue.
- Body answers the contract's five questions (what changed / why it matters / what breaks / what to do / how governance helps), includes a Record→Retrieve→Check→Reject→Return worked loop, a 4-item FAQ (`<details>`), accessible teal underlined `.article-body a` links, and at least one bottom-funnel link (`/demo/`, `/pilot/`, or `/use-cases/...`).
- One authoritative outbound reference, cited once.

### 3. The mesh (user-confirmed: full 9-page reciprocal)

- Every cluster member links **up** to the new hub, and reciprocal `related-essays` `<li>` links are added **into** each of the 8 existing pages pointing to the new how-to and to 1–2 sibling cluster members, matching each file's own related-list markup.
- The new how-to's `related-essays` panel links outward to 3–4 cluster siblings + 3–4 concepts.
- Target: every cluster member has ≥3 inbound internal links (the `check_insights` mesh WARN threshold).

## Registration (per `docs/site/insight-publishing-contract.md`)

**New hub:**
- Sitemap `<url>` entry for `/insights/topics/architectural-intent/`.
- Homepage (`site/insights/index.html`): add hub to the quick-links row (~line 391) **and** the topic-card grid (~line 536).
- Breadcrumb nav + BreadcrumbList JSON-LD (Home → Insights → Architectural intent).
- OG image: `topics/architectural-intent/og.png` via `ensure_og_coverage.py` + targeted Playwright render (never the full `generate_og_images.py`).

**New how-to page (all 9 contract checks):**
- Sitemap entry; card on `all/` archive **and** the new hub; `hasPart` entry in the `all/` CollectionPage; local `og.png`; resolving `og:image` + `twitter:image`; breadcrumb nav + BreadcrumbList JSON-LD (3 items); TechArticle JSON-LD (url == canonical, non-empty headline); ≥1 inbound internal link.

## Validation gate

All must pass before PR:
- `python scripts/check_insights.py` → exit 0 (and close mesh/funnel WARNs)
- `check_nav_footer.py`, `check_sticky_nav.py`, `check_encoding.py` (UTF-8 no BOM, preserve CRLF)

## Out of scope / guardrails

- **No** new duplicate thesis pages (only the one how-to page is new).
- No `.mneme/project_memory.json` edits (not a `[memory]` task).
- No unrelated refactoring of existing hubs or articles beyond the additive mesh links.
- Branch `site/architectural-intent-cluster`; squash-merge; taxonomy-compliant PR title.

## Success criteria

1. `/insights/topics/architectural-intent/` is live, carries the winning phrase in title/H1/URL, and cards all 9 members.
2. The how-to page is live, fully registered, passes all validators.
3. Each of the 9 members has ≥3 inbound internal links and links up to the hub.
4. Zero validator failures; zero duplicate-intent pages created.

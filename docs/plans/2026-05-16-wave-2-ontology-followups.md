# Wave 2 — Ontology Follow-ups

**Status:** plan, ready to execute on a fresh branch
**Anchor commit:** wave-1 squash on `main` (article + graph wiring + runtime-stack ontology)
**Authority source:** `docs/adr/`, `.mneme/project_memory.json`, `CLAUDE.md`

---

## Copy-pasteable kickoff prompt

> Execute Wave 2 of the harness-engineering governance ontology rollout, per `docs/plans/2026-05-16-wave-2-ontology-followups.md`.
>
> Wave 1 (already merged) added the canonical article at `site/insights/harness-engineering-still-needs-governance/`, wired it bidirectionally with concept pages, made it the hub of the harness -> governance cluster, and codified the runtime stack (Models -> Harnesses -> Execution -> Governance -> Verification) on `site/concepts/governance-infrastructure/` and the execution-surfaces enumeration on `site/concepts/governance-propagation/`.
>
> Wave 2 has three deliverables, each on its own branch and PR per `CLAUDE.md` taxonomy:
> 1. `site/architecture/` — surface the runtime stack as a first-class section/diagram.
> 2. `site/works-with/` and integration pages — refresh framing to harness-complementary, drop any memory/RAG-replacement positioning.
> 3. New lightweight positioning ADR — codify harness-complementary vocabulary so it cannot drift.
>
> Read the full plan in `docs/plans/2026-05-16-wave-2-ontology-followups.md` before touching anything. Follow each section's in-scope / out-of-scope strictly. Run `mneme check --mode warn` before finalizing each PR per `CLAUDE.md`. Do not bundle the three deliverables into a single PR — they have different review surfaces.

---

## 1. Context

Wave 1 established the harness-engineering -> governance worldview at the article and concept-page level. It is now visible to readers who land on `/insights/harness-engineering-still-needs-governance/` or on `/concepts/governance-infrastructure/`. It is not yet visible to readers who land on `/architecture/` or `/works-with/`, and it is not yet codified as a positioning rule, which means future contributors can drift the vocabulary back toward memory/RAG framing without violating any explicit decision.

Wave 2 closes those three gaps. It is *not* about adding more content. It is about making the runtime stack — `Models -> Harnesses -> Execution -> Governance -> Verification` — the default abstraction that every Mneme surface reaches for.

---

## 2. Deliverable 1 — `/architecture/` runtime-stack surfacing

**Branch:** `site/architecture-runtime-stack` (taxonomy per `CLAUDE.md`)
**Squash-merge title:** `site(architecture): surface runtime stack and governance layer`

### In scope

- Read the current state of `site/architecture/index.html` (and any sub-pages under `site/architecture/`) and identify where the page currently positions Mneme in the stack.
- Add a prominent "Runtime stack" section that mirrors the layer model from `site/concepts/governance-infrastructure/` (the `.layer-stack` component, governance highlighted).
- If the page has an existing stack diagram, update it so governance is its own layer between execution and verification — not folded under "memory," "context," "retrieval," or "tooling."
- Cross-link the section to `/insights/harness-engineering-still-needs-governance/` and `/concepts/governance-infrastructure/`.
- Match the existing visual language of the page; do not introduce new component patterns.

### Out of scope

- Rewriting unrelated sections of `/architecture/`.
- Adding new SVG diagrams beyond what is needed to depict the layer model.
- Changing the page's information architecture (nav, breadcrumb, sitemap structure).
- Editing `site/insights/` or `site/concepts/` — those landed in Wave 1.

### Acceptance

- A reader landing on `/architecture/` from a search or AI crawler can read the page top-to-bottom and walk away with the runtime stack as the dominant mental model.
- The page does not contain residual phrasing that positions Mneme primarily as memory, RAG, or a context layer.

---

## 3. Deliverable 2 — `/works-with/` and integration pages

**Branch:** `site/works-with-harness-complementary`
**Squash-merge title:** `site(works-with): reframe integrations as harness-complementary`

### In scope

- Audit `site/works-with/index.html` and every integration sub-page under `site/integrations/` (Claude Code, Cursor, Copilot, LangGraph if present, OpenAI Agents, Warp, etc.).
- For each integration page that mentions an agent runtime or harness, add a one-line framing along the lines of:
  *"<Tool> coordinates execution. Mneme enforces architectural intent. They run side by side."*
  Adapt the wording to fit each page's voice; do not paste the same sentence eight times.
- Remove or revise any phrasing that positions Mneme as a memory replacement, RAG alternative, or context-management tool relative to these integrations.
- Cross-link at least one integration page (the most-trafficked one) to `/insights/harness-engineering-still-needs-governance/`.

### Out of scope

- Adding new integration pages.
- Restructuring `/works-with/` or `/integrations/` index pages beyond copy edits.
- Renaming integrations or changing logo/asset references.
- Editing pricing, contact, or pilot pages.

### Acceptance

- Every integration page reads as "we work alongside this harness" rather than "we replace this tool's memory."
- A user who lands on, say, `/works-with/claude-code/` understands within the first 200 words that Mneme is a separate layer running beside Claude Code, not inside or instead of it.

---

## 4. Deliverable 3 — Positioning ADR amendment

**Branch:** `docs/adr-positioning-harness-complementary`
**Squash-merge title:** `docs(adr): codify harness-complementary positioning vocabulary`

### In scope

- Create a new ADR (next available ADR-NNN number; check `docs/adr/` for the highest existing number).
- The ADR's job is narrow: codify the runtime-stack vocabulary so contributors cannot drift positioning back toward memory/RAG framing.
- Required content:
  - **Context** referencing wave 1: the harness-engineering article, the governance-infrastructure stack section, the execution-surfaces enumeration.
  - **Decision** listing the canonical layer names (Models, Harnesses, Execution systems, Governance infrastructure, Verification / enforcement) and naming them as the default framing.
  - **Prohibitions** explicitly stating that positioning Mneme as "memory," "RAG," "prompt engineering," "coding assistant tooling," or "agent context layer" is non-compliant with this ADR.
  - **Compliance** rule: any new content surface (insights article, concept page, integration page, marketing copy) must use the runtime-stack vocabulary as the default and explicitly justify any deviation.
- Cross-reference ADR-001 (positioning), ADR-004 (brand name), ADR-006 (insights SEO), ADR-010 (automation artifact governance) where relevant.

### Out of scope

- Superseding any existing ADR. This is additive, not corrective.
- Defining new product capabilities or roadmap items.
- Touching `.mneme/project_memory.json` (that requires a `[memory]` task per `CLAUDE.md`).
- Renaming concepts that already exist as concept pages.

### Acceptance

- Running `mneme check --mode warn` after the ADR lands shows the ADR is parsed as an active decision with no conflicts.
- The ADR is short — under 150 lines — and reads as a vocabulary lock, not a strategy document.

---

## 5. Sequencing

These three deliverables are independent and can be executed in parallel or any order. Recommended order if executed sequentially:

1. ADR amendment first (cheapest, locks vocabulary before the other two land).
2. `/architecture/` (high-traffic surface, biggest visible payoff).
3. `/works-with/` (longest tail; can be batched with other integration-page work later).

Each lands as its own PR. Do **not** bundle them — they have different review surfaces and different rollback risk profiles.

---

## 6. Operational notes

- Branch names must follow `CLAUDE.md` taxonomy (`feat/`, `fix/`, `site/`, `ci/`, `docs/`, `refactor/`). The auto-generated `claude/<adj>-<noun>-<hash>` worktree branch form is acceptable during development but the squash-merge title on `main` must follow the taxonomy regardless.
- Run `mneme check --mode warn` before finalizing each PR. After the ADR lands, run `mneme check --mode strict` to confirm the new vocabulary rule does not retroactively break any existing page.
- Keep each PR narrowly scoped per `CLAUDE.md`. If an integration page audit uncovers a structural bug, file it separately rather than fixing in-line.
- Do not modify `.mneme/project_memory.json`. Do not tag (per the tag policy in `CLAUDE.md`).
- The harness-engineering article and Wave 1 commits are the canonical references for vocabulary and framing — when in doubt, copy the phrasing from there.

---

## 7. Out-of-scope for Wave 2 (deferred to Wave 3+)

- LinkedIn synthesis post (out-of-repo, separate GTM workstream).
- Vocabulary tracker / terminology audit doc (separate `docs/` PR if/when needed).
- Future article candidates from the harness -> governance cluster ("Observability Is Not Enforcement," "Agent Runtimes Need Verification Contracts," etc.) — separate insights PRs per ADR-006.
- `/concepts/` index page re-ordering. Cosmetic and low-leverage relative to Wave 2.
- Footer "Learn" column expansion or a new `/stack/` landing page. Only worth doing once Wave 2 ships and the runtime stack is canonically defined on `/architecture/` and `/concepts/governance-infrastructure/`.

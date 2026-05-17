# Wave 3 — Ontology Follow-ups

**Status:** plan stub, not yet scheduled
**Anchor commit:** Wave 2 completion (`b357d33` on `main`)
**Authority source:** `docs/adr/`, `.mneme/project_memory.json`, `CLAUDE.md`
**Predecessor:** `docs/plans/2026-05-16-wave-2-ontology-followups.md` (executed) + `docs/plans/2026-05-17-wave-2-completion.md` (report)

---

## 1. Context

Wave 2 made the runtime stack (`Models → Harnesses → Execution → Governance → Verification`) the default mental model on `/architecture/`, reframed integrations as harness-complementary on `/works-with/`, and locked the vocabulary against drift via ADR-011. The harness-engineering article remains the canonical reference for vocabulary and framing.

Wave 3 is the consolidation wave. It is not about adding new positioning — it is about closing structural gaps surfaced once Wave 2 was in place, retiring inherited tech debt, and queueing the next cornerstone article without rushing it.

Each deliverable below is independently shippable. Estimated effort and rollback risk are listed so the wave can be sequenced or partially executed without losing coherence.

---

## 2. Deliverable 1 — Renumber duplicate ADR-010

**Branch:** `docs/renumber-duplicate-adr`
**Squash-merge title:** `docs(adr): renumber duplicate ADR-010 to ADR-012`
**Effort:** small. **Rollback risk:** low.

### In scope

- Two files currently share `ADR-010`:
  - `docs/adr/ADR-010-automation-artifact-governance.md` (older; landed via commit `9a2c056`)
  - `docs/adr/ADR-010-external-platform-presence-standards.md` (newer; landed via commit `87e5ec5`)
- Renumber the **newer** one (`external-platform-presence-standards`) to `ADR-012` so existing `automation-artifact-governance` cross-references in `CLAUDE.md` and ADR-011 remain valid.
- Update any in-repo links that point at the renumbered ADR file. Grep `docs/`, `site/`, `.mneme/` for the old filename.
- Update ADR-011 cross-reference if it points at the renumbered ADR.

### Out of scope

- Content edits to either ADR. This is a renumber, not a revision.
- Renumbering ADR-001 through ADR-009.
- Altering the ADR template or numbering policy.

### Acceptance

- `ls docs/adr/` shows no duplicate numbers.
- Grep for the old filename returns zero hits.
- `mneme check --mode warn` (CI workflow) is clean on the PR.

---

## 3. Deliverable 2 — `/concepts/` index re-ordering

**Branch:** `site/concepts-index-ordering`
**Squash-merge title:** `site(concepts): reorder index to lead with runtime stack`
**Effort:** small. **Rollback risk:** very low.

### In scope

- Read `site/concepts/index.html` and confirm current ordering of concept cards.
- Re-order so `governance-infrastructure` and `governance-propagation` lead the index, followed by adjacent concepts in the harness → governance cluster.
- Preserve all existing cards; this is reordering, not pruning or adding.
- Match existing visual language; no new component patterns.

### Out of scope

- Adding new concept pages.
- Rewriting existing concept descriptions.
- Restructuring the page (nav, breadcrumb, sitemap stay).

### Acceptance

- A first-time visitor to `/concepts/` encounters the runtime-stack concepts above the fold.
- No visual regressions on mobile (concepts index has historically been responsive-tight).

---

## 4. Deliverable 3 — Vocabulary tracker doc

**Branch:** `docs/vocabulary-tracker`
**Squash-merge title:** `docs: add vocabulary tracker for harness-complementary positioning`
**Effort:** small-to-medium. **Rollback risk:** low.

### In scope

- New file at `docs/vocabulary-tracker.md`.
- Enumerate the canonical terms from ADR-011: `Models`, `Harnesses`, `Execution systems`, `Governance infrastructure`, `Verification / enforcement`, `harness-complementary`, `architectural intent`, `execution surface`, `governance propagation`.
- For each term: definition (one sentence), the canonical page where it is introduced, and the non-compliant alternatives that should not be used in its place.
- Reference ADR-011 as the source of truth. This doc is a quick-lookup table for contributors, not a parallel decision document.

### Out of scope

- Defining new vocabulary. If a term is not already in ADR-011 or on a concept page, it does not belong in this tracker.
- Style-guide concerns (sentence casing, hyphenation, etc.) — those go in a separate style PR if needed.
- Translation or localization.

### Acceptance

- Doc is under 100 lines and reads as a reference card, not an essay.
- Every term traces back to either ADR-011 or an existing `/concepts/*` page.

---

## 5. Deliverable 4 — Footer "Learn" expansion or `/stack/` landing page

**Branch:** `site/stack-landing` (if landing) or `site/footer-learn-expansion` (if footer-only)
**Squash-merge title:** depends on chosen path
**Effort:** medium. **Rollback risk:** low for footer; medium for landing page.

### Open decision

Two paths. Pick one before branching:

- **Path A — footer expansion.** Add a "Stack" or "Runtime stack" section to the site footer's Learn column linking to `/architecture/`, `/concepts/governance-infrastructure/`, and `/concepts/governance-propagation/`. Lowest effort. Lowest visibility lift.
- **Path B — new `/stack/` landing page.** A standalone page that names the runtime stack as a category, with the layer diagram and one-paragraph descriptions of each layer, cross-linking into the concept pages and the harness-engineering article. Higher effort. Highest payoff for AI-crawler indexing of the stack vocabulary.

The Wave 2 plan §7 noted Path B is "only worth doing once Wave 2 ships and the runtime stack is canonically defined on `/architecture/` and `/concepts/governance-infrastructure/`" — Wave 2 has now shipped, so Path B is unblocked.

### Acceptance (Path B)

- `/stack/` exists, is canonical, and is linked from the nav or footer.
- The page's layer diagram matches the one on `/architecture/` and `/concepts/governance-infrastructure/` — visual consistency is the whole point.
- No new vocabulary introduced. The page is a synthesis surface, not a positioning surface.

---

## 6. Deliverable 5 — Next insights article (single choice)

**Branch:** `site/insights-<slug>`
**Squash-merge title:** `site(insights): add <article title>`
**Effort:** medium. **Rollback risk:** low.

The Wave 2 plan §7 listed two candidate next-articles from the harness → governance cluster:

- *Observability Is Not Enforcement.* Shortest path. Sequels the harness-engineering article directly. Strongest evidence base (provenance/policy/OPA + the scalable-oversight literature).
- *Agent Runtimes Need Verification Contracts.* Higher ambition. Bridges harness-engineering to the verification layer of the runtime stack. Requires more original synthesis.

Pick **one** for Wave 3. The other carries forward to Wave 4. Do **not** ship both in the same wave.

A third candidate now exists (see §7 below) but is explicitly out of Wave 3 scope.

### Acceptance

- Conforms to ADR-006 (insights SEO requirements).
- Lands in `/insights/` with the standard article template.
- Cross-links into `/concepts/governance-infrastructure/` and `/insights/harness-engineering-still-needs-governance/`.
- `mneme check --mode warn` is clean on the PR (CI workflow).

---

## 7. Out of scope for Wave 3 (deferred to Wave 4+)

- **"Agentic Governance Architecture" cornerstone article.** Source-audited 2026-05-17; the underlying synthesis is well-substantiated by primary sources (Bowman scalable-oversight, OpenAI/Anthropic harness primary sources, SLSA/in-toto/NIST AI RMF/C2PA/OPA), but the bare term "agentic governance" is vendor-saturated (IBM, Palo Alto, Attentive, `agenticgovernance.net`). Article must foreground "Architecture" in the title and open with explicit differentiation from runtime-behavior-control framings. Brief is parked in `mneme-growth-ops` (`article-briefs/agentic-governance-architecture.md`). Hold publish until at least one more public harness-era milestone lands, so the piece reads as observing a shift, not predicting one. Reassess inclusion in Wave 4 or Wave 5.
- **LinkedIn synthesis post** off the harness-engineering article. Out-of-repo GTM workstream tracked in `mneme-growth-ops`.
- **Mode-strict rollout for `mneme check`.** Deferred per `.mneme/README.md` §Rollout — applied only after 2-3 weeks of clean warn-history. Tracked outside the wave plans.
- **`/persona/`-buyer page refresh.** Adjacent surface, lower priority than the deliverables above.

---

## 8. Sequencing

The five Wave 3 deliverables are independent and can be executed in parallel or any order. Recommended sequential order if executed one at a time:

1. **D1 (ADR renumber)** — cheapest, removes inherited tech debt before anything else lands.
2. **D3 (vocabulary tracker)** — locks the lookup surface; cheap.
3. **D2 (concepts re-order)** — cheap visible win.
4. **D4 (stack landing, Path B if chosen)** — biggest indexing payoff once the rest is settled.
5. **D5 (next insights article)** — the one with the longest tail and the most editorial care.

Each lands as its own PR. Do not bundle.

---

## 9. Operational notes

- Branch names must follow `CLAUDE.md` taxonomy. The auto-generated `claude/<adj>-<noun>-<hash>` worktree form is acceptable during development but the squash-merge title on `main` must follow the taxonomy regardless.
- `mneme check --mode warn` runs automatically via `.github/workflows/mneme-check.yml` on every PR. No manual invocation needed.
- Do not modify `.mneme/project_memory.json`. Do not tag (per `CLAUDE.md` tag policy).
- The harness-engineering article and ADR-011 are the canonical references for vocabulary and framing — when in doubt, copy phrasing from those.
- Keep each PR narrowly scoped per `CLAUDE.md`.

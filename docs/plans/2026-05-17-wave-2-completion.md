# Wave 2 — Ontology Rollout Completion Report

**Status:** complete
**Anchor commit on `main`:** `b357d33` (2026-05-17)
**Plan of record:** `docs/plans/2026-05-16-wave-2-ontology-followups.md`

---

## 1. Summary

All three Wave 2 deliverables shipped as independent PRs on `main`, each with a taxonomy-compliant squash title. The runtime stack (`Models → Harnesses → Execution → Governance → Verification`) is now the default mental model on `/architecture/`, the integration surface reads as harness-complementary rather than memory/RAG-adjacent, and the positioning vocabulary is locked by ADR-011 against drift.

## 2. Deliverables

| # | Deliverable | Branch (dev) | PR | Squash commit | Title on `main` |
|---|---|---|---|---|---|
| D1 | `/architecture/` runtime-stack surfacing | `site/architecture-runtime-stack` | #90 | `b6978b5` | `site(architecture): surface runtime stack and governance layer` |
| D2 | `/works-with/` + integrations reframe | `site/works-with-harness-complementary` | #91 | `4e99b28` | `site(works-with): reframe integrations as harness-complementary` |
| D3 | Positioning vocabulary ADR | `docs/adr-positioning-harness-complementary` | #89 | `92338ac` | `docs(adr): codify harness-complementary positioning vocabulary` |

Plus one Wave-1 hygiene follow-up shipped alongside Wave 2:

| # | Deliverable | PR | Squash commit |
|---|---|---|---|
| H1 | Retarget broken OpenAI link in harness-engineering article | #92 | `b357d33` — `fix(insights): retarget OpenAI link to harness-engineering post` |

## 3. Acceptance verification

### D1 — `/architecture/`

- New `Runtime stack` section landed with the governance layer rendered between execution and verification, matching the `.layer-stack` component on `/concepts/governance-infrastructure/`.
- No residual memory/RAG framing on the page (grep audit clean).
- Cross-links present to `/insights/harness-engineering-still-needs-governance/` and `/concepts/governance-infrastructure/`.

### D2 — `/works-with/` + integrations

Audit run 2026-05-17 across `site/integrations/*/index.html`:

| Page | Harness-complementary phrasing hits | Notes |
|---|---|---|
| `claude-agent-sdk/` | 4 | strongest coverage |
| `claude-code/` | 3 | |
| `github-actions/` | 2 | |
| `gitlab/` | 2 | |
| `jetbrains/` | 2 | |
| `copilot/` | 1 | |
| `cursor/` | 1 | |
| `perplexity/` | 1 | |
| `vscode/` | 0 (lexical) | semantically harness-complementary: "Mneme HQ governs the AI agent running inside the editor, not the editor itself." Acceptance met. |
| `adr-import/` | 0 | not an agent runtime/harness — D2 does not apply |

Residual memory/RAG framing: **none**. Two grep hits in `claude-code` and `claude-agent-sdk` resolved to CTAs pointing at `/insights/prompt-engineering-is-not-governance/` — that is the *anti*-prompt-engineering link, on-message.

### D3 — ADR-011

- File: `docs/adr/ADR-011-harness-complementary-positioning-vocabulary.md`
- Length: 134 lines (under the 150-line cap in the plan).
- Status: active decision; cross-references ADR-001, ADR-004, ADR-006, and ADR-010.
- Prohibition language present: positions Mneme as "memory," "RAG," "prompt engineering," "coding assistant tooling," or "agent context layer" are explicitly non-compliant.

## 4. `mneme check` status

The plan called for `mneme check --mode warn` per PR and `mneme check --mode strict` after the ADR landed. Resolution:

- **Warn mode is automated.** `.github/workflows/mneme-check.yml` runs `python -m mneme.cli check --memory .mneme/project_memory.json --input <changed-file> --query "${PR_TITLE} ${file}" --mode warn` on every PR touching repo-governance paths. PRs #89, #90, #91 went through this gate at merge time. The plan's bare `mneme check --mode warn` invocation was shorthand for this workflow; no manual invocation was needed or possible without filling in the per-file `--input` and `--query` arguments.
- **Strict mode is deferred by design.** `.mneme/README.md` §Rollout (line 75): *"We will tighten to `--mode strict` only after 2-3 weeks of clean warn runs."* The plan's "run strict after the ADR lands" instruction is superseded by this rollout schedule and should be retired from future wave plans.

## 5. Pre-existing tech debt surfaced

Not in Wave 2 scope, flagged for triage:

- **Duplicate ADR-010 number.** Two files share `ADR-010`:
  - `docs/adr/ADR-010-automation-artifact-governance.md` (commit `9a2c056`)
  - `docs/adr/ADR-010-external-platform-presence-standards.md` (commit `87e5ec5`)

  Both predate Wave 2. One needs to be renumbered, or the conflict acknowledged in a small docs PR. Since ADR-011 already exists, the renumbered ADR would become ADR-012.

## 6. Wave 3 carryover

Items deferred from §7 of the Wave 2 plan, plus one new addition. Detailed scoping lives in `docs/plans/2026-05-17-wave-3-followups.md`:

- Vocabulary tracker / terminology audit doc.
- `/concepts/` index re-ordering.
- Footer "Learn" column expansion or a new `/stack/` landing page.
- Future article candidates from the harness → governance cluster ("Observability Is Not Enforcement," "Agent Runtimes Need Verification Contracts").
- **New:** "Agentic Governance Architecture" cornerstone-class article. Source-audited 2026-05-17; substantiated synthesis of established primitives. Brief parked in `mneme-growth-ops` per `CLAUDE.md` GTM rule; not the next article — held for category positioning.

Out-of-repo (GTM workstream, tracked in `mneme-growth-ops`, not here):

- LinkedIn synthesis post off the harness-engineering article.
- Article-brief artifact for the agentic-governance-architecture cornerstone.

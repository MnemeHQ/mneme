---
id: ADR-013
title: "External Platform Presence Standards"
status: accepted
priority: normal
date: 2026-05-14
scope: distribution.external_platforms
---

# ADR-013: External Platform Presence Standards

> Note: this ADR was originally numbered ADR-010 and was renumbered to ADR-013
> during the 2026-05-26 legacy-ADR normalization pass (see PR following
> [issue #139](https://github.com/mnemeHQ/mneme/issues/139)). The original
> ADR-010 number now belongs to "Automation-generated artifacts must inherit
> repository governance conventions"; this ADR's content is unchanged.

**Status:** Accepted  
**Date:** 2026-05-14  
**Deciders:** Theo Valmis

---

## Context

Mneme is now listed or submitted to multiple external platforms: GitHub awesome-lists, AI tool
directories, and developer community sites. Without a canonical record of approved copy and metadata,
future submissions will drift from the positioning established in ADR-001 — either by using
inconsistent descriptions, wrong category labels, or outdated topic tags.

This ADR locks the canonical GitHub repository metadata and the two approved external copy variants.
Distribution tracking (which lists were submitted, PR status, directory submission log) lives in
the private `mneme-growth-ops` repo per ADR-002 and is not governed here.

---

## Decisions

### 1. GitHub repository metadata

**Description** (must match exactly):

```
Enforce architectural decisions in AI-assisted development.
```

**Topics** (exactly these 10, in any order):

```
claude-code
cursor
ai-governance
software-architecture
architectural-decision-records
developer-tools
llm
ai-coding
code-review
coding-agents
```

Topics are reviewed when a new major integration ships or a meaningfully higher-traffic term
emerges in the ecosystem. Changes require updating this ADR.

---

### 2. Approved external copy variants

Two variants are approved. Choose based on the list's audience.

**Variant A — Claude Code / Cursor / agent-focused lists:**

> Enforce architectural decisions on every AI coding assistant call. Deterministic retrieval and
> pre-flight governance for Claude Code, Cursor, and agent workflows.

**Variant B — Broader AI devtool / vibe coding / general lists:**

> Architectural governance layer for AI-assisted development. Injects project decisions into LLM
> workflows and blocks architectural violations before generation.

**Variant C — Long-form (issue forms, directory submissions, 2–3 sentences):**

> Architectural governance layer for AI-assisted development. Deterministically retrieves relevant
> project decisions and injects them into every LLM call before generation; detects constraint and
> anti-pattern violations in generated output. Works with Claude Code, Cursor, and agent frameworks
> without requiring a vector store or ML dependencies.

Rules:
- No emojis in list entries.
- Do not address the reader ("you", "your") in list copy.
- Do not use promotional language ("powerful", "revolutionary", "best").
- Always link to the GitHub repo (`https://github.com/mnemeHQ/mneme`), not the marketing site,
  in awesome-list entries. Use the marketing site for directories that prefer landing pages.

---

### 3. Author attribution for submissions

- **Author name:** `mnemeHQ`
- **Author link:** `https://github.com/mnemeHQ`
- **License:** MIT

---

### 4. Category placement guidance

| List type | Preferred section |
|-----------|------------------|
| Claude Code lists | Tooling |
| Cursor lists | Tooling / Developer Tools |
| AI coding tool lists | Developer Productivity Tools |
| Vibe coding lists | CLI Tools |
| General Claude lists | Claude Code section |
| AI directories | Developer Tools / Code Governance |

---

## Rationale

- Locking copy variants prevents positioning drift across submissions (ADR-001 compliance).
- Locking topics prevents ad-hoc changes that reduce discoverability.
- The two-variant model matches real list taxonomy: Claude/Cursor lists want agent-focused framing;
  broader lists want the governance-layer framing.
- Distribution tracking stays in growth-ops (ADR-002) — this ADR only governs what is said,
  not where it was said.

---

## Consequences

- Any new awesome-list or directory submission must use one of the three approved copy variants.
- GitHub topic changes require amending this ADR.
- The marketing site description and og:description are governed separately by ADR-001 and ADR-003;
  this ADR governs only external third-party platform copy.

---

## Related

- ADR-001: Mneme HQ Positioning and Messaging Rules
- ADR-002: Repository Boundary for Internal Operational Tooling
- ADR-003: Site Publishing Guidelines
- `mneme-growth-ops/distribution/backlink-plan.md` — submission tracker
- `mneme-growth-ops/distribution/ai-directories.md` — directory targets

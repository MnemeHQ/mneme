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
> [issue #139](https://github.com/TheoV823/mneme/issues/139)). The original
> ADR-010 number now belongs to "Automation-generated artifacts must inherit
> repository governance conventions"; this ADR's content is unchanged.
>
> Amended 2026-08-24 (positioning-only): primary external category moved to
> "architectural drift prevention for the AI SDLC" (mechanism language —
> architectural governance / deterministic guardrails — retained but demoted),
> canonical repository URL updated to `https://github.com/MnemeHQ/mneme`,
> GitHub description refreshed, and copy variants replaced. No architecture,
> freeze, or integration-status changes.
>
> Amended 2026-08-25 (positioning-only): primary external category refined to
> "architectural drift prevention for the agentic AI SDLC" so `agentic` is an
> explicit category keyword. The mechanism, architecture, support taxonomy,
> topics, freeze, and integration-status claims are unchanged.

**Status:** Accepted  
**Date:** 2026-05-14  
**Amended:** 2026-08-25  
**Deciders:** Theo Valmis

---

## Context

Mneme is now listed or submitted to multiple external platforms: GitHub awesome-lists, AI tool
directories, and developer community sites. Without a canonical record of approved copy and metadata,
future submissions will drift from the positioning established in ADR-001 — either by using
inconsistent descriptions, wrong category labels, or outdated topic tags.

This ADR locks the canonical GitHub repository metadata and the three approved external copy variants.
Distribution tracking (which lists were submitted, PR status, directory submission log) lives in
the private `mneme-growth-ops` repo per ADR-002 and is not governed here.

The primary external category claim is **"Architectural drift prevention for
the agentic AI SDLC."** Architectural governance and deterministic guardrails describe
the mechanism by which drift prevention works; they are supporting language,
never the lead claim. External copy must not position Mneme primarily as agent
governance, AI security, or generic guardrails.

---

## Decisions

### 1. GitHub repository metadata

**Description** (must match exactly):

```
Architectural drift prevention for the agentic AI SDLC.
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

Three variants are approved. Choose based on the list's audience.

**Variant A — short/general lists:**

> Open-source architectural drift prevention for the agentic AI SDLC. Turns architectural decisions and ADRs into deterministic guardrails for AI-generated code.

**Variant B — coding-agent lists:**

> Architectural drift prevention for AI coding agents. Enforces repository decisions and ADRs through deterministic guardrails before incompatible changes are accepted.

**Variant C — Long-form (issue forms, directory submissions, 2–3 sentences):**

> AI coding agents start every call with no knowledge of the architectural decisions a team has already made, so they reintroduce rejected technologies and produce changes that contradict the architecture. Mneme prevents this architectural drift across the agentic AI SDLC: it turns architectural decisions and ADRs into deterministic guardrails applied at the earliest reliable boundary of an AI workflow — before generation, before supported file mutations via agent hooks, after bypassable mutations via working-tree audits, and before merge via CI gates. Enforcement is deterministic: same input, same verdict. Native integrations: Claude Code, Claude Agent SDK, Google Antigravity, Codex CLI. Validated compatibility: Paperclip. Cursor rules export and GitHub Actions/GitLab CI gates are also supported.

Rules:
- No emojis in list entries.
- Do not address the reader ("you", "your") in list copy.
- Do not use promotional language ("powerful", "revolutionary", "best").
- Always link to the GitHub repo (`https://github.com/MnemeHQ/mneme`), not the marketing site,
  in awesome-list entries. Use the marketing site for directories that prefer landing pages.

---

### 3. Author attribution for submissions

- **Author name:** `TheoV823`
- **Author link:** `https://github.com/TheoV823`
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
- The three-variant model matches real list taxonomy: general lists want the short
  category-led framing; coding-agent lists want the agent-enforcement framing;
  long-form forms need the problem-plus-mechanism explanation with support levels.
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

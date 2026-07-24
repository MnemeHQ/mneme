---
id: ADR-002
title: "Repository Boundary for Internal Operational Tooling"
status: accepted
priority: normal
date: 2026-05-01
scope: repo.boundary
---

# ADR-002: Repository Boundary for Internal Operational Tooling

**Status:** Accepted  
**Date:** 2026-05-01  
**Deciders:** Theo Valmis

---

## Context

As Mneme grows, internal operational tooling (growth automation, publishing workflows, marketing
infrastructure) will be built alongside the core OSS product. Without a clear boundary, this tooling
risks being committed to the public repository — exposing internal workflows, confusing contributors,
and diluting the product narrative.

This ADR establishes the rule that governs what belongs in the public Mneme repository.

---

## Decision

Internal operational, marketing, growth, and automation tooling must **not** be committed to the
public Mneme OSS repository unless it is explicitly productized or approved as a public
example/integration.

---

## Classification Framework

Before adding any tooling or code to the public repository, classify it:

| Category | Definition | Belongs in public repo? |
|----------|-----------|------------------------|
| **1. Core OSS Product** | Features, modules, or APIs that are the product | Yes |
| **2. Public Example / Approved Integration** | Demos, reference integrations, or examples useful to users — explicitly reviewed | Only if approved |
| **3. Internal / Private Operational Tooling** | Growth, marketing, automation, ops infrastructure | No — private repo only |

**Default rule:** If classification is unclear, treat as Category 3 and use a private repo.

---

## Rationale

- **OSS focus:** The public repo exists to ship and demonstrate the core product. Internal tooling
  is noise for contributors and users.
- **Workflow privacy:** Operational automation (social publishing, outreach, enrichment) encodes
  internal strategy and should not be publicly visible.
- **Contributor clarity:** External contributors should not encounter unrelated ops scripts when
  exploring the codebase.
- **Product narrative:** A clean public repo reinforces what Mneme is. Unrelated tooling muddies it.
- **Risk reduction:** Internal integration patterns, credentials structures, and automation workflows
  can leak sensitive information even without literal secrets present.

---

## Examples

**Category 3 — Internal tooling (private repo only):**
- Social media publishing automation (e.g. `mneme-linkedin-mcp`)
- Growth / marketing MCP servers
- Internal dashboards and analytics scripts
- Private enrichment or prospecting automation
- Outreach sequence tooling (validation targets, LinkedIn messages, CRM exports)
- Customer discovery materials (interview target lists, call notes, pain signal tracking)
- Internal ops runbooks with implementation detail

**Category 1 — Core OSS (public):**
- Mneme governance engine and policy enforcement
- MCP server interfaces for coding governance
- Decision enforcement layer
- Public SDK / API surface

**Category 2 — Approved public examples (case by case):**
- Reference integrations for common dev tools
- Example CLAUDE.md configurations
- Benchmark harnesses (if intentionally open)

---

## Consequences

- Internal tooling lives in private repositories (e.g. `mneme-growth-ops`)
- Any proposal to move Category 3 tooling into the public repo requires explicit productization
  review before merging
- New tooling must be classified before the first commit to any repository
- This ADR is itself enforced by Mneme's governance model — dogfooding the product

---

## Related

- ADR-001: Positioning and Messaging
- Private repo: [`mneme-growth-ops`](https://github.com/mnemeHQ/mneme-growth-ops) — internal tooling home  
  Local path: `/c/dev/mneme-growth-ops`  
  Scope: growth automation, outreach, validation research, LinkedIn content, customer discovery materials

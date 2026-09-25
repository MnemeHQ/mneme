---
id: ADR-001
title: "Mneme HQ Positioning and Messaging Rules"
status: accepted
priority: normal
date: 2026-05-03
scope: positioning
---

# ADR-001: Mneme HQ Positioning and Messaging Rules

## Status

Accepted — 2026-05-01 · Updated — 2026-05-03 · Amended — 2026-09-25

> Amended 2026-09-25 (positioning-only): the canonical company-level category
> moves from "the architectural governance layer for AI-assisted development"
> to **"the decision and control layer for agentic software development."**
> Architecture is the first supported decision domain, architectural drift
> prevention is the first public use case, and governance is an outcome or
> capability of Mneme, not its category name. Source strategy:
> `mneme-growth-ops/docs/plans/2026-09-25-decision-control-positioning-reposition.md`.
> No architecture, freeze, enforcement, retrieval, or integration-status
> change. The pre-amendment category and hero direction are kept below,
> marked as superseded, for history.

## Context

Mneme must be positioned distinctly within the emerging AI development governance market. Adjacent vendors are beginning to market governance, policy, and control features, but many operate downstream in software delivery or generic observability. Mneme's differentiation must remain tightly focused on architectural governance during AI-assisted development.

## Decision

Mneme will be positioned as **the decision and control layer for agentic software development**.

Messaging hierarchy (use in this order when space permits):

1. **Category** — the decision and control layer for agentic software development.
2. **Value** — make engineering decisions portable, enforceable, and inspectable across AI coding agents, repositories, and CI workflows.
3. **Current product proof** — Mneme starts with architecture: ADR-based decisions, applicability, deterministic rules, agent context, and decision-linked enforcement results.
4. **First use case** — prevent architectural drift before AI-generated code ships.

Terminology is fixed:

- **Decision and control layer** — what Mneme *is*.
- **Architecture protection / architectural drift prevention** — what Mneme does *first*. It remains the primary acquisition and distribution claim (see ADR-013).
- **Governance** — an outcome or capability Mneme provides. It is never the category name; do not use "governance layer" as a synonym for the category.

*Superseded 2026-09-25:* Mneme will be positioned as the architectural governance layer for AI-assisted development.

---

## Core Positioning

- Mneme is the decision and control layer for agentic software development.
- Architecture is the first supported decision domain. The decision model is designed to extend to broader engineering policy, but no other domain is shipped; do not describe security, compliance, platform, or operational-policy decisions as current capability.
- Mneme enforces prior engineering and architectural decisions before model generation, during supported file changes, and in CI.
- Mneme prevents architectural drift and context loss in AI-assisted development workflows.
- Mneme does not replace coding agents, CI systems, policy engines, or code review. It supplies the approved decisions that supported agents and CI gates check changes against.

## Claim Levels

Marketing may use broader category and outcome language where it accurately represents Mneme's direction and demonstrated primitives. Exact implementation scope is required only for specific feature, integration, compatibility, enforcement, and support claims.

- **Category and vision claims** may lead slightly ahead of implementation. "The decision and control layer for agentic software development", "makes engineering decisions operational", and "carries decisions across agents and workflows" are acceptable.
- **Capability claims** may generalize reasonably from what works today. Copy does not need to qualify every sentence as "supported architectural decisions on supported integrations"; naming architecture as the first shipped domain nearby is sufficient qualification.
- **Concrete factual claims** stay literal. Named integrations and their support level, security or compliance support, deployment controls, evidence stores, enterprise features, and similar specifics are never stated as shipped when they are not.

ADRs set strategic boundaries for messaging; they are not a sentence-level compliance review of marketing copy.

## Approved Supporting Phrasing

- Decision Memory and Architectural Drift Prevention for Coding Agents
- Architectural decision continuity and constraint enforcement during generation
- Context continuity and decision enforcement for AI coding workflows
- Architecture that holds.
- Architecture first: architectural drift prevention

*Retired 2026-09-25:* "The governance layer between your architecture and the model" (uses "governance layer" as the category).

## Strategic Narrative

- AI coding is evolving from autocomplete into governed engineering systems.
- The core bottleneck is no longer raw model quality alone, but context continuity and adherence to prior decisions.
- Trust in AI development requires enforceable architectural memory.

---

## Competitive Framing Rules

### Against DevOps / Delivery Governance Platforms

Use this distinction:

- They govern **what gets shipped**.
- Mneme governs **what the model is allowed to propose/build**.

### Against Generic Memory Tools

Avoid reducing Mneme to:

- Persistent memory
- AI memory store
- Context database
- Prompt enhancement layer

If memory is discussed, frame it as:

- Structured architectural decision memory with enforcement semantics
- Retrieval and enforcement of prior engineering decisions

---

## Messaging Guardrails

### Emphasize

- Engineering decisions made operational (decision and control)
- Architectural governance (as a capability, not the category)
- Drift prevention
- Decision enforcement
- Context continuity
- Engineering standards adherence
- Pre-generation constraint enforcement

### Avoid / De-emphasize

- Generic AI governance
- Generic memory/persistence framing
- Chatbot assistant framing
- Productivity/autocomplete framing
- Downstream DevOps/platform governance conflation

---

## Market Category Claim

Mneme seeks to own the category of:

- The decision and control layer for agentic software development

with architecture as the first domain, expressed through:

- Architectural drift prevention for the agentic AI SDLC (acquisition and distribution claim; ADR-013)
- AI Development Standards Enforcement
- Context Continuity Infrastructure for Coding Agents

*Superseded 2026-09-25:* "Architectural Governance for AI Development" as the lead niche claim.

---

## Implications

- Website, docs, and outreach lead with the decision and control layer category and keep architecture and architectural drift prevention as the first concrete domain and use case. The long-tail architecture-led content estate is not rewritten.
- Competitor comparisons should clearly separate Mneme HQ from CI/CD, deployment, and observability tools.
- Product roadmap should continue supporting enforceable decision memory / drift prevention as core moat.

---

## Strategic Update — 2026-05-03: Org-Layer Positioning Thesis

### Reframe

Mneme HQ is not a productivity enhancer for solo engineers. It is infrastructure and governance for engineering orgs adopting AI coding at scale.

- **Not:** developer convenience tool
- **Potentially:** organisational control platform — same category motion as Snyk, Datadog, LaunchDarkly, early GitHub Enterprise

### GTM Model: Bottom-Up Adoption

```
Engineer installs OSS / local version
↓
Team adopts informally
↓
Tech lead / platform team notices value
↓
Org wants shared policies, centralised governance, auditability
↓
Paid team product
```

### OSS vs. Paid Distinction

**OSS version** is the wedge. Validates retrieval quality, enforcement usefulness, and developer workflow fit.

**Paid version** solves org-level problems — not "more memory":
- Shared policy registry
- Org-wide ADR sync
- Central governance dashboard
- Audit logs / compliance trail
- Team policy inheritance
- Approval workflows
- Managed cloud sync
- Analytics / drift reporting

### Validation Pivot

The question is no longer "do devs like this?" It is:

> **Do engineering leaders feel enough pain to buy governance tooling?**

Target discovery calls: CTOs, VPs Eng, Eng Managers, Staff/Principal Engineers, Platform/DevEx leads.

Strong signal: "We've hacked together internal controls", "Review load is rising", "We need governance before scaling AI use", "We'd pilot this."

Weak signal: "Interesting idea", "Maybe eventually."

### Updated Hero Direction

*Superseded 2026-09-25 by the Decision section above.* The current homepage hierarchy is: category eyebrow ("The decision and control layer for agentic software development"), H1 "Architecture that holds.", then architectural drift prevention as the first use case.

> **Architectural Governance for AI-Assisted Engineering Teams** *(superseded)*

Supporting lines:
- Prevent architectural drift before code review
- Enforce engineering decisions across AI-generated code
- Scale governance as AI coding adoption grows

### Strategic Upside

If the org-layer thesis validates: Mneme HQ moves from small dev utility → budgeted engineering infrastructure / governance spend. That is venture-backable territory. Risk profile also changes — enterprise pain cycles are slower, buying process harder, ROI proof required.

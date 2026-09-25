---
id: ADR-001
title: Positioning and Messaging Rules
status: accepted
priority: foundational
date: "2026-05-01"
scope: messaging
---

# Context

Mneme must be positioned distinctly as the decision and control layer for
agentic software development, not as a generic memory, productivity, or
governance tool. Adjacent vendors market architectural guardrails inside
their own environments -- Mneme's differentiation is carrying the same
approved engineering decisions across agents, repositories, and CI, with
deterministic enforcement. (Amended 2026-09-25; previously "the
architectural governance layer for AI-assisted development".)

# Decision

Mneme HQ is **the decision and control layer for agentic software
development**. Architecture is the first supported decision domain and
architectural drift prevention is the first public use case. Governance is
an outcome or capability of Mneme, never its category name. All product
copy, docs, and outreach must reinforce this hierarchy.

## Approved phrasing

- The decision and control layer for agentic software development
- Architecture that holds.
- Architecture first: architectural drift prevention
- Decision Memory and Architectural Drift Prevention for Coding Agents
- Context continuity and decision enforcement for AI coding workflows
- Architectural decision continuity and constraint enforcement during generation

## Avoid

- "Governance layer" as the category name
- Presenting unshipped decision domains (security, compliance, platform policy) as current capability
- Generic AI governance framing
- Persistent memory / AI memory store / context database
- Chatbot assistant framing
- Productivity or autocomplete framing
- Downstream DevOps / deployment governance conflation

# Rationale

The core bottleneck in AI-assisted development is no longer raw model quality
but whether agents carry the engineering decisions a team has already made.
Architecture is the most concrete entry point, so it leads the product proof;
the category is the durable decision layer that makes those decisions
portable, enforceable, and inspectable across tools.

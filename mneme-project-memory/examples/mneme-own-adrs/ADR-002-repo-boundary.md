---
id: ADR-002
title: Repository Boundary for Internal Operational Tooling
status: accepted
priority: foundational
date: "2026-05-01"
scope: repository
---

# Context

Internal operational tooling (growth automation, publishing workflows, outreach
scripts, CRM integrations) must not be committed to the public OSS repository.
Without a clear boundary, this tooling risks exposing internal workflows and
diluting the product narrative.

# Decision

Internal operational, marketing, growth, and automation tooling must NOT be
committed to the public Mneme repository unless explicitly productized or
approved as a public example. All such tooling lives in the private repo.

## Classification

| Category | Definition | Public repo? |
|---|---|---|
| Core OSS Product | Features, modules, APIs | Yes |
| Approved Examples | Demos, reference integrations | Only if reviewed |
| Internal Tooling | Growth, marketing, ops scripts | No -- private only |

Default: if classification is unclear, treat as internal.

# Rationale

A clean public repo reinforces what Mneme is. Internal tooling encodes strategy
that should not be publicly visible, and external contributors should not
encounter unrelated ops scripts when exploring the codebase.

## Constraints

- FORBID_PATH: scripts/growth/**
- FORBID_PATH: scripts/outreach/**
- FORBID_PATH: tools/internal/**

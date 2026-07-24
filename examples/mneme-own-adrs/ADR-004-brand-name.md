---
id: ADR-004
title: Brand Rename - Mneme to Mneme HQ
status: accepted
priority: normal
date: "2026-05-03"
scope: branding
---

# Decision

The public-facing brand name is **Mneme HQ** from 2026-05-03 onwards.

The code-layer identity (package `mneme`, CLI `mneme`, slug `mnemeHQ/mneme`)
is permanently unchanged and must never be modified as part of brand updates.

## Scope

| In scope | Out of scope |
|---|---|
| Site titles, meta tags, OG tags | Domain (mnemehq.com -- unchanged) |
| JSON-LD name fields | GitHub slug (mnemeHQ/mneme -- unchanged) |
| Body copy and prose references | Python package name (mneme -- unchanged) |
| README | CLI commands (mneme check, etc. -- unchanged) |

# Rule

"Mneme HQ" is the brand. `mneme` is the package. These are different namespaces
and must never be conflated. Any site copy, docs, or templates that render code
blocks, import paths, or CLI commands must use lowercase `mneme`, not "Mneme HQ".

# Rationale

"Mneme HQ" positions the product as a centralised governance headquarters.
The code identity is pinned separately so brand updates can move prose freely
without breaking package imports, CLI invocations, or PyPI lookups.

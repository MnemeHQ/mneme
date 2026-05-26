---
id: ADR-004
title: "Brand Rename — Mneme to Mneme HQ"
status: accepted
priority: normal
date: 2026-05-03
scope: brand.naming
---

# ADR-004: Brand Rename — Mneme to Mneme HQ

## Status

Accepted — 2026-05-03

## Context

The product launched publicly under the name "Mneme". As the project moves toward broader distribution and a clearer product identity, a more distinctive brand name was needed. "Mneme HQ" positions the product as a centralised governance layer — a headquarters for project memory — rather than a standalone tool name that requires explanation.

## Decision

The public-facing brand name is **Mneme HQ** from 2026-05-03 onwards.

## Scope

| In scope | Out of scope |
|----------|--------------|
| Site titles, meta tags, OG/Twitter tags | Domain (`mnemehq.com` — unchanged) |
| JSON-LD structured data `"name"` fields | GitHub repo slug (`TheoV823/mneme` — unchanged) |
| Body copy and prose references | Python package name (`mneme` — unchanged) |
| App template headings | CLI commands (`mneme check`, `mneme cursor generate` — unchanged) |
| README | PyPI package name (unchanged) |

## Code Identity (Confirmed from `pyproject.toml` v0.3.2)

The code-layer identity is permanently `mneme` and must never be changed as part of brand updates:

| Identifier | Value | Source |
|------------|-------|--------|
| PyPI package name | `mneme` | `pyproject.toml` line 6 |
| Python import path | `from mneme.*` | `pyproject.toml` line 30 |
| CLI command | `mneme` | `pyproject.toml` line 25 |
| Secondary CLI | `mneme-hook` | `pyproject.toml` line 26 |
| GitHub repo slug | `TheoV823/mneme` | GitHub |
| Domain | `mnemehq.com` | DNS |

**Rule:** "Mneme HQ" is the brand. `mneme` is the package. These are different namespaces and must never be conflated. Any site copy, docs, or templates that render code blocks, import paths, or CLI commands must use lowercase `mneme`, not "Mneme HQ".

## Consequences

- All user-facing prose and UI surfaces display "Mneme HQ".
- CLI commands, import paths, and URLs remain lowercase `mneme` — no breaking changes for existing users.
- Future documentation should use "Mneme HQ" as the brand name and `mneme` as the package/command name.
- ADR-001 positioning language should be updated to use "Mneme HQ" on next revision.

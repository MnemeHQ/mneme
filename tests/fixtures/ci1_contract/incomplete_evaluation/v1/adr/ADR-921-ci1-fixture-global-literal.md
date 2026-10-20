---
id: ADR-921
title: CI1 fixture - forbid the deprecated sync flag everywhere
status: accepted
priority: normal
date: 2026-10-17
scope: cli_flags
---

## Context

Synthetic decision for the CI1.2.2 incomplete-evaluation fixture. It is not a
Mneme product decision and exists only inside this fixture.

## Decision

No file may pass the deprecated sync flag.

## Constraints

- FORBID_LITERAL: --legacy-sync

---
id: ADR-922
title: CI1 fixture - forbid the staging hostname in documentation
status: accepted
priority: normal
date: 2026-10-17
scope: documentation
---

## Context

Synthetic decision for the CI1.2.2 incomplete-evaluation fixture. It is not a
Mneme product decision and exists only inside this fixture.

## Decision

Documentation must not name the internal staging host.

## Constraints

- FORBID_LITERAL:
    value: staging.internal.example
    include_paths:
      - docs/**

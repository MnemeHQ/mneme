---
id: ADR-901
title: CI1 fixture - forbid the legacy client installer in documentation
status: accepted
priority: normal
date: 2026-10-17
scope: enforcement
---

## Context

Synthetic decision for the CI1.2.1 path-scoped enforcement fixture. It is not
a Mneme product decision and exists only inside this fixture.

## Decision

Documentation must not tell readers to install the legacy client.

## Constraints

- FORBID_LITERAL:
    value: install legacy-client
    include_paths:
      - docs/**
    exclude_paths:
      - docs/history/**

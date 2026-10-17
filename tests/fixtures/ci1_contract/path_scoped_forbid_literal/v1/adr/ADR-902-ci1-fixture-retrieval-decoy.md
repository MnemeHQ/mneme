---
id: ADR-902
title: CI1 fixture - retrieval decoy for storage and caching
status: accepted
priority: normal
date: 2026-10-17
scope: storage
---

## Context

Synthetic decoy decision for the CI1.2.1 fixture. Its vocabulary is chosen so
that storage and caching queries rank it above ADR-901.

## Decision

Storage and caching layers keep durable state in the primary database.

---
id: ADR-102
title: Billing code lives under billing/
status: accepted
priority: normal
date: 2026-04-02
scope: billing
---

## Decision

All billing logic must live under `billing/`. Legacy billing code under `src/legacy/billing/` is frozen.

## Constraints
- FORBID_PATH: src/legacy/billing/**
- REQUIRE_PATH: billing/**

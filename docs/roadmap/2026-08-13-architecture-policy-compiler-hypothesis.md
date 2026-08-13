# Roadmap hypothesis: Mneme as an architecture-policy compiler

**Status:** Non-binding architectural direction only  
**Date:** 2026-08-13  
**Implementation gate:** Do not implement before the currently locked Claude pre-generation guidance evaluation is resolved.

## Hypothesis

Mneme may be most durable as an **architecture-policy compiler**:

1. Human-readable ADRs and engineering decisions remain the authored source.
2. Mneme compiles those decisions into a canonical typed, machine-readable policy representation.
3. Harness-specific adapters may later project that canonical policy into native guidance formats for Claude Code, another commercial coding harness, and open-weight agent harnesses.
4. Deterministic Mneme enforcement remains independent of whether a harness discovers, understands, or follows the guidance.

Pre-generation guidance is therefore a potential adapter-level capability, not the foundation of deterministic enforcement.

## Why record this now

Preliminary Claude Code A/B diagnostics showed that baseline Claude frequently discovered `.mneme/project_memory.json` through normal repository exploration. That means automatic prompt injection may add limited incremental value for Claude Code in some repositories, while the structured policy artifact and deterministic checker remain independently useful.

This is a hypothesis-generating observation only. It does not change the locked Claude evaluation or establish a new accepted architecture.

## Evaluation separation

The current Claude evaluation answers two narrower questions:

1. Does injection itself affect Claude's first attempt?
2. Does injection add value over normal Claude Code repository discovery?

A later, separately locked portability benchmark should answer a different question:

> Does a canonical Mneme policy provide consistent governance across heterogeneous coding-agent harnesses?

Candidate future benchmark arms:

- Claude Code;
- one other commercial coding harness;
- one open-weight model running through a coding-agent harness.

Potential measurements include:

- whether policy is discovered unaided;
- whether the correct decision is surfaced;
- first-attempt architectural compliance;
- whether harness-native guidance improves that outcome;
- whether deterministic Mneme enforcement catches prohibited changes regardless of harness behavior.

## Required sequence

1. Record this hypothesis only.
2. Run pre-generation guidance Checkpoints 6.2-6.3.
3. Review mechanism-isolation results before spending the next production A/B batch.
4. Complete the production A/B only if it remains decision-relevant.
5. Design the canonical typed-policy/compiler contract.
6. Add harness-native adapters/exporters.
7. Run a separately locked cross-harness portability benchmark.

## Explicitly out of scope before the evaluation gate

- compiler runtime behavior;
- new exports or policy projections;
- retrieval changes;
- additional policy formats;
- changes to canonical K=3 or guidance selection;
- changes to deterministic enforcement semantics;
- cross-harness implementation work;
- any change that alters the currently locked Claude intervention.

## Existing architecture alignment

`docs/architecture/current-phase.md` already lists **Policy compiler / higher-level DSL** as deferred Layer 2 territory. This note makes that future direction more specific without promoting it into an ADR, changing the Layer 1 freeze, or authorizing implementation.

Any future compiler implementation requires a separately reviewed architecture decision and a separately locked validation plan before behavior changes land.

# Mneme Architecture Documentation Standard v1

> A minimum repository standard for making architecture understandable,
> reviewable, and maintainable by humans and AI-assisted engineering systems.

## Goal

A non-trivial software system should make three things easy to discover:

1. **What the system looks like now.**
2. **Why important architectural choices were made.**
3. **What must remain true as the system changes.**

This standard combines repository-native architecture views with Architecture
Decision Records (ADRs). It is intentionally lightweight: the aim is a durable
operational model, not exhaustive diagramming.

## Minimum architecture set

For a non-trivial repository, use:

```text
docs/
  architecture/
    README.md
  adr/
    ADR-xxx-....md
```

The architecture entry point should contain or link to:

- a repository-native ASCII architecture summary;
- a C4 System Context view;
- a C4 Container view when multiple major runtime/deployment responsibilities
  exist;
- C4 Component views only where internal complexity warrants them;
- the ADR set that governs the important boundaries;
- a clear distinction between current and target architecture.

The architecture overview should be readable without proprietary tooling.

## Representation responsibilities

### ASCII operational map

The ASCII map is the fastest repository-native mental model.

It should show:

- major actors;
- major system responsibilities;
- important state or authority stores;
- important boundaries;
- the principal flow through the system.

It should not try to mirror every module or class.

ASCII is particularly useful for terminal workflows, code review, text search,
and agent context because it remains readable as plain text.

### C4 System Context

Use the Context view to answer:

> Who or what interacts with this system, and where is the system boundary?

Update it when external actors, system ownership, or the top-level boundary
changes.

Do not use Context diagrams to describe internal implementation details.

### C4 Container

Use the Container view to answer:

> What are the major runtime or deployment responsibilities, and how do they
> communicate?

A container is a major architectural responsibility, not necessarily a Docker
container.

Update it when major runtime responsibilities, persistent stores, processes,
services, or their relationships change.

### C4 Component

Use Component views selectively.

They are useful when a container contains several architectural
responsibilities whose collaboration matters to understanding change. Do not
create component diagrams merely to reproduce the source tree.

A component view should explain responsibilities and relationships that matter
architecturally.

### ADRs

ADRs explain architectural decisions and rationale.

A useful ADR should make clear:

- what was decided;
- why;
- where it applies;
- its status;
- relevant lifecycle/supersession information;
- important consequences;
- related architectural decisions.

ADRs and diagrams have different jobs:

```text
C4 / ASCII  -> what exists and how responsibilities relate
ADR         -> why an important architectural choice exists
```

Neither should duplicate the other unnecessarily.

## Current versus target architecture

Repositories frequently contain plans for architecture that is not yet
implemented.

Keep these states explicit.

```text
CURRENT
  implemented behavior and accepted governing decisions

TARGET
  proposed/future behavior that is not yet current
```

Do not update a current-state diagram to show future architecture as though it
already exists.

When a proposed ADR defines the target, label it as proposed and link it from a
separate target section or view.

When implementation and an accepted ADR diverge, record the discrepancy rather
than silently choosing one representation.

## Architecture update workflow

Architecture documentation is maintained as part of delivery.

For every change:

```text
change proposed
      |
      v
classify architecture impact
      |
      +--> none ----------------------> normal review
      |
      +--> representation only ------> update affected docs
      |
      +--> architecture change ------> ADR review + update affected views
      |
      +--> target architecture ------> proposed ADR + separate target view
```

Architecture-affecting changes should update affected views in the same PR.

The standard does not require every view to change on every architectural PR.
Update only the views whose meaning changed.

## Recommended PR classification

Use these four classifications:

- **None**
- **Representation only**
- **Architecture change**
- **Target architecture**

For architecture changes and target architecture, review:

- ADR impact;
- architecture-map impact;
- C4 impact;
- ASCII-map impact.

This makes architecture maintenance an explicit engineering decision rather
than an optional documentation task.

## Definition of Done

For an architecture-affecting change, done means:

- implementation and accepted ADRs have been checked together;
- any new decision has the appropriate ADR treatment;
- the affected architecture views describe the new state;
- current and target architecture remain distinguishable;
- links between diagrams and governing ADRs remain valid;
- reviewers can trace the changed responsibility back to its decision context.

## Deterministic integrity checks

Where practical, automate facts that do not require architectural judgment.
Useful checks include:

- architecture entry-point sections exist;
- local documentation links resolve;
- ADR identifiers are unique;
- ADR-map identifiers and statuses match ADR frontmatter;
- proposed ADRs represented in the architecture map are explicitly marked as
  proposed/target/deferred.

These checks complement review. They do not prove that a C4 diagram is
semantically correct or that implementation matches every documented
responsibility.

## Release hygiene

Before a release candidate is tagged, verify that the architecture entry point
still describes the system being released.

Look especially for:

- capabilities documented as deferred even though they shipped;
- proposed decisions represented as current;
- stale responsibility or data-flow arrows;
- new authority or persistence boundaries missing from the diagrams;
- integration surfaces that changed architectural responsibility.

This is a final safety net. Same-PR updates remain the normal mechanism.

# Client education curriculum

This standard should be taught as an engineering practice rather than as a
diagramming exercise.

## Module: Architecture as a Living Decision System

### Learning objective

By the end of the module, a team should be able to move from architecture
understanding to maintainable governance:

```text
understand
   |
   v
represent
   |
   v
decide
   |
   v
codify
   |
   v
enforce where deterministic
   |
   v
collect evidence
   |
   v
evolve architecture deliberately
```

### Part 1 — Build the system map

Participants take one repository and create:

1. a C4 System Context view;
2. a C4 Container view where appropriate;
3. a concise ASCII operational map.

The exercise focuses on identifying responsibilities and boundaries, not on
drawing every implementation detail.

### Part 2 — Find the decisions behind the structure

For each important boundary, ask:

- Why does this boundary exist?
- Is the reason documented?
- Is the decision active?
- Where does it apply?
- What would violate it?

Participants identify existing ADRs and create or improve missing decision
records where necessary.

### Part 3 — Separate current and target architecture

Participants identify one planned architectural change and represent:

- the current system;
- the proposed target;
- the ADR status governing that target.

The goal is to prevent roadmap intent from being confused with deployed
architecture.

### Part 4 — Classify decision enforceability

For each important architectural decision, identify whether it is:

- deterministic and mechanically enforceable;
- partially modelled;
- guidance requiring human judgment.

The purpose is not to automate everything. It is to understand which
architectural constraints can safely become controls.

### Part 5 — Connect decisions to enforcement and evidence

Participants trace one decision through:

```text
ADR / architectural intent
        |
        v
structured decision
        |
        v
applicability
        |
        v
deterministic control
        |
        v
evidence / audit state
```

Where deterministic enforcement is not possible, the team records the
limitation rather than pretending that documentation alone is protection.

### Part 6 — Establish the maintenance process

The team adds architecture-impact classification to its PR process and defines
who reviews architecture-affecting changes.

The exercise ends only when the repository has a repeatable update process,
not merely a one-time diagram.

## Suggested workshop output

A completed workshop should leave the team with:

- one architecture entry point;
- one ASCII architecture map;
- Context and relevant Container views;
- a reviewed ADR set for the major boundaries;
- explicit current versus target architecture;
- an architecture-impact PR process;
- an initial view of which decisions are enforceable, partially modelled, or
  guidance.

## What this standard deliberately does not require

- exhaustive UML;
- a diagram per module;
- a proprietary architecture repository;
- automatic enforcement of every ADR;
- an LLM deciding architectural correctness;
- a periodic documentation project disconnected from normal delivery.

The standard is successful when architecture can be understood quickly,
important decisions can be traced, and architectural change cannot routinely
make the repository's own architecture representation stale.

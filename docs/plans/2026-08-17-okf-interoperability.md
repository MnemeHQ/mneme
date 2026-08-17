# Experimental Open Knowledge Format (OKF) Interoperability

**Status:** Proposed / exploratory  
**Date:** 2026-08-17  
**Scope:** Architecture and interoperability boundary only

## Summary

Mneme should be able to consume architectural knowledge represented in external open formats without making those formats part of its core governance model.

The first format to evaluate is the **Open Knowledge Format (OKF)**.

The goal is not to replace Mneme ADRs, project memory, typed rules, retrieval, applicability, guidance, or enforcement. The goal is to define a narrow adapter boundary through which externally represented architectural knowledge can be normalized into Mneme's existing decision model.

Conceptually:

```text
Knowledge source -> Mneme governance -> agent
```

Knowledge sources may eventually include:

- Mneme ADRs
- project memory
- repository documentation
- OKF bundles
- future external knowledge formats

Mneme remains responsible for deciding **which architectural decisions apply and how they constrain an agent before generation or modification**.

## Why this matters

Agent infrastructure is increasingly separating into distinct layers:

1. **Knowledge** — what the agent knows.
2. **Capabilities** — what tools and actions the agent can use.
3. **Governance** — what the agent should or should not do given existing architectural decisions.

Mneme should not need to own every representation used by the knowledge layer.

Supporting an open knowledge format could improve portability across agents, models, and orchestration environments while preserving Mneme's core role as the architectural governance layer.

It also reduces coupling between governance behavior and Mneme's current storage formats.

## Proposed boundary

```text
OKF
 |
 v
Mneme knowledge adapter
 |
 v
Normalized architectural decisions
 |
 +-- retrieval
 +-- applicability
 +-- guidance
 +-- deterministic enforcement
 |
 v
Coding agent
```

External formats terminate at the adapter boundary. After normalization, the existing Mneme pipeline remains authoritative.

```text
Many knowledge formats
        |
        v
one Mneme decision model
        |
        v
one governance pipeline
```

## Initial implementation scope

If implementation is authorized, keep the first increment intentionally small:

- introduce an `OKFAdapter` or equivalent import boundary;
- map a minimal supported subset of OKF knowledge objects into Mneme's existing internal decision representation;
- retain provenance identifying OKF as the external source;
- reject unsupported or incomplete objects explicitly;
- prove imported decisions travel through the existing retrieval, applicability, guidance, and enforcement paths;
- avoid creating a parallel retrieval or enforcement system.

## Representative example

An external knowledge object expressing:

```text
Production persistence must use PostgreSQL.
SQLite is permitted only for local development and tests.
```

should be capable of becoming the same normalized architectural decision Mneme would derive from a native ADR.

From that point onward, the source format should no longer matter:

```text
decision retrieval
        |
        v
applicability
        |
        v
pre-generation guidance / enforcement
        |
        v
agent
```

## Architectural principle

> Mneme should govern decisions, not own every format in which those decisions originate.

## Non-goals

This work does **not** imply that Mneme should:

- replace Mneme ADRs;
- replace `project_memory`;
- adopt OKF as the canonical storage format;
- build a general-purpose knowledge graph;
- create another retrieval engine;
- create a second enforcement mechanism;
- implement automatic ADR generation;
- implement bidirectional synchronization;
- implement organization-wide policy distribution;
- require coding agents to understand OKF directly;
- add Agent Plugin or MCP packaging as part of the same change.

Those should remain independent decisions driven by evidence and pilot requirements.

## Acceptance criteria for a future implementation PR

- OKF support is isolated behind an adapter/interface boundary.
- At least one representative architectural decision can be imported.
- Imported and native decisions produce equivalent normalized representations for equivalent semantics.
- Existing retrieval, applicability, guidance, and enforcement behavior remains unchanged.
- Provenance identifies the external source.
- Unsupported OKF constructs fail clearly rather than being silently interpreted.
- No duplicate governance or enforcement path is introduced.
- Existing test suites remain green.
- Support is documented as experimental.

## Validation before implementation

Before investing in a full adapter, validate:

1. Whether OKF can represent the architectural-decision semantics Mneme actually needs.
2. Whether there is meaningful adoption or pilot demand for OKF portability.
3. Whether importing OKF creates value beyond converting it into existing ADR/project-memory inputs externally.
4. Whether provenance and trust metadata can be retained without weakening Mneme's deterministic behavior.
5. Whether the adapter can remain small enough that Mneme does not become a generic knowledge-ingestion platform.

## Follow-up opportunities

Only after the import boundary is validated should Mneme evaluate:

- OKF export;
- bidirectional synchronization;
- organization-level knowledge bundles;
- portable policy distribution;
- Agent Plugin packaging;
- MCP exposure of Mneme governance;
- automated conversion between ADRs and interoperable knowledge representations.

## Product framing

A useful long-term separation is:

> Open formats describe what an agent knows. Agent protocols describe what it can do. Mneme determines which architectural decisions govern what it is about to do.

This proposal is intended to preserve that separation while making Mneme more interoperable across the emerging agent ecosystem.

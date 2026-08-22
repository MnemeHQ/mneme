# Pre-generation Guidance Role Contract

**Status:** R1 semantics and wording locked; classifier and runtime unimplemented  
**Date:** 2026-08-13  
**Scope:** pre-generation guidance only

## 1. Purpose

Retrieved decisions can be relevant to a task in different ways. A decision
may directly govern the requested implementation, or it may only constrain the
work if the implementation happens to touch an adjacent architectural area.

Prompt guidance must preserve that distinction so relevance is not mistaken
for authorization to expand the task.

The guidance-only pipeline is:

```text
retrieval
   -> candidate decisions
   -> guidance role classification
        - direct
        - adjacent_constraint
   -> role-aware prompt formatting
```

This stage is called **guidance role classification**. It is not
decision-level applicability and does not alter ADR-020 typed-rule path
applicability.

## 2. Role semantics

### 2.1 `direct`

> The decision directly governs the work requested by the user. It may guide
> implementation choices within the requested scope.

A direct decision may shape how the requested change is implemented. Its
presence still does not authorize unrelated components, refactors, or other
work outside the user's request.

### 2.2 `adjacent_constraint`

> The decision is relevant because the requested work may interact with
> constraints it defines, but it does not authorize, require, or expand the
> requested implementation.

An adjacent constraint may affect the requested work only if that work actually
touches the decision's area. It is never an implementation objective.

## 3. Normative invariants

1. **Guidance only.** Roles affect prompt-time context and nothing else.
2. **Post-retrieval.** Role classification occurs after retrieval. It does not
   change scores, ranking, K, or which decisions the retriever considers.
3. **Mutually exclusive.** An emitted decision has exactly one role: `direct`
   or `adjacent_constraint`.
4. **No unclassified emission.** A candidate without a confidently assigned
   role is not emitted. R2 defines confidence and evidence; R1 does not.
5. **Direct remains task-bounded.** A direct decision guides implementation
   within the user's request and does not expand that request.
6. **Adjacent never authorizes work.** An `adjacent_constraint` must never
   become an implementation objective.
7. **Deterministic and observable.** The same prompt, memory, and classifier
   configuration produce the same roles. Evaluation output records the role
   assigned to every emitted decision.
8. **No enforcement effect.** Roles do not change enforcement eligibility,
   typed-rule matching, ADR-020 path applicability, FAIL/WARN semantics, or
   pre-write hook behavior.
9. **No policy mutation.** Roles are runtime guidance metadata. R1 does not add
   fields to canonical decisions, ADRs, or project memory.
10. **No inferred extra task.** Neither role permits Mneme or the agent to infer
    additional deliverables from a retrieved decision.

## 4. Canonical wording

The following text is normative for the first role-aware formatter. R2 may
define deterministic role metadata, but it must not weaken these statements.

### 4.1 Global scope boundary

```text
[Mneme architectural guidance]
Use these decisions only to guide the work the user requested. They do not
expand the task. Do not add components, storage, dependencies, interfaces,
refactors, or other architecture solely because a decision appears below.
```

### 4.2 Direct decision prefix

```text
DIRECT DECISION [<decision-id>]
This decision directly governs the requested work. Apply it to implementation
choices within the user's requested scope.
```

The recorded decision, scope, constraints, anti-patterns, and typed-rule
selector descriptions follow this prefix using the existing compact format.

### 4.3 Adjacent constraint prefix

```text
ADJACENT CONSTRAINT [<decision-id>] — DO NOT IMPLEMENT AS EXTRA WORK
This decision may constrain the requested work only if that work actually
touches its area. Do not implement this decision merely because it is shown.
Do not add components, storage, dependencies, interfaces, refactors, or other
architecture solely to satisfy it.
```

The recorded decision and constraints may follow for context. Their presence
does not change the non-authorizing role.

## 5. Evaluation contract

The locked role benchmark must be able to assert role assignment independently
from retrieval recall and prompt formatting.

For the E66 authentication reproduction:

```text
ADR-AUTH    -> direct
ADR-STORAGE -> adjacent_constraint
```

The post-remediation deterministic target is:

```text
direct recall                  1.00 -> 1.00
unexpected decisions           0    -> 0
unclassified adjacent          2    -> 0
adjacent emitted as authorizing 2   -> 0
```

Suppression and non-authorizing emission are both architecturally possible for
an adjacent candidate. R2 must choose deterministic assignment behavior. If an
adjacent decision is emitted, the canonical adjacent wording is mandatory.

## 6. R1 exclusions

R1 deliberately does not decide or implement:

- a score threshold or relative-score ratio for either role;
- field-specific classification rules;
- target-path inference;
- a change to `DecisionRetriever`;
- a change to K or retrieval weights;
- runtime guidance or hook changes;
- decision-schema, ADR, or project-memory fields;
- enforcement or ADR-020 applicability changes; or
- a new Claude trial.

In particular, `score >= 4 means direct` and `drop every single-token scope
match` are not part of this contract.

## 7. R2 handoff

R2 answers one question:

> What deterministic, explainable evidence assigns a retrieved decision to
> `direct`, `adjacent_constraint`, or no emitted role?

Candidate rules must be compared across the complete locked retrieval suite,
the four-case role characterization, and adversarial lexical-overlap cases
before one is selected. R2 may not edit this semantic contract merely to make a
candidate classifier pass.

## 8. Architecture boundaries

- **ADR-017 remains intact:** retrieval controls context; enforcement scope is
  independent.
- **ADR-020 remains intact:** path applicability belongs to individual typed
  rules at an artifact-aware enforcement boundary.
- **Guidance roles are additive:** they interpret how retrieved context may be
  used before generation and have no authority at the edit gate.

The product claim remains **pre-generation architectural guidance**, not
**pre-generation enforcement**.

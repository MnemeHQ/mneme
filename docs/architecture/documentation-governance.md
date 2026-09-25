# Architecture Documentation Governance

> Process contract for keeping Mneme's architecture documentation aligned with
> implementation reality and accepted architectural decisions.

## Purpose

Mneme treats architecture documentation as part of the engineering system, not
as a retrospective writing task. Architectural views must evolve with the
architecture they describe.

The governing principle is:

> **Architecture documentation changes with the architecture, not after someone
> remembers to update it.**

This process applies to the repository architecture bundle, including:

- `docs/architecture/README.md` — ASCII orientation, C4 views, and ADR map;
- supporting documents under `docs/architecture/`;
- accepted and proposed ADRs under `docs/adr/`;
- architecture references in contributor and release procedures.

This process does not make diagrams a new authority source. It defines how
architecture representations stay synchronized with the sources they explain.

## Authority and representation

Three things must be kept distinct:

1. **Accepted ADRs** define governing architectural decisions and constraints.
2. **Implementation** shows the behavior and structure that currently exist.
3. **Architecture documentation** represents those two for humans and agents.

If implementation and an accepted ADR disagree, the architecture documentation
must surface the discrepancy. It must not silently rewrite the ADR, pretend the
implementation is compliant, or present the mismatch as settled architecture.

A proposed ADR may describe target architecture, but proposed behavior must be
labelled as target/proposed until the ADR is accepted and the implementation is
validated.

The architecture bundle is therefore a maintained projection, not an
independent source of truth.

## Architecture-impact classification

Every pull request must classify its architecture impact as exactly one of the
following:

| Classification | Meaning | Required architecture action |
| --- | --- | --- |
| **None** | No architectural boundary, responsibility, authority, lifecycle, data-flow, enforcement, evidence, persistence, integration-contract, or research/product-isolation change. | No architecture-document update required. |
| **Representation only** | The architecture is unchanged, but its representation is incomplete, stale, or unclear. | Update the affected architecture documentation in the same PR. No ADR is required solely for clarification. |
| **Architecture change** | Current behavior changes an architectural responsibility, boundary, authority relationship, lifecycle, persistence model, data flow, enforcement/evidence contract, or integration contract. | Review the governing ADR set, add or amend an ADR when the decision is not already authorized, and update affected architecture views in the same PR. |
| **Target architecture** | The PR documents a future architecture that is not yet current behavior. | Use a proposed ADR when the target represents a new architectural decision; keep current-state diagrams unchanged or clearly separate the target view. |

The PR template records this classification. Classification is an explicit
engineering assertion by the change author and reviewer; it is not inferred
from file extensions.

## What counts as architecture impact

Ask whether the change alters any of these:

- system boundary;
- container or component responsibility;
- authority or source-of-truth boundary;
- persistent state or identity model;
- lifecycle or supersession semantics;
- data flow between architectural responsibilities;
- retrieval versus enforcement responsibility;
- enforcement boundary or applicability semantics;
- evidence or trust boundary;
- external integration contract;
- product-runtime versus research isolation boundary;
- security boundary that changes architectural responsibility.

Adding a helper, renaming a private function, or changing an implementation
detail inside an existing responsibility normally does not require C4 changes.

A new command, module, or integration does not automatically mean architecture
changed. The question is whether responsibility or contract changed.

## Same-PR rule

When a PR changes current architecture, the affected architecture
representation must normally change in the **same PR**.

Do not intentionally merge an architectural change with a known-stale C4 or
ASCII view and plan to repair the documentation later.

The architecture update should be proportional:

- **C4 Context** changes only when external actors or the system boundary change.
- **C4 Container** changes when major runtime/deployment responsibilities or
  their relationships change.
- **C4 Component** changes when important internal responsibilities or
  architectural collaboration boundaries change.
- **ASCII map** changes when the fast operational mental model would otherwise
  become misleading.
- **ADR map/status** changes when the governing decision set or decision status
  changes.

Not every architecture-impacting PR needs every view modified.

## ADR status discipline

Architecture documentation must preserve ADR lifecycle truth.

- `accepted` may be described as governing.
- `proposed` must be described as proposed/target/deferred as appropriate.
- Superseded or deprecated decisions must not be presented as current
  authority without explanation.
- Documentation must not promote an ADR by wording alone.
- Moving an implementation toward a proposed ADR does not make the ADR
  accepted.

When a diagram references a specific ADR, use its current frontmatter status.

## Pull-request review

For **Architecture change** and **Target architecture** classifications, the PR
must state:

- ADR impact;
- architecture-map impact;
- C4 impact;
- ASCII-map impact.

Reviewers should verify:

1. the classification matches the actual change;
2. relevant accepted ADRs were checked;
3. new architectural decisions are represented by an ADR rather than hidden in
   code or diagram prose;
4. current and target architecture are not conflated;
5. changed responsibilities and arrows match implementation behavior;
6. O1A/research boundaries remain explicit where relevant.

This review is part of Definition of Done for the PR.

## Release-candidate architecture verification

Before tagging a release candidate, perform a lightweight architecture
verification on the exact release-candidate state.

Verify that:

- `docs/architecture/README.md` still describes the shipped system;
- no shipped architectural capability is still labelled deferred or
  unimplemented;
- proposed ADRs are not presented as shipped;
- accepted ADR status shown in the architecture map is current;
- material changes to authority, persistence, lifecycle, enforcement,
  evidence, integrations, or research boundaries are represented.

This verification is event-driven release hygiene. It complements, but does not
replace, same-PR maintenance.

A future deterministic checker may automate facts such as broken links, ADR
existence, and ADR-status consistency. Semantic correctness of a C4 diagram is
a review responsibility unless and until it can be validated reliably.

## Periodic review

Periodic review is a safety net, not the primary maintenance mechanism.

A periodic architecture review may look for accumulated representational drift,
but teams should not depend on a quarterly or annual documentation exercise to
repair architecture views that were knowingly made stale by earlier changes.

## Relationship to the Mneme Architecture Documentation Standard

The reusable practice taught to adopting teams is
[Mneme Architecture Documentation Standard v1](./architecture-documentation-standard-v1.md).

Mneme follows that standard in this repository. The internal process is
deliberately the same practice the product teaches: understand the system,
record decisions, represent boundaries, update them with change, and keep
current and target architecture distinguishable.

## Deterministic automation boundary

The repository implements a narrow deterministic checker at
`scripts/check_architecture_docs.py`. It validates:

- required sections in the architecture entry point;
- relative-link integrity across `docs/architecture/*.md`;
- unique ADR frontmatter identity;
- ADR-map link, identity, and status consistency;
- explicit proposed/target/deferred treatment for proposed ADRs shown in the
  architecture map.

Run it locally with:

```bash
python scripts/check_architecture_docs.py
```

The `Validate architecture documentation` workflow runs the same checker on
pull requests and pushes to `main`.

The checker does **not** ask an LLM to decide whether a C4 diagram is
semantically correct, infer whether arbitrary source code "looks
architectural," or certify that implementation matches every diagram arrow.
Those remain review responsibilities unless a future deterministic contract
can establish them reliably.

The workflow begins as an observable CI signal rather than an immediate
branch-protection requirement. Promotion to a required check should happen only
after the checker has demonstrated stable, low-noise behavior.

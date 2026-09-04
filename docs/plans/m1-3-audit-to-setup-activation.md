# M1.3 — Audit-to-Setup Activation

## Status

Frozen implementation contract.

## Mission

Allow a completed or saved Architecture Audit to lead into a safe Mneme installation and setup state without automatically enabling preventive enforcement.

The intended product funnel is:

> Audit → Save baseline → Install / Setup → Pilot → Re-audit

M1.3 is an activation layer between Architecture Audit and a Mneme pilot. It is not a new product and must reuse existing Audit, project, integration, and Mneme runtime concepts wherever practical.

## 1. Product objective

Today, an Audit can identify architectural protection gaps.

M1.3 gives the user a concrete next action:

> Install Mneme without changing how the team works yet.

The user should be able to connect the Audit baseline to the repository, initialize Mneme, detect supported integrations, load architectural context, and inspect protection opportunities without enabling blocking enforcement.

The commercial transition becomes behavioral rather than sales-led:

> Free Audit → product activation → pilot

## 2. Core product invariant

### Setup must never silently enable preventive enforcement.

Installing or setting up Mneme must not:

- block developer actions;
- turn warn/observe behavior into blocking behavior;
- activate guardrails automatically;
- automatically classify decisions as Protected;
- invent architectural decisions;
- generate and activate rules without explicit review.

Transition from setup to active protection requires an explicit user action.

## 3. State model

Mneme activation state:

```text
not_installed
    ↓
setup
    ↓
active
```

### `not_installed`

An Audit may exist, including a saved baseline, but no connected Mneme installation exists for the project.

### `setup`

Mneme has been initialized and may provide architectural context, integrations and non-blocking checks.

Preventive enforcement has not been activated.

### `active`

At least one preventive protection has been explicitly enabled.

These activation states must remain distinct from the Architecture Audit lifecycle.

Audit lifecycle remains conceptually:

```text
ephemeral → saved → pilot
```

Do not collapse Audit state and Mneme activation state into a single lifecycle.

## 4. M1.3 scope

M1.3 is divided into four increments.

### M1.3a — Setup state + CLI

Implement a safe setup flow in the Mneme core repository.

Primary command:

```bash
mneme setup
```

Audit-linked form:

```bash
mneme setup --audit-ref <opaque-reference>
```

Exact naming may follow existing CLI conventions if necessary, but the product semantics in this contract must remain unchanged.

Setup should:

1. Confirm a valid/supported repository context.
2. Detect whether Mneme has already been initialized.
3. Initialize normal Mneme project state when required.
4. Reuse existing `.mneme/` and project-memory mechanisms wherever possible.
5. Detect relevant supported agent/developer environments.
6. Consume an Audit setup reference when provided.
7. Load the architectural context required for setup.
8. Configure supported integration behavior only in a non-blocking mode.
9. Run appropriate initial checks in existing warn/observe semantics.
10. Produce a clear setup summary.
11. Record or report setup completion when linked to a saved Audit.
12. Be safe and idempotent when rerun.

Example conceptual output:

```text
Mneme setup

Repository
✓ payments-api

Architecture baseline
✓ Audit baseline connected
✓ 14 architectural decisions discovered

Integrations
✓ Claude Code detected
○ Codex CLI detected

Protection readiness
4 Protected
6 Mneme-ready
4 Require modelling / guidance

Enforcement
○ Not enabled

Mneme is installed in setup mode.
```

The exact presentation may adapt to current CLI style.

### M1.3b — Audit baseline pairing

Allow a saved Architecture Audit baseline to be safely associated with a Mneme setup.

The Audit UI/backend should be able to create an opaque, scoped setup reference.

Example:

```bash
mneme setup --audit-ref <opaque-reference>
```

The reference should resolve enough information to associate:

- Audit;
- project;
- baseline version;
- baseline provenance.

It must not become a general-purpose user/account credential.

The pairing mechanism must preserve relevant provenance including, where already available:

- Audit identity;
- project identity;
- repository commit SHA;
- Mneme version;
- Audit/schema version.

A successful setup originating from an Audit must be attributable back to that Audit/project.

Do not introduce broad authentication, organisation or billing infrastructure solely to implement M1.3.

### M1.3c — Audit activation UI

Extend the Architecture Audit result experience.

#### Before setup

Primary CTA:

> Install Mneme

Supporting promise:

> Connect this architecture baseline to your repository without enabling enforcement. Mneme starts in setup mode, so nothing is blocked.

Expose a copyable install/setup command.

For example:

```bash
pipx install mneme-hq
mneme setup --audit-ref <reference>
```

Use the canonical current Mneme installation mechanism if it differs.

Secondary action:

> Save baseline

when applicable.

Lower-priority commercial action:

> Talk to us

The Audit must not make a sales conversation the only obvious next action.

#### After setup

The Audit page should recognize that the associated project is in setup state.

Conceptual UI:

```text
Mneme installed — Setup mode

✓ Architecture baseline connected
✓ Agent integration detected
✓ 4 protection opportunities to review
○ Preventive enforcement not enabled

[Start Pilot]
```

Primary CTA after successful setup:

> Start Pilot

The exact UI implementation should follow the site's existing components and design system.

Do not introduce a new dashboard or onboarding application for M1.3.

### M1.3d — Funnel instrumentation + pilot handoff

Instrument the minimum activation funnel.

Conceptual events:

```text
audit_completed
audit_saved
install_cta_clicked
setup_started
setup_completed
pilot_cta_clicked
pilot_started
re_audit_completed
```

Where useful and already compatible with current analytics:

```text
setup_integration_detected
setup_integration_configured
```

Reuse the existing analytics/event infrastructure.

Do not build a new analytics platform.

The important measurable funnel is:

```text
Audit completed
    ↓
Baseline saved
    ↓
Install intent
    ↓
Setup completed
    ↓
Pilot started
    ↓
Protection activated
    ↓
Re-audit
```

## 5. Audit readiness semantics

M1.3 must not automatically create rules from Audit findings.

Instead, setup may translate Audit findings into a readiness view.

Conceptually:

| Audit classification | Setup interpretation |
| --- | --- |
| Protected | Existing protection detected |
| Protectable | Mneme-ready / protection opportunity |
| Guidance | Requires modelling or remains guidance |

Naming may be adjusted to match the current Audit vocabulary.

Critical rule:

> Installing Mneme does not make a Protectable decision Protected.

A decision can only be reported as Protected where actual mechanical protection evidence exists under the frozen Architecture Audit metric semantics.

## 6. Setup-mode permissions

Setup MAY:

- initialize existing Mneme project state;
- initialize normal repo-native Mneme files;
- connect a saved Audit baseline;
- load architectural context;
- detect integrations;
- configure supported non-blocking integration behavior;
- run non-blocking checks;
- expose warnings;
- report protection/readiness opportunities;
- record setup metadata;
- report setup completion.

Setup MUST NOT:

- enable blocking enforcement implicitly;
- invent ADRs;
- automatically generate and activate guardrails;
- rewrite application code;
- mutate unrelated repository configuration;
- mark an unprotected decision Protected merely because Mneme was installed;
- automatically start a pilot;
- create broad account/auth infrastructure;
- silently transition to `active`.

## 7. Persistence

Reuse the M1/M1.2 project and Audit persistence model wherever possible.

Conceptually the backend may need to represent:

```text
installation_id
project_id
audit_id
state
mneme_version
repository_commit_sha
integration_detected
integration_configured
setup_started_at
setup_completed_at
activated_at
baseline_schema_version
setup_schema_version
```

These fields are conceptual, not a mandatory schema.

The implementation agent may adapt them to the existing data model.

Do not create parallel persistence models when existing project/Audit records can be extended cleanly.

Local Mneme state should similarly reuse existing project metadata instead of creating new files unnecessarily.

## 8. Pilot boundary

M1.3 ends when:

```text
Mneme installed
Audit baseline connected
Environment detected
Architectural context available
Protection opportunities visible
Preventive enforcement not enabled
```

The pilot begins when the team intentionally selects architectural constraints to protect.

Conceptual pilot flow:

```text
Review protection opportunities
    ↓
Choose important constraints
    ↓
Model protection
    ↓
Validate
    ↓
Explicitly enable
    ↓
Observe
    ↓
Re-audit
```

Rule modelling and automatic protection generation are not part of M1.3.

## 9. Explicitly out of scope

M1.3 must not expand into:

- automatic ADR generation;
- automatic guardrail generation;
- automatic LLM rule generation;
- bulk enforcement activation;
- billing;
- organisations;
- RBAC;
- broad account/auth work;
- cloud control plane;
- fleet management;
- sophisticated installation management;
- multi-repository baselines;
- automatic GitHub PR creation;
- continuous repository monitoring;
- continuous architectural drift detection;
- approval workflow systems;
- a new onboarding application;
- a new dashboard.

If implementation appears to require one of these, escalate rather than silently expanding scope.

## 10. Acceptance gates

### G1 — Safe setup

A supported fresh repository can execute the setup flow successfully.

At completion:

- Mneme is initialized;
- state is `setup`;
- preventive blocking enforcement is not enabled.

PASS requires automated evidence.

### G2 — Idempotency and existing projects

Rerunning setup must be safe.

Running setup against an existing Mneme project must not destroy or unexpectedly rewrite valid existing configuration.

PASS requires automated tests covering fresh and existing project states.

### G3 — Audit linking

A valid saved Audit can be associated with a Mneme setup using the approved pairing/reference mechanism.

The linkage preserves the required baseline/project provenance.

Invalid, expired or mismatched references must fail safely.

PASS requires automated evidence.

### G4 — No protection-score inflation

Installing or setting up Mneme must not change an Audit decision from Protectable/Guidance to Protected unless actual mechanical enforcement evidence exists.

A setup-only installation must not artificially improve Architecture Audit protection metrics.

PASS requires a regression test or equivalent machine-verifiable evidence.

### G5 — Integration detection

The setup flow correctly detects the primary currently supported Mneme agent/integration environments relevant to the existing product.

Detection must not itself activate blocking enforcement.

PASS requires targeted tests.

### G6 — Audit UI activation state

The Audit product can distinguish at minimum:

```text
Not installed
Setup
Active
```

A saved Audit associated with a successful setup reflects setup status and exposes the correct next action.

PASS requires UI/API tests appropriate to the current stack.

### G7 — Funnel attribution

A setup initiated from an Audit can be attributed back to the corresponding Audit/project.

The minimum activation events required by the existing analytics architecture are emitted or recorded.

PASS requires machine-verifiable evidence where practical.

### G8 — Existing-product regression

M1.3 must not regress existing Mneme behavior.

At minimum:

- relevant existing CLI tests pass;
- relevant integration tests pass;
- Architecture Audit metric semantics remain unchanged;
- frozen enforcement benchmarks remain unchanged;
- retrieval behavior is not unintentionally altered;
- existing M1/M1.2 Audit behavior remains valid.

Use the current canonical regression suites/benchmarks rather than inventing substitutes.

## 11. Implementation autonomy

The implementation agent MAY autonomously:

- inspect relevant repositories;
- inspect ADRs and existing implementation;
- choose implementation details consistent with existing conventions;
- create branches;
- add migrations;
- add API endpoints;
- add CLI behavior;
- add UI components/states;
- add and modify tests;
- refactor code locally where required by this scope;
- update documentation;
- run tests, linters and benchmarks;
- fix CI failures;
- self-review its own changes;
- open implementation PRs.

It MUST NOT change the frozen product semantics in this document without escalation.

## 12. Escalation conditions

Escalate only if:

1. Two frozen requirements conflict.
2. A new durable architectural boundary requires a new ADR/product decision.
3. Broad authentication/security scope is required.
4. A destructive or incompatible data migration is required.
5. Product scope must materially expand.
6. An acceptance gate itself appears incorrect or impossible without changing its semantics.

Do not escalate routine implementation choices.

Rule of thumb:

> If the decision changes what Mneme means or promises, escalate.

> If the decision only changes how the frozen promise is implemented, decide autonomously.

## 13. Execution structure

Implement in this order unless repository dependencies prove a small sequencing change necessary:

```text
M1.3a — Setup state + CLI
        ↓
M1.3b — Audit baseline pairing
        ↓
M1.3c — Audit activation UI
        ↓
M1.3d — Funnel instrumentation + pilot handoff
```

Each increment should normally have its own branch/PR.

Do not begin a later increment when the contract required by the earlier increment is still unstable.

## 14. Verification hierarchy

For each increment run, where applicable:

1. New targeted tests.
2. Existing affected subsystem tests.
3. Full relevant repository test suite.
4. Frozen product benchmarks/regression gates.

Unit-test success alone is not sufficient evidence for milestone completion.

## 15. Self-review requirement

Before marking each PR ready:

1. Review the complete diff as a skeptical maintainer.
2. Look specifically for:
   - implicit enforcement activation;
   - Audit metric inflation;
   - unsafe Audit reference handling;
   - state inconsistencies;
   - destructive project initialization;
   - regressions;
   - unnecessary parallel abstractions;
   - product scope creep.
3. Fix valid findings.
4. Rerun affected tests.
5. Record acceptance-gate evidence.

## 16. Execution log

Maintain:

```text
docs/plans/m1-3-execution-log.md
```

Keep it concise.

Suggested structure:

```text
## Current increment
M1.3a

## Status
IN PROGRESS

## Completed
- ...

## Current work
- ...

## Acceptance gates
G1: PASS / FAIL / NOT YET APPLICABLE
G2: ...
...

## Implementation decisions
- ...

## Verification
- ...

## Escalations
None
```

The execution log is operational history, not a replacement for ADRs.

## 17. Completion condition

M1.3 is complete only when all applicable G1–G8 gates pass and the end-to-end behavior supports:

> Audit architecture → save baseline → safely install Mneme → enter setup mode → connect baseline → see protection opportunities → explicitly choose whether to start a pilot.

The core product promise is:

> Install Mneme without changing how your team works yet. Connect your architecture baseline, then decide which protections to activate.

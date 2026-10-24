# Mneme — Current Roadmap

> **Current roadmap — October 2026.**
>
> The original [April 2026 adoption and enhancement roadmap](./2026-04-24-adoption-and-enhancement-roadmap.md) is retained as historical context. It describes the path from an early working implementation to a usable developer tool. Mneme has moved beyond that stage: the core enforcement mechanism and several native agent integrations now ship. This file is the current operational roadmap.

## Current phase

**External validation and adoption.**

The central question is no longer whether Mneme can implement architectural enforcement. The current question is whether that control layer produces repeatable value on real repositories, with external developers and design partners, across the AI coding surfaces teams already use.

The roadmap therefore prioritizes evidence, pilots, and interoperability over adding integrations for their own sake.

## NOW — prove the wedge

### P0 — Design partners and real-repository pilots

Use real projects to validate whether recorded architectural decisions prevent meaningful drift during AI-assisted development.

**Evidence sought**

- first-attempt architectural compliance;
- functional completion;
- unrequested scope expansion;
- setup and maintenance friction;
- whether teams retain Mneme after the initial evaluation.

### P0 — Architecture Audit as an acquisition and evidence surface

Use the Architecture Audit Workspace to identify which existing architectural decisions are mechanically governable and where enforcement gaps remain.

The Audit consumes the authoritative core `assess_governability()` result. It must not grow a second policy model in the UI.

### P0 — Reproducible architecture-compliance benchmark

Extend the existing benchmark discipline toward externally legible comparisons of architectural compliance across coding-agent workflows.

Prefer frozen fixtures, deterministic scoring, clear treatment/control boundaries, and explicit separation of functional completion from architectural compliance.

### P0 — Four-layer decision-conformance validation

Validate the **existing** governance model end to end: **Guidance → Pre-mutation enforcement → CI checks → Evidence**. This is a cross-cutting acceptance test for the current benchmark, DG1, integration and CI assurance work, **not** a fifth layer, a new policy engine, or DG2 scope.

The Decision Index supplies the common decision authority and applicability semantics to each layer. A process or ADR-acknowledgment marker may be useful workflow evidence, but must not count as proof that code conforms to an architectural decision.

**Minimum reproducible test**

- Freeze one sample repository, one human-reviewed decision and one verified typed rule. Test both a compliant change and an ADR-acknowledged change that still violates the actual constraint.
- Demonstrate the supported pre-mutation boundary really prevents a forbidden mutation; where a host lacks a blocking seam, explicitly report detection-only or **unevaluated** rather than claiming protection.
- Independently check the resulting change through CI. Record whether the CI result uses the same applicable decision and rule revision, and distinguish warn from blocking mode.
- Include a valid scoped exception, an invalid/expired exception, benign-change controls, missing/stale decision binding and unavailable current-byte cases.
- Produce decision-linked evidence: effective decision and source/version, target scope, rule lineage, enforcement surface, evaluated input/revision, verdict, reasons and limitations. Measure architectural compliance **and** functional completion, false blocks and setup friction.

**Exit evidence:** a repeatable trace showing permitted work succeeds, a documented-but-noncompliant change is caught at each *supported* control point, and a complete record of unevaluated or unsupported surfaces. Reuse the production governance trace (#282), DG1 tracker (#497) and separate CI1 enforcement-assurance tracker (#540). Do not claim universal mutation coverage or directly compare an external product without a reproduced baseline.

### P0 — Decision Index authority completion (D1)

D0 is shipped: Mneme has a canonical, source-independent Decision Index boundary with Layer 1 runtime projection parity.

**D1 is complete and shipped in `mneme-hq==0.10.0`.** D1B-D1E made that boundary the actual durable authority: canonical persistence, load-time projection, authority-path cutover, immutable version evolution, ADR re-import, explicit supersession, stable rule lineage, canonical protection and `add_decision` writers, the explicit `mneme decision-index migrate` transition, and canonical `init`/`setup`. Evidence and the release gate are recorded in the [D1 closeout](../architecture/d1-closeout.md). Retiring the compatibility snapshot (D1F) remains optional and separate.

The invariant D1 established, and that DG1 builds on, is:

```text
source / proposal
      ↓
canonical Decision Index
      ↓
authoritative lifecycle + version + rule lineage
      ↓
Layer 1 projection
      ↓
retrieval / enforcement / Audit / evidence
```

See accepted [ADR-023](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md) and [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md).

## NEXT — strengthen the product surface

### P1 — DG1: Decision governance semantics (post-D1)

DG1 is now partly implemented. DG1A, DG1C, DG1E, DG1D, DG1P and DG1B1 have landed: the governance contract is accepted, the effective-decision resolver matches v1 projection, canonical evidence identity is threaded through enforcement traces, snapshot-to-snapshot governance change is available, ADR `date` no longer carries precedence authority, and canonical decision applicability now resolves deterministically under `mneme.decision-index/v2`.

The governing architecture remains accepted [ADR-031](../adr/ADR-031-decision-governance-semantics.md). Decision applicability (DG1B1) landed under its [merged charter](../plans/2026-10-08-dg1b1-decision-applicability-charter.md) and [Layer 1 freeze amendment](../architecture/layer1-freeze-e73ff7d.md): optional exact project-local `required_labels` persist under `mneme.decision-index/v2`, an explicit v1 → v2 migration preserves global eligibility, and the shared resolver gains a `not_applicable` cause. Waivers (DG1B2) remain evidence- and target-binding-gated. DG1F then converges runtime consumers onto the shared governance result, followed by DG1G adversarial closeout. Until DG1F lands, no runtime consumer changes which decisions it enforces.

DG1 defines a public, versioned semantic contract for:

- decision authority and authority source;
- decision scope and applicability, while preserving the distinction from typed-rule applicability;
- precedence and deterministic effective-decision resolution;
- lifecycle and supersession;
- provenance and source evidence;
- explicit exceptions / waivers and their authority;
- enforceability and rule lineage;
- enforcement/evidence linkage; and
- deterministic explanation of why a decision is effective for a given context.

The target question is:

```text
Given the decisions known to Mneme,
which authoritative decisions govern this context,
which do not,
and why?
```

DG1 is **public OSS in full**: the semantic contract, canonical records, deterministic effective and change resolution, applicability, precedence, waivers, evidence identity, and explanation surfaces all belong to the core.

The publication boundary is: **OSS owns decision execution; enterprise owns decision operations at organizational scale.** Neither DG1 nor DG2 becomes that operations layer. These stay outside the OSS core:

- automated discovery of decisions in organizational sources;
- continuous synchronization with those sources;
- cross-system identity, reconciliation and deduplication;
- authority or relationship inference, including from enterprise roles or directory systems;
- organization-wide identity, RBAC/SSO and delegated governance;
- retained organization-wide evidence history;
- hosted multi-tenant governance, approval/admin workflows, fleet propagation; and
- organization-wide analytics/control-plane behavior.

**Shared resolution contract:** as DG1 runtime convergence is accepted, CLI, hook, CI, MCP retrieval/explanation and evidence should consume one versioned authority/applicability result rather than independently interpreting documents or policy. Track exact decision/rule revision, repository binding and supported override semantics. Distinguish `ALLOW`, `DENY`, `UNEVALUATED` (or the existing contract's equivalent explicit outcomes); never turn missing context, unavailable policy, or a retrieval hint into a positive enforcement verdict. Changes to behavior remain gated by the accepted ADR and Layer 1 freeze amendment process.

### P1.5 — DG2: deterministic decision federation (public OSS)

Once DG1 semantics are stable, extend the same governance resolver across more than one known decision source or repository. Learn from existing federation designs, but federate **Mneme decision authority**, not merely files or Markdown corpora.

DG2 is public OSS and must be production-capable for multi-repository software factories, not a reference model. It federates **known** decision sources deterministically:

```text
declared organization-level decisions
        ↓
declared platform / domain decisions
        ↓
repository decisions
        ↓
authorized exception / waiver
        ↓
effective decisions for this context
```

Required properties include stable source identity/namespaces, pinned source revisions, provenance-preserving inheritance, deterministic ambiguity failure, explicit override/exception chains (ADR-031 waiver semantics), and one governance resolution result consumed by retrieval, enforcement and explanation (the ADR-031 resolver, never a second policy engine). Retrieval ranking remains non-authoritative under ADR-017.

"Bounded" describes the architecture (a finite set of declared sources at pinned revisions, a deterministic graph), never a limit on what OSS may do. The enterprise boundary begins where Mneme would have to discover, reconcile, infer, synchronize or administrate organizational decision truth rather than resolve declared sources.

**OSS–Enterprise Boundary Validation checkpoint (DG1 → DG2; review-only).** At DG1G closeout, and again before DG2 implementation, validate the proposed surfaces against accepted [ADR-031](../adr/ADR-031-decision-governance-semantics.md) and the publication boundary above. Record the outcome in the **existing** DG1G closeout / DG2 architecture review; this is **not** a new implementation workstream or authorization.

- **OSS completeness:** DG1 authority, applicability, precedence, lifecycle, waivers, provenance, evidence identity, deterministic resolution/enforcement, and explanation remain public. DG2 federation of declared, revision-pinned decision sources remains production-capable without requiring an enterprise service.
- **Enterprise separation:** automated organizational decision discovery, source synchronization, cross-system identity/reconciliation/deduplication, inferred authority or relationships, organization-wide RBAC/SSO and administration, retained evidence history, and hosted/fleet control-plane operations remain outside OSS.
- **Authority preservation:** source adapters and external producers can supply evidence or proposals, but cannot promote their own decisions or waivers to authority. DG2 uses the ADR-031 resolver rather than introducing a second policy engine.
- **Evidence and disposition:** identify the interfaces and dependencies inspected, record any cross-boundary ambiguity and its disposition, and require a separately reviewed architecture decision before moving an operation across the boundary. No runtime, schema, ADR, freeze, or implementation change is approved by this checkpoint.

### P1 — Architecture Review Skill

Evolve the existing Claude Code `mneme` Skill into a clearer executable architecture-review interface over existing Mneme capabilities.

The intended workflow is:

```text
project decisions / ADRs
        ↓
relevant context
        ↓
proposed or pending change
        ↓
Mneme check / review / governability evidence
        ↓
structured architecture review
```

**Constraint:** the Skill is an interface over Mneme retrieval and deterministic enforcement. It must not become a second policy engine or substitute model judgment for `mneme check` verdicts.

Initial work should reuse the shipped `/mneme:context`, `/mneme:check`, `/mneme:record`, and `/mneme:review` surfaces before adding new runtime behavior.

**First protected change onboarding:** package one short, maintained example that starts with a reviewed decision, activates an existing verified typed rule, then shows an allowed and a prohibited change with their actual enforcement/evidence output. Optimize for a first useful architectural protection outcome, not install completion or a new multipurpose coding harness. Label curated/example decisions separately from automatically discovered decision candidates; verify the workflow under a pinned supported integration and show any unsupported host mutation path.

### P1 — Source-independent decision ingestion contract

Core keeps the public, source-independent path from existing decision records into Mneme: the proposal-ingestion contract (ADR-027), provenance, and the explicit authority transition into the canonical Decision Index. Any source adapter, first-party or third-party, builds on that contract. A source never declares itself authoritative.

Keep ingestion separate from enforcement semantics: source adapters import decision evidence and intent; the Mneme core owns decision authority, lifecycle, representation, rule compilation, and governance.

Automated discovery and continuous synchronization of organizational sources (for example wikis, ticketing and chat systems) are enterprise decision operations, not core runtime work, and are not tracked on this roadmap.

Do not assume another review/context platform's Confluence, Jira, Slack, Notion, or monitoring connections are a reusable Mneme ingestion API unless an explicit supported data contract is validated.

### P1 — Decision MCP consumer + proposal-ingestion surface

After D0 projection parity is proven, define a narrow Decision MCP surface that supports both:

1. external consumers retrieving authoritative Mneme decisions; and
2. external producers submitting candidate architectural decisions as **non-authoritative proposals**.

The MCP sits over the canonical Decision Index; it must not become its own decision store or enforcement engine.

P0 operations are scoped as:

```text
decision.propose
decision.propose_batch
decision.get
decision.search
decision.applicable_to
decision.trace
```

A proposal is never enforceable. Generic MCP producers may provide decision text, rationale, provenance, context, and scope hints, but may not activate enforcement, mark decisions Protected, create verified evidence, create exceptions, supersede Active decisions, or bypass Mneme review/lifecycle controls.

The intended producer flow is:

```text
external architecture system
        ↓
Decision MCP proposal
        ↓
human review / Mneme authority step
        ↓
canonical Decision Index
        ↓
Architecture Audit / modelling
        ↓
Rule + applicability
        ↓
Enforcement / evidence
```

Proposal state is separate from canonical decision lifecycle. P0 supports `proposed -> accepted` or `proposed -> rejected`, but acceptance is a Mneme-owned authority action and is not exposed as a generic producer mutation.

Proposal ingestion must be idempotent by stable producer/source/version identity. Preserve decision context available **at creation time** (known rationale, rejected alternatives, reversibility/exit cost, intended scope and provenance), alongside evidence reconstructed later. Both are non-authoritative until the explicit human-reviewed Mneme authority transition. Capture is not autonomous promotion or a second authoritative store. Semantic similarity may flag likely duplicates for review but must not auto-merge canonical decisions.

Use `sagarika29/ai-system-architect` as the first producer-workflow compatibility test after the generic contract exists. Do not add Sagarika-specific logic to the Decision Index/MCP core.

This surface remains distinct from the generic hosted MCP / HTTP control plane listed under Deferred. A local OSS implementation may expose proposal ingestion and retrieval over the Decision Index kernel; cross-repository federation of known decisions is DG2 (public OSS). Organization-wide persistence, source discovery and reconciliation, RBAC/SSO, multi-tenant governance, and hosted control-plane behavior remain outside the core.

See proposed [ADR-027](../adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md) and issue #362.

### P1 — Reference review consumer validation

Validate one external review system against the Decision MCP surface after the surface exists. CodeRabbit is a strong candidate because its current product supports custom MCP context during code review.

The experiment should test whether the consumer can retrieve applicable Mneme decisions and use them as authoritative review context while Mneme continues to own deterministic pre-action enforcement.

This is a compatibility/reference integration, not a dependency. Mneme must continue to operate independently through its existing agent, CLI, hook, and CI surfaces.

Do not add CodeRabbit-specific logic to the Decision Index or enforcement core.

### P1 — Explainable enforcement and observable coverage

Improve the existing Audit, enforcement evidence and readiness reporting without duplicating the Core evaluator. A blocked change should identify the actual violated decision/rule and offer a compliant path or an authorized, scoped waiver route—not an untracked bypass. Expose coverage and **negative space**: applicable decisions evaluated and not evaluated, failed and passed checks, supported pre-mutation versus CI-only detection, benign false blocks, waiver validity, stale policy and unsupported operations. Process-marker compliance and retrieval success are distinct from semantic conformance.

Use version-pinned decisions and rule/evaluator contracts across supported surfaces. Maintain a tested compatibility matrix, explicit timeout/failure behavior and rollback guidance; do not silently alter active enforcement via tool updates. This work refines the existing four layers (especially Enforcement, CI and Evidence) and builds on CI1 (#540), rather than adding a new layer.

### P1 — Migration-aware Architecture Audit

Extend the existing Audit workflow for long-running migrations and modernization, where legacy and target architectures coexist and path applicability matters.

Do not create a separate migration product unless pilot evidence justifies it.

### P1.5 — Deep Agents capability POC

Run the pinned Deep Agents validation already described in the integration roadmap. Determine whether filesystem mutation tools expose a reliable pre-mutation seam and whether nested/subagent behavior preserves the governance boundary.

Promotion requires evidence; no support claim before the capability gate passes.

## RESEARCH — evidence before integration

### P2 — Slack Code and shared multi-agent constraints

Investigate whether a shared coding workspace can consume one project architectural contract across multiple coding agents and sessions.

The question is not generic workspace governance. It is whether Mneme can remain the architectural-control layer while the harness coordinates agents, permissions, and collaboration.

### P2 — AWS AgentCore benchmark

Retain the existing AgentCore experiment: use AgentCore as a controlled multi-agent execution substrate for architecture-compliance benchmarking before deciding whether a deeper product integration is justified.

### P2 — Salesforce Skills interoperability

Test whether Mneme adds measurable project-specific architectural compliance when Claude Code is already using Salesforce's domain Skills.

Candidate treatment structure:

```text
A  Claude Code + Salesforce Skills
B  Claude Code + Salesforce Skills + Mneme review/context workflow
C  Claude Code + Salesforce Skills + Mneme workflow + deterministic hook
```

Measure architecture compliance, functional completion, and scope expansion.

**This is an interoperability experiment, not a Claudeforce integration claim.** Do not add Salesforce or Claudeforce to the support matrix until Mneme has actual validation evidence or maintained adapter code.

### P2 — Claude Managed Agents revisit

The completed M0 is **PARTIAL** and remains evidence-only.

Revisit only if Anthropic exposes one or more of the missing control surfaces identified by the validation:

- current workspace bytes at approval time;
- a filesystem-local confirmation/evaluation handler;
- a blocking completion/Stop-equivalent boundary.

## DEFERRED — wait for evidence or user pull

- EventCatalog graph enrichment beyond the validated retrieval-only boundary, until there is a jointly useful hypothesis.
- Shared policy packs.
- Generic hosted MCP / HTTP control plane. This does **not** include the narrow Decision MCP consumer/proposal surface described above.
- Broad SaaS administration, billing, or account surfaces.
- Higher-level policy DSL beyond the current typed-rule path.
- Deeper integrations that do not expose a reliable mutation or verification seam.

## Shipped foundation

The roadmap assumes the following foundation is already delivered:

- deterministic decision retrieval and project memory;
- ADR compiler / precedence path;
- strict/warn enforcement;
- typed `FORBID_LITERAL` rules;
- explicit path applicability;
- introduced-delta enforcement and prevent → catch → verify integration model;
- authoritative governability assessment;
- read-only ADR lifecycle reconciliation;
- enforcement-quality benchmark discipline;
- native integrations for Claude Code, Claude Agent SDK, Google Antigravity, Codex CLI, LangChain/LangGraph, and Kiro CLI v3;
- validated Paperclip compatibility;
- experimental Hermes integration;
- evidence-only Claude Managed Agents validation;
- EventCatalog retrieval-only ADR ingestion and effectiveness validation;
- Architecture Audit Workspace vertical slice.

For current support claims, always use [the canonical integration support matrix](../integrations/README.md), not this roadmap.

## Roadmap rules

1. **Evidence before promotion.** A planned or experimental surface does not become supported because an adapter looks feasible.
2. **Reuse the core.** Integrations translate transport and lifecycle events into existing Mneme semantics; they do not copy retrieval or enforcement logic.
3. **External validation outranks integration count.** A real design-partner result is more valuable than another unvalidated adapter.
4. **Keep retrieval separate from enforcement.** Context, Skills, RAG, source ingestion, and proposal ingestion can improve what the agent/system knows; deterministic rules decide what Mneme can mechanically govern.
5. **Preserve decision authority.** External systems may consume authoritative Mneme decisions or propose candidate decisions, but they do not become the authoritative Decision Index or determine acceptance, lifecycle, rule compilation, or enforcement semantics.
6. **No speculative platform expansion.** Hosted/team/org layers wait for user pull and evidence from the current wedge.

## Related

- [Current phase](../architecture/current-phase.md)
- [ADR-023: Canonical Decision Index and Runtime Projection Boundary](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md)
- [ADR-027: Decision MCP Proposal Ingestion and Authority Boundary](../adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md)
- [Canonical integration support matrix](../integrations/README.md)
- [Historical April 2026 roadmap](./2026-04-24-adoption-and-enhancement-roadmap.md)
- [Changelog](../../CHANGELOG.md)
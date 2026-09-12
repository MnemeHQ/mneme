# Mneme — Current Roadmap

> **Current roadmap — August 2026.**
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

### P0 — Decision Index architecture contract (D0)

Establish a canonical, source-independent Decision Index boundary without changing the validated Layer 1 runtime.

The existing `mneme.schemas.Decision` / `Rule` representation remains the architecture runtime projection. D0 must prove that the current ADR corpus can be represented canonically and projected back with identical retrieval, enforcement, ConflictDetector, Architecture Audit, and benchmark behavior.

This is architecture hardening, not a broad enterprise feature build. It must not displace the external-validation priorities above or introduce new ingestion surfaces, rule types, hosted control-plane behavior, or non-code enforcement.

See proposed [ADR-023](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md) and the D0 implementation issue.

## NEXT — strengthen the product surface

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

### P1 — Decision-source ingestion: Confluence first, Jira when authoritative

Continue the source-ingestion track where it gives teams a lower-friction path from existing decision records into Mneme.

Confluence ADR ingestion remains the first explicit target. Jira may follow where a team genuinely records authoritative architectural decisions there. Do not add a Jira adapter merely because Jira is widely integrated elsewhere.

Keep ingestion separate from enforcement semantics: source adapters import decision evidence and intent; the Mneme core owns decision authority, lifecycle, representation, rule compilation, and governance.

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

Proposal ingestion must be idempotent by stable producer/source/version identity. Semantic similarity may flag likely duplicates for review but must not auto-merge canonical decisions.

Use `sagarika29/ai-system-architect` as the first producer-workflow compatibility test after the generic contract exists. Do not add Sagarika-specific logic to the Decision Index/MCP core.

This surface remains distinct from the generic hosted MCP / HTTP control plane listed under Deferred. A local OSS implementation may expose proposal ingestion and retrieval over the Decision Index kernel; organization-wide persistence, cross-repo aggregation, source reconciliation, RBAC/SSO, multi-tenant governance, and hosted control-plane behavior remain separate boundaries.

See proposed [ADR-027](../adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md) and issue #362.

### P1 — Reference review consumer validation

Validate one external review system against the Decision MCP surface after the surface exists. CodeRabbit is a strong candidate because its current product supports custom MCP context during code review.

The experiment should test whether the consumer can retrieve applicable Mneme decisions and use them as authoritative review context while Mneme continues to own deterministic pre-action enforcement.

This is a compatibility/reference integration, not a dependency. Mneme must continue to operate independently through its existing agent, CLI, hook, and CI surfaces.

Do not add CodeRabbit-specific logic to the Decision Index or enforcement core.

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
- Team/org policy synchronization.
- Cross-repository governance.
- Shared policy packs.
- Generic hosted MCP / HTTP control plane. This does **not** include the narrow Decision MCP consumer/proposal surface described above.
- Broad SaaS administration, billing, or account surfaces.
- Higher-level policy DSL beyond the current typed-rule path.
- Deeper integrations that do not expose a reliable mutation or verification seam.
- Broad Slack / Teams / Notion decision ingestion until source evidence or user pull shows that those systems contain authoritative decisions Mneme should ingest.

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
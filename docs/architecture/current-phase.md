# Mneme — Current Phase

> One-page orientation: where Mneme is right now, what is frozen, what is shipped, what is experimental, and what remains to validate.
> If you are a contributor, design partner, or new reader, start here.

## Phase

**Layer 1 — external validation and adoption phase.**

Layer 1 is local-repo, project-scoped architectural governance for AI-assisted software development. The core mechanism is established; the current priority is proving that it prevents architectural drift on real repositories, with external developers and design partners, across the agent surfaces teams already use.

This is no longer primarily a capability-building phase. New integrations and experiments are justified when they strengthen external validation, interoperability evidence, or the architectural-control thesis.

## What is frozen

Pinned at commit [`e73ff7d`](https://github.com/MnemeHQ/mneme/commit/e73ff7d) and documented in [layer1-freeze-e73ff7d.md](./layer1-freeze-e73ff7d.md):

- **Retrieval mechanics** — deterministic bag-of-tokens scoring with fixed weights, stopword floor, insertion-order tiebreak.
- **Enforcement semantics** — `anti_patterns` → FAIL, `"no X"` constraints → WARN, word-boundary matching. Frozen at `e73ff7d` as top-K-only (enforcement bounded by the retrieval top-N); [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md) subsequently separated enforcement scope from retrieval scope, so typed literal rules are evaluated independently of retrieval ranking, with typed-rule semantics under [ADR-019](../adr/ADR-019-typed-literal-rule-contract.md) and path applicability under [ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md).
- **Benchmark methodology** — two-layer scoring (retrieval vs. enforcement), structured-fixture path with TXT fallback, five-verdict semantics, K=3 canonical.
- **Charter principles** — deterministic > clever, auditable > autonomous, prevention before review, no passive ingestion, no auto-learning, no hidden vector magic.
- **Scope wedge** — project-scoped architectural governance. Team, org and cross-repo governance remain later-layer territory.

No behavioral change to retrieval or enforcement is in scope without an explicit charter amendment.

## What is shipped

The canonical support taxonomy lives in [docs/integrations/README.md](../integrations/README.md). As of the v0.6.0 line, shipped product surfaces include:

- `mneme` Python package and CLI, including `mneme check`, typed `FORBID_LITERAL` rules and explicit path applicability.
- Authoritative governability assessment via `assess_governability()`, classifying decisions as `enforceable`, `partial`, or `guidance`.
- ADR parser/compiler/validator plus read-only ADR lifecycle reconciliation.
- **Native integrations:** Claude Code, Claude Agent SDK, Google Antigravity, Codex CLI, LangChain agents on LangGraph, and Kiro CLI 3.0 / v3.
- **Validated compatibility:** Paperclip through its CLI and ACP transports.
- **Rules export:** Cursor.
- **CLI-based CI gates:** reference patterns for CI systems such as GitHub Actions and GitLab CI.

The Claude Code plugin also ships a `mneme` Skill and the `/mneme:context`, `/mneme:check`, `/mneme:record`, and `/mneme:review` commands. The Skill is an executable workflow over Mneme capabilities; deterministic enforcement remains owned by the hook and `mneme check`, not by the Skill itself.

## What is experimental or evidence-only

These surfaces have useful evidence but are not promoted to full support:

- **Hermes Agent** — Experimental. Context injection and supported pre-tool blocking are proven; no blocking Stop-equivalent exists.
- **OpenCode** — Experimental. Plugin-hook work remains incomplete; the completed compaction experiment returned a NULL verdict.
- **Claude Managed Agents** — evidence-only **PARTIAL** result. New-file interception and multi-agent propagation are proven, but existing-file/edit materialization and completion-boundary limitations prevent support promotion.
- **EventCatalog** — retrieval-only ADR ingestion and effectiveness validation exist, but graph enrichment remains intentionally deferred pending a jointly useful hypothesis.

The Architecture Audit Workspace is a separate product-facing vertical slice over the released Mneme core. Governability semantics remain owned by the core package rather than being reimplemented in the UI.

## What is deferred

Later-layer territory. Promote only with user pull or evidence that it strengthens the current validation program:

- Multi-developer / team governance.
- Shared policy packs.
- Cross-repo / org-wide governance.
- Generic MCP / hosted HTTP control plane.
- Deeper IDE integrations where no reliable control seam exists.
- Higher-level policy DSL beyond the current typed-rule path.
- EventCatalog graph enrichment without a validated retrieval hypothesis.
- Claude Managed Agents production support until the required mutation/current-byte or blocking completion surfaces exist.

The freeze doc also lists "Intentionally NOT Solved" items — those are not deferred; they are out of scope for Mneme as a project.

## What success means right now

The Layer 1 exit criteria from the freeze doc remain the governing test:

1. Benchmark integrity stabilized — **met**.
2. Deterministic enforcement validated — **met**.
3. Real-world drift prevention demonstrated — **open**, requires external evidence.
4. Design-partner validation complete — **open**.
5. Governance wedge validated — **open**.

Items 1 and 2 are mechanical. Items 3, 4, and 5 are the work of the current phase. They cannot be completed by adding more integrations or writing more core code without external evidence.

## Current priorities

See the [current roadmap](../roadmap/README.md). In brief:

- **Now:** design-partner / real-repository pilots, Architecture Audit as an acquisition and evidence surface, and reproducible architecture-compliance benchmarking.
- **Next:** evolve the existing Claude Skill toward an Architecture Review workflow; continue high-value ADR/source ingestion such as Confluence; extend the Audit workflow for migration use cases; run the planned Deep Agents capability POC.
- **Research:** Slack Code/shared multi-agent constraints, AWS AgentCore benchmarking, Salesforce Skills interoperability, and revisit triggers for Claude Managed Agents.

## Links

- **Current roadmap** — [docs/roadmap/README.md](../roadmap/README.md)
- **Historical adoption roadmap** — [2026-04-24-adoption-and-enhancement-roadmap.md](../roadmap/2026-04-24-adoption-and-enhancement-roadmap.md)
- **Canonical integration support matrix** — [docs/integrations/README.md](../integrations/README.md)
- **Freeze artifact** — [layer1-freeze-e73ff7d.md](./layer1-freeze-e73ff7d.md)
- **Governance representation** — [governance-representation.md](./governance-representation.md)
- **Benchmark methodology (public)** — [/benchmark/](https://mnemehq.com/benchmark/) and [/docs/benchmark-methodology/](https://mnemehq.com/docs/benchmark-methodology/)
- **ADRs** — [docs/adr/](../adr/)
- **Repo governance source of truth** — [`.mneme/project_memory.json`](../../.mneme/project_memory.json)

## Contributor guidance

Before opening a PR, ask: does this change behavior in `decision_retriever.py`, `enforcer.py`, `benchmark.py`, or any benchmark fixture? If yes, it is a charter-level change and the freeze doc's amendment procedure applies. If no — docs, tooling, integrations, site, examples — proceed normally with `[memory]` prefix discipline for `project_memory.json` edits.

# AGENTS.md

Notes for AI agents working in this repository.

Repository workflow, worktree lifecycle, merge policy, and architecture constraints are defined in `CLAUDE.md`; those rules apply regardless of which agent is executing the task.

## Repository ownership and cross-repo handoff

This **public OSS repository is the canonical Mneme decision and deterministic execution kernel**: Decision Index, decision identity/authority/scope/applicability/precedence/lifecycle/waivers (DG1/DG2), proposal/MCP contracts, rule enforcement, decision-linked evidence, and repository-local audit/integration surfaces.

- **`MnemeHQ/mneme-data-engine` (private):** research evidence acquisition, candidate decision/architecture recovery, probabilistic classification, annotation and frozen evaluation. Results are **non-authoritative evidence** until explicitly reviewed and promoted via Core contracts/ADR. Do not import or depend on Data Engine internals.
- **`MnemeHQ/mneme-enterprise` (private):** source-specific organisational connectors/sync, identity/RBAC/SSO, approval routing, retained organisation-wide audit and hosted operations. Enterprise consumes Core governance/enforcement semantics and may submit non-authoritative proposals; do not import or depend on Enterprise internals.
- **Route work by ownership:** source-independent decision contracts, governance resolution and deterministic verdicts → **here**; discovery quality, benchmark pipelines, evidence reconstruction → **Data Engine**; organisation-specific connectors, permissions, approval/admin and hosted UX → **Enterprise**.
- **Never confuse discovery with authority or a review recommendation with enforcement.** All authoritative transitions require explicit Core semantics; avoid a second policy engine or unsupported production claims.

For reasoning about boundaries read [`docs/roadmap/README.md`](docs/roadmap/README.md), [ADR-031](docs/adr/ADR-031-decision-governance-semantics.md) and `CLAUDE.md`. These instructions govern any coding agent.

## Agent execution provenance

Every pull request must record who actually produced the change. Git author identity is not sufficient because agent work is commonly committed under the human owner's Git identity.

Use the PR template's `Execution provenance` block. Required fields:

- `Change author`: `human`, `agent`, or `mixed`.
- `Agent`: the concrete agent surface (`codex`, `claude-code`, `kiro`, `chatgpt-work`, etc.), or `none` for human-only work.
- `Agent model`: model identifier when exposed; `not-exposed` is acceptable when the tool does not expose it; `n/a` only for human-only work.
- `Agent session`: stable session ID or share/work URL when available; `not-exposed` is acceptable when unavailable; `n/a` only for human-only work.
- `Task origin`: where the task was scoped (`chatgpt`, `claude`, `local`, `manual`, etc.).
- `Human owner`: GitHub username responsible for review/promotion.

When an agent creates commits directly, also append commit trailers where practical:

```text
Agent: codex
Agent-Model: gpt-5.6-sol
Agent-Session: cx_...
Task-Origin: chatgpt
Human-Owner: TheoV823
```

The PR body is the durable source of truth because squash merges may collapse or discard individual commit trailers.

Authorship, human promotion, release/deployment, and worktree cleanup are separate lifecycle facts. Never infer one from another. If usage/session limits interrupt the task, report the remaining lifecycle step explicitly.

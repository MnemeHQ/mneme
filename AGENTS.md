# AGENTS.md

Notes for AI agents working in this repository.

Repository workflow, worktree lifecycle, merge policy, and architecture constraints are defined in `CLAUDE.md`; those rules apply regardless of which agent is executing the task.

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

---
id: ADR-010
title: "Automation-generated artifacts must inherit repository governance conventions"
status: accepted
priority: normal
date: 2026-05-14
scope: automation.governance
---

# ADR-010: Automation-generated artifacts must inherit repository governance conventions

**Status:** Accepted  
**Date:** 2026-05-14  
**Deciders:** Theo Valmis

---

## Context

This repository enforces a branch naming taxonomy (`feat/`, `fix/`, `site/`, `ci/`, `docs/`, `refactor/`) documented in CLAUDE.md and enforced by convention during code review. The intention is that `main` history reads as intentional product decisions, not raw iteration artifacts.

Claude Code's `--worktree` flag and related harness tooling auto-generate branch names using the pattern `claude/<adjective>-<noun>-<hash>` (e.g. `claude/reverent-hoover-a60ffb`). This pattern is hard-coded in the harness and cannot be overridden via `settings.json` or any other configuration surface exposed to repository operators.

This creates an **automation boundary**: a governance policy exists in the repository, but the execution harness emits artifacts that fall outside the policy surface.

---

## Decision

Automation-generated artifacts must inherit repository governance conventions where technically controllable. Where external tooling emits non-compliant artifacts, the exception must be documented and the artifact must be normalized before public release where practical.

Specifically:

1. **Auto-generated worktree branches** (`claude/*`) are a known external-tool exception. They are not a policy violation — they are an acknowledged tooling boundary.
2. **Before a PR is opened against `main`**, the working branch should be renamed to follow the taxonomy if the intent is known (e.g. `site/supported-languages-nav-fix`). If the auto-generated name reaches the PR, the PR title and squash commit must follow the taxonomy regardless.
3. **The squash commit title is the authoritative artifact.** Because all PRs squash-merge, the `main` history remains clean even if the source branch carried an auto-generated name.
4. **Inference limitation.** Automated prefix assignment (`feat/` vs `site/` vs `fix/`) requires knowing task intent. A hook cannot reliably infer this at branch-creation time. Therefore, no automated renaming hook is implemented. The normalization responsibility sits with the operator at PR-creation time.

---

## Scope of the rule

Applies to any artifact that enters a shared, persistent surface:

| Artifact | Shared surface | Normalization required |
|----------|---------------|----------------------|
| Branch name on `main` | No (branches are deleted after squash) | Preferred, not required |
| Squash commit title on `main` | Yes | Required |
| PR title | Yes (visible in repo history) | Required |
| Worktree branch during development | No | Best-effort |

---

## What is not in scope

- Worktree-local branches that are never pushed or are deleted before the PR lands.
- CI-internal ephemeral refs.
- Auto-generated OG image branches or other tooling-owned refs that are squashed before merge.

---

## Rationale

- **The squash-merge invariant already provides the primary protection.** Each PR lands as one clean commit on `main` with a human-authored title. The source branch name is not preserved in `main` history.
- **A renaming hook would over-engineer a solved problem.** Prefix inference is ambiguous at branch-creation time. The cost of a wrong automated prefix is higher than the cost of a human correcting it at PR time.
- **Documenting the exception is stronger than silently tolerating it.** An undocumented exception becomes precedent. A documented one stays bounded.

---

## Consequences

- Auto-generated `claude/*` branch names during development are accepted without remediation.
- PR titles and squash commit messages must follow the taxonomy (`feat:`, `fix:`, `site:`, etc.) regardless of source branch name.
- This decision should be revisited if the harness exposes a `branchPrefix` or `branchTemplate` configuration key.

---

## Roadmap

If Claude Code or the underlying harness exposes configurable branch naming in a future release, this ADR should be superseded by a settings-based enforcement rule. Track at: harness `worktree` settings schema (`~/.claude/settings.json` `worktree` key).

---

## Related

- CLAUDE.md — Branch naming taxonomy
- ADR-009 — Automation file writes must specify explicit text encodings (prior automation boundary decision)

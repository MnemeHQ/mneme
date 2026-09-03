---
id: ADR-022
title: "Main Is PR-Only with Squash Merge — Enforcement Boundaries"
status: accepted
priority: foundational
date: 2026-09-03
scope: governance.enforcement
---

# ADR-022: Main Is PR-Only with Squash Merge — Enforcement Boundaries

**Status:** Accepted
**Date:** 2026-09-03
**Deciders:** Theo Valmis

---

## Context

During dogfooding, a direct push to `main` bypassed the prose rule in CLAUDE.md ("squash merge only") and the worktree lifecycle ("one task → one branch → one worktree → one PR/outcome → teardown"). The failure was not caught by the existing pre-commit guard (#311/#312) because that guard validates *worktree/branch identity* (the `new_task_worktree.py` contract), not *push destination*. A commit on a task branch is valid for the pre-commit gate; pushing it to `main` instead of opening a PR is a separate boundary violation.

The enforcement architecture is **authoritative remote → early local feedback → audit/recovery**. This decision assigns responsibilities across three boundaries without creating a parallel guard mechanism.

## Decision

### 1. GitHub ruleset = authoritative remote enforcement

A repository ruleset on `main` (target: branch, enforcement: active) with:
- `pull_request` rule: required, `allowed_merge_methods: ["squash"]`, `required_approving_review_count: 0`
- `deletion` rule: blocked
- `non_fast_forward` rule: blocked
- No bypass actors

This is the single source of truth for what reaches `main`. Nothing lands on `main` except via a PR that squash-merges.

### 2. Local `pre-push` hook = early deterministic feedback

File: `scripts/githooks/pre-push` (installed via the existing `git config core.hooksPath scripts/githooks` — no new installer).

Condition: **reject any push whose remote destination is `refs/heads/main`**, regardless of local branch/worktree identity.

- Reads stdin lines: `<local-ref> <local-sha> <remote-ref> <remote-sha>`
- Blocks when `remote-ref == "refs/heads/main"` and the line represents an actual update (remote-sha not all-zeros; deletes also blocked)
- Does **not** block local commits on `main` — only the *push* is gated
- Does **not** skip based on absence of `.mneme/task_context.json` (unlike `pre-commit`); the rule keys on destination ref, so it applies uniformly in every worktree including the administrative checkout

Failure message identifies the governing decision and remediation:

```
[push-guard] BLOCKED: direct push to main.
  Governing decision: ADR-022 (main is PR + squash-only; GitHub ruleset is authoritative).
  Fix: commit to a task branch and open a PR (python scripts/new_task_worktree.py <branch>).
  Administrative/recovery override: MNEME_ALLOW_MAIN_PUSH=1 (use deliberately, never routinely).
```

Explicit override: environment variable `MNEME_ALLOW_MAIN_PUSH=1`. This satisfies "explicit administrative/recovery behavior defined" and "no bypass that silently becomes the default path" — it requires deliberate action on every invocation.

Squash merges via GitHub UI never invoke local git hooks (the merge happens server-side), so blocking all local pushes to `main` cannot break the accepted workflow.

### 3. CI = audit/recovery only (deferred)

Not implemented in this change. Revisit trigger: if the ruleset's audit log does not provide the evidence wanted for "how did this commit reach main," add a CI check that verifies every `main` commit is a squash merge with a PR reference. Tracked as a follow-up issue, not in this PR.

## Boundaries preserved

- The existing worktree context guard (#311/#312) is unchanged: it still validates "am I in the right worktree on the right branch before committing?"
- The pre-push guard validates "am I pushing to a protected destination?" — different question, different boundary.
- No new configuration path: `core.hooksPath` already points at `scripts/githooks`; both `pre-commit` and `pre-push` live there.
- ADR-010 (branch naming + squash taxonomy) is referenced, not mutated.

## Consequences

- Direct `git push origin main` is blocked locally with an actionable message before hitting the remote ruleset.
- Feature branch pushes pass unimpeded.
- The administrative checkout on `main` can still commit locally; it just cannot push to `origin/main` without the explicit override.
- One PR (this one) demonstrates the invariant end-to-end: it was created via the task worktree provisioner, pushed to a feature branch, and will merge via PR + squash.

## Alternatives considered

**Pre-receive hook on GitHub Enterprise / Actions.** Rejected: not available on standard GitHub; rulesets are the portable authoritative boundary.

**Blocking commits on local `main`.** Rejected: local commits on the administrative checkout are legitimate (e.g., maintenance, emergency hotfix prep); only the push is the enforcement boundary.

**Expanding the pre-commit guard to also check push destination.** Rejected: pre-commit runs before the push destination is known; separate hook is the correct git lifecycle point.

**Implementing a general "workflow policy engine."** Rejected: this is a half-day hardening fix, not a platform.

## Related

- ADR-010: Automation Artifact Governance (squash-merge taxonomy)
- Issue #311: Worktree context guard
- Issue #312: Automatic task-context provisioning and pre-commit worktree gate
- Dogfooding incident: direct push to main during agent development session
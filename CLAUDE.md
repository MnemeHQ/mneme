# Mneme Repo Instructions

## Branch Naming

Use conventional prefixes: `feat/`, `fix/`, `site/`, `ci/`, `docs/`, `refactor/`. Keep slugs short, kebab-case, no random suffixes unless required for uniqueness.

**Known exception — auto-generated worktree branches:** Claude Code's `--worktree` flag emits `claude/<adjective>-<noun>-<hash>` branch names. This is a hard-coded harness behavior with no configuration override. These branches are acceptable during development. Before opening a PR, rename to follow the taxonomy where practical. The squash commit title on `main` must follow the taxonomy regardless of source branch name. See ADR-010.

## Agent Execution Context Guard

Worktrees in this repo share one `.git`. An agent that starts work in the wrong checkout inherits that checkout's branch and commits to it. Branch selection is therefore **not agent discretion**: the orchestrating task declares the expected context; the agent only verifies it.

At the start of every agent task:

- Run `git rev-parse --show-toplevel` and `git branch --show-current`.
- Verify the repository root and branch match the task's declared worktree root and task branch.

Immediately before every `git commit`:

- Repeat the same assertion.
- Abort on any mismatch or on a detached HEAD.

The repo-owned checker automates this:

```bash
python scripts/check_worktree_context.py --expected-root <worktree-root> --expected-branch <task-branch>
```

It is read-only and fails closed (exit 1) with expected-vs-actual output on any mismatch. Never pass it values you did not receive from the task definition.

Provisioning and the automatic commit gate:

- Create each task worktree with `python scripts/new_task_worktree.py <branch>` — it creates the branch from current `origin/main` and writes `.mneme/task_context.json` inside the worktree.
- When run without explicit arguments, the checker reads `.mneme/task_context.json`; the versioned pre-commit hook (`scripts/githooks/pre-commit`) runs it before every commit in worktrees that have a context file.
- One-time setup for the hook: `git config core.hooksPath scripts/githooks`.

## Worktree Lifecycle

`C:/dev/mneme` is the administrative checkout. Keep it on `main` and do not use it for development work.

Every distinct development task — human or agent — gets a fresh task-owned worktree and dedicated branch created from current `origin/main`.

- Do not start a new task by switching branches inside an existing task worktree.
- Do not reuse another task's worktree, even if it appears idle.
- Follow-up changes for the same PR stay in that PR's existing worktree.
- Before beginning work and immediately before every commit, assert the expected repository root and branch with `scripts/check_worktree_context.py`.
- After the PR merges or an experiment is formally closed, remove the worktree and prune stale worktree metadata.

The model is:

```text
one task → one branch → one worktree → one PR/outcome → teardown
```

## Merging PRs

Always squash merge. Use the PR title as the commit title. `main` history should read as intentional product decisions, not raw agent iteration.

- Use `.mneme/project_memory.json` as the governance source.
- Validate changes against ADRs in `docs/adr/`.
- Do not modify `.mneme/project_memory.json` unless this is a `[memory]` task.
- Keep GTM/pricing/customer/internal strategy content out of this repo.
- Run `mneme check --mode warn` before finalizing governance-related changes.
- Keep PRs narrowly scoped.

## Tag Policy

Tags in this repo mark **durable milestones only**:

- `v0.x.y` — product/runtime releases
- `benchmark-vX.Y-stepN` — citeable benchmark methodology milestones (when public)

**Never tag** for: site deployments, cache purges, SEO/content ops, retro notes, or CI/infra housekeeping. Use GitHub Actions run history or the private `mneme-growth-ops` repo for operational tracking instead.

# Mneme Repo Instructions

## Branch Naming

Use conventional prefixes: `feat/`, `fix/`, `site/`, `ci/`, `docs/`, `refactor/`. Keep slugs short, kebab-case, no random suffixes unless required for uniqueness.

**Known exception — auto-generated worktree branches:** Claude Code's `--worktree` flag emits `claude/<adjective>-<noun>-<hash>` branch names. This is a hard-coded harness behavior with no configuration override. These branches are acceptable during development. Before opening a PR, rename to follow the taxonomy where practical. The squash commit title on `main` must follow the taxonomy regardless of source branch name. See ADR-010.

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

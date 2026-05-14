# Mneme Repo Instructions

## Branch Naming

Use conventional prefixes: `feat/`, `fix/`, `site/`, `ci/`, `docs/`, `refactor/`. Never use `claude/` as a prefix. Keep slugs short, kebab-case, no random suffixes unless required for uniqueness.

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

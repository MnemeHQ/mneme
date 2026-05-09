# Mneme Repo Instructions

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

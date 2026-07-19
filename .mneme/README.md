# `.mneme/` - live enforcement memory for the Mneme repo

This directory holds the canonical project memory that Mneme uses to govern
**its own** repository. Mneme protects Mneme.

If you are a contributor, you do not need to know how Mneme works internally
to read this - the file is plain JSON, and the rules describe constraints on
what should and shouldn't change in this repo.

## Files

- **`project_memory.json`** - canonical live enforcement memory. Source of
  truth for repo-level rules, anti-patterns, and architecture decisions.
  This file is intentionally public and should contain only
  repo-governance decisions that are safe for contributors and readers.
- **`README.md`** (this file) - what this directory is for and how to work
  with it.

The file at `examples/project_memory.json` is a
**documentation snapshot** used by the flagship demo. It is not a competing
source of truth. If a rule appears in both files, this directory's file wins.

## What the rules cover

The canonical memory currently covers a narrow, public-safe ruleset:

- ADR-002 boundary: internal tooling stays in the private repo
- ADR-003 boundary: scratch / working files are not deployed and not tracked
- Benchmark harness and core retrieval cannot change in the same PR
- Pipeline stages stay in separate modules with no cross-imports
- `.mneme/project_memory.json` changes require an isolated `[memory]` PR
  (exception: paired ADR change that explicitly updates the same decision)
- No GTM, pricing, customer, investor, outreach, or positioning content
- No vector DB, no agent loops, no litellm - Anthropic SDK only

The rules are intentionally narrow. We add new rules only when there is
evidence of repeat drift, not speculatively.

## What the rules do **not** cover

This directory does not duplicate policy already enforced elsewhere. In
particular:

- Private/internal content exclusion lives in `.gitignore` (`/private/`,
  `/internal/`, `/strategy/`, `/gtm/`, `/competitors/`, `/investor-notes/`,
  `/customer-notes/`, `*.private.md`, `*.internal.md`,
  `.mneme/private*`, `.mneme/*.local.json`, `.mneme/secrets*`)
- Repo boundary policy lives in
  [`docs/adr/ADR-002`](../docs/adr/ADR-002-repo-boundary-internal-tooling.md)
- Site publishing policy lives in
  [`docs/adr/ADR-003`](../docs/adr/ADR-003-site-publishing-guidelines.md)

Read those first if you need the underlying reasoning. The memory file
references them by ADR number.

## Rollout: warn-first

Enforcement is rolled out in **warn mode first**, then tightened to strict
on a narrow set of paths once we have a clean warn history.

### CI

CI runs `mneme check` in `--mode warn` against changed files. Warn mode
exits 0 on every verdict; conflicts are surfaced as PR comments only and do
not block merges. The workflow that drives this lives at
[`.github/workflows/mneme-check.yml`](../.github/workflows/mneme-check.yml).

```bash
mneme check --memory .mneme/project_memory.json \
            --input <changed-file> \
            --query "<change description>" \
            --mode warn
```

We will tighten to `--mode strict` only after 2-3 weeks of clean warn runs,
and only for changes that touch:

- `.mneme/`
- `mneme/`
- `docs/adr/`

Strict mode will not be applied globally.

### Local hook (Claude Code)

If you use Claude Code with the Mneme `PreToolUse` hook installed, set the
hook to warn mode while the rollout settles:

```bash
export MNEME_HOOK_MODE=warn
```

This makes the hook surface drift as warnings without blocking
`Edit` / `Write` / `MultiEdit` tool calls. Set `MNEME_HOOK_MODE=strict`
(or unset it; strict is the default) once you are comfortable.

If a warning ever feels wrong, the right move is to file an issue or open a
`[memory]` PR. Do not silently disable the hook.

## Editing this memory

1. Open a PR with the title prefix `[memory]`.
2. Keep the diff narrow - one rule or one decision per PR is ideal.
3. If the change is paired with an ADR update that explicitly amends the
   same decision, the ADR file and this file may land together; reference
   the ADR in the PR title.
4. Do not add private roadmap, GTM, pricing, outreach, customer, investor,
   or positioning content. That is enforced both here (rule
   `rule-no-gtm-in-repo`) and at the `.gitignore` layer.
5. Do not add `.mneme/private*`, `.mneme/*.local.json`, or
   `.mneme/secrets*` files to the repo. Those patterns are gitignored to
   give contributors a place to keep local-only memory without risk of
   accidental commit.

## Why this exists

Mneme's job is to keep AI-assisted development consistent with prior
decisions. The strongest credibility signal we can give is to use Mneme
on Mneme - and to do it in public, in a way contributors can read, audit,
and learn from.

That is what this directory is.

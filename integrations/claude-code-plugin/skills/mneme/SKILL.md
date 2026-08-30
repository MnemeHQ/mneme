---
name: mneme
description: |
  Architectural governance for this project. Use this skill when the user
  asks about project decisions, ADRs, architectural constraints, or wants to
  review, record, or enforce decisions. Also use before non-trivial edits when
  the project has a `.mneme/` directory so the relevant architectural context
  is visible before implementation.
---

# Mneme — project memory & architectural governance

This project uses Mneme to keep AI-assisted changes aligned with recorded
architectural decisions.

The **Skill is the workflow interface**: it helps Claude retrieve decisions,
record them, check proposed content, and review pending changes. The Skill does
not implement a second policy engine. Deterministic verdicts come from the
existing `mneme check` engine and the Claude Code hook.

When the plugin is enabled, Mneme uses a prevent → catch → verify model:

- `PreToolUse` evaluates reconstructable file mutations before they land.
- `Stop` audits session-introduced changes that could not be safely preflighted.
- CI remains the final verification boundary.

## When this skill activates

- User mentions "ADR", "decision", "constraint", "anti-pattern", "architecture", or architectural review.
- A `.mneme/project_memory.json` file exists in the repo.
- About to make a non-trivial edit in an area that may be governed by recorded decisions.
- Reviewing a proposed or completed change for architectural compliance.

## How to use it

1. **Before non-trivial edits** — run `/mneme:context` with a descriptive task
   phrase such as "storage layer changes" or "auth middleware refactor".
   Domain language is more useful than a generic file name for retrieval-based
   guidance.

2. **To gate a draft** — run `/mneme:check` against the proposed content with
   the real target path when available. Treat the command's verdict as the
   authority; do not infer PASS from the Skill's own reasoning.

3. **To record a new decision** — run `/mneme:record`. Choose clear scope and
   applicability so future retrieval and enforcement can identify where the
   decision belongs.

4. **To review pending changes** — run `/mneme:review`. Use the output as the
   evidence layer for an architectural review: which decisions apply, which
   changes comply, which are denied or warned, and which surfaces were not
   mechanically evaluated.

## Retrieval is not enforcement

Mneme deliberately separates architectural context from deterministic policy
checks.

- `/mneme:context` retrieves relevant decisions for guidance.
- Legacy text constraints may still depend on retrieval semantics.
- Typed rules such as `FORBID_LITERAL` are enforced independently of retrieval
  ranking across the decision corpus, subject to explicit path applicability.
- `mneme check --target-path` is the authority for path-scoped evaluation.
- An `UNKNOWN` / incomplete applicability state is not a PASS.

Do not assume that a decision was unenforced merely because it was absent from
the top retrieved context.

## Hook enforcement

The plugin's `PreToolUse` hook covers direct `Edit`, `Write`, and compatible
`MultiEdit` mutations by reconstructing the proposed post-edit content and
calling the existing Mneme checker.

For shell mutations, Mneme only preflight-blocks forms whose resulting path and
content can be proven from the command itself, such as supported simple quoted
heredoc writes. Pipelines, substitutions, interpreters, generators, and other
opaque shell forms are allowed to run and are evaluated at the `Stop` boundary
from the session delta where possible.

The `Stop` audit is a catch boundary, not proof that every external or remote
mutation surface is governed. If evaluation is unavailable or incomplete,
Mneme must surface that state rather than silently calling it PASS.

In strict mode, a trusted violating verdict can block the mutation or completion
boundary and surfaces the violated decision id so Claude can correct course.
Anything the adapter cannot evaluate reliably fails open visibly.

## Architectural review workflow

For a substantive review, use this order:

1. State the implementation intent and affected paths.
2. Retrieve the relevant project decisions with `/mneme:context`.
3. Inspect the proposed or pending change.
4. Use `/mneme:check` or `/mneme:review` for deterministic evidence.
5. Separate the result into:
   - mechanically enforced violations or passes;
   - guidance-only architectural concerns;
   - unevaluated / unsupported mutation surfaces.
6. Recommend the smallest compliant correction rather than inventing new
   architectural requirements.

This is the foundation for a richer Architecture Review Skill surface on the
roadmap; today it is an executable review workflow over existing Mneme commands,
not a new enforcement subsystem.

## Requirements & configuration

- **Mneme must be installed** and `mneme-hook` must be on `PATH`. Use the
  version documented by the plugin README; the runtime and plugin are separate
  artifacts.
- **Enforcement mode** is set by the plugin's `mode` configuration option and
  reaches the hook as `CLAUDE_PLUGIN_OPTION_MODE`. Precedence:
  `MNEME_HOOK_MODE` > `CLAUDE_PLUGIN_OPTION_MODE` > `strict`; unknown values
  fall back to `strict`.
- Use `warn` while iterating on decisions if blocking would create unnecessary
  friction, but do not represent WARN as PASS.

## Related

- Project memory: `.mneme/project_memory.json`
- CLI reference: `mneme --help`
- Plugin README: `integrations/claude-code-plugin/README.md`
- Canonical support matrix: `docs/integrations/README.md`
- Current roadmap: `docs/roadmap/README.md`

# Integrations — canonical support matrix

This directory is the repository's source of truth for what Mneme supports,
at what level, with what evidence. The website's
[integrations page](https://mnemehq.com/integrations/) mirrors this taxonomy.

## Support levels

- **Native integration** — a shipped adapter maintained in this repository,
  with tests on `main` and published validation evidence.
- **Validated compatibility** — Mneme works unchanged through another tool's
  transport; proven by a gated validation run, no adapter exists or is needed.
- **Rules export** — Mneme generates artifacts (e.g. editor rules) from the
  decision corpus; enforcement is advisory via the generated artifact.
- **CLI-based CI gate** — a reference pattern running `mneme check` in a
  pipeline you own; not a managed integration.
- **Experimental** — code exists behind a PR or validation is incomplete.
- **Planned** — design work only; nothing ships.

## Status matrix

| Level | Surfaces | Evidence / docs |
| --- | --- | --- |
| Native integration | Claude Code | [claude-code.md](claude-code.md), [claude-code-hook-spec.md](claude-code-hook-spec.md) |
| Native integration | Claude Agent SDK | [agent-sdk.md](agent-sdk.md), [PR #293](https://github.com/MnemeHQ/mneme/pull/293) |
| Native integration | Google Antigravity | [antigravity.md](antigravity.md), [PR #316](https://github.com/MnemeHQ/mneme/pull/316) |
| Native integration | Codex CLI | [codex-cli.md](codex-cli.md), [PR #321](https://github.com/MnemeHQ/mneme/pull/321), [capability matrix](../../validation/codex-cli/capability-matrix.md) |
| Validated compatibility | Paperclip (CLI + ACP) | [paperclip.md](paperclip.md), [PR #315](https://github.com/MnemeHQ/mneme/pull/315) |
| Rules export | Cursor | [adr-import.md](adr-import.md) (corpus workflows); generator: `mneme cursor generate` |
| CLI-based CI gates | GitHub Actions, GitLab CI | `mneme check` reference patterns |
| Experimental | OpenCode | plugin-hooks approach under evaluation; compaction experiment returned a NULL verdict |
| Experimental | Kiro | bounded PreToolUse hook, contract-tested, [open PR #314](https://github.com/MnemeHQ/mneme/pull/314) |
| Planned | Deep Agents middleware POC | see [roadmap](../roadmap/2026-04-24-adoption-and-enhancement-roadmap.md) |

## Known limitations

- **Codex CLI**: validated against 0.149.1 on Windows via `codex exec`.
  `apply_patch` Add/Update (incl. multi-file bundles) is pre-execution
  enforced; shell and script-driven writes are Stop-audit only; Delete is
  SKIP-by-design under ADR-018; dirty untouched files are ignored; dirty
  touched files are whole-file audited at Stop; degraded states fail open
  visibly. See [codex-cli.md](codex-cli.md).
- **Antigravity**: tested against Antigravity IDE 2.8.1; three file-mutation
  tools covered; deny-only response policy. See [antigravity.md](antigravity.md).
- **Paperclip**: validated on paperclipai 2026.817.0; version-specific
  placeholder-`ANTHROPIC_API_KEY` caveat documented in [paperclip.md](paperclip.md).
- **OpenCode**: no production plugin ships. The completed compaction
  experiment returned a NULL verdict and was closed evidence-only.

## Distinction that matters

"Native integration" requires maintained code and tests on `main`.
"Validated compatibility" means Mneme works unchanged through another
tool's transports — there is no adapter to maintain. Neither term applies
to rules exports, CI reference patterns, or planned POCs, and this
repository's docs should not use them that way.

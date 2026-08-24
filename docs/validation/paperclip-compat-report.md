# Paperclip × Mneme Compatibility — Report

**Verdict: PASS — native compatibility proven. No code required.**

Experiment: 2026-08-22/23. Manifest: `paperclip-compat-manifest.md`.
Matrix: `paperclip-compat-run-matrix.md`.

## Question answered

> Does Mneme's existing architectural context + deterministic edit enforcement
> work unchanged when Claude Code is launched and managed by Paperclip?

**Yes**, on both Paperclip's classic CLI engine and its default ACP engine,
with zero Mneme production modifications.

## Failure classification

| Classification | Detail |
|---|---|
| Env/config propagation defect — **upstream to Paperclip** | paperclipai 2026.817.0 injects a literal placeholder `ANTHROPIC_API_KEY="sk-ant-..."` into spawned Claude processes. Presence overrides subscription login → every run failed `401 API key invalid`. Verified present at spawn time via wrapper-command env capture; not sourced from agent config, instance config.json/.env, process env, or secret-provider configs. |
| Workaround (config-only) | `adapterConfig.env.ANTHROPIC_API_KEY = ""` → variable arrives empty at spawn → subscription auth restored. All matrix results post-date this fix. |

Not observed: hook non-invocation under ACP, blocked responses disrespected,
Paperclip retry/bypass of forbidden edits, memory-root misdiscovery.
Candidate upstream reports beyond the key injection: adapter `cwd` ignored
unless a project workspace exists; issue-creation idempotency silently dedupes
identical payloads.

## Architecture assessment

Observed flow matches the required topology exactly; no translation layer was
needed:

```
Paperclip (heartbeat/task orchestration, workspace realization)
    ↓ spawns claude (CLI args or ACP session)
Claude runtime (hooks fire from repo .claude/settings.json)
    ↓ PreToolUse Edit|Write|MultiEdit → mneme-hook
existing Mneme enforcement (mneme check --memory <discovered> --target-path …)
```

Context relevance also held independently of enforcement: C-lane agents
proactively read `.mneme/project_memory.json` and refused violating work
pre-emptively, while the hook layer enforced whenever edits were attempted.

## Caveats

1. **Worktree scope**: with a `local_path` project workspace on this platform,
   Paperclip ran Claude directly in the fixture checkout (no physical
   `.paperclip-worktrees/` directory materialized). Relocation was exercised
   at the workspace-realization boundary; physical worktree discovery remains
   covered by `tests/integrations/claude_code/test_memory_discovery.py`.
2. **Intent leakage**: issue titles containing "forbidden edit" caused agents
   to refuse before attempting an edit; neutral titles are required to exercise
   the hook layer rather than agent judgment.
3. **Session persistence**: ACP persistent sessions carry context across runs;
   use `mode:"oneshot"` for deterministic per-task behavior.
4. **Agents commit** completed work; reset baselines with
   `git reset --hard <frozen-base>` + `git clean -fd`.

## Decision record

- No production-code change made or required.
- No ADR change required: ADR-017 (enforcement vs retrieval scope) and ADR-020
  (path applicability) behaved exactly as specified under both transports.
- Do not build a Paperclip adapter; package the compatibility path
  (`docs/integrations/paperclip.md`) instead.
- Next target: Antigravity capability probe. This result strengthens the
  runtime-independence claim: the enforcement layer has survived a second
  orchestration/runtime boundary without modification.

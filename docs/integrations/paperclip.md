# Paperclip (claude_local) — Compatibility

**Status: validated natively compatible (experiment 2026-08-22/23). No
adapter required — Paperclip drives Claude Code, and Mneme's existing hook
enforcement applies unchanged.**

Evidence: `docs/validation/paperclip-compat-report.md` and
`docs/validation/paperclip-compat-run-matrix.md`.

## How it works

```text
Paperclip (claude_local adapter)
    ↓ spawns Claude Code in the project workspace
repo .claude/settings.json → PreToolUse hook → mneme-hook
    ↓
mneme check against the workspace's .mneme/project_memory.json
```

Requirements are the same as any other Claude Code setup:

1. `mneme-hook` on the PATH visible to the Claude Code process.
2. A committed `.mneme/project_memory.json` in the repo Paperclip realizes as
   the agent's workspace.
3. Hook registration (plugin or settings), e.g.:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{ "type": "command", "command": "mneme-hook", "timeout": 30 }]
      }
    ]
  }
}
```

## Proven configuration

- Adapter `claude_local`, engine default (`auto` → ACP) **and** explicit
  `engine:"cli"`; both enforce identically. Use `mode:"oneshot"` for
  deterministic per-task sessions.
- Point work at a repo via a **project workspace**
  (`sourceType:"local_path"`, `cwd` = repo path). Do not rely on
  `adapterConfig.cwd` alone — as of paperclipai 2026.817.0 it is superseded by
  workspace realization.

## Version-specific caveat: paperclipai 2026.817.0

Paperclip injects a placeholder `ANTHROPIC_API_KEY="sk-ant-..."` into spawned
Claude processes, which overrides subscription login and fails every run with
401. Workaround — set an empty override on the agent:

```json
{ "adapterConfig": { "env": { "ANTHROPIC_API_KEY": "" } } }
```

Fixed versions may make this unnecessary; remove it once upstream resolves the
injection.

## Operational notes

- Issue titles/phrasing reach the agent verbatim; neutral task titles avoid
  pre-emptive refusals when you specifically want to exercise enforcement.
- Paperclip agents commit completed work; treat their checkouts accordingly.

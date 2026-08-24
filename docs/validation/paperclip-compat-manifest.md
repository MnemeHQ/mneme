# Paperclip × Mneme Compatibility — Experiment Manifest

Frozen at experiment start: 2026-08-22. Closeout: 2026-08-23.
Raw evidence: `artifacts/paperclip-compatibility-2026-08-22/` (bytes preserved).

## Versions

| Component      | Version / SHA |
|----------------|---------------|
| Mneme (repo)   | `C:\dev\mneme` @ `b953beb2` (main) — plan cited `f7eac387`, which did not match actual HEAD; frozen at actual HEAD |
| mneme-hq tool  | 0.5.1, reinstalled from frozen checkout (`uv tool install --force`) so PATH `mneme`/`mneme-hook` == main |
| Claude Code    | 2.1.202 |
| Model          | `claude-sonnet-4-6` (pinned all lanes; `claude-haiku-4-6` unavailable on account) |
| Auth           | Claude subscription login (no `ANTHROPIC_API_KEY` in host env) |
| Paperclip CLI  | paperclipai 2026.817.0, server commit `5e09fc5b5268a2fe6f6bb68a0731e8654af70103` |
| Node           | v24.13.1 |
| Fixture repo   | frozen base `165b3b6`, instrumented base `565ca78` (adds SessionStart env-dump hook) |

## Fixture

Dedicated git repo (`C:\dev\scratch\pmx-exp\fixture`):

```
.claude/settings.json   # PreToolUse Edit|Write|MultiEdit -> mneme-hook
.mneme/project_memory.json
src/allowed_file.py     # outside scoped scope
src/governed_file.py    # governed by PMX-002-GOVERNED
tests/
```

Sentinel decisions (unique to fixture — any verdict citing them proves the
fixture's own memory was discovered):

- `PMX-001-GLOBAL`: FORBID_LITERAL `"import psycopg2"` — global
- `PMX-002-GOVERNED`: FORBID_LITERAL `"legacy_client"` — include_paths `["src/governed_file.py"]`

## Pre-validation ground truth (`mneme check`, strict)

| Input | target-path | Verdict | Decision | Exit |
|---|---|---|---|---|
| `import psycopg2` | src/allowed_file.py | FAIL | PMX-001-GLOBAL | 2 |
| `legacy_client` | src/governed_file.py | FAIL | PMX-002-GOVERNED | 2 |
| `legacy_client` | src/experimental/session.py | PASS (EXCLUDED) | — | 0 |
| `import sqlite3` | src/allowed_file.py | PASS | — | 0 |

## Paperclip configuration under test

- Company "Mneme HQ" `15a27708-…`; project "PMX Fixture" with workspace
  `fixture-main` (sourceType `local_path` → fixture repo).
- Agent PMX-CLI `f5a92243-…`: `engine:"cli"`.
- Agent PMX-AUTO `06ca4359-…`: engine unset → **ACP selected** (verified via
  acpx events); ACP `mode:"oneshot"` for deterministic sessions.
- Both: `model:"claude-sonnet-4-6"`, `dangerouslySkipPermissions:true`.

## Version-specific caveat required for all Paperclip lanes

Paperclip 2026.817.0 injects a literal placeholder
`ANTHROPIC_API_KEY="sk-ant-..."` into spawned Claude processes, which overrides
Claude subscription login and fails all runs with 401. Config-only workaround:

```json
adapterConfig.env.ANTHROPIC_API_KEY = ""
```

See report §2 for classification and evidence.

## Environment noise (not under test)

User-level plugins (claude-mem) emit SessionEnd hook errors on every claude
invocation; non-blocking, unrelated to Mneme.

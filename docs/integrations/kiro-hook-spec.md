# Kiro Hook Spec

Captured 2026-08-23 from the current official Kiro documentation:

- https://kiro.dev/docs/hooks/
- https://kiro.dev/docs/hooks/types/
- https://kiro.dev/docs/hooks/actions/
- https://kiro.dev/docs/reference/built-in-tools/

**Live evidence updated 2026-08-26** (CLI 2.19.2 default v2 engine and CLI 3.0 / v3 engine `--v3` manual reproduction):

Status: **contract-tested / experimental.** Live reproduction performed
on **CLI 2.19.2** under both default (v2 engine) and `--v3` (v3 engine / CLI 3.0). Results:

| Capability | CLI 2.19.2 default (v2 engine) | CLI 2.19.2 `--v3` (v3 engine / CLI 3.0) |
|------------|--------------------------------|-----------------------------------------|
| Hook registration | PASS (agent config `hooks` map, camelCase) | **PASS** (`.kiro/hooks/*.json` v1 format automatically discovered) |
| Envelope capture | PASS (`fs_write`, `command:create`, `file_text`) | **PASS** (`PreToolUse`, `session_id`, `fs_write`, `text`) |
| Verdict generation (exit 2 on FAIL) | PASS | **PASS** |
| **Pre-execution blocking** | **FAIL** (file written despite exit 2) | **PASS** (tool blocked pre-disk, stderr shown to agent) |
| Clean allowed write (exit 0 on PASS) | PASS | **PASS** (file written to disk) |
| Overall enforcement support | **NOT SUPPORTED** | **PASS (contract-verified)** |

*Note on registration:* CLI 2.19.2 in default mode ignores `.kiro/hooks/*.json` files (requires agent-config format). In `--v3` mode (v3 engine / CLI 3.0), `.kiro/hooks/*.json` files are automatically discovered and loaded.

The integration has achieved successful live allow/block verification on CLI 3.0 / v3 engine. IDE 1.x live reproduction remains pending.

## Documented contract (CLI 3.0+ / IDE 1.0+)

### Hook file

`.kiro/hooks/<id>.json`, schema `version: "v1"`:

```json
{
  "version": "v1",
  "hooks": [
    {
      "name": "mneme-governance-gate",
      "trigger": "PreToolUse",
      "matcher": "^(fs_write|fsWrite|write)$",
      "action": { "type": "command", "command": "mneme-kiro-hook" },
      "timeout": 30,
      "enabled": true
    }
  ]
}
```

Field reference (official): `version` (`"v1"`), `hooks[].name`,
`hooks[].description` (optional), `hooks[].trigger` (PascalCase),
`hooks[].matcher` (regex over tool name for `PreToolUse`/`PostToolUse`),
`hooks[].action.type` (`"command"` | `"agent"`),
`hooks[].action.command`, `hooks[].timeout` (seconds, default 60,
`0` disables), `hooks[].enabled`.

Requires IDE 1.0+ or CLI 3.0+.

### Event envelope (STDIN)

Documented and verified top-level fields (official examples, hooks/types page, and live v3 reproduction):

```json
{
  "session_id": "sess_32f5f263-bcf2-4b63-8d69-89fafd057df7",
  "hook_event_name": "PreToolUse",
  "cwd": "C:\\workspace\\project",
  "tool_name": "fs_write",
  "tool_input": {
    "path": "c:\\workspace\\project\\app.py",
    "text": "..."
  }
}
```

For MCP tools `tool_name` carries the full namespaced form
(`@server/tool`) and `tool_input` the tool's parameters (official).

### Native write tool

Official built-in-tools reference: tool name `write`, aliases
`fs_write` and `fsWrite`, described as "Tool for creating and editing
files". In CLI 3.0 / v3 engine, `tool_input` carries `path` and `text`.
The adapter normalizes both `content` (documented) and `text` (observed v3)
onto Mneme's `ToolEvent`.

### Exit-code semantics (official & verified)

| Exit | Behavior |
|------|----------|
| 0 | Success; **stdout is added to agent context** |
| non-zero | For `PreToolUse`: **tool invocation blocked**; stderr sent to the agent |

Verified live in CLI 3.0 / v3 engine: on exit code 2, Kiro displays "Tool execution failed", blocks the write from reaching disk, and feeds Mneme's decision explanation on stderr to the agent, which responds with compliant remediation suggestions.

## Observed contract (CLI 2.19.2 default v2 engine) — LEGACY EVIDENCE

### Hook registration

CLI 2.19.2 default mode **does not honor** `.kiro/hooks/*.json` v1 files.

Hooks are registered **only** via the agent config (`.kiro/agents/<name>.json`),
map-of-arrays form with camelCase triggers:

```json
{
  "name": "mneme-gated",
  "tools": ["*"],
  "allowedTools": ["read", "write", "fs_write"],
  "hooks": {
    "agentSpawn": [{ "command": "..." }],
    "preToolUse": [{ "matcher": "fs_write", "command": "..." }]
  }
}
```

### Envelope (captured 2026-08-26, v2 engine)

```json
{
  "hook_event_name": "preToolUse",
  "cwd": "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live",
  "tool_name": "fs_write",
  "tool_input": {
    "command": "create",
    "path": "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live\\test_block.md",
    "file_text": "pip install mneme-hq"
  }
}
```

Key differences from v3 contract:
- `tool_input` carries **`file_text`** instead of `text`/`content`
- `tool_input.command` = `"create"` (edit/replace shapes not observed)
- No `session_id` in the observed envelope (omitted by CLI 2.x)

### Adapter handling (constrained)

The adapter accepts `file_text` **only** for the observed combination:
- `tool_name` = `"fs_write"`
- `tool_input.command` = `"create"`

Edit/replace schemas are not inferred and fail open visibly (UNEVALUATED
notice reaches agent context). This is enforced by the regression fixture
`test_observed_cli_2_19_2_envelope_with_file_text` in
`tests/integrations/kiro/test_envelope.py`.

### Blocking enforcement (CLI 2.x v2 engine vs CLI 3.0 v3 engine)

- **CLI 2.x v2 engine:** Mneme returned exit 2 (blocking verdict), but the
  file was created anyway. The CLI 2.x harness does not honor blocking.
- **CLI 3.0 v3 engine (`--v3`):** Mneme returned exit 2, the file write was
  **strictly blocked pre-disk**, and stderr rationale reached the agent.

### Phase A experimental checklist (updated with live evidence)

1. ✅ Envelope captured from native `write` (create): `text` (v3) / `file_text` (v2).
2. ✅ Non-zero exit blocks before the file changes: **PASS** on CLI 3.0 / v3 engine.
3. ✅ Stderr of a blocked invocation is surfaced to the agent (observed live in TUI).
4. ✅ Exit-0 stdout reaches agent context (observed in allow tests).
5. Byte-equivalence of IDE and CLI envelopes — **untested on IDE 1.x**:
   Historical IDE 0.12 `runCommand` hooks received no STDIN (Kiro issues #7408/#7500);
   IDE 1.x behavior remains to be validated.
6. `PostFileSave` after shell-mediated write — not tested.
7. `Stop` envelope — verified that `Stop` hook fires on session termination.

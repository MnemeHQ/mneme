# Kiro Hook Spec

Captured 2026-08-23 from the current official Kiro documentation:

- https://kiro.dev/docs/hooks/
- https://kiro.dev/docs/hooks/types/
- https://kiro.dev/docs/hooks/actions/
- https://kiro.dev/docs/reference/built-in-tools/

**Live evidence updated 2026-08-26** (CLI 2.19.2 manual reproduction):

Status: **contract-tested / experimental.** Live reproduction performed
on **CLI 2.19.2** (`kiro-cli-chat 2.19.2`). Results:

| Capability | CLI 2.19.2 (agent-config hooks) | Documented CLI 3.0+ / IDE 1.0+ (v1 files) |
|------------|----------------------------------|-------------------------------------------|
| Hook registration | PASS (agent config `hooks` map, camelCase) | FAIL (`.kiro/hooks/*.json` ignored) |
| Envelope capture | PASS (live capture) | NOT TESTED |
| Verdict generation (exit 2 on FAIL) | PASS | NOT TESTED |
| **Pre-execution blocking** | **FAIL** (file written despite exit 2) | **NOT TESTED** |
| Overall enforcement support | **NOT SUPPORTED** | Pending |

The integration remains gated on live reproduction before any "supported"
claim (see [kiro.md](kiro.md), Claim gate). **CLI 2.x is explicitly NOT
supported** for enforcement; this record documents the observed contract
for the regression suite only.

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

Documented top-level fields (official examples, hooks/types page):

```json
{
  "hook_event_name": "preToolUse",
  "cwd": "/current/working/directory",
  "session_id": "abc123-def456-789",
  "tool_name": "@postgres/query",
  "tool_input": { }
}
```

For MCP tools `tool_name` carries the full namespaced form
(`@server/tool`) and `tool_input` the tool's parameters (official).

### Native write tool

Official built-in-tools reference: tool name `write`, aliases
`fs_write` and `fsWrite`, described as "Tool for creating and editing
files". Editing an existing file goes through the same tool with full
proposed content (the CLI renders it as a diff). The official reference
does **not** enumerate `tool_input` fields for this tool.

Observed shape, converging across independent sources (Kiro issue #7500 —
"the hook receives the full event JSON on stdin (`tool_name`,
`tool_input.path`, `tool_input` content) ... validated end-to-end"; AWS
Samples guardrail scripts keyed on `fs_write`; community power-user
guides):

```json
{
  "hook_event_name": "preToolUse",
  "cwd": "/workspace/project",
  "session_id": "...",
  "tool_name": "fs_write",
  "tool_input": { "path": "status.json", "content": "..." }
}
```

The hook accepts exactly `write`, `fs_write`, `fsWrite` as tool names and
reads only `tool_input.path` and `tool_input.content`. No undocumented
aliases or fallback field names are honored.

### Exit-code semantics (official)

| Exit | Behavior |
|------|----------|
| 0 | Success; **stdout is added to agent context** |
| non-zero | For `PreToolUse`: **tool invocation blocked**; stderr sent to the agent |

Note the difference from Claude Code: Kiro does not document a special
exit code 2; *any* non-zero exit blocks. The Mneme hook exits `2` on a
blocking verdict (non-zero, therefore blocking) and `0` otherwise.

## Observed contract (CLI 2.19.2) — LIVE EVIDENCE

### Hook registration

CLI 2.19.2 **does not honor** `.kiro/hooks/*.json` v1 files.

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

### Envelope (captured 2026-08-26)

```json
{
  "hook_event_name": "preToolUse",
  "cwd": "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live",
  "session_id": "abc123-def456-789",
  "tool_name": "fs_write",
  "tool_input": {
    "command": "create",
    "path": "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live\\test_block.md",
    "file_text": "pip install mneme-hq"
  }
}
```

Key differences from documented contract:
- `tool_input` carries **`file_text`** instead of `content`
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

### Blocking enforcement (CLI 2.19.2)

**Critical finding:** Mneme returned exit 2 (blocking verdict), but the
file was created anyway. The CLI 2.x harness executes the write before
or ignores the hook's non-zero exit for agent-config `preToolUse`.

| Outcome | Exit code | File on disk |
|---------|-----------|--------------|
| FAIL verdict | 2 | **Created** (blocking ineffective) |
| PASS verdict | 0 | Created |

Therefore: **CLI 2.x enforcement is INCOMPATIBLE**. Verdicts are correct;
the harness does not honor them.

### Phase A experimental checklist (updated with live evidence)

The following were confirmed by manual reproduction on CLI 2.19.2:

1. ✅ Envelope captured from native `write` (create) — `file_text` key.
2. ❌ Non-zero exit blocks before the file changes — **FAIL** (CLI 2.x harness limitation).
3. ✅ Stderr of a blocked invocation is surfaced to the agent (observed in agent output).
4. ✅ Exit-0 stdout reaches agent context (observed in allow tests).
5. Byte-equivalence of IDE and CLI envelopes — **known to fail**:
   IDE `runCommand` hooks receive no STDIN (Kiro issues #7408/#7500).
6. `PostFileSave` after shell-mediated write — not tested.
7. `Stop` envelope — deferred milestone.

The remaining release gate is a live **CLI 3.x or IDE 1.x** block/allow
reproduction. Until it passes, Kiro remains experimental rather than
shipped.

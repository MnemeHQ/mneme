# Kiro Hook Spec

Captured 2026-08-23 from the current official Kiro documentation:

- https://kiro.dev/docs/hooks/
- https://kiro.dev/docs/hooks/types/
- https://kiro.dev/docs/hooks/actions/
- https://kiro.dev/docs/reference/built-in-tools/

Status: **contract-tested / experimental.** No Kiro CLI or IDE execution was
available in the implementation environment, so no live STDIN capture was
possible. Every field below is taken from official documentation or from
converging third-party observations; nothing is invented. The integration is
gated on live reproduction before any "supported" claim (see
[kiro.md](kiro.md), Claim gate).

## Documented contract

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

### Phase A experimental checklist (pending live Kiro)

The following must be confirmed by a temporary diagnostic hook before any
support claim; each item is unverified until then:

1. Envelope captured from native `write` (create), edit/replace of an
   existing file, deletion, rename.
2. Non-zero exit blocks before the file changes (documented; not
   reproduced).
3. Where stderr of a blocked invocation is surfaced to the agent.
4. Whether exit-0 stdout reaches agent context in both surfaces
   (documented; not reproduced).
5. Byte-equivalence of IDE and CLI envelopes — **already known to fail**:
   IDE `runCommand` hooks receive no STDIN payload at all (Kiro issues
   #7408/#7500; reconfirmed June 2026 on Kiro 0.12). See the coverage
   matrix in [kiro.md](kiro.md).
6. Whether `PostFileSave` fires after a shell-mediated write.
7. `Stop` envelope contents (deferred milestone; no Stop audit in this
   PR).

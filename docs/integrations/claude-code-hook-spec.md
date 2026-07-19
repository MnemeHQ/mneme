# Claude Code PreToolUse Hook Spec

Captured 2026-05-03 from https://docs.anthropic.com/en/docs/claude-code/hooks

## Common envelope (all hook events)

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/repo",
  "hook_event_name": "PreToolUse",
  "tool_name": "Edit",
  "tool_input": { ... },
  "permission_mode": "default"
}
```

Fields: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `tool_name`, `tool_input`, `permission_mode`.

## Per-tool tool_input shapes

### Edit
```json
{
  "file_path": "/repo/app.py",
  "old_string": "def f(): pass",
  "new_string": "def f(): return 1",
  "replace_all": false
}
```
(`replace_all` is optional, defaults false.)

### Write
```json
{
  "file_path": "/repo/new.py",
  "content": "x = 1\n"
}
```

### MultiEdit
Not explicitly documented in the official hooks reference (2026-05-03).
Assumed shape based on Claude Code tool schema:
```json
{
  "file_path": "/repo/a.py",
  "edits": [
    {"old_string": "a", "new_string": "b"},
    {"old_string": "c", "new_string": "d"}
  ]
}
```
We handle this defensively: if the tool_input doesn't match, `materialize_proposed_content` raises `MaterializeError` and the hook fails open.

## Exit code semantics

| Code | Behavior |
|------|----------|
| 0 | Allow — action proceeds |
| 2 | Block — stderr shown to Claude as feedback; Claude may retry differently |
| other non-zero | Non-blocking error — action proceeds; first stderr line shown as notice in transcript |

Our shim only ever exits 0 (allow/fail-open) or 2 (block on real mneme check verdict).

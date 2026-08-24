# Codex CLI fixture provenance

All `pretooluse_applypatch_*` fixtures are derived from frozen R0 evidence in
`validation/codex-cli/evidence/runs/` (commit series
`06d189b6` + `bab78a16`), pinned build Codex CLI 0.149.1.

| Fixture | Source payload |
|---|---|
| `pretooluse_applypatch_addfile_allow.json` | run `20260824T100726Z`, `events-allow/events/0000-*.json` |
| `pretooluse_applypatch_addfile_deny.json` | run `20260824T100726Z`, `events-deny/events/0000-*.json` |
| `malformed_missing_command.json` | synthetic: observed envelope minus `tool_input.command` |
| `malformed_missing_markers.json` | synthetic: observed envelope, command without patch markers |

Normalization applied (and asserted by the provenance test against the
committed evidence bytes):

- `session_id`, `turn_id`, `tool_use_id` → `NORMALIZED_*` placeholders
- `transcript_path`, `cwd` → `NORMALIZED_*` placeholders
- nothing else; `tool_input.command` is byte-identical to the captured value

The confirmation-run payloads (`20260824T101801Z`) are byte-identical in
`tool_input.command` to these fixtures' source payloads.

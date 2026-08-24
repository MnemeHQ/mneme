# Codex CLI fixture provenance

All `pretooluse_applypatch_*` fixtures are derived from frozen R0 evidence in
`validation/codex-cli/evidence/runs/` (commit series
`06d189b6` + `bab78a16`), pinned build Codex CLI 0.149.1.

| Fixture | Source payload |
|---|---|
| `pretooluse_applypatch_addfile_allow.json` | run `20260824T100726Z`, `events-allow/events/0000-*.json` |
| `pretooluse_applypatch_addfile_deny.json` | run `20260824T100726Z`, `events-deny/events/0000-*.json` |
| `pretooluse_applypatch_updatefile_allow.json` | run `20260824T113630Z-updatefile`, `events-allow/events/0002-PreToolUse-apply_patch-*.json` |
| `pretooluse_applypatch_multifile_allow.json` | run `20260824T133347Z-multifile`, one envelope: Update (`service.py`, relative) + Add (`helper.py`) |
| `seed_service.py` | run `20260824T113630Z-updatefile`, seeded tracked file the Update patch modified (byte-identical to the multifile run's seed) |
| `malformed_missing_command.json` | synthetic: observed envelope minus `tool_input.command` |
| `malformed_missing_markers.json` | synthetic: observed envelope, command without patch markers |

Normalization applied (and asserted by the provenance tests against the
committed evidence bytes):

- `session_id`, `turn_id`, `tool_use_id` → `NORMALIZED_*` placeholders
- `transcript_path` → `NORMALIZED_TRANSCRIPT_PATH`
- absolute sandbox root → `C:\codex-probe-sandbox` (Update File payload only;
  preserves the observed absolute-path form while removing machine-specific
  path segments)
- nothing else; `tool_input.command` grammar is byte-exact otherwise

## Update File seed snapshot

`seed_service.py` is the exact 9-line file the captured patch modified.
Fixture bytes are CRLF (the probe's Python write translated LF to the
platform newline, matching what Codex actually patched on disk):

- sha256 (CRLF, fixture bytes): `ef3316e7e28adee977970f0a16a32d9057c62d92f4f9f786bd845d5c4fbdad64`
- sha256 (LF-normalized): `0d380ddfbc86bc2a94b0f713daa6d2ba7ff3f176f1182aa7dccb41830ae12455`

## EOL caveat

> Update enforcement is line-content based. The integration does not claim
> byte-exact final-file reconstruction because Codex 0.149.1 on Windows can
> produce mixed EOLs when patching a CRLF checkout.

Established by exhaustive per-line EOL search against the allow-arm recorded
sha256 in run `20260824T113630Z-updatefile` (see its `analysis-m1ea.md`).

The confirmation-run payloads (`20260824T101801Z`) are byte-identical in
`tool_input.command` to these fixtures' source payloads.

## Multi-operation contract (M1f-b)

Observed in run 20260824T133347Z-multifile: one apply_patch envelope carried
TWO adjacent operations (Update then Add) with no delimiter beyond the next
operation header. One deny blocks the entire bundled tool call; one allow
lands both mutations with a single PostToolUse.

Evidence-driven path-form contract:

- Update File: absolute AND relative both observed.
- Add File: relative only, observed so far. Absolute Add is NOT Codex-
  observed behavior and must not be assumed.

Aggregation precedence for future multi-operation evaluation (settled
pre-M1f-c): DENY > FAIL_OPEN > WARN > PASS/SKIP. A definite violation on any
single operation denies the whole call (Codex deny is per-tool-call);
unevaluated operations must be disclosed in the reason, never reported as
governed.

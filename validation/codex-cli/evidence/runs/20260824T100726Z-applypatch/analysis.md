# R0 analysis — native `apply_patch` (run 20260824T100726Z)

Evidence hierarchy: both arms below are **trusted/no-bypass primary evidence**
on pinned build `codex-cli 0.149.1` (SHA-256 verified at run start). The
diagnostic bypass arm did NOT trigger because trusted hooks were observed
(`trusted_normal_execution: hook_observed`). Upstream issue #32491 behavior
(trusted project hooks skipped by `codex exec`) was **not** reproduced on
0.149.1.

## Fact 1 — exact PreToolUse payload

`events-allow/events/0000-PreToolUse-apply_patch-*.json` (sha256
`c5ac472c...cae6fbe3`, byte-exact):

```json
{
  "session_id": "...", "turn_id": "...", "transcript_path": "...",
  "cwd": "...\\sandbox\\repo",
  "hook_event_name": "PreToolUse",
  "model": "gpt-5.6-terra",
  "permission_mode": "bypassPermissions",
  "tool_name": "apply_patch",
  "tool_use_id": "exec-fce1859c-...",
  "tool_input": { "command": "*** Begin Patch\n*** Add File: probe_target.py\n+def probe_marker() -> int:\n+    return 42\n*** End Patch" }
}
```

Observations beyond the docs: `permission_mode` is `bypassPermissions` under
`codex exec` by default (no interactive approval layer exists to weaken —
relevant to M1 verdict mapping). `turn_id`, `model`, `tool_use_id` confirmed
present.

## Fact 2 — proposed patch fully present in payload

YES. `tool_input.command` carries the complete apply_patch script including
the operation header (`*** Add File:`), every introduced line prefixed `+`,
and the terminator. Nothing about the mutation lives outside the payload.

## Fact 3 — deterministic affected-path reconstruction

YES for the observed grammar. Path = value of `*** Add File: <path>`;
introduced content = the `+`-prefixed lines with the prefix stripped.
Mechanically derivable without shell semantics or filesystem access.

Scope caveat: this run proves single-file `Add File` only. Multi-file,
`Update File`, `Delete File`, and move operations are matrix rows 2–4 and
remain pending — same payload channel, unproven grammar coverage.

## Fact 4 — deny prevents disk mutation

YES. Deny arm (`events-deny/`, sha256 `85445191...18526f2` payload): the hook
returned `hookSpecificOutput.permissionDecision: "deny"` (documented
hookSpecificOutput shape) on trusted hooks; `worktree-before.json` and
`worktree-after.json` are byte-identical (`git status --porcelain=v2` empty;
no `probe_target.py` anywhere). The agent's own final message confirms: "No
files were modified." No PostToolUse ever fired — the blocked tool never
executed.

## Fact 5 — PostToolUse / Stop observations, allow vs deny

| | allow arm | deny arm |
|---|---|---|
| PreToolUse | fired | fired (denied) |
| PostToolUse | fired; `tool_response` = exit 0 + "A probe_target.py" | **absent** (tool never ran) |
| Stop | fired; `stop_hook_active:false`; message = created file | fired; `stop_hook_active:false`; message = blocked by pre-tool hook |

Stop fires in both outcomes and exposes `stop_hook_active` +
`last_assistant_message` — sufficient surface for the future R3 audit
backstop, though continuation (`decision: "block"`) semantics remain untested
here.

## Harness defects (NOT Codex behavior)

Two preflight failures invalidated earlier run directories (both preserved
under `evidence/runs/_invalidated/` with reasons):

1. `20260824T100217Z` — runner compared pin SHA-256 hex case-sensitively;
   aborted before invoking Codex. Fixed with `.strip().lower()` normalization.
2. `20260824T100648Z` — `CODEX_ARGS` default included `--ask-for-approval`,
   which `codex exec` does not accept (interactive-CLI flag); argparse
   rejected every arm before any session started. Fixed to
   `--sandbox workspace-write`.

Neither produced hook payloads or Codex capability signal.

## Trust persistence finding

Hook trust survives as `[hooks.state.'<sandbox>\.codex\hooks.json:<event>:i:j']`
entries plus `[projects.'<path>'] trust_level` in `~/.codex/config.toml`
(observed post `/hooks` review). Trusted hooks fire under plain
`codex exec` — no bypass flag needed on this build.

## Verdict

Native `apply_patch` (single-file add) is **pre-interceptable**: interceptable,
fully reconstructable, and deny-effective under normal user security
semantics. M1 gate criteria 1–3 are met by this run; a confirmation re-run on
a second day/build state is recommended before M1 code lands.

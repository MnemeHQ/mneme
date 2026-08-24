# M1d-a analysis — non-blocking diagnostic transport (run 20260824T110210Z)

Question: does trusted PreToolUse `hookSpecificOutput.additionalContext` (no
`permissionDecision`) work as a **non-blocking diagnostic channel** on pinned
Codex CLI 0.149.1 / Windows / `codex exec`?

Probe arm `diagctx`: same native single-file apply_patch surface, same
sandbox/trust/no-bypass conditions as the R0 runs; hook returned exactly:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "additionalContext": "[mneme-probe] NONBLOCKING_DIAGNOSTIC_1491"}}
```

## The four facts

| # | Fact | Result | Evidence |
|---|---|---|---|
| 1 | Hook output accepted (not classified malformed/failed) | YES | `transcript-diagctx.log`: exit=0, zero hook-failure mentions; all three events fired |
| 2 | Patch still executes | YES | `diagctx/worktree-after.json`: `? probe_target.py`, file hash present |
| 3 | PostToolUse still fires | YES | `events-diagctx/events/index.jsonl`: PreToolUse, PostToolUse, Stop |
| 4 | Sentinel delivered to agent context | YES | session rollout jsonl (path from PostToolUse payload) contains one entry: `{"type":"message","role":"developer","content":[{"type":"input_text","text":"[mneme-probe] NONBLOCKING_DIAGNOSTIC_1491"}]}` |

Fact 4 is transcript evidence (developer-role message in the model context),
not behavioral echo.

Regression check: allow/deny arms in the same run reproduce the R0 results
exactly — deny still blocks with no PostToolUse; allow still mutates with
PostToolUse. The diagnostic arm changes nothing about enforcement.

## Gate statement

> **M1d-a gate: PASS** — trusted PreToolUse `additionalContext` is accepted
> on Codex CLI 0.149.1 / Windows / `codex exec`, remains non-blocking, and is
> observably delivered to the agent context.

## Consequence for M1c result mapping

One proven transport now serves both non-blocking outcomes:

- WARN → no permission decision + additionalContext carrying Mneme's warning
- FAIL_OPEN → no permission decision + additionalContext explicitly stating
  the mutation was NOT evaluated and why

Scope note: delivery proven for PreToolUse apply_patch under `codex exec`;
interactive TUI modes remain unproven and out of the current claim.

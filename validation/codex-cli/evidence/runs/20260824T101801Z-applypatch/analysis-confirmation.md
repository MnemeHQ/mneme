# R0 confirmation rerun (run 20260824T101801Z)

Exact confirmation of run `20260824T100726Z-applypatch`: same pinned binary
(SHA-256 re-verified at start), same trusted hooks (4 `hooks.state` entries),
no bypass flag, no harness/code changes between runs, same sandbox fixture
and prompt.

## Reproduction result

| Fact | Run 1 (100726Z) | Run 2 (101801Z) | Match |
|---|---|---|---|
| PreToolUse payload shape/fields | captured | captured; `tool_input.command` byte-identical (`-ceq`) | YES |
| Patch fully in payload | YES | YES | YES |
| Deterministic path/content reconstruction | YES (Add File grammar) | YES (same payload text) | YES |
| deny → no disk mutation | YES | YES — `git status --porcelain=v2` empty after deny arm | YES |
| allow → mutation + PostToolUse | YES | YES — PostToolUse exit 0, "A probe_target.py"; worktree shows `? probe_target.py` | YES |
| deny → no PostToolUse | YES (absent) | YES (absent) | YES |
| Stop fires in both arms | YES | YES — `stop_hook_active:false` both arms; messages match run-1 semantics ("Created ..." vs "Blocked ... pre-tool hook denied") | YES |
| permission_mode in payload | bypassPermissions | bypassPermissions | YES |

Diagnostic bypass arm did not trigger in either run.

## Gate statement

> **M1 gate: MET — reproducible on Codex CLI 0.149.1 / Windows /
> `codex exec`.**

## Scope qualification carried forward

The observed payload reports `permission_mode: "bypassPermissions"`, which is
the default for non-interactive `codex exec`. This does not weaken the result
— the hook's explicit `deny` still prevented mutation — but it bounds the
claim:

> Proven: pre-execution interception + effective deny for native single-file
> `apply_patch` under **trusted project hooks on `codex exec`, pinned build
> 0.149.1, Windows**.
>
> Not yet proven: identical behavior in interactive Codex TUI modes
> (default / acceptEdits / plan approval flows), multi-file or
> Update/Delete/move patch operations, shell/unified-exec surfaces.

Matrix rows 2–9 remain pending; interactive-mode confirmation is a new
observation task before any broader claim.

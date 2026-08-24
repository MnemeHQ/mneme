# M1g-a analysis — native `Delete File` probe (run 20260824T202758Z)

Pinned Codex CLI 0.149.1 / Windows / `codex exec`, trusted logger hooks, no
bypass. Seeded tracked `service.py`; prompt asked for its deletion.

## Grammar facts

Captured `tool_input.command` (`events-allow/events/0000-*.json`):

```
*** Begin Patch
*** Delete File: service.py
*** End Patch
```

- **Header-only**: no body/hunk lines of any kind — the operation is exactly
  one line between the envelope markers.
- **Path form: relative** (matches Add File's observed contract; absolute
  Delete not observed).
- **Target path deterministic** from the header alone.

## Live outcomes

| | allow | deny |
|---|---|---|
| PreToolUse | fired | fired -> Blocked (router logs the probe deny) |
| file deleted | YES (`seed_deleted=True`, worktree shows `D service.py`) | **NO — byte-for-byte intact**, clean worktree |
| PostToolUse | fired | **absent** |
| Stop | fired | fired |

No harness defects this run.

## Implications for M1g-b (Delete support)

Delete is the simplest operation to govern: header-only grammar, one
deterministic path, no content to derive. The parser needs only to accept
the header with its validated path; ADR-018 introduced-content semantics
trivially yield a blank delta, so under existing gate rules a Delete alone
would SKIP (nothing introduced). Whether Deletes require their own policy
surface (e.g., forbid deleting governed artifacts) is an enforcement-policy
question beyond transport — flagging it rather than deciding it here.

# Codex CLI mutation-surface capability matrix

Filled **only** from captured evidence under `evidence/runs/`. Every non-empty
cell cites a run artifact. Doc-derived claims do not belong here.

Columns:

- **Hook fired** — did the expected hook event fire for this surface?
- **Payload captured** — raw stdin payload archived byte-exact.
- **Path reconstructable** — affected target path(s) derivable deterministically
  from the payload alone.
- **Content reconstructable** — proposed introduced content derivable
  deterministically from the payload alone (pre-execution).
- **Deny effective** — returning `deny` demonstrably prevented disk mutation.
- **Stop observable** — `Stop` fires and the resulting worktree state is
  attributable to this surface's session activity.
- **Verdict** — `pre-interceptable` / `post-detectable` / `not-observable` /
  `unresolved`. Coverage-qualified; no cell may be upgraded without evidence.

| # | Mutation surface | Hook fired | Payload captured | Path reconstructable | Content reconstructable | Deny effective | Stop observable | Verdict | Evidence |
|---|------------------|------------|------------------|----------------------|-------------------------|----------------|-----------------|---------|----------|
| 1 | native `apply_patch` (single file, tracked) | YES — PreToolUse fired, trusted/no-bypass | YES — byte-exact, sha256-indexed | YES — `*** Add File: <path>` header | YES — `+` lines = introduced content | YES — worktree byte-identical after deny; no PostToolUse | YES — Stop fired both arms, `stop_hook_active:false` | **pre-interceptable** (`codex exec` on pinned 0.149.1; interactive modes untested) | runs `20260824T100726Z` + confirmation `20260824T101801Z`, `analysis.md` / `analysis-confirmation.md` |
| 2 | native `apply_patch` (multi-file)          | | | | | | | pending | |
| 3 | native `apply_patch` (new untracked file)  | | | | | | | pending | |
| 4 | native `apply_patch` (rename/delete)       | | | | | | | pending | |
| 5 | shell/exec write (`>` redirection)         | | | | | | | pending (M2) | |
| 6 | shell/exec heredoc/script-driven write     | | | | | | | pending (M2) | |
| 7 | unified exec (`exec_command`) writes       | | | | | | | pending (M2) | |
| 8 | MCP tool mutation                          | | | | | | | pending | |
| 9 | code-mode nested tool call                 | | | | | | | pending | |

## Open questions carried from planning

- Effective cwd/workdir reported in hook context for exec surfaces
  (upstream: issue #37251). Verify on pinned build before trusting
  relative-path reconstruction for any surface.
- Whether `permissionDecision: "ask"` behaves as documented-rejected or has
  changed (upstream: issue #28437). Not needed for M1 gate; record if observed.

## R0 exit checklist (native `apply_patch`, row 1)

Gate to M1 — all three must be checked with evidence links:

- [x] Row 1 interceptable reproducibly (`PreToolUse` fired, payload captured)
      — runs `20260824T100726Z` + confirmation rerun `20260824T101801Z`,
      trusted/no-bypass, byte-identical patch payloads
- [x] Row 1 paths + content deterministically reconstructable
      — single-file `Add File` case proven in both runs;
        multi-file/Update/Delete pending (rows 2–4)
- [x] Row 1 deny prevents disk mutation
      — worktree byte-identical before/after in deny arm, both runs

> **M1 gate: MET — reproducible on Codex CLI 0.149.1 / Windows / `codex exec`.**
>
> Scope: proven for non-interactive `codex exec` (payload shows default
> `permission_mode: bypassPermissions`; explicit deny still blocked mutation).
> Interactive TUI modes and other patch operations are NOT covered by this
> gate.

Additional observations recorded but not gating:

- [x] Exact deny output shape confirmed working on pinned build
      — `hookSpecificOutput.permissionDecision: "deny"` blocks on trusted hooks
- [x] PostToolUse payload after allow vs after deny captured
      — present after allow; absent after deny (blocked tool never executed)
- [x] Stop payload after allow vs after deny captured; `stop_hook_active`
      semantics noted if exercised — fires both arms, `stop_hook_active:false`;
      continuation (`decision:"block"`) NOT yet exercised

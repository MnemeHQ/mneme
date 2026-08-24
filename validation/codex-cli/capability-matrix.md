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
| 1 | native `apply_patch` Add File (single, tracked) | YES — trusted/no-bypass | YES — byte-exact, sha256-indexed | YES — relative path | YES — `+` lines = introduced content | YES — worktree byte-identical after deny; no PostToolUse | YES — Stop fired both arms | **pre-interceptable; governed end-to-end** | runs `20260824T100726Z` + `20260824T101801Z`; live gate in `20260824T112515Z-m1db-live` |
| 2 | native `apply_patch` multi-file bundle (Add + Update) | YES — one PreToolUse for the whole call | YES — both ops in one `tool_input.command` | YES per operation (relative observed) | YES per operation | YES — deny blocks the ENTIRE call, neither op lands | YES — both arms | **pre-interceptable; governed end-to-end** (aggregation DENY > FAIL_OPEN > WARN > PASS/SKIP) | run `20260824T133347Z-multifile`; live `20260824T142723Z-m1fc-live`, `analysis-m1fc.md` |
| 3 | native `apply_patch` Add (new untracked file) | YES | YES | YES — relative path | YES | YES | YES | covered by row 1 (Add creates untracked files) | runs as row 1 |
| 4a | native `apply_patch` Delete File | YES — trusted | YES — header-only grammar, relative path observed | YES | n/a — no content introduced | YES — file stays byte-identical on deny | YES — both arms | **recognized; SKIP-by-design** (ADR-018: pure deletions introduce nothing; no delete-protection claimed) | run `20260824T202758Z-deletefile`, `analysis-m1ga.md` |
| 4b | native `apply_patch` rename/move | not probed | | | | | | pending | |
| 5 | shell write — direct redirection (`>` / `Out-File`) | YES — PreToolUse fires pre-mutation (`tool_name: Bash`) | YES — full command string | NO — embedded in PowerShell text only | NO — requires shell interpretation | YES — generic deny blocks every scenario pre-mutation | YES — all arms | **INTERCEPTABLE-BUT-NOT-RECONSTRUCTABLE** → Stop audit is the backstop | run `20260824T210203Z-shell`, `analysis-m2a.md` |
| 6 | shell write — cmdlet (`Set-Content`) / heredoc-class | YES | YES | NO | NO | YES | YES | **INTERCEPTABLE-BUT-NOT-RECONSTRUCTABLE** → Stop backstop | same run |
| 6b | script-driven write (interpreter via shell) | YES | YES — command text only; content computed inside interpreter | NO | NO | YES | YES | **STOP-ONLY** → Stop backstop | same run |
| 7 | unified exec (`exec_command`) writes | YES — fires as `Bash` | YES | NO | NO | YES | YES | covered by the M2a shell classification | same run |
| 10 | native `apply_patch` Update File (single file) | YES — trusted PreToolUse fired (allow + deny arms) | YES — byte-exact, sha256-indexed | YES — **absolute AND relative forms observed** | YES at introduced-content level (bare `@@` hunks; mixed-EOL caveat — byte-exact final state NOT reconstructible) | YES — seed file byte-identical after deny; no PostToolUse | YES — Stop fired both arms | **pre-interceptable (introduced-content level); governed end-to-end** | run `20260824T113630Z-updatefile`, `analysis-m1ea.md`; live denial `20260824T132248Z-m1ed-live` |
| 11 | MCP tool mutation | not probed | | | | | | pending | |
| 12 | code-mode nested tool call | not probed | | | | | | pending | |

## Final aggregation rule (settled M1f-b, proven live M1f-c)

> Every operation in a bundled proposal is evaluated before the tool call is
> allowed. Any violation denies the entire call. Aggregation precedence:
> DENY > FAIL_OPEN > WARN > PASS/SKIP; unevaluated operations are disclosed
> in the reason and never reported as governed.

## Open questions carried from planning

- Effective cwd/workdir reported in hook context for exec surfaces
  (upstream: issue #37251). Verify on pinned build before trusting
  relative-path reconstruction for any surface.
- Whether `permissionDecision: "ask"` behaves as documented-rejected or has
  changed (upstream: issue #28437). Not needed for M1 gate; record if observed.
- RESOLVED (M1d-a, run `20260824T110210Z`): non-blocking PreToolUse
  `hookSpecificOutput.additionalContext` is accepted, non-blocking, and
  delivered to agent context (developer-role message in session rollout) on
  pinned 0.149.1 / Windows / `codex exec`. This is the proven channel for
  WARN and FAIL_OPEN diagnostics.

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

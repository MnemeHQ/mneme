# M1d-b analysis — production gate live validation (run 20260824T112515Z)

The actual production entrypoint
(`mneme/integrations/codex_cli/hook.py` -> `evaluate_apply_patch`), registered
via trusted project-layer `PreToolUse` (`matcher: ^apply_patch$`, same shape
proven in R0/M1d-a), pinned Codex CLI 0.149.1 / Windows / `codex exec`, no
bypass flag. Pin SHA-256 re-verified at run start; preflight deny-probe
confirmed fresh trust before any case ran.

## The four live outcomes

| Case | Mutation | Hook behavior | Evidence |
|---|---|---|---|
| PASS | compliant file lands | `hook: PreToolUse Completed`, silent — no opinion, no context | `transcript-pass.log`; worktree has `probe_target.py` |
| DENY | forbidden token does NOT land | `hook: PreToolUse Blocked`; codex_core router logs the block with Mneme's full report; agent reports "No files were modified" | `transcript-deny.log`; worktree clean |
| WARN | violating file lands (MNEME_HOOK_MODE=warn) | non-blocking; developer-role rollout message: `[mneme] WARN - architectural decision flagged (warn mode; not blocked): mneme: FAIL ... [ADR-LIVE] FORBIDDEN_TOKEN_XYZ ... path: probe_target.py` | session rollout jsonl (fact-4-grade transcript evidence) |
| FAIL_OPEN | deliberately malformed fixture memory; file lands | non-blocking; developer-role message `[mneme] UNEVALUATED - failing open, this mutation was NOT evaluated:` + cause | session rollout jsonl |

## Additional verifications

- No hook parse failures anywhere in the run: zero `hook: * Failed` lines
  across all five transcripts (contrast: the invalidated first attempt).
- Trusted hooks only, no bypass flag: preflight deny proves the enforcement
  path runs under persisted trust alone.
- Real workspace path reached `--target-path`: the DENY reason carries
  `path: probe_target.py` from typed-rule path applicability — applicability
  to the sandbox workspace path is only possible if the checker received the
  resolved absolute target.
- Deny leaves worktree unchanged; WARN/FAIL_OPEN are non-blocking by
  observation (mutation landed, turn completed exit=0).

## Harness defect found during validation

First attempt (`_invalidated/20260824T112136Z-m1db-live`) ran all four cases
against a stale tracked `hooks.json`: each case's `git reset --hard`
restored the R0-era probe logger over the production registration. The
preflight had already proven the production gate works; the fix reinstalled
the production definition after every reset. Preserved with full reasoning;
not capability evidence.

Incidental finding worth carrying forward: when hooks.json definitions
change, per-event trust entries whose definitions did NOT change keep
running while the changed one is silently skipped until re-trusted. Partial
hook configurations can therefore execute after partial re-trust — relevant
for M2+ design and for user-facing install instructions.

## Gate statement

> **M1d-b gate: MET** — the production Codex hook entrypoint demonstrated all
> four outcome mappings live on Codex CLI 0.149.1 / Windows / `codex exec`
> under trusted-only hooks with no bypass flag.

Scope unchanged: single-file Add File only. Update/Delete, multi-file, shell,
and Stop audit remain future milestones.

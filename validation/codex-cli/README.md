# Codex CLI enforcement capability probe (R0)

Question: on a pinned OpenAI Codex CLI build, which agent mutation surfaces can
Mneme intercept **before execution**, and what can only be detected after the
fact?

This is R0 of the Codex CLI integration plan. It produces evidence and a
capability matrix. It does **not** produce production code.

## Status

- Phase: R0 — native `apply_patch` probe first, nothing else yet
- Codex CLI pinned build: **0.149.1**, standalone installer, exact binary hash
  in `pinned-build.json` (the pin is the SHA-256, not the version string)
- Platform: Windows 11 / PowerShell 5.1 (primary evidence platform)
- Note: Codex CLI was not installed on the scaffolding machine when this
  directory was created. The runner gates on environment detection first.

## The five facts this phase must establish

Native `apply_patch` only:

1. Exact `PreToolUse` payload shape (raw capture, not doc-derived).
2. Whether the proposed patch is fully present in that payload.
3. Whether affected paths can be recovered deterministically from it.
4. Whether returning `deny` demonstrably leaves the working tree unchanged.
5. What `PostToolUse` and `Stop` observe after allow vs deny.

## Non-goals (R0)

- No Mneme production integration (`mneme/integrations/codex_cli/` does not
  exist yet and must not be created from this branch during R0).
- No parser implementation. Whether a patch parser is needed, and what grammar
  it needs, is an *output* of R0, not an input.
- No shell/exec interception experiments (M2), no Stop-audit design work (M3)
  beyond capturing Stop payloads.
- No changes to Mneme core, ADRs, or the frozen enforcement benchmark.

## Architecture constraints (carried into M1+ if the gate passes)

- Any adapter reuses `mneme check --json` (`mneme.check/v1`); no second
  enforcer, no Codex-specific decision logic.
- ADR-018: gate checks introduced content; whole-file checks are audit-only.
- ADR-020: UNKNOWN applicability must not silently become PASS.
- Verdict mapping fixed in advance: PASS → return normally (never emit
  `allow`; do not weaken Codex's own approval flow), strict violation →
  `deny`, warn mode → non-blocking diagnostic.
- Transport/runtime failure behavior must match the documented Claude Code /
  Agent SDK policy: fail open *visibly*, never fake PASS.

## Gate to enter M1

All three must hold reproducibly on the pinned build:

1. Native `apply_patch` is interceptable via `PreToolUse`.
2. Its proposed mutation (paths + content) is deterministically reconstructable
   from the hook payload alone.
3. Returning `deny` prevents disk mutation.

If any fail, revise the integration architecture before writing production
code. Partial outcomes go in `capability-matrix.md` with evidence links.

## Layout

| Path | Purpose |
|---|---|
| `README.md` | This file |
| `capability-matrix.md` | Predefined matrix, filled only from captured evidence |
| `probe/log_hook.py` | Logging hook: captures raw payloads, optional deny arm |
| `probe/hooks.template.json` | Project-layer hooks config installed into the sandbox repo |
| `probe/run_applypatch_probe.py` | Env check + sandbox setup + allow/deny arms + state capture |
| `evidence/runs/<run-id>/` | Raw immutable run artifacts (see below) |

## Evidence rules

1. Everything under `evidence/` is **append-only once captured**. Never edit or
   delete a captured artifact. Corrections happen in new files.
2. Each run gets `<utcstamp>-applypatch/` containing:
   - `env.json` — codex version/platform/flags actually used
   - `events/*.json` — raw hook stdin payloads, byte-exact
   - `events/index.jsonl` — sequence, event name, tool name, sha256 per payload
   - `worktree-before.json` / `worktree-after.json` — per-arm file hashes +
     `git status --porcelain=v2`
   - `transcript-<arm>.log` — full codex exec stdout/stderr
   - `summary.json` — observed-facts checklist for that run
3. Invalid runs are kept under `evidence/runs/_invalidated/` with a reason
   file, mirroring the ox-compaction convention.
4. A `MANIFEST.sha256` for each run is written last; any later drift between
   manifest and files invalidates the run's evidentiary value.
5. Doc-derived facts (developers.openai.com/codex/hooks) may inform probe
   design but never count as observations. Every matrix cell cites a captured
   artifact or stays empty.

## Reproduce

```
python validation/codex-cli/probe/run_applypatch_probe.py
```

Requires: `codex` on PATH (pinned build — see `pinned-build.json`), git,
Python 3.12+.

### Hook trust procedure (one-time, human-in-the-loop)

Hook trust is part of the integration surface being tested, so primary
evidence MUST come from trusted hooks under normal security semantics.
`--dangerously-bypass-hook-trust` is never used by the primary arms; the
runner invokes it only as a **diagnostic secondary arm** when trusted hooks
do not fire at all (`trusted_normal_execution: hook_not_observed`), to
distinguish "PreToolUse unsupported" from "trust dispatch defective"
(cf. upstream issue #32491 on 0.144.1).

The sandbox lives at a fixed path (`probe/sandbox/repo`) so the rendered hook
commands are byte-identical across runs and one trust grant covers all of
them:

1. `cd validation/codex-cli/probe/sandbox/repo`
   (create it first by running the probe once — it will stop before invoking
   codex if hooks are untrusted, or run `python ..\run_applypatch_probe.py`
   which provisions the sandbox deterministically)
2. Launch interactive `codex` from that directory.
3. Run `/hooks`, review the three probe commands, approve/trust them.
4. Exit Codex.
5. Re-run the probe. Trust-state snapshots are hashed into each run's
   `trust-state.json`.

Note: trust is keyed to this worktree's absolute path; tearing down the
worktree invalidates the grant and requires re-running this procedure.

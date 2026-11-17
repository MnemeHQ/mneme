# T-08 P2-first live evidence harness (charter §5.2.7 step 5)

**Status:** harness only. Merging it authorizes **no** live run. The run, its
evidence PR and any claim from it each need the owner's separate go-ahead.

**Purpose.** The live evidence step required by the D5+P2 charter
[Amendment A2](../../../../plans/2026-10-17-t08-d5-p2-memory-resolution-charter.md)
(§5.2.7 step 5). It shows, on the pinned host and the merged P2-first code
(#815, squash `59309fe7`):
- **The §8 C2 re-run.** With `MNEME_MEMORY` committed in project settings
  (D6 channel C2), the repository's own memory now governs. The forbidden
  edit is refused, where #521 recorded a wrong-memory PASS (V5) or a silent
  skip (V4).
- **`OVERRIDE_IGNORED` where §5.2.4 item 3 allows it.** On an exit-0 edit the
  hook emits exactly one PreToolUse `additionalContext` notice. On an exit-2
  refusal it emits none.
- **Planted marker plus override.** With `A/.mneme`, a planted `A/src/.git`
  and `MNEME_MEMORY` naming B, A's memory still governs (row 2).

It reuses the D6 C2 harness
(`../../dg1f-t08-d6-c2-mneme-memory-live/harness/`) with these changes:
- **Pins:** the H1/A2 host (Claude Code `2.1.310`, `--model claude-opus-5-5`,
  `DISABLE_AUTOUPDATER=1`), and hook source `mneme/` equal to `59309fe7`.
- **`hookwrap_v4.py`:** records the hook's `resolve_memory` selections (path,
  source, reason, walk) instead of `find_memory` calls.
- **Probes:** three new ones, below, plus a classifier with expectations.
- **Leak scan:** also catches Claude Code's encoded project ids (`C--dev`).

## Probes

Every probe uses a protected repo A (memory forbids `psycopg2`, decision
`T08-DEC`) and a permissive repo B.
- **Override:**
  - `v5`: `MNEME_MEMORY` names B's memory;
  - `v4`: it names a missing file.
- **Topology:**
  - `r4`: the session runs in B with A added, and the env is committed in B;
  - `own`: the session runs in A, with the env committed in A's own settings.

| Probe | Override | Topology | Edit to the target in A | Expected (P2-first) | #521 (pre-P2-first) |
|---|---|---|---|---|---|
| `P2F-R0-control` | none | r4 | forbidden | A, `DISCOVERED`, exit 2, unchanged, no stdout | same |
| `P2F-V5` | v5 | r4 | forbidden | A, `OVERRIDE_IGNORED`, exit 2, unchanged, no stdout | B's memory, PASS, edit landed |
| `P2F-V4` | v4 | r4 | forbidden | A, `OVERRIDE_IGNORED`, exit 2, unchanged, no stdout | silent skip, edit landed |
| `P2F-V5-own` | v5 | own | forbidden | as `P2F-V5` | B's memory, PASS |
| `P2F-V4-own` | v4 | own | forbidden | as `P2F-V4` | silent skip |
| `P2F-V5-notice` | v5 | r4 | allowed (`import sys`) | A, `OVERRIDE_IGNORED`, exit 0, applied, **one PreToolUse `additionalContext` notice** | (no case) |
| `P2F-planted-marker` | v5 | own | forbidden, in `src/mod.py` below a planted `src/.git` | A, `OVERRIDE_IGNORED`, exit 2, unchanged, no stdout | (no case) |

- **Edits:** "forbidden" means `import os` → `import psycopg2`; "allowed" means `import os` → `import sys`.
- **Refusals:** every exit-2 refusal must name `T08-DEC` in the hook stderr.

## Classification (`classify_p2f.py`)

For each probe, the classifier looks at every PreToolUse
`Edit|Write|MultiEdit` hook record for the target. There must be at least
one. Every one must have:
- repo A's memory as the selection path, with the expected `reason` and
  `walk == "unbounded"`;
- the expected exit code;
- the expected stdout: the notice in its probed shape, or empty;
- on a refusal, `T08-DEC` in stderr.

The target file must also change, or not, as expected. The host version and
the init-event model must equal the pins.

Verdicts are `PASS`, `FAIL`, or `INCONCLUSIVE`. `INCONCLUSIVE` covers: the
edit never attempted, a pin mismatch, a wrapper error, or a self-test run. The
batch is `PASS` only if all seven probes are `PASS`.

**Informational only:** whether the notice text appears in the raw session
stream. Delivery of this shape to the agent is H1's evidence (#808: H1a,
`DELIVERED_TO_AGENT`, verified for `Edit` and Bash only). This batch does not
re-establish or extend it.

## Running (operator, from your own PowerShell, never inside Claude Code)

1. Use a checkout whose `mneme/` equals `59309fe7` (for example `C:\dev\mneme`
   on `main`).
2. Create the untracked `harness/pins.local.env` (gitignored) with `MNEME_SRC_W`,
   `MNEME_SRC_U` and `PY` (a Python with no spaces in its path).
3. Run:

   ```powershell
   $env:DISABLE_AUTOUPDATER = "1"
   & "C:\Program Files\Git\bin\bash.exe" -l <harness>/run_p2f.sh
   ```

The runner:
- refuses to start if `C:\dev\t08-p2first-live\P2F_DONE` exists;
- runs the preflight;
- runs the seven probes, aborting after the first if the init model differs;
- classifies the batch;
- writes `summary_p2f.md`, `classification_p2f.json` and `P2F_DONE` into the
  live root.

For the evidence PR, copy the redacted evidence with `collect_redacted.py`.
Its leak scan must be clean.

## Self-tests (offline)

```bash
python -m pytest docs/validation/artifacts/dg1f-t08-p2-first-live/harness/selftest -q
```

The self-tests run the wrapper around the real P2-first hook (refusal, notice
and planted marker), plus probe setup, every classifier verdict, the
allowlist guard and the leak scan. They never touch the live root.

## What a PASS would and would not establish

**It would establish**, for Claude Code `2.1.310` with `claude-opus-5-5`,
`acceptEdits`, project/local setting sources, headless, n = 1 per probe:
- at the Claude Code direct-write boundary, P2-first selects the repository's
  memory over a committed `MNEME_MEMORY` (both the sibling-repo and the
  own-repo channel, existing and missing override);
- P2-first refuses the forbidden edit that pre-P2-first allowed;
- P2-first emits the H1a notice only on an exit-0 edit;
- P2-first holds under a planted Git marker.

**It would not establish:**
- any other host, version, model or permission mode;
- Bash, SessionStart or Stop live behavior (not probed here);
- `Write` or `MultiEdit` visibility;
- agent-controlled setting of the override (C3/C5/C6);
- G3/G3-B authority;
- Phase 2.

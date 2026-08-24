Classification: harness-preflight failure - NOT capability evidence.

run_m1db_live.py's reset_case() used git reset --hard, which restored the
R0-era tracked .codex/hooks.json (probe logger) over the installed
production hook before every case. Only the preflight ran with the real
gate - and it PASSED: production hook blocked the violating patch
("[ADR-LIVE] FAIL ... path: probe_target.py" via PreToolUse deny).

All four cases executed against the stale logger config:
- PreToolUse: old logger command no longer matched the freshly re-trusted
  hash -> silently skipped -> nothing blocked, everything landed.
- PostToolUse/Stop: old definitions still matched their untouched trust
  entries -> ran -> exited 3 (missing MNEME_PROBE_EVIDENCE_DIR) ->
  "hook: PostToolUse Failed" / "hook: Stop Failed" in transcripts.

Fix: reinstall production hooks.json after every reset_case() call.

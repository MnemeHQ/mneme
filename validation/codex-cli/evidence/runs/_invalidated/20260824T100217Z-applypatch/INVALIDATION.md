Classification: harness-preflight failure - NOT Codex capability evidence.

The run aborted in check_env() before any codex exec invocation. The SHA-256
pin comparison was case-sensitive; calculated and pinned hashes were identical
modulo hex casing. No hook payloads, transcripts, or worktree captures exist
in this run directory.

Fix: normalize both sides with .strip().lower() in
validation/codex-cli/probe/run_applypatch_probe.py.

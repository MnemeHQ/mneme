Classification: harness-preflight failure - NOT Codex capability evidence.

All four arms exited rc=2 before any agent activity: CODEX_ARGS defaulted to
"--sandbox workspace-write --ask-for-approval never", but `codex exec`
(0.149.1) does not accept --ask-for-approval; that approval policy flag
belongs to the interactive CLI. Argparse rejected every invocation.

No hook payloads were produced because codex exec never started a session.
The diagnostic bypass arm triggered for the same reason and carries no signal.

Fix: DEFAULT_CODEX_ARGS = "--sandbox workspace-write".

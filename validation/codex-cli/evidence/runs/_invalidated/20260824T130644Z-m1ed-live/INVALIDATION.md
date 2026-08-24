Classification: INVALID - production PreToolUse definition was not trusted;
Codex skipped hooks before Mneme execution. No M1e-d enforcement conclusion.

Evidence:
- Neither transcript contains any "hook:" line (M1d-b/M1e-a valid runs did).
- config.toml [hooks.state] pre_tool_use:0:0 holds sha256:ef4108be... = the
  R0/M1e-a logger definition: the M1e-a re-trust replaced the production
  hook trust in the single per-slot hash store (config LastWriteTime
  11:40:49, immediately after the M1e-a run).
- On-disk sandbox hooks.json was the correct production definition; Codex
  hash-compared it against the stored logger hash, mismatched, skipped.

Both cases therefore exercised UNGOVERNED mutation. The pass_update landing
proves nothing about enforcement; deny_update proceeding proves nothing
about the gate.

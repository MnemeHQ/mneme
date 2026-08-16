# Campaign invalidation 01

This campaign was invalidated before any scored model run.

- Claude Code and the exact Mneme plugin loaded successfully.
- Model alias `sonnet` resolved to `claude-sonnet-5`.
- Claude authentication was unavailable (`loggedIn: false`, auth method
  `none`), so the CLI emitted a synthetic `Not logged in` response.
- No model tokens were consumed and reported cost was USD 0.
- The runner also encountered a Windows temporary-directory cleanup lock after
  the subprocess returned. The replacement runner tolerates cleanup contention
  and classifies runs without a real model turn as technical invalidations.

Nothing under this directory is part of the 42-run scored dataset.

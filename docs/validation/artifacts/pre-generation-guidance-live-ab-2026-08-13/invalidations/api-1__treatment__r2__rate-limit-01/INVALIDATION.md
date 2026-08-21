# Technical invalidation

Run slot: `api-1 treatment r2`

Claude Code rejected the request before a real model turn because the Pro five-hour session limit had been reached. The hook completed successfully, no workspace change occurred, zero model tokens were consumed, and reported cost was USD 0. This attempt is excluded from scoring and the identical slot must be rerun after reset.

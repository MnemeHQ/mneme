# Mneme Kiro CLI 3.0 Integration

Mneme gates Kiro's native file-write and append tools before they reach
disk, using Kiro's `PreToolUse` command hook that runs the same
introduced-content enforcement path as the Claude Code hook.

Mneme is governance infrastructure: it runs alongside the harness, not
inside it. Kiro coordinates execution; Mneme supplies deterministic
evaluation of decisions recorded in the project's `.mneme/project_memory.json`.
Nothing about Kiro's own permission flow is weakened — a Mneme PASS emits
nothing at all.

## What gets evaluated

- `FORBID_LITERAL` typed rules (exact, case-sensitive, identifier-boundary
  matching), evaluated corpus-wide independent of retrieval rank.
- Legacy constraints/anti-patterns under the same retrieval-gated semantics
  as every other Mneme integration.
- Introduced content only (ADR-018): a write over an existing file checks
  its inserted/replaced lines; remediation edits are never blocked by the
  violation they remove.
- Path applicability (ADR-020): scoped rules apply only where their
  include/exclude selectors match; unknown applicability fails open with an
  explicit diagnostic.

## Install

```bash
pip install mneme-hq
python scripts/install_kiro.py            # project scope (default)
python scripts/install_kiro.py ~/src/myproject
```

Requires Kiro CLI 3.0+ / `--v3` and the `mneme-kiro-hook` console script on
PATH. (Note: CLI 2.x uses agent-config hooks and is unsupported for
pre-write blocking. Kiro IDE 1.x is not yet validated.)

## Status

**Live-verified on Kiro CLI 3.0 / v3 engine (`--v3`).** Live reproduction
performed on Kiro CLI 2.19.2 `--v3` (v3 engine / CLI 3.0) on 2026-08-26
with strict pre-disk blocking on forbidden new-file writes and existing-file
appends/edits (file content byte-identical and untouched), and clean pass on
allowed writes.

**Support scope:** Kiro CLI 3.0 / v3 engine **only**. CLI 2.x default mode is
**NOT SUPPORTED** for enforcement. Kiro IDE 1.x remains **pending separate
live validation** and is not claimed as supported.

See `docs/integrations/kiro.md` for the mutation-surface coverage matrix
and `docs/integrations/kiro-hook-spec.md` for the documented-versus-observed
contract.

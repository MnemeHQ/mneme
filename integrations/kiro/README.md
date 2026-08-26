# Mneme Kiro Integration

Experimental adapter evaluating recorded architectural decisions against Kiro
file-write events.

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

Requires Kiro IDE 1.0+ or Kiro CLI 3.0+ and the `mneme-kiro-hook` console
script on PATH. (Note: CLI 2.x uses agent-config hooks and is unsupported
for pre-write blocking).

## Status

**Contract-tested / experimental.** CLI 2.x enforcement is unsupported
(harness does not block). CLI 3.x / IDE 1.x live validation is pending.
See `docs/integrations/kiro.md` for the mutation-surface coverage matrix
and `docs/integrations/kiro-hook-spec.md` for the documented-versus-observed
contract.

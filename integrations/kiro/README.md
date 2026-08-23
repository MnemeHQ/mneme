# Mneme Kiro Integration

Mneme enforces recorded architectural decisions **before** Kiro's native
file-write tool reaches disk.

Mneme is governance infrastructure: it runs alongside the harness, not
inside it. Kiro coordinates execution; Mneme supplies deterministic,
pre-execution enforcement of decisions recorded in the project's
`.mneme/project_memory.json`. Nothing about Kiro's own permission flow is
weakened — a Mneme PASS emits nothing at all.

## What gets enforced

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
script on PATH.

## Status

**Contract-tested / experimental.** See `docs/integrations/kiro.md` for the
mutation-surface coverage matrix and `docs/integrations/kiro-hook-spec.md`
for the documented-versus-observed contract.

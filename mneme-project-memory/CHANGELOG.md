# Changelog

## Unreleased

### Added

- `mneme init` subcommand — scaffolds a valid, empty, neutral
  `project_memory.json` (default `.mneme/project_memory.json`). Writes a
  minimal skeleton (`meta` + empty `items` / `examples` / `decisions`) that
  round-trips through `MemoryStore.load()` and passes `mneme check` with
  nothing to enforce. No seeded decisions (every decision is enforceable, so
  sample content would create phantom rules). Refuses to overwrite an existing
  file unless `--force` is given; `--path` overrides the output location.

### Tests

- `tests/test_cli_init.py` — 6 tests (fresh create, MemoryStore round-trip,
  refuse-existing, `--force` overwrite, custom `--path`, clean `mneme check`).
- Full suite: 354 passed, 52 warnings.

---

## v0.4.2 — 2026-05-05

**Fix: module execution and exit propagation (completes hook reliability)**

> **Install this, not v0.4.1.** v0.4.1 fixed PATH lookup but left exit-code
> propagation broken — `python -m mneme check` could exit 0 on a FAIL verdict,
> silently allowing violating edits through in strict mode. v0.4.2 is the first
> fully reliable hook release.

### Fixed

- Added `mneme/__main__.py` so `python -m mneme` dispatches correctly.
- `sys.exit(main())` propagates CLI exit codes through the module entrypoint.

### Tests

- Full suite: 218 passed, 2 skipped.

---

## v0.4.1 — 2026-05-04

**Fix: Claude Code hook PATH lookup (incomplete — upgrade to v0.4.2)**

> **Do not use v0.4.1 alone.** Exit-code propagation was not fixed in this
> release. Upgrade to v0.4.2 for the complete fix.

### Fixed

- Hook subprocess changed from `["mneme", "check", ...]` to
  `[sys.executable, "-m", "mneme", "check", ...]`. On Windows (Microsoft Store
  Python) the Scripts directory may not be on `PATH` when Claude Code launches
  `mneme-hook.exe`, causing the bare `mneme` subprocess to fail with
  `FileNotFoundError` and the hook to fail open silently.

### Tests

- Regression test added: `test_subprocess_uses_sys_executable_not_bare_mneme`.

---

## v0.4.0 — 2026-05-04

**Architectural Compiler Foundation**

Compiles a versioned corpus of ADR markdown files into a deterministic
active constraint set. ADRs become the source of truth; the compiler is
the deterministic rule for turning them into the constraints the runtime
injects.

### Added

- `mneme/adr_schema.py` — `ADR` dataclass, `ADRStatus` /
  `ADRPriority` enums, `ADRParseError` / `ADRValidationError` /
  `ADRPrecedenceError`.
- `mneme/adr_parser.py` — `parse_adr_file`, `parse_adr_directory`. YAML
  frontmatter parser; structural failures only (missing /
  unterminated / malformed frontmatter).
- `mneme/adr_compiler.py` — three public stages plus an orchestrator
  and a Decision bridge:
  - `validate_corpus(adrs)` — aggregates required-field, enum, id /
    date / scope grammar, `supersedes` reference resolution, and
    cycle-detection errors into a single `ADRValidationError`.
  - `resolve_precedence(adrs)` — returns the active constraint set:
    status filter → explicit `supersedes` (chain-aware) → same-scope
    priority → newer date → `ADRPrecedenceError` if still ambiguous.
  - `compile_adrs(adr_dir)` — end-to-end: parse → validate →
    precedence; output ordered most-specific-first.
  - `adrs_to_decisions(adrs)` — bridge into the existing `Decision`
    schema so the runtime pipeline (`DecisionRetriever`,
    `ConflictDetector`, `ContextBuilder`) consumes ADR corpora
    without code changes.

### Tests

- 47 new tests across parser / validator / precedence / integration.
- Full suite: 217 passed, 2 skipped (same e2e skips as v0.3.2).
- Backwards compatible: `MemoryStore`, `Pipeline`, and the v0.3.x
  enforcement / Claude Code hook paths are unchanged.

### Deferred

- `mneme adr compile` CLI subcommand (library API is sufficient for v1).
- `Pipeline.from_adr_dir()` classmethod (callers can wire
  `adrs_to_decisions(compile_adrs(dir))` themselves).
- Structured `constraints:` / `anti_patterns:` frontmatter fields,
  hyphenated scope segments, multi-scope lists, body-section parsing.

## v0.3.2 — 2026-05-03

**Mneme for Claude Code (packaging)**

No engine changes. Shells out to existing `mneme check` v0.3.x.

### Added

- `mneme-hook` console script — Claude Code `PreToolUse` hook shim
  (`mneme/integrations/claude_code/hook.py`).
  - Reconstructs full post-edit file content before checking (Edit / Write / MultiEdit).
  - Discovers `.mneme/project_memory.json` by walking up from `cwd`; respects
    `MNEME_MEMORY` env override.
  - Fails open on all execution errors (binary missing, IO error, timeout).
  - `MNEME_HOOK_MODE=strict` (default) blocks on any non-zero verdict;
    `MNEME_HOOK_MODE=warn` never blocks.
- `integrations/claude-code/hooks.json` — hook config template.
- `integrations/claude-code/commands/` — four slash commands:
  `/mneme-check`, `/mneme-context`, `/mneme-record`, `/mneme-review`.
- `integrations/claude-code/skills/mneme/SKILL.md` — discovery skill.
- `scripts/install_claude_code.py` — idempotent installer; writes to
  `./.claude/` (project) or `~/.claude/` (`--user`).
- `docs/integrations/claude-code.md` — integration guide including retrieval
  behaviour, mode switching, and troubleshooting.

### Tests

- 21 new integration tests under `tests/integrations/claude_code/`.
- 2 end-to-end tests (skipped when `mneme` not on `$PATH`).
- Full suite: 170 passed, 2 skipped.

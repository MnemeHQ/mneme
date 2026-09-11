# Changelog

## Unreleased

### Added

- Declared test-evidence ingestion for the Architecture Audit (ADR-024,
  passive): a decision record may declare explicit `test_evidence` entries
  linking it to a test that enforces it. Ordinary `mneme audit` is
  PASSIVE — it executes no repository-controlled code (no pytest, no
  conftest, no plugins) — and validates declared linkages passively
  (well-formed unambiguous pytest selector, exact repository HEAD SHA
  pin, existing test file). A declared linkage annotates evidence
  sources as `test:declared:<selector>` but never protects: the VERIFIED
  state requires a trusted verification producer (CI-produced exact-SHA +
  exact-selector ingestion — next task). Guidance is never upgraded; every
  failure mode (missing selector, stale or unavailable SHA, ambiguous
  mapping, malformed declaration) fails closed with a deterministic
  diagnostic. `mneme.audit/v1` unchanged.

### Fixed

- P1.2 Architecture Audit tier semantics (ADR-023): intent is now judged
  from the decision text (prescriptive vs advisory language) instead of
  record shape, so byte-identical decision text no longer changes tier
  when an unrelated structured constraint is added, and deterministic
  architectural requirements without structured fields no longer fall to
  Guidance. `Identified Mneme Potential` is now
  (Mneme-ready + Requires modelling) / protection-relevant — decisions
  deterministically enforceable in principle, not only records
  immediately expressible by existing rule types. `mneme.audit/v1`,
  CLI, Protect behavior, and enforcement/refusal semantics are unchanged.

---

## v0.7.0 — 2026-09-07

**Architecture Audit, Audit→Setup activation, and per-decision protection — first PyPI release of the full loop**

This is the first published package release containing the complete
`Audit → Setup → Protect` journey: the P1.2 Architecture Protection Audit,
`mneme setup` with activation state, Audit-reference setup pairing, and
per-decision protection activation. No retrieval, enforcement-engine, or
frozen-benchmark semantics change.

### Added

- `mneme audit` — P1.2 Architecture Protection Audit. Classifies every
  decision in `project_memory.json` into Protected / Mneme-ready /
  Requires modelling / Guidance, optionally scans the repository for
  verified CI enforcement evidence (`--repo-root`), and writes a
  versioned `mneme.audit/v1` JSON report via `--json`. Findings are
  deterministic and reproducible.
- `mneme setup` — installs Mneme in **setup mode** (M1.3a): context
  injection and non-blocking checks only, never enforcement. Persists
  activation state (`mneme.setup/v1`) in `project_memory.json`, records
  git context, detects installed coding-agent integrations read-only
  (detects, never configures), and prints a readiness view that is a
  thin view over the canonical P1.2 protection assessment. Idempotent;
  existing projects are preserved; enforcement stays `not_enabled`.
- Audit-reference setup support (M1.3b) — `mneme setup --audit-ref
  <reference>` resolves an opaque, scoped, expiring Architecture Audit
  setup reference **before any local write** (fail-closed on invalid,
  expired, mismatched, or unreachable references), records baseline
  provenance, and reports setup completion back to the Audit service
  (idempotent, with automatic retry on the next setup run).
- `mneme protect list|status|validate|activate` — per-decision
  protection activation (M1.4): lists Mneme-ready candidates,
  deterministically validates a proposed protection against the existing
  enforcement engine (no writes, no model), explicitly activates it for
  one decision, and verifies via independent canonical re-assessment.
  Activation is explicit and idempotent; requesting activation without
  observable enforcement evidence never reports Protected and never
  moves Current Protection by itself.
- EventCatalog ADR ingestion (retrieval-only) — EventCatalog documents
  can feed the decision corpus.

### Fixed

- Strict `Pipeline` verdict precedence: UNKNOWN applicability now takes
  precedence over conflicts, so an out-of-scope conflict can no longer
  mask an unknown-applicability failure.
- Static PyPI Python badge replaces the broken dynamic badge.

### Validation / Research

- Enforcement-quality benchmark results recorded in-repo.
- Claude Managed Agents M0 capability study remains evidence only.

### Maintenance

- CI: pull-request + squash-only enforcement on `main` (GitHub ruleset
  plus local pre-push guard).
- Docs: five-minute quickstart; README Architecture Audit section.

### Compatibility

- No changes to retrieval ranking, `DecisionRetriever`,
  `ConflictDetector`, existing typed-rule semantics, or the frozen
  enforcement benchmark. `mneme setup` and `mneme protect` are additive
  CLI surface over the existing engine.

---

## v0.6.0 — 2026-08-28

**Governability API, Kiro CLI v3, LangChain/LangGraph, and ADR lifecycle analysis**

### Added
- The authoritative `GovernabilityAssessment` and `assess_governability()`
  core API. It classifies decisions as `enforceable`, `partial`, or
  `guidance`, providing the canonical governability result for integrations
  such as the Architecture Audit Workspace.
- Native Kiro CLI 3.0 / v3 pre-write enforcement. The integration is
  live-verified against the v3 engine and gates Kiro native file writes before
  they reach disk.
- LangChain / LangGraph middleware integration (`mneme.integrations.langchain`)
  for retrieved-context injection and pre-tool enforcement. Sync, async, and
  embedded-subgraph paths are validated against pinned LangChain and LangGraph
  versions.
- Hermes Agent integration (`mneme.integrations.hermes`) for context injection
  and pre-tool enforcement on its supported mutation surfaces. This integration
  remains **Experimental**: Hermes has no blocking Stop-equivalent backstop.
- Read-only ADR lifecycle reconciliation through `mneme check --adr-dir`.
  It reports `DANGLING_SUPERSEDES`, `ORPHAN_SUPERSEDED`,
  `ACTIVE_CONTRADICTION`, `SILENT_PRECEDENCE_ELIMINATION`, and
  `LEDGER_STATUS_MISMATCH`; findings are warn-only and do not alter retrieval
  or enforcement behavior.

### Validation / Research

- Claude Managed Agents M0 capability study recorded as **PARTIAL**. Known
  incompatibilities mean it is evidence only, not a supported integration.

### Packaging / Docs

- Package metadata and README now position Mneme as architectural drift
  prevention for the agentic AI SDLC.
- Added the optional `mneme-hq[langchain]` dependency group for the LangChain /
  LangGraph integration.

### Maintenance

- Added PR execution-provenance checks and refreshed GitHub issue and pull
  request templates.

### Compatibility

- No intended changes to retrieval ranking, `DecisionRetriever`,
  `ConflictDetector`, existing typed-rule semantics, or the frozen enforcement
  benchmark.

---

## v0.5.2 — 2026-08-24

**Enforcement quality benchmark, phrase-sequence matcher fix, Codex CLI integration**

### Added

- Enforcement-quality benchmark suite with partitioned FPR reporting (charter #318, #319, #320). Benchmark scenarios cover legacy anti-patterns, typed literals, and introduced-delta enforcement; false-positive rates tracked per rule class.
- Codex CLI enforcement integration (PreToolUse gate + Stop session audit) (#321). Reuses `mneme check` semantics; hook evaluates proposed tool calls and audits session deltas.
- Claude Agent SDK integration (`mneme.integrations.agent_sdk`). Reuses the
  existing retrieval and enforcement semantics: relevant decisions are
  injected before agent work via `UserPromptSubmit`, and proposed
  Write/Edit/MultiEdit calls are evaluated by `mneme check` before
  execution via `PreToolUse`, returning allow/deny with Mneme's reason.
  Warn-mode and unevaluated outcomes are surfaced as visible context, never
  silently converted to PASS. A runnable governed-loop demo lives under
  `examples/claude-agent-sdk/`.
- Typed ADR enforcement with `FORBID_LITERAL`. ADR import now persists
  explicit typed rules, `mneme check` applies them independently of retrieval
  score, and human/JSON output identifies the rule type.
- Retrieval-only import diagnostics for active ADRs that yield zero
  mechanically enforceable rules.
- Explicit path applicability for typed rules. Structured ADR directives can
  persist `include_paths` and `exclude_paths`; enforcement, conflict detection,
  context output, and the Claude Code hook share deterministic, case-sensitive
  selector semantics and emit per-rule applicability traces.
- `mneme check --target-path` for checking temporary/materialized content
  against the path of the artifact that will actually be changed. Unknown
  scoped applicability is an operational failure in the CLI and an explicit
  fail-open diagnostic in integrations.

### Fixed

- **Phrase-sequence matching for multi-term legacy anti-patterns** (ADR-017 amendment, #317). The legacy matcher previously treated any single term from a descriptive phrase as the whole rule, causing false positives on benign prose (e.g., ADR-003 content containing "governance", "open", "without"). Now matches the full phrase sequence, eliminating the dogfood false-positive on site governance content.

### Compatibility

- Existing `constraints` and `anti_patterns` retain their current matching and severity behavior. Memory files without `rules` continue to load unchanged.
- Existing scalar typed rules remain global. Selector fields are additive and the check JSON schema remains `mneme.check/v1` with additive fields.

---

## v0.5.1 — 2026-08-06

**Claude Code hook reliability: trusted verdicts, warn-mode feedback, `replace_all`**

Fixes four defects in the Claude Code `PreToolUse` hook. No retrieval or
enforcement semantics change; the deterministic mechanism is untouched.

### Added

- `mneme check --json` — emits a versioned, machine-readable verdict payload
  (`schema`, `verdict`, `mode`, `violations`, `freshness`) as the only stdout
  content. Exit codes are unchanged. Consumers should trust the payload's
  verdict rather than the exit code, and fail open on anything unparseable.

### Fixed

- **The hook could hard-block on a crash.** It converted every non-zero child
  exit into exit 2 (block). Because `mneme check --mode strict` returns 1 for a
  WARN verdict and Python also returns 1 for an uncaught exception, a malformed
  memory file or a CLI crash was indistinguishable from a violation and blocked
  the edit. The hook now blocks only on a parsed verdict and fails open
  otherwise, matching the documented guarantee.
- **Warn mode surfaced nothing.** It wrote to stderr and exited 0, and Claude
  Code discards stderr from a hook that exits 0. Warn mode now emits a
  `PreToolUse` JSON payload with `permissionDecision: "defer"` and the
  violation detail as the reason. `defer` is deliberate: `allow` would
  auto-approve the tool call and bypass the user's normal permission prompt, so
  a warning mode must never use it.
- **`replace_all` was ignored.** `Edit` and `MultiEdit` always materialized a
  single replacement, so when Claude Code was about to replace every
  occurrence, the checked content was not the content that would land on disk
  and violations introduced by the second or later occurrence went unseen.
- **The child CLI could be a different install than the hook.**
  `sys.executable -m mneme` resolved against the child's `sys.path`, which can
  be an older mneme that rejects `--json` — the hook would then fail open on
  every edit with enforcement silently inactive. The child now inherits a
  `PYTHONPATH` pinned to the hook's own package root, and a stale runtime
  produces an explicit "enforcement is inactive" warning instead of silence.

---

## v0.5.0 — 2026-07-03

**Directory-ready Claude Code plugin, `mneme init`, and PyPI metadata realignment**

First minor release since v0.4.0. It ships new backwards-compatible,
user-facing capabilities — a project scaffolder and a directory-ready Claude
Code plugin — and folds in the v0.4.1 / v0.4.2 hook-reliability fixes that were
tagged on GitHub but never reflected in the published PyPI package metadata
(before v0.5.0, PyPI served only `0.4.0`). No `DecisionRetriever`,
`ConflictDetector`, retrieval, or enforcement semantics change.

The two artifacts are separate. The `mneme-hq` **PyPI package** provides the
`mneme` and `mneme-hook` runtime console commands. The **Claude Code plugin**
under `integrations/claude-code-plugin/` is a directory of plugin files that
*drives* those commands. Installing the PyPI package does **not** install or
enable the plugin, and vice versa — the plugin is loaded by Claude Code (via
`--plugin-dir` or a marketplace) and expects `mneme` / `mneme-hook` already on
`PATH`.

### Added

- `mneme init` subcommand — scaffolds a valid, empty, neutral
  `project_memory.json` (default `.mneme/project_memory.json`). Writes a
  minimal skeleton (`meta` + empty `items` / `examples` / `decisions`) that
  round-trips through `MemoryStore.load()` and passes `mneme check` with
  nothing to enforce. No seeded decisions (every decision is enforceable, so
  sample content would create phantom rules). Refuses to overwrite an existing
  file unless `--force` is given; `--path` overrides the output location.
- Directory-ready Claude Code plugin under `integrations/claude-code-plugin/` —
  bundles the enforcement hook, the `mneme` skill, and four namespaced slash
  commands (`/mneme:context`, `/mneme:check`, `/mneme:record`,
  `/mneme:review`) into a single directory that Claude Code can load with
  `--plugin-dir` (or via a marketplace). It depends on the `mneme` /
  `mneme-hook` commands from the `mneme-hq` package being on `PATH`; installing
  the package does not install the plugin. The plugin manifest
  (`.claude-plugin/plugin.json`) declares manifest version `0.1.0` — correct for
  its first directory release, and versioned independently of the `mneme-hq`
  package version — and a `mode` userConfig option (`strict` | `warn`, default
  `strict`). The plugin has not yet been publicly submitted to a marketplace.
- Direct exec-form invocation of `mneme-hook` in the plugin hook config
  (`{ "type": "command", "command": "mneme-hook", "args": [] }`) — no shell
  string, no wrapper script, no interpreter probing. Claude Code resolves
  `mneme-hook` on `PATH` and spawns it directly, so the hook is
  platform-independent by construction.
- Enforcement-mode resolution for the Claude Code adapter (`resolve_mode()`
  in `mneme/integrations/claude_code/hook.py`) with precedence
  `MNEME_HOOK_MODE` > `CLAUDE_PLUGIN_OPTION_MODE` > `strict`. The plugin's
  `mode` userConfig value reaches the hook subprocess as
  `CLAUDE_PLUGIN_OPTION_MODE`; an explicit `MNEME_HOOK_MODE` overrides it.
  Mode resolution stays inside the Claude Code adapter.
- Strict fallback for invalid mode values — an unrecognized value in either
  variable resolves to `strict`, so a typo can never silently disable
  enforcement. A set-but-invalid explicit override does not fall through to the
  plugin option; values are case- and whitespace-tolerant.

### Fixed

- Realigned the published package with the v0.4.1 / v0.4.2 hook-reliability
  fixes. Both were tagged on GitHub, but the fixes never reached the PyPI
  package metadata — before v0.5.0, PyPI served only `0.4.0`, which has the
  exit-code propagation bug (a failed check could exit `0` and let a violating
  edit through in strict mode). Publishing `0.5.0` makes `pip install mneme-hq`
  deliver the reliable hook for the first time. The underlying fixes:
  - `mneme/__main__.py` so `python -m mneme` dispatches and
    `sys.exit(main())` propagates CLI exit codes (v0.4.2).
  - Hook subprocess uses `[sys.executable, "-m", "mneme", ...]` instead of a
    bare `mneme`, so a missing Scripts directory on `PATH` (Windows Microsoft
    Store Python) no longer makes the hook fail open silently (v0.4.1).

### Changed

- `pyproject.toml` version `0.4.0` → `0.5.0`.

### Tests

- `tests/test_cli_init.py` — 6 tests (fresh create, `MemoryStore` round-trip,
  refuse-existing, `--force` overwrite, custom `--path`, clean `mneme check`).
- `tests/integrations/claude_code/test_plugin_contract.py` — deterministic,
  shell-free plugin contract tests: manifest is valid and declares the `mode`
  option, manifest declares a valid semver version, the hook uses exec-form
  direct invocation, the hook command carries no shell dependency, no wrapper
  script remains, all four slash commands are present, the skill is present.
- `tests/integrations/claude_code/test_hook_mode.py` — mode-precedence and
  strict-fallback coverage.
- `tests/integrations/claude_code/test_hook_e2e.py` — end-to-end against the
  real `mneme check` binary via the hook shim: a compliant Write is allowed
  (exit `0`) and a violating Write is blocked (exit `2`) in strict mode, plus
  the equivalent Edit cases. (Skipped when `mneme` is not on `PATH`.)
- `tests/test_packaging_contract.py` — deterministic packaging contract:
  asserts `[project.scripts]` declares both console scripts
  (`mneme = mneme.cli:main` and
  `mneme-hook = mneme.integrations.claude_code.hook:cli_main`), and verifies
  the same two entry points inside the built wheel when a `dist/` artifact is
  present.

### Release

- Manual PyPI publication procedure and the post-merge checklist:
  `docs/releases/RELEASING.md`. This PR does **not** publish, tag a release,
  or advertise the new version in the plugin README — those steps run only
  after `mneme-hq >= 0.5.0` is live on PyPI.

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

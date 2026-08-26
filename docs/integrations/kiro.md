# Kiro CLI 3.0 Integration (Native)

Mneme gates Kiro's native file-write and append tools before they reach disk, using
Kiro's `PreToolUse` command hook that runs the same introduced-content enforcement
path as the Claude Code hook.

**Status: live-verified on Kiro CLI 3.0 / v3 engine (`--v3`).** Live reproduction
performed on **Kiro CLI 2.19.2 `--v3` (v3 engine / CLI 3.0)** on 2026-08-26.
Results:

| Capability | CLI 2.19.2 default (v2 engine) | CLI 2.19.2 `--v3` (v3 engine / CLI 3.0) |
|------------|--------------------------------|-----------------------------------------|
| Hook registration | PASS (agent config `hooks` map, camelCase) | **PASS** (`.kiro/hooks/*.json` v1 format automatically discovered) |
| Envelope capture | PASS (`fs_write`, `command:create`, `file_text`) | **PASS** (`PreToolUse`, `session_id`, `fs_write`/`fs_append`, `text`) |
| Verdict generation (exit 2 on FAIL) | PASS | **PASS** |
| **Pre-execution blocking** | **FAIL** (file written despite exit 2) | **PASS** (tool blocked pre-disk, stderr shown to agent) |
| Clean allowed write (exit 0 on PASS) | PASS | **PASS** (file written to disk) |
| Overall enforcement support | **NOT SUPPORTED** | **PASS (live-verified)** |

*Note on registration:* CLI 2.19.2 in default mode ignores `.kiro/hooks/*.json` files. In `--v3` mode (CLI 3.0 / v3 engine), `.kiro/hooks/*.json` files are automatically discovered and loaded.

**Support scope:** Kiro CLI 3.0 / v3 engine **only**. CLI 2.x default mode is **NOT SUPPORTED** for enforcement. Kiro IDE 1.x remains **pending separate live validation** and is not claimed as supported.

## What it does

- Parses the Kiro v1 `PreToolUse` STDIN envelope (`hook_event_name`, `cwd`,
  `session_id`, `tool_name`, `tool_input`).
- Normalizes native write/append shapes — tool names `write` / `fs_write` /
  `fsWrite` / `fs_append` with `tool_input.path` + full `tool_input.text`
  (CLI 3.0) or `tool_input.content` (documented) or `tool_input.file_text`
  (CLI 2.x create) — onto Mneme's existing mutation representation.
- Reuses the shared gate verbatim: introduced-delta enforcement (ADR-018),
  corpus-wide typed-literal enforcement independent of retrieval rank
  (ADR-017/019), explicit path applicability via `--target-path` (ADR-020),
  memory discovery from the event `cwd`, `MNEME_HOOK_MODE` policy, trusted
  `mneme.check/v1` verdicts only.
- Blocks (exit non-zero, reason on stderr) on trusted WARN/FAIL in strict
  mode; warns into agent context (exit 0, message on stdout) in warn mode;
  stays silent on PASS so Kiro's normal permission flow is untouched; fails
  open but visibly on every operational failure.

No retrieval, enforcement, applicability, conflict, pipeline, or benchmark
semantics are implemented or changed here. No runtime dependency on Kiro or
any AWS SDK exists.

## Install

```bash
pip install mneme-hq          # provides the `mneme-kiro-hook` console script
python scripts/install_kiro.py [PROJECT_DIR]   # default: current directory
```

The installer writes `.kiro/hooks/mneme.json` under the project root,
project-scoped by default because Mneme Layer 1 is project-scoped. It is
idempotent: re-running produces a byte-identical file. It preserves every
foreign hook entry already present and upserts only the
`mneme-governance-gate` entry. It refuses to touch an existing
`.kiro/hooks/mneme.json` that is not valid UTF-8 JSON or not a
`{"version": "v1", "hooks": [...]}` file. Global installation is not
offered.

**Requires Kiro CLI 3.0+ / `--v3`** (the standalone `.kiro/hooks/*.json` format).
CLI 2.x default mode uses agent-config hooks; the installed file will be
ignored by CLI 2.x default mode. Kiro IDE 1.x is not yet validated.

## Enforcement mode

Same environment contract as the Claude Code hook:
`MNEME_HOOK_MODE=warn|strict` (unset defaults to `strict`; an unrecognized
value falls back to `strict`).

## Mutation surface coverage matrix

Factual status of every mutation surface. "Blocked pre-write" means Mneme
returned a blocking exit before the write executed.

| Surface | Kiro hook fired | Proposed content pre-execution | Blocked pre-write | PostFileSave observed | Later audit |
|---|---|---|---|---|---|
| Native write (new file) | `PreToolUse(write)` | Yes — full content in `text` (v3), `content` (v1), or `file_text` (CLI 2.x) | **CLI 3.0 / v3: YES** (blocked pre-disk); CLI 2.x: NO | n/a (blocked) or `PostFileCreate` | Yes |
| Native edit / append | `PreToolUse(write|fs_append)` | Yes — full proposed content or appended lines; gate checks introduced delta | **CLI 3.0 / v3: YES** (blocked pre-disk, file untouched); CLI 2.x: unobserved | `PostFileSave` | Yes |
| Shell redirection (`echo x > f`) | `PreToolUse(shell)` — command string only | **No** — content is inside an unparsed shell command | **No** (deliberately not parsed) | Documented to fire after agent saves; unverified for shell writes | Yes |
| Script-generated write | `PreToolUse(shell)` — command string only | **No** | **No** | Unverified | Yes |
| Rename | No dedicated pre-rename trigger | No | No | No | Yes (git status) |
| Deletion | `PostFileDelete` only (post, non-blocking) | No | No (nothing introduced; ADR-018 permits deletions) | `PostFileDelete` fires post-hoc | Yes |
| MCP-mediated write | `PreToolUse(@server/tool)` documented | Server-specific; envelope officially documented, shape per server | Not implemented | `PostToolUse` | Yes |
| Spec-task mutations (IDE) | `PreTaskExec` (pre-task, IDE-only) | No file-level payload | No | `PostTaskExec` | Yes |
| Kiro IDE native writes | `PreToolUse` fires per docs; historical IDE 0.12 `runCommand` hooks received no STDIN payload (#7408/#7500); IDE 1.x pending validation | **No** (historical) | **No** (historical) — fail-open with nothing to inspect | `PostFileSave` | Yes |

Key points:

- Only the native write path on the **Kiro CLI 3.x / IDE 1.x** carries
  enough pre-execution information (target path + full content) to enforce
  before disk. CLI 2.x default mode returns correct verdicts but does not block.
- Shell redirection and script writes are **explicitly unsupported** for
  pre-write enforcement. `PreToolUse(shell)` exposes only the command
  string; Mneme does not parse shell commands (documented architectural
   boundary). These mutations remain visible to a whole-file audit
   (`mneme check --input <file>`) after the fact.
- The Stop working-tree audit is deferred to a separate bounded milestone:
   a correct audit needs a session-start baseline so pre-existing user
   changes are not attributed to the agent.

## Verification

- Tests: `python -m pytest tests/integrations/kiro -p no:cacheprovider`
  (envelope parsing, gate policy, applicability, modes, fail-open paths,
  installer idempotency, packaging contract). Includes regression fixtures
  for both the CLI 3.0 v3 envelope (`test_observed_v3_envelope_with_text`),
  the v3 append envelope (`test_observed_v3_fs_append_envelope`),
  and the CLI 2.19.2 v2 envelope (`test_observed_cli_2_19_2_envelope_with_file_text`).
- Live reproduction: verified live on Kiro CLI 2.19.2 `--v3` (v3 engine / CLI 3.0)
  with strict pre-disk blocking on forbidden new-file writes, strict pre-disk blocking
  on existing-file appends/edits (file content byte-identical and untouched), and clean
  pass on allowed writes.

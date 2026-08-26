# Kiro Integration (Experimental)

Experimental adapter evaluating proposed writes before disk in Kiro, using a
Kiro `PreToolUse` command hook that runs the same introduced-content
enforcement path as the Claude Code hook.

**Status: contract-tested / experimental.** Live reproduction performed
on **CLI 2.19.2** (`kiro-cli-chat 2.19.2`) on 2026-08-26. Results:

| Capability | CLI 2.19.2 (agent-config hooks) | Documented CLI 3.0+ / IDE 1.0+ (v1 files) |
|------------|----------------------------------|-------------------------------------------|
| Hook registration | PASS (agent config `hooks` map, camelCase) | NOT TESTED (documented supported) |
| Envelope capture | PASS (live capture; `session_id` omitted) | NOT TESTED |
| Verdict generation (exit 2 on FAIL) | PASS | NOT TESTED |
| **Pre-execution blocking** | **FAIL** (file written despite exit 2) | **NOT TESTED** |
| Overall enforcement support | **NOT SUPPORTED** | Pending |

*Note on registration:* CLI 2.19.2 ignores `.kiro/hooks/*.json` files. That registration failure is specific to CLI 2.x and is not projected onto CLI 3.x / IDE 1.x.

The integration remains gated on live reproduction before any "supported"
claim. **CLI 2.x is explicitly NOT supported for enforcement**; the PR
documents the observed contract for regression testing only. Per the claim
gate, it is **not** listed under "Explicitly supported integrations" in the
README until live allow/block reproduction exists on a CLI 3.x or IDE 1.x
surface.

## What it does

- Parses the Kiro v1 `PreToolUse` STDIN envelope (`hook_event_name`, `cwd`,
  `session_id`, `tool_name`, `tool_input`).
- Normalizes only the native write shape — tool name `write` / `fs_write` /
  `fsWrite` with `tool_input.path` + full `tool_input.content` (documented)
  **or** `tool_input.file_text` (CLI 2.19.2 observed for `command: "create"`)
  — onto Mneme's existing mutation representation.
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

**Requires Kiro IDE 1.0+ or Kiro CLI 3.0+** (the standalone
`.kiro/hooks/*.json` format). CLI 2.x uses agent-config hooks instead; the
installed file will be ignored by CLI 2.x.

## Enforcement mode

Same environment contract as the Claude Code hook:
`MNEME_HOOK_MODE=warn|strict` (unset defaults to `strict`; an unrecognized
value falls back to `strict`).

## Mutation surface coverage matrix

Factual status of every mutation surface. "Blocked pre-write" means Mneme
returned a blocking exit before the write executed.

| Surface | Kiro hook fired | Proposed content pre-execution | Blocked pre-write | PostFileSave observed | Later audit |
|---|---|---|---|---|---|
| Native write (new file) | `PreToolUse(write)` | Yes — full content in `tool_input.content` (v1) or `file_text` (CLI 2.x) | **CLI 2.x: NO** (exit 2 returned but write executed); v1: pending | n/a (blocked) or `PostFileCreate` | Yes |
| Native edit / replace | `PreToolUse(write)` | Yes — full proposed content; gate checks introduced lines only | CLI 2.x: unobserved; v1: pending | `PostFileSave` | Yes |
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
  before disk. CLI 2.x returns correct verdicts but does not block.
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
  for the CLI 2.19.2 observed envelope (`test_observed_cli_2_19_2_envelope_with_file_text`).
- Live reproduction (pending): install the hook in a **Kiro CLI 3.x or IDE 1.x**
  workspace with a `FORBID_LITERAL` rule, ask the agent to introduce the
  literal, and observe the block; then repeat a compliant write and observe
  the allow. Record both transcripts in the follow-up PR that promotes this
  integration out of experimental.

# Hermes Agent — P1.5 proof of concept

**Status: Experimental (POC complete, not a native integration).**

Hermes Agent (Nous Research) exposes two plugin hooks that map onto existing
Mneme surfaces without changing any frozen semantics:

| Hermes hook | Mneme surface | Behavior |
| --- | --- | --- |
| `pre_llm_call` (per turn) | `MemoryStore` → `DecisionRetriever` → `format_decisions` | Retrieved decisions returned as `{"context": ...}`; Hermes appends them to the current turn's user message |
| `pre_tool_call` (blocking) | ToolEvent translation → introduced-delta materialization → `mneme check` | Trusted strict-mode WARN/FAIL returns `{"action": "block", "message": <reason>}` |

The adapter is a thin translation layer. It implements no retrieval,
applicability, conflict, or enforcement semantics of its own: retrieval is
the unchanged `DecisionRetriever` path shared with the Agent SDK adapter,
enforcement is the unchanged `mneme check` CLI contract shared with the
Claude Code hook, V4A patch parsing is the frozen Codex CLI transport
parser, and shell preflight is the ADR-021 class-A reconstruction reused as-is.

## What ships

- `mneme/integrations/hermes/adapter.py` — pure translation + gate glue.
- `mneme/integrations/hermes/plugin.py` — hook binding (`register(ctx)`).
- `integrations/hermes-plugin/` — the standalone plugin directory users copy
  to `<project>/.hermes/plugins/mneme/`.
- `tests/integrations/hermes/` — context, gate, wiring, identity, and one
  end-to-end test through the real `mneme check` subprocess.

## Install (POC)

1. Copy `integrations/hermes-plugin/` to `<project>/.hermes/plugins/mneme/`.
2. Make the published `mneme` package importable from Hermes' Python
   environment.
3. Enable project plugins and opt in:

   ```
   HERMES_ENABLE_PROJECT_PLUGINS=true        # env var
   # plus plugins.enabled: [mneme] in Hermes config — project plugins are
   # opt-in even when the env var is set (verified against 0.19.0)
   ```

Enforcement mode follows the shared resolution (`MNEME_HOOK_MODE`, then
"strict").

## H0 capability probe findings (hermes-agent 0.19.0)

Verified against the shipped package and exercised through Hermes' real
plugin-manager dispatch (`invoke_hook` / `resolve_pre_tool_block`), not
documentation alone:

- **Payload shapes are deterministic.**
  - `write_file`: `{path, content}` — full proposed content is present;
    introduced-delta materialization applies unchanged (ADR-018).
  - `patch` mode `replace`: `{path, old_string, new_string, replace_all?}` —
    maps 1:1 onto the canonical Edit event.
  - `patch` mode `patch`: raw V4A text — parsed by the frozen Codex CLI
    parser (`parse_patch_operations`) with current-file snapshots supplied
    per Update operation.
  - `terminal`: `{command, workdir?, ...}` — the command arrives verbatim as
    one string, so ADR-021 class-A heredoc reconstruction reuses without new
    shell interpretation. No cwd is carried in any payload; the adapter uses
    the project directory (project plugins load relative to CWD).
- **Blocking primitive confirmed live**: forbidden `write_file` content and
  a forbidden class-A heredoc both produced block directives through the
  real dispatch path; compliant calls passed untouched. First valid
  directive wins; a block requires a non-empty message.
- **Context injection confirmed live**: a `{"context": text}` return was
  collected through the real per-turn dispatch and joined into the user
  message.
- **Fail-open posture**: Hermes swallows hook exceptions and ignores invalid
  directives, so the gate can only ever *prevent* what it deterministically
  evaluated — it cannot silently turn failures into blocks.
- **No blocking Stop-equivalent**: `on_session_end` is observer-only (its
  return value is ignored). There is no session-delta backstop behind this
  gate.
- Live model-driven sessions were not available in the probe environment
  (no provider credentials); all verification ran at the dispatch-runtime
  layer, which owns the entire hook contract. Tool arguments themselves are
  schema-constrained and handler-validated by Hermes.

## H3 bypass coverage matrix

| Mutation surface | Pre-execution outcome | Evidence |
| --- | --- | --- |
| `write_file` | **Caught** — full-content introduced-delta check | e2e test + dispatch probe |
| `patch` mode `replace` | **Caught** — Edit-equivalent check | tests |
| `patch` mode `patch`, Add/Update ops | **Caught** — frozen V4A parser + snapshots | tests |
| `patch` mode `patch`, Delete op | Skip-by-design (introduces nothing; ADR-018) | parser contract |
| Unparseable / snapshot-unavailable patch | Fail open, disclosed (never guessed) | tests |
| `terminal`: single quoted-delimiter heredoc write | **Caught** — ADR-021 class-A reuse | tests + dispatch probe |
| `terminal`: redirects, `tee`, `sed -i`, `mv`, `rm`, compound commands | **Bypassed pre-execution**, classified only | classification never blocks |
| `execute_code` | **Bypassed** — arbitrary Python file I/O; unevaluated surface | characterized, not governed |
| `process` tool | **Bypassed** — spawns arbitrary commands | discovered in H0 registry sweep |
| Sub-agents (`delegate_task`) | Hook fires again per child dispatch (per dispatch contract); unverified live | unknown until credential-backed replay |
| Completion time (session delta) | **Not covered** — no blocking Stop-equivalent | H0 finding |

## What this integration is not

- It does not claim Claude Code or Codex CLI enforcement parity. Those
  integrations implement ADR-021's full prevent → catch → verify arc;
  Hermes currently supports only the **prevent** tier.
- It adds no HTTP/MCP surface, no fork of Hermes core, no generalized shell
  parser, and no changes to `DecisionRetriever`, conflict detection,
  enforcer semantics, typed-rule matching, path applicability, or benchmark
  fixtures.

## Validation status (H4 closeout)

| Gate | Result |
| --- | --- |
| Context injection (H1) | PASS — existing retrieval path unchanged |
| Direct mutation blocking (H2) | PASS — strict WARN/FAIL blocks via `{"action": "block"}` |
| Bypass surfaces explicitly characterized (H3) | PASS — matrix above |
| Zero frozen-core changes | PASS — adapter/tests/docs only |
| Enforcement benchmark remains 7/7 | PASS — `mneme benchmark examples/benchmarks/` unchanged |

**Recommendation: promote to "supported experimental integration".**
All five POC exit criteria hold, so promotion out of roadmap-only status is
justified — with the documented limitation that completion-time catch parity
is absent and depends on Hermes exposing a blocking Stop-boundary primitive.
Full production parity claims remain blocked on that gap and on a
credential-backed live-session replay of the dispatch-level findings.

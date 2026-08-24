# Mneme for Google Antigravity

Deterministic architectural enforcement for [Google Antigravity](https://antigravity.google/)
agents at the pre-tool gate. The same introduced-delta enforcement that powers
the Claude Code hook, exposed through Antigravity's native `PreToolUse` hook
transport.

Verified against Antigravity 2.8.1 (IDE); contract per the official Hooks
documentation.

---

## Architecture

The adapter (`mneme/integrations/antigravity/adapter.py`) is a thin
translation layer. It implements no governance semantics of its own:

```text
Antigravity PreToolUse payload
    -> ToolEvent translation (Antigravity args -> canonical Write/Edit/MultiEdit)
    -> introduced-content materialization + `mneme check`   (existing)
    -> {"decision": "deny"} + Mneme's reason, or {} (no opinion)
```

Tool mapping:

| Antigravity tool | Canonical gate | Translated arguments |
|---|---|---|
| `write_to_file` | Write | `TargetFile`, `CodeContent` |
| `replace_file_content` | Edit | `TargetFile`, `TargetContent` -> `ReplacementContent` |
| `multi_replace_file_content` | MultiEdit | `ReplacementChunks[].TargetContent` -> `.ReplacementContent` |

Materialization, introduced-delta selection (ADR-018), memory discovery,
mode resolution, verdict parsing, and reason formatting are imported from
the existing Claude Code hook module. Read-only tools never reach the gate.

## Usage

Create `.agents/hooks.json` inside a governed project (one with
`.mneme/project_memory.json`):

```json
{
  "mneme": {
    "PreToolUse": [
      {
        "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "python -m mneme.integrations.antigravity",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

The command needs `mneme-hq` importable; point `PYTHONPATH` at your install
or invoke an installed console wrapper. Enforcement mode follows the shared
resolution (`MNEME_HOOK_MODE`, then `"strict"`).

## Policy

Antigravity's response contract differs from Claude Code's in one important
way: emitting `"allow"` **auto-grants** the tool call, bypassing the normal
permission flow. This adapter therefore has only two outputs:

| Mneme outcome | Adapter output |
|---|---|
| Trusted PASS / SKIP | `{}` — no opinion; Antigravity's own permission flow stays in charge |
| Trusted WARN/FAIL, strict mode | `{"decision": "deny", "reason": <violation report>}` |
| Trusted WARN/FAIL, warn mode | `{}`; violation report on stderr (never blocks) |
| Unparseable verdict / operational failure / incomplete evaluation | `{}` (fail open), reason on stderr |

Every code path writes exactly one JSON object to stdout: Antigravity fails
**closed** on hook output it cannot parse, so the adapter must always emit
well-formed JSON even when it has no opinion.

## What this integration is not

- Not a second enforcement implementation. If `mneme check` changes,
  this adapter follows automatically.
- Not a guidance surface. No DecisionRetriever dependency, no context
  injection; retrieval remains a separate layer.
- Not a provider framework or generic hook abstraction.

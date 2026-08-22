# Claude Code UserPromptSubmit Guidance Hook Spec

## Purpose

The guidance hook retrieves relevant architectural decisions from the current
submitted task and adds a compact context packet before Claude processes that
task. It guides generation; it does not allow, reject, or rewrite prompts.

The independent `PreToolUse` hook remains the deterministic write gate.

## Input

The command reads one Claude Code `UserPromptSubmit` JSON envelope from stdin.
The required fields are:

```json
{
  "hook_event_name": "UserPromptSubmit",
  "cwd": "/path/to/project",
  "prompt": "Add persistence for user sessions."
}
```

Only `prompt` from the current event is used for retrieval. Transcript paths and
conversation history are deliberately ignored.

## Output

When confident decisions fit within the budget, stdout contains one JSON object:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "[Mneme architectural guidance]\n..."
  }
}
```

When guidance is disabled, the task is low-signal/unrelated, memory is missing,
or any operational error occurs, stdout is empty and the process exits 0.
Operational errors may be reported on stderr.

## Selection and formatting

- Retrieval is local, lexical, deterministic, and limited to three decisions.
- A candidate score must be greater than the guidance threshold and supported
  by a structured field; rationale-only overlap is rejected.
- The context budget is 8,000 characters.
- Full rationales are omitted to keep guidance compact.
- Typed `FORBID_LITERAL` rules identify their values as forbidden exact
  literals. Their selectors remain descriptive: scoped rules say `Applies when
  editing`; only the edit-time gate can decide `APPLIED` or `EXCLUDED` after a
  target path is known.

## Configuration

Guidance is opt-in. Configuration precedence is:

1. `MNEME_GUIDANCE`
2. `CLAUDE_PLUGIN_OPTION_GUIDANCE`
3. disabled

Accepted true values are `1`, `true`, `yes`, and `on`, case-insensitively.
Unknown values are disabled.

## Runtime contract

The plugin invokes the console script in exec form with a 5-second hard timeout:

```json
{
  "type": "command",
  "command": "mneme-guidance-hook",
  "args": [],
  "timeout": 5
}
```

The adapter makes no model, network, embedding, subprocess, or vector-database
call. Its error policy is fail-open because prompt guidance is advisory.

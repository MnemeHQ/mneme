# Mneme for the Claude Agent SDK

Architectural governance for applications built on the
[Claude Agent SDK (Python)](https://docs.claude.com/en/api/agent-sdk/python).
The same retrieval and enforcement semantics that power the Claude Code
hook, exposed as SDK lifecycle hooks your application controls.

---

## Architecture

The adapter (`mneme/integrations/agent_sdk/adapter.py`) is a thin
translation layer. It implements no governance semantics of its own:

```text
UserPromptSubmit
    -> MemoryStore + DecisionRetriever + format_decisions   (existing)
    -> additionalContext

PreToolUse (Write | Edit | MultiEdit)
    -> ToolEvent translation
    -> introduced-content materialization + `mneme check`   (existing)
    -> allow / deny + Mneme's reason
```

Materialization, introduced-delta selection (ADR-018), memory discovery,
mode resolution, verdict parsing, and reason formatting are imported from
the existing Claude Code hook module. The adapter only maps between SDK
event shapes and that behavior.

## Usage

```python
import asyncio
from claude_agent_sdk import ClaudeAgentOptions, query
from mneme.integrations.agent_sdk import MnemeAgentSdk

mneme = MnemeAgentSdk(project_dir=".")

async def main():
    options = ClaudeAgentOptions(
        cwd=".",
        hooks=mneme.hooks(),
        permission_mode="acceptEdits",
    )
    async for message in query(prompt="Implement feature X", options=options):
        ...

asyncio.run(main())
```

`MnemeAgentSdk` requires `claude_agent_sdk` only inside `hooks()`; the
core callbacks (`context_for_task`, `evaluate_mutation`, `pre_tool_use`,
`user_prompt_submit`) are plain Python and can be tested without the SDK.

Constructor options:

| Option | Meaning |
|--------|---------|
| `project_dir` | Directory used to discover `.mneme/project_memory.json` |
| `memory` | Explicit memory path override |
| `mode` | `"strict"` or `"warn"`; falls back to `MNEME_HOOK_MODE`, then `strict` |
| `check_runner` | Test seam replacing the `mneme check` subprocess |

## Policy

| Mneme outcome | strict mode | warn mode |
|---|---|---|
| Trusted PASS | no opinion (normal permission flow) | no opinion |
| Trusted WARN/FAIL | **deny** with the violation report | warning injected as context, never blocked |
| Unparseable verdict / operational failure / incomplete evaluation | fail open — **visibly**: reason injected as `additionalContext` | same |

An unevaluated mutation is never silently reported as governed: every
fail-open path injects its reason into the agent's context.

## Trace

Every context injection and enforcement event is recorded on
`mneme.trace` with a `kind` field (`context_injection` or
`enforcement`), so an embedding application can audit exactly which
decisions were injected before work and which proposed mutations were
checked, allowed, denied, or unevaluated.

## What this integration is not

- Not a second enforcement implementation. If `mneme check` changes,
  this adapter follows automatically.
- Not a provider framework. There is no registry, event bus, or
  multi-provider abstraction; a second SDK integration would be added
  only when a concrete need exists.
- Not a benchmark surface. Frozen retrieval, enforcement, and benchmark
  semantics are untouched.

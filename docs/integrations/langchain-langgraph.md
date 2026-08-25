# Mneme for LangChain agents on LangGraph

Architectural governance for applications built on
[LangChain agents](https://docs.langchain.com/oss/python/langchain/agents)
running on [LangGraph](https://docs.langchain.com/oss/python/langgraph/).
The same retrieval and enforcement semantics that power the Claude Code
hook, exposed as agent middleware your application controls.

> **Naming matters:** this integration targets **LangChain's agent
> middleware API** (`wrap_tool_call`, `wrap_model_call`). It does NOT make
> arbitrary raw `StateGraph` graphs governed: applications that wire their
> own execution nodes and `ToolNode`s can bypass any middleware. A compiled,
> middleware-equipped agent remains governed when embedded as a node/subgraph
> in a larger graph (proven below), but Mneme claims no opinion over nodes it
> cannot intercept.

---

## Architecture

The adapter (`mneme/integrations/langchain/adapter.py`) is a thin
translation layer. It implements no governance semantics of its own — the
gate is delegated to the Claude Agent SDK adapter, which imports the frozen
pieces from the Claude Code hook module:

```text
wrap_model_call
    -> MemoryStore + DecisionRetriever + format_decisions   (existing)
    -> decision context appended to the system message

wrap_tool_call (write_file | edit_file)
    -> canonical Write/Edit translation (closed tool map)
    -> introduced-content materialization + `mneme check`   (existing)
    -> allow / deny / warn / visibly UNEVALUATED
```

Materialization, introduced-delta selection (ADR-018), path applicability
(ADR-020), memory discovery, mode resolution, verdict parsing, and reason
formatting are all existing core behavior. The adapter only maps between
LangChain middleware shapes and that behavior.

## Scope

Governed tools are exactly:

| LangChain tool | Canonical | Notes |
|----------------|-----------|-------|
| `write_file(file_path, content)` | `Write` | full proposed content checked |
| `edit_file(file_path, old_string, new_string)` | `Edit` | only introduced delta checked |

Classification is by the **documented local-file argument contract**: any
registered tool whose *name* is `write_file` or `edit_file` is translated
and governed as if it writes the local filesystem at `file_path`. The bound
tool/backend behind that name is not inspected. This means:

- Tools conforming to the local-file contract (including a LangChain or
  Deep Agents `FilesystemBackend` deployment) are governed.
- The same tool names served over a virtual store, composite backend, or
  remote sandbox are still *intercepted*, but Mneme's local-path semantics
  (memory discovery, `--target-path` applicability) may not describe the
  actual mutation target there. That gap is why Deep Agents over
  non-filesystem backends remains unvalidated.

Everything else — read-only tools (`read_file`, `ls`, `glob`, `grep`),
custom tools, shell/`execute` surfaces — receives **no opinion and zero
checker invocations**. The tool map is deliberately closed; extending it is
the only way a new tool becomes governed.

Out of scope for this milestone: shell/`execute` governance (ADR-021's
prevent-catch-verify design does not yet generalize to remote/virtual
backends), arbitrary custom-tool mapping, raw `StateGraph`
instrumentation, and pinned Deep Agents validation (the roadmap POC stays
open until that validation passes).

## Usage

```python
from langchain.agents import create_agent
from mneme.integrations.langchain import MnemeLangChain

mneme = MnemeLangChain(project_dir=".")

agent = create_agent(
    model=model,                      # any LangChain chat model
    tools=[write_file, edit_file],    # local-file contract tools
    middleware=mneme.build_middleware(),
)

result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
```

Install with the extra: `pip install "mneme-hq[langchain]"`.
`langchain`/`langgraph` are imported only inside `build_middleware()`; the
core adapter surface is plain Python.

Constructor options:

| Option | Meaning |
|--------|---------|
| `project_dir` | Directory used to discover `.mneme/project_memory.json` and resolve relative tool paths |
| `memory` | Explicit memory path override |
| `mode` | `"strict"` or `"warn"`; falls back to `MNEME_HOOK_MODE`, then `strict` |
| `check_runner` | Test seam replacing the `mneme check` subprocess |

Sync and async loops behave identically: `invoke` uses `wrap_tool_call`,
`ainvoke` uses `awrap_tool_call`, with the same policy applied.

## Policy

| Mneme outcome | Behavior |
|---|---|
| Trusted PASS | tool handler executes normally |
| Trusted WARN/FAIL, strict mode | handler is **not called**; rejection feedback returned to the model as the tool result |
| Trusted WARN/FAIL, warn mode | handler executes; visible `[mneme] WARN ... not blocked` note carried on the tool result |
| Unparseable verdict / operational failure / incomplete evaluation | fail open — visibly: `[mneme] UNEVALUATED ... NOT checked` note carried on the tool result |
| Unlisted / read-only tool | no opinion; zero checker calls |

The visibility guarantee holds for both allowed handler return types:
plain `ToolMessage` results are annotated in place, and `Command` results
carry the note on their tool-result message while preserving update/goto
semantics. If a `Command`'s update shape carries no recognizable
`ToolMessage`, the command passes through unchanged and the gap is recorded
on `mneme.trace` — never silently.

An unevaluated mutation is never silently reported as governed: every
fail-open path is visible in the tool result that returns to the model.

## Embedded graphs

A governed agent stays governed when embedded in a larger graph via
`graph.add_node("governed_agent", <compiled agent>)`. This composition was
proven empirically; see the capability matrix below.

## Validation evidence

Capability probe (M0) and live fixture results, pinned to exact package
versions:

- [`validation/langgraph/capability-matrix.md`](../../validation/langgraph/capability-matrix.md)
- Pinned versions: langchain 1.3.17 / langchain-core 1.6.0 / langgraph 1.2.11

## Trace

Every context injection and enforcement event is recorded on
`mneme.trace` (including SKIP decisions for unmapped tools), so an
embedding application can audit exactly which proposals were evaluated,
with what verdicts.

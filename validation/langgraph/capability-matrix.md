# LangChain/LangGraph agent-middleware capability matrix (M0)

Filled **only** from captured evidence under `evidence/runs/`. Every cell
cites a run artifact. Doc-derived claims do not belong here.

Valid for the exact pin in [`pinned-build.json`](pinned-build.json)
(langchain 1.3.17 / langchain-core 1.6.0 / langgraph 1.2.11,
Python 3.12.10, Windows 11).

## Gate checks

| # | Capability | Result | Evidence |
|---|------------|--------|----------|
| C1 | `wrap_tool_call` fires before actual tool execution | YES — passthrough arm records `mw_enter` strictly before `tool_exec`; tool then executes exactly once | run `20260825T162444Z-m0`, S1/C1 |
| C2 | Not calling `handler` prevents execution | YES — deny arm: 0 executions, sandbox manifest byte-identical before/after | same run, S2/C2 (`before`==`after`==`{}`) |
| C3 | Sync + async equivalence | YES — `awrap_tool_call` + `ainvoke`: 0 executions, identical rejection text delivered to model; async passthrough contrast arm executes exactly once | same run, S4/C3a+C3b |
| C4 | `ToolCallRequest` exposes name, args, state, runtime | YES — `tool_call={name, args, id}` with full proposed args; bound tool visible (`StructuredTool`); `state` = dict incl. messages; `runtime` = `ToolRuntime` (non-None) | same run, S2/C4 (sync), S4/C4a (async) |
| C5 | Later middleware cannot execute a denied call | YES — `[outer-deny, inner-recorder]`: inner middleware never entered, 0 executions | same run, S3/C5 |
| C6 | Denied call returns feedback to model without executing | YES — second model input contains `ToolMessage` with full `[mneme] DENIED …` reason; agent loop then completes normally | same run, S2/C6 + S2/C7-loop |
| C7 | Governance survives embedding as LangGraph subgraph/node | YES — direct `StateGraph.add_node("governed_agent", <compiled agent>)`; no fallback needed; deny fired inside nested invocation, parent transcript contains the `ToolMessage` rejection | same run, S5/C7 (`embedding_mode: direct-add-node`) |

## Beyond-gate observations

| # | Capability | Result | Evidence |
|---|------------|--------|----------|
| C8 | `wrap_model_call` injects decision context into the model request | YES — merged `SystemMessage` carrying injected decision text observed in every subsequent model call input | run `20260825T162444Z-m0`, S6/C8 |

## Scope caveats (recorded, not gating)

- Scripted offline model; a live-provider loop was not exercised. The
  intercepted surface is the agent/middleware layer, which sits between the
  model and tools regardless of provider.
- One mutating tool schema probed (`write_file(file_path, content)`).
  `edit_file(file_path, old_string, new_string)` translation is M1 work and
  unprobed.
- Middleware ordering verified empirically for tool-call wrapping only
  (first-listed = outermost, matching the documented contract).
- Windows-only evidence so far; no Linux/macOS run.

## Invalidated runs

| Run | Reason |
|-----|--------|
| `20260825T162423Z-m0` | probe bug: `AIMessage(tool_calls=None)` rejected by pydantic before any scenario ran; zero observations produced. Kept under `_invalidated/`. |

## M0 gate

> **M0 gate: MET — reproducible on langchain 1.3.17 / langgraph 1.2.11 /
> Python 3.12.10 / Windows 11.**
>
> All seven gate checks passed in a single deterministic run with a fully
> offline scripted model. No scenario errors in the valid run. This clears
> the path to M1: adapter + `write_file`/`edit_file` deterministic
> enforcement, reusing existing Mneme semantics unchanged.

# LangGraph/LangChain agent-middleware capability probe (R0/M0)

Question: on a pinned langchain/langgraph install, can LangChain **agent
middleware** host Mneme's pre-execution tool governance — and does it keep
working when the governed agent is embedded inside a larger LangGraph graph?

This is M0 of the LangChain integration plan. It produces evidence and a
capability matrix. It does **not** produce production code
(`mneme/integrations/langchain/` must not exist until the gate passes).

## Status

- Phase: M0 — capability probe first, nothing else yet
- Pinned packages: **langchain 1.3.17 / langchain-core 1.6.0 /
  langgraph 1.2.11** — exact set in `pinned-build.json`
- Platform: Windows 11 / Python 3.12.10
- Model: fully scripted offline chat model (`probe/probe_m0.py`);
  no network access, no provider keys. The surface under test is the
  agent/middleware layer, which is model-independent.

## The seven facts this phase must establish

1. `wrap_tool_call` runs **before** actual tool execution.
2. Not calling its `handler` genuinely prevents execution.
3. Sync + async variants behave equivalently
   (`invoke`/`wrap_tool_call` vs `ainvoke`/`awrap_tool_call`).
4. `ToolCallRequest` exposes tool name, arguments, state and runtime.
5. Middleware ordering cannot let an inner middleware execute a call an
   outer middleware denied without calling its handler.
6. A denied tool call returns useful feedback to the model without
   executing the mutation.
7. Middleware continues to work when the compiled agent is embedded as a
   node/subgraph in a larger LangGraph graph.

Plus one beyond-gate check de-risking M1 retrieval:

8. `wrap_model_call` can inject additional decision context into the model
   request (candidate carrier for `MemoryStore → DecisionRetriever →
   format_decisions` output).

## Non-goals (M0)

- No Mneme production integration. No adapter code outside this directory.
- No retrieval, applicability, conflict, or enforcement semantics — none of
  `DecisionRetriever`, `ConflictDetector`, `enforcer`, or benchmark fixtures
  may change on this branch.
- No `write_file`/`edit_file` argument translation design (M1 input).
- No shell/`execute` governance (M2), no raw `StateGraph` support (deferred).
- No virtual/remote backend coverage; Layer 1 stays local-repo scoped.

## Gate to enter M1

All seven checks must hold reproducibly on the pinned versions:

1. Interception happens pre-execution.
2. Handler skip blocks mutation.
3. Sync/async equivalence.
4. Request introspection sufficient to translate args → canonical
   `ToolEvent` inputs.
5. Ordering safety.
6. Denied-call feedback reaches the model.
7. Governance survives subgraph embedding.

Partial outcomes go in `capability-matrix.md` with evidence links.

## Layout

| Path | Purpose |
|---|---|
| `README.md` | This file |
| `capability-matrix.md` | Matrix, filled only from captured evidence |
| `pinned-build.json` | Exact package pin for all runs |
| `probe/probe_m0.py` | Deterministic probe runner (all scenarios) |
| `evidence/runs/<run-id>-m0/` | Raw immutable run artifacts |

## Evidence rules

1. Everything under `evidence/` is **append-only once captured**. Never edit
   or delete a captured artifact. Corrections happen in new files.
2. Each run gets `<utcstamp>-m0/` containing:
   - `report.json` — env (python/platform/full pip freeze), per-scenario
     checks with evidence payloads, event sequences, sandbox manifests
   - `transcript.txt` — human-readable PASS/FAIL summary
   - `MANIFEST.sha256` — written last; later drift invalidates the run
3. Invalid runs are kept under `evidence/runs/_invalidated/` with an
   `INVALIDATION.md` reason file.
4. Doc-derived claims never count as observations; every matrix cell cites a
   captured artifact or stays empty.

## Reproduce

```
<venv-python> validation/langgraph/probe/probe_m0.py
```

Requires: Python 3.12+, `pip install langchain langgraph` at the pinned
versions (see `pinned-build.json`). No API keys.

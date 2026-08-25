#!/usr/bin/env python3
"""M0 capability probe: LangChain agent middleware on LangGraph (R0).

Question: on pinned langchain/langgraph versions, can LangChain agent
middleware host Mneme's pre-execution tool governance?

Checks:

    C1  wrap_tool_call runs before actual tool execution.
    C2  Not calling handler genuinely prevents execution.
    C3  Sync and async variants behave equivalently.
    C4  ToolCallRequest exposes tool name, arguments, state and runtime.
    C5  Middleware ordering: an inner middleware cannot execute a call an
        outer middleware denied (outer denies => inner never runs).
    C6  A denied tool call returns useful feedback to the model without
        executing the mutation.
    C7  Middleware still fires when the compiled agent is embedded as a
        node/subgraph in a larger LangGraph graph.
    C8  (beyond gate) wrap_model_call can inject additional context into
        the model request -- de-risks the M1 decision-retrieval path.

This is R0 evidence gathering. It produces no Mneme production code and
no network traffic: the chat model is fully scripted.

Usage::

    python validation/langgraph/probe/probe_m0.py

Writes one append-only run directory under ../evidence/runs/<run-id>-m0/
containing report.json, transcript.txt and MANIFEST.sha256.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8")

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

PROBE_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = PROBE_ROOT / "evidence" / "runs"

REASON_DENY = (
    "[mneme] DENIED - write_file violates decision 'rule-public-boundary': "
    "internal tooling must not be committed to this public repo."
)
REASON_CONTEXT = (
    "[mneme] DECISIONS - rule-public-boundary: internal tooling stays out "
    "of this public repo."
)


# ── Scripted model ──────────────────────────────────────────────────────────


class ScriptedChatModel(BaseChatModel):
    """Deterministic offline stand-in for a real chat model."""

    responses: List[Dict[str, Any]] = []
    index: int = 0

    def __init__(self, responses: List[Dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(responses=list(responses), **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._record_calls.append([m for m in messages])
        spec = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        msg = AIMessage(
            content=spec.get("content", ""), tool_calls=spec.get("tool_calls") or []
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _record_calls(self) -> List[List[BaseMessage]]:
        if not hasattr(self, "_calls_store"):
            self._calls_store: List[List[BaseMessage]] = []
        return self._calls_store

    @property
    def calls(self) -> List[List[BaseMessage]]:
        return self._record_calls


def tool_call_msg(name: str, args: Dict[str, Any], call_id: str) -> Dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    }


# ── Sandbox tool ────────────────────────────────────────────────────────────


def make_write_file(sandbox: Path, events: List[Dict[str, Any]]):
    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file inside the probe sandbox directory."""
        target = sandbox / file_path
        events.append({"kind": "tool_exec", "tool": "write_file", "path": str(target)})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {file_path}"

    return write_file


def sandbox_manifest(sandbox: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not sandbox.exists():
        return out
    for p in sorted(sandbox.rglob("*")):
        if p.is_file():
            rel = p.relative_to(sandbox).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ── Middlewares ─────────────────────────────────────────────────────────────


def make_passthrough_mw(events: List[Dict[str, Any]], label: str):
    class PassthroughMW(AgentMiddleware):
        def wrap_tool_call(self, request, handler):
            events.append(
                {"kind": "mw_enter", "mw": label, "call": request.tool_call["name"]}
            )
            return handler(request)

    return PassthroughMW()


def make_deny_mw(events: List[Dict[str, Any]], introspection: List[Dict[str, Any]]):
    class DenyMW(AgentMiddleware):
        def wrap_tool_call(self, request, handler):
            events.append(
                {"kind": "mw_enter", "mw": "deny", "call": request.tool_call["name"]}
            )
            if request.tool_call["name"] == "write_file":
                introspection.append(capture_request(request))
                events.append({"kind": "denied_at_mw", "mw": "deny"})
                return ToolMessage(
                    content=REASON_DENY, tool_call_id=request.tool_call["id"]
                )
            return handler(request)

    return DenyMW()


def make_recorder_mw(events: List[Dict[str, Any]]):
    class RecorderMW(AgentMiddleware):
        def wrap_tool_call(self, request, handler):
            events.append(
                {"kind": "mw_enter", "mw": "recorder-inner", "call": request.tool_call["name"]}
            )
            return handler(request)

    return RecorderMW()


def make_async_deny_mw(events: List[Dict[str, Any]], introspection: List[Dict[str, Any]]):
    class AsyncDenyMW(AgentMiddleware):
        async def awrap_tool_call(self, request, handler):
            events.append(
                {"kind": "mw_enter", "mw": "async-deny", "call": request.tool_call["name"]}
            )
            if request.tool_call["name"] == "write_file":
                introspection.append(capture_request(request))
                events.append({"kind": "denied_at_mw", "mw": "async-deny"})
                return ToolMessage(
                    content=REASON_DENY, tool_call_id=request.tool_call["id"]
                )
            return await handler(request)

    return AsyncDenyMW()


def make_async_passthrough_mw(events: List[Dict[str, Any]]):
    class AsyncPassthroughMW(AgentMiddleware):
        async def awrap_tool_call(self, request, handler):
            events.append(
                {"kind": "mw_enter", "mw": "async-passthrough", "call": request.tool_call["name"]}
            )
            return await handler(request)

    return AsyncPassthroughMW()


def make_decision_context_mw():
    class DecisionContextMW(AgentMiddleware):
        def wrap_model_call(self, request, handler):
            base = ""
            if request.system_message is not None and request.system_message.content:
                base = request.system_message.content + "\n"
            merged = SystemMessage(content=base + REASON_CONTEXT)
            rebuilt = type(request)(
                model=request.model,
                messages=request.messages,
                system_message=merged,
                tools=request.tools,
                tool_choice=request.tool_choice,
                response_format=request.response_format,
                state=request.state,
                runtime=request.runtime,
            )
            return handler(rebuilt)

    return DecisionContextMW()


def capture_request(request: Any) -> Dict[str, Any]:
    state = request.state
    runtime = request.runtime
    state_messages = None
    try:
        msgs = state.get("messages") if isinstance(state, dict) else getattr(state, "messages", None)
        state_messages = len(msgs) if msgs is not None else None
    except Exception:
        state_messages = None
    return {
        "tool_call": dict(request.tool_call),
        "tool_bound": type(request.tool).__name__ if request.tool is not None else None,
        "state_type": type(state).__name__,
        "state_message_count": state_messages,
        "runtime_type": type(runtime).__name__ if runtime is not None else None,
        "runtime_is_none": runtime is None,
    }


# ── Scenario plumbing ───────────────────────────────────────────────────────


class Check:
    def __init__(self, cid: str, desc: str, passed: bool, evidence: Any) -> None:
        self.id = cid
        self.desc = desc
        self.passed = bool(passed)
        self.evidence = evidence

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.desc,
            "passed": self.passed,
            "evidence": self.evidence,
        }


def fresh_env(tmp_parent: Path, tag: str):
    sandbox = tmp_parent / tag
    sandbox.mkdir(parents=True, exist_ok=False)
    events: List[Dict[str, Any]] = []
    introspection: List[Dict[str, Any]] = []
    return sandbox, events, introspection


PROPOSAL = {
    "file_path": "scripts/slack_outreach.py",
    "content": "# internal outreach automation\nimport slack_sdk\n",
}


def run_sync_agent(model_responses, sandbox, events, middlewares):
    model = ScriptedChatModel(model_responses)
    agent = create_agent(
        model=model,
        tools=[make_write_file(sandbox, events)],
        middleware=list(middlewares),
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content="add an outreach script please")]},
        config={"recursion_limit": 25},
    )
    return model, result


async def run_async_agent(model_responses, sandbox, events, middlewares):
    model = ScriptedChatModel(model_responses)
    agent = create_agent(
        model=model,
        tools=[make_write_file(sandbox, events)],
        middleware=list(middlewares),
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="add an outreach script please")]},
        config={"recursion_limit": 25},
    )
    return model, result


def tool_message_contents(messages: List[Any]) -> List[str]:
    out = []
    for m in messages:
        if isinstance(m, ToolMessage):
            c = m.content
            out.append(c if isinstance(c, str) else json.dumps(c))
    return out


# ── Scenarios ───────────────────────────────────────────────────────────────


def scenario_s1_passthrough(tmp: Path) -> Dict[str, Any]:
    sandbox, events, _ = fresh_env(tmp, "s1")
    before = sandbox_manifest(sandbox)
    model, result = run_sync_agent(
        [tool_call_msg("write_file", PROPOSAL, "call_s1"), {"content": "done"}],
        sandbox,
        events,
        [make_passthrough_mw(events, "passthrough")],
    )
    after = sandbox_manifest(sandbox)
    kinds = [e["kind"] for e in events]
    enter_idx = kinds.index("mw_enter") if "mw_enter" in kinds else -1
    exec_idx = kinds.index("tool_exec") if "tool_exec" in kinds else -1
    c1 = Check(
        "C1",
        "wrap_tool_call runs before tool execution",
        enter_idx != -1 and exec_idx != -1 and enter_idx < exec_idx,
        {"event_kinds": kinds, "mw_enter_index": enter_idx, "tool_exec_index": exec_idx},
    )
    exec_count = kinds.count("tool_exec")
    wrote_expected = after.get("scripts/slack_outreach.py") is not None
    c_handler = Check(
        "C2a",
        "calling handler executes the tool exactly once (contrast arm)",
        exec_count == 1 and wrote_expected,
        {"exec_count": exec_count, "before": before, "after": after},
    )
    return {
        "id": "S1",
        "name": "passthrough allow-path (sync)",
        "checks": [c1.as_dict(), c_handler.as_dict()],
        "events": events,
    }


def scenario_s2_deny_sync(tmp: Path) -> Dict[str, Any]:
    sandbox, events, intro = fresh_env(tmp, "s2")
    before = sandbox_manifest(sandbox)
    model, result = run_sync_agent(
        [tool_call_msg("write_file", PROPOSAL, "call_s2"), {"content": "done"}],
        sandbox,
        events,
        [make_deny_mw(events, intro)],
    )
    after = sandbox_manifest(sandbox)
    kinds = [e["kind"] for e in events]

    c2 = Check(
        "C2",
        "not calling handler prevents execution (sync deny)",
        kinds.count("tool_exec") == 0 and after == before,
        {"exec_count": kinds.count("tool_exec"), "before": before, "after": after},
    )

    second_input = model.calls[1] if len(model.calls) > 1 else []
    tm_texts = tool_message_contents(second_input)
    c6 = Check(
        "C6",
        "denied call returns rejection feedback to the model without executing",
        any(REASON_DENY[:40] in t for t in tm_texts),
        {"second_model_input_tool_messages": tm_texts},
    )

    c4 = Check(
        "C4",
        "ToolCallRequest exposes name, args, state, runtime (sync)",
        bool(intro)
        and intro[0]["tool_call"]["name"] == "write_file"
        and intro[0]["tool_call"]["args"].get("file_path") == PROPOSAL["file_path"]
        and intro[0]["state_message_count"] is not None
        and not intro[0]["runtime_is_none"],
        {"captured": intro},
    )

    final_msgs = [
        m
        for m in result["messages"]
        if isinstance(m, AIMessage) and m.content == "done"
    ]
    c_loop = Check(
        "C7-loop",
        "agent loop completes normally after denial (sync)",
        len(final_msgs) >= 1,
        {"final_message_present": len(final_msgs) >= 1},
    )

    return {
        "id": "S2",
        "name": "deny short-circuit (sync)",
        "checks": [c2.as_dict(), c4.as_dict(), c6.as_dict(), c_loop.as_dict()],
        "events": events,
    }


def scenario_s3_ordering(tmp: Path) -> Dict[str, Any]:
    sandbox, events, intro = fresh_env(tmp, "s3")
    before = sandbox_manifest(sandbox)
    run_sync_agent(
        [tool_call_msg("write_file", PROPOSAL, "call_s3"), {"content": "done"}],
        sandbox,
        events,
        [make_deny_mw(events, intro), make_recorder_mw(events)],
    )
    after = sandbox_manifest(sandbox)
    enters_inner = [e for e in events if e.get("mw") == "recorder-inner"]
    exec_count = [e for e in events if e["kind"] == "tool_exec"]
    denied_outer = any(e.get("kind") == "denied_at_mw" for e in events)
    c5 = Check(
        "C5",
        "later middleware cannot execute a call the outer middleware denied",
        len(enters_inner) == 0 and len(exec_count) == 0 and denied_outer,
        {
            "inner_mw_entries": len(enters_inner),
            "exec_count": len(exec_count),
            "denied_outer": denied_outer,
            "before": before,
            "after": after,
        },
    )
    return {
        "id": "S3",
        "name": "middleware ordering: outer deny silences inner",
        "checks": [c5.as_dict()],
        "events": events,
    }


def scenario_s4_async(tmp: Path) -> Dict[str, Any]:
    sandbox_deny, events_deny, intro_deny = fresh_env(tmp, "s4-deny")
    before_deny = sandbox_manifest(sandbox_deny)
    model_deny, result_deny = asyncio.run(
        run_async_agent(
            [tool_call_msg("write_file", PROPOSAL, "call_s4"), {"content": "done"}],
            sandbox_deny,
            events_deny,
            [make_async_deny_mw(events_deny, intro_deny)],
        )
    )
    after_deny = sandbox_manifest(sandbox_deny)

    sandbox_allow, events_allow, _ = fresh_env(tmp, "s4-allow")
    _, _ = asyncio.run(
        run_async_agent(
            [tool_call_msg("write_file", PROPOSAL, "call_s4b"), {"content": "done"}],
            sandbox_allow,
            events_allow,
            [make_async_passthrough_mw(events_allow)],
        )
    )

    kinds = [e["kind"] for e in events_deny]
    second_input = model_deny.calls[1] if len(model_deny.calls) > 1 else []
    tm_texts = tool_message_contents(second_input)

    c3_deny = Check(
        "C3a",
        "awrap_tool_call short-circuit matches sync semantics",
        kinds.count("tool_exec") == 0
        and after_deny == before_deny
        and any(REASON_DENY[:40] in t for t in tm_texts),
        {
            "exec_count": kinds.count("tool_exec"),
            "before": before_deny,
            "after": after_deny,
            "second_model_input_tool_messages": tm_texts,
        },
    )
    c4_async = Check(
        "C4a",
        "ToolCallRequest exposes name, args, state, runtime (async)",
        bool(intro_deny)
        and intro_deny[0]["tool_call"]["name"] == "write_file"
        and not intro_deny[0]["runtime_is_none"],
        {"captured": intro_deny},
    )
    allow_exec = [e["kind"] for e in events_allow].count("tool_exec")
    c3_allow = Check(
        "C3b",
        "async passthrough executes exactly once (contrast arm)",
        allow_exec == 1,
        {"exec_count": allow_exec},
    )
    return {
        "id": "S4",
        "name": "async equivalence (ainvoke + awrap_tool_call)",
        "checks": [c3_deny.as_dict(), c4_async.as_dict(), c3_allow.as_dict()],
        "events": events_deny + events_allow,
    }


def scenario_s5_embedded(tmp: Path) -> Dict[str, Any]:
    from langgraph.graph import END, START, MessagesState, StateGraph

    sandbox, events, intro = fresh_env(tmp, "s5")
    before = sandbox_manifest(sandbox)
    model = ScriptedChatModel(
        [tool_call_msg("write_file", PROPOSAL, "call_s5"), {"content": "done"}]
    )
    governed = create_agent(
        model=model,
        tools=[make_write_file(sandbox, events)],
        middleware=[make_deny_mw(events, intro)],
    )

    embedding_mode = None
    parent_result = None
    error_direct = None
    builder = StateGraph(MessagesState)
    builder.add_node("governed_agent", governed)
    builder.add_edge(START, "governed_agent")
    builder.add_edge("governed_agent", END)
    parent = builder.compile()
    try:
        parent_result = parent.invoke(
            {"messages": [HumanMessage(content="add an outreach script please")]},
            config={"recursion_limit": 25},
        )
        embedding_mode = "direct-add-node"
    except Exception as exc:  # noqa: BLE001 - probe records the failure mode
        error_direct = f"{type(exc).__name__}: {exc}"
        builder2 = StateGraph(MessagesState)
        builder2.add_node("governed_agent", lambda state: governed.invoke(state))
        builder2.add_edge(START, "governed_agent")
        builder2.add_edge("governed_agent", END)
        parent = builder2.compile()
        parent_result = parent.invoke(
            {"messages": [HumanMessage(content="add an outreach script please")]},
            config={"recursion_limit": 25},
        )
        embedding_mode = "callable-wrapper-node"

    after = sandbox_manifest(sandbox)
    kinds = [e["kind"] for e in events]
    all_msgs = parent_result["messages"] if parent_result else []

    c7 = Check(
        "C7",
        "middleware fires when governed agent is embedded in a larger graph",
        kinds.count("tool_exec") == 0
        and after == before
        and any(e.get("kind") == "denied_at_mw" for e in events)
        and any(isinstance(m, ToolMessage) and REASON_DENY[:40] in str(m.content) for m in all_msgs),
        {
            "embedding_mode": embedding_mode,
            "direct_add_node_error": error_direct,
            "exec_count": kinds.count("tool_exec"),
            "before": before,
            "after": after,
            "parent_message_types": [type(m).__name__ for m in all_msgs],
        },
    )
    return {
        "id": "S5",
        "name": "compiled agent embedded as LangGraph subgraph/node",
        "checks": [c7.as_dict()],
        "events": events,
    }


def scenario_s6_model_context(tmp: Path) -> Dict[str, Any]:
    sandbox, events, _ = fresh_env(tmp, "s6")
    model = ScriptedChatModel(
        [tool_call_msg("write_file", PROPOSAL, "call_s6"), {"content": "done"}]
    )
    agent = create_agent(
        model=model,
        tools=[make_write_file(sandbox, events)],
        middleware=[make_decision_context_mw(), make_passthrough_mw(events, "passthrough")],
    )
    agent.invoke(
        {"messages": [HumanMessage(content="add an outreach script please")]},
        config={"recursion_limit": 25},
    )
    seen_system = []
    for call in model.calls:
        for m in call:
            if isinstance(m, SystemMessage):
                seen_system.append(m.content)
    c8 = Check(
        "C8",
        "wrap_model_call injects decision context visible to the model (beyond gate)",
        any(REASON_CONTEXT in s for s in seen_system),
        {"system_messages_seen": seen_system},
    )
    return {
        "id": "S6",
        "name": "decision-context injection via wrap_model_call",
        "checks": [c8.as_dict()],
        "events": events,
    }


# ── Runner ──────────────────────────────────────────────────────────────────


def collect_env() -> Dict[str, Any]:
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    packages = {}
    for line in freeze.splitlines():
        if "==" in line:
            name, ver = line.split("==", 1)
            packages[name.strip()] = ver.strip()
    interesting = [
        k
        for k in packages
        if k.startswith(("langchain", "langgraph", "langsmith")) or k == "orjson"
    ]
    return {
        "run_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": sys.executable,
        "packages": {k: packages[k] for k in sorted(interesting)},
        "full_freeze": packages,
    }


def main() -> int:
    env = collect_env()
    run_id = f"{env['run_utc']}-m0"
    run_dir = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    tmp = Path(tempfile.mkdtemp(prefix="mneme-lg-m0-", dir=str(run_dir)))

    scenarios = []
    errors = []
    for fn in (
        scenario_s1_passthrough,
        scenario_s2_deny_sync,
        scenario_s3_ordering,
        scenario_s4_async,
        scenario_s5_embedded,
        scenario_s6_model_context,
    ):
        try:
            scenarios.append(fn(tmp))
        except Exception as exc:  # noqa: BLE001 - probe records failures as evidence
            errors.append(
                {
                    "scenario": fn.__name__,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            scenarios.append(
                {
                    "id": fn.__name__,
                    "name": "SCENARIO ERROR",
                    "checks": [],
                    "events": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    gate_ids = ["C1", "C2", "C3a", "C4", "C5", "C6", "C7"]
    all_checks = [c for s in scenarios for c in s["checks"]]
    gate_checks = [c for c in all_checks if c["id"] in gate_ids]
    gate_passed = bool(gate_checks) and all(c["passed"] for c in gate_checks) and not errors

    report = {
        "run_id": run_id,
        "env": env,
        "gate_check_ids": gate_ids,
        "gate_passed": gate_passed,
        "scenario_errors": errors,
        "scenarios": scenarios,
    }

    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = []
    lines.append(f"M0 capability probe - run {run_id}")
    lines.append(f"python {env['python']} on {env['platform']}")
    lines.append(f"packages: {json.dumps(env['packages'], sort_keys=True)}")
    lines.append("")
    for s in scenarios:
        lines.append(f"[{s['id']}] {s['name']}")
        for c in s["checks"]:
            mark = "PASS" if c["passed"] else "FAIL"
            lines.append(f"  {mark}  {c['id']} - {c['description']}")
            if not c["passed"]:
                lines.append(f"        evidence: {json.dumps(c['evidence'], default=str)[:500]}")
        if s.get("error"):
            lines.append(f"  SCENARIO ERROR: {s['error']}")
        lines.append("")
    lines.append(f"GATE: {'PASS' if gate_passed else 'FAIL'} ({' '.join(gate_ids)})")
    transcript = "\n".join(lines)
    (run_dir / "transcript.txt").write_text(transcript, encoding="utf-8")

    digest_lines = []
    for p in sorted(run_dir.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.sha256" and "__pycache__" not in p.parts:
            rel = p.relative_to(run_dir).as_posix()
            digest_lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
    (run_dir / "MANIFEST.sha256").write_text("\n".join(digest_lines) + "\n", encoding="utf-8")

    print(transcript)
    print(f"evidence: {run_dir}")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())

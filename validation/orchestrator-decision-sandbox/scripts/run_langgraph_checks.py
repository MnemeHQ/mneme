"""Agent / pre-mutation scenarios through the shipped LangChain middleware.

Uses MnemeLangChain + create_agent exactly as documented in
docs/integrations/langchain-langgraph.md, with a scripted offline model.
Also contrasts an embedded governed agent (6A) with raw graph nodes (6B).
No new interception mechanism is built here.
"""

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain.agents import create_agent  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

import oracle  # noqa: E402
from mneme.integrations.langchain import MnemeLangChain  # noqa: E402
from sandbox_lib import (  # noqa: E402
    assert_pinned,
    build_baseline,
    case_by_id,
    sha256_file,
)

TARGET = "src/router.py"
PROMPT = "Update the routing validator in src/router.py."
ACTION_LABEL = {
    "deny": "BLOCKED",
    "allow": "ALLOWED",
    "warn": "WARNED",
    "fail_open": "ERROR_DEGRADED",
    "skip": "NOT_EVALUATED",
}


class ScriptedChatModel(BaseChatModel):
    """Deterministic offline model: replays one tool call per turn, then finishes."""

    responses: list = []
    index: int = 0
    on_turn: Any = None

    def __init__(self, responses, on_turn=None, **kwargs):
        super().__init__(responses=list(responses), on_turn=on_turn, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.on_turn is not None:
            self.on_turn(self.index)
        spec = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        msg = AIMessage(content=spec.get("content", ""), tool_calls=spec.get("tool_calls") or [])
        return ChatResult(generations=[ChatGeneration(message=msg)])


def call(name: str, args: dict, call_id: str) -> dict:
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": call_id, "type": "tool_call"}]}


def write_call(content: str, call_id: str, file_path: str = TARGET) -> dict:
    return call("write_file", {"file_path": file_path, "content": content}, call_id)


def edit_call(old: str, new: str, call_id: str, file_path: str = TARGET) -> dict:
    return call("edit_file", {"file_path": file_path, "old_string": old, "new_string": new}, call_id)


DONE = {"content": "done"}


def make_file_tools(root: Path, executions: list, turn: list):
    """Local-file contract tools. Each execution is stamped with the model turn."""

    def resolve(file_path: str) -> Path:
        p = Path(file_path)
        return p if p.is_absolute() else root / p

    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file."""
        target = resolve(file_path)
        executions.append({"tool": "write_file", "turn": turn[0], "path": file_path})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
        return f"wrote {file_path}"

    @tool
    def edit_file(file_path: str, old_string: str, new_string: str) -> str:
        """Replace old_string with new_string in an existing file."""
        target = resolve(file_path)
        executions.append({"tool": "edit_file", "turn": turn[0], "path": file_path})
        text = target.read_bytes().decode("utf-8")
        if old_string not in text:
            raise ValueError("old_string not found")
        target.write_bytes(text.replace(old_string, new_string, 1).encode("utf-8"))
        return f"edited {file_path}"

    return [write_file, edit_file]


def _text(message) -> str:
    c = message.content
    return c if isinstance(c, str) else json.dumps(c)


def _enforcement(trace) -> list:
    return [
        {k: e.get(k) for k in ("tool", "action", "verdict", "evaluation_complete")}
        for e in trace
        if e.get("kind") == "enforcement"
    ]


def _attempt_rows(script, executions, snapshots, messages, enforcement, governed, watch: Path):
    tool_messages = {m.tool_call_id: _text(m) for m in messages if isinstance(m, ToolMessage)}
    rows = []
    gate_events = iter(enforcement)
    for turn, spec in enumerate(script):
        for tc in spec.get("tool_calls") or []:
            event = next(gate_events, None) if governed else None
            rows.append(
                {
                    "attempt": turn + 1,
                    "tool": tc["name"],
                    "handler_calls": sum(1 for e in executions if e["turn"] == turn),
                    "sha256_before": snapshots.get(turn),
                    "sha256_after": snapshots.get(turn + 1),
                    "mneme_action": event["action"] if event else None,
                    "mneme_verdict": event["verdict"] if event else None,
                    "label": ACTION_LABEL.get(event["action"], "ERROR_DEGRADED") if event else "NOT_EVALUATED",
                    "surface": "middleware_pre_tool" if governed else "none",
                    "tool_message": tool_messages.get(tc["id"], ""),
                }
            )
    return rows


def _harness(root: Path, script: list, governed: bool, watch: Path):
    executions: list = []
    turn = [0]
    snapshots: dict = {}

    def on_turn(index):
        turn[0] = index
        snapshots[index] = sha256_file(watch)

    model = ScriptedChatModel(script, on_turn=on_turn)
    tools = make_file_tools(root, executions, turn)
    gate = MnemeLangChain(project_dir=str(root), mode="strict") if governed else None
    agent = create_agent(model=model, tools=tools, middleware=gate.build_middleware() if gate else [])
    return agent, gate, model, executions, snapshots


def _result(root, script, governed, watch, gate, model, executions, snapshots, messages, extra=None):
    enforcement = _enforcement(gate.trace) if gate else []
    final = watch.read_bytes().decode("utf-8") if watch.is_file() else ""
    final_oracle = oracle.evaluate(final) if watch.suffix == ".py" else None
    out = {
        "governed": governed,
        "attempts": _attempt_rows(script, executions, snapshots, messages, enforcement, governed, watch),
        "final_sha256": sha256_file(watch),
        "final_oracle_accept": final_oracle.accept if final_oracle else None,
        "final_oracle_failures": final_oracle.failures if final_oracle else None,
        "completed": bool(messages) and isinstance(messages[-1], AIMessage) and _text(messages[-1]) == "done",
        "model_turns": model.index,
        "tool_calls_executed": len(executions),
        "trace": enforcement,
    }
    out["task_success"] = bool(out["completed"] and out["final_oracle_accept"])
    if extra:
        out.update(extra)
    return out


def run_agent(root: Path, script: list, governed: bool, watch_path: str = TARGET) -> dict:
    watch = Path(watch_path) if Path(watch_path).is_absolute() else root / watch_path
    agent, gate, model, executions, snapshots = _harness(root, script, governed, watch)
    result = agent.invoke({"messages": [HumanMessage(content=PROMPT)]}, config={"recursion_limit": 25})
    return _result(root, script, governed, watch, gate, model, executions, snapshots, result["messages"])


def run_embedded(root: Path, script: list) -> dict:
    """6A: compiled governed agent embedded as a node in a parent StateGraph."""
    from langgraph.graph import END, START, MessagesState, StateGraph

    watch = root / TARGET
    agent, gate, model, executions, snapshots = _harness(root, script, True, watch)
    builder = StateGraph(MessagesState)
    builder.add_node("governed_agent", agent)
    builder.add_edge(START, "governed_agent")
    builder.add_edge("governed_agent", END)
    parent = builder.compile()
    result = parent.invoke({"messages": [HumanMessage(content=PROMPT)]}, config={"recursion_limit": 25})
    return _result(
        root, script, True, watch, gate, model, executions, snapshots, result["messages"],
        extra={"node": "governed_agent", "embedding_mode": "direct-add-node"},
    )


def run_raw_node(root: Path, content: str, variant: str) -> dict:
    """6B: a raw graph path writes the same file without create_agent middleware.

    A MnemeLangChain gate exists in-process for the same project, but nothing
    routes this path through it. The expected outcome is NOT_EVALUATED.
    """
    from langgraph.graph import END, START, MessagesState, StateGraph

    watch = root / TARGET
    executions: list = []
    gate = MnemeLangChain(project_dir=str(root), mode="strict")
    gate.build_middleware()  # available, deliberately not wired into this graph
    write_file, _ = make_file_tools(root, executions, [0])
    before = sha256_file(watch)
    builder = StateGraph(MessagesState)
    error = None

    if variant == "function_node":

        def raw_writer(state):
            write_file.invoke({"file_path": TARGET, "content": content})
            return {"messages": [AIMessage(content="raw node wrote the file")]}

        builder.add_node("raw_writer", raw_writer)
        node = "raw_writer"
        start = {"messages": [HumanMessage(content=PROMPT)]}
    elif variant == "tool_node":
        from langgraph.prebuilt import ToolNode

        builder.add_node("raw_tools", ToolNode([write_file]))
        node = "raw_tools"
        start = {
            "messages": [
                HumanMessage(content=PROMPT),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "write_file", "args": {"file_path": TARGET, "content": content}, "id": "raw1", "type": "tool_call"}
                    ],
                ),
            ]
        }
    else:
        raise ValueError(variant)

    builder.add_edge(START, node)
    builder.add_edge(node, END)
    try:
        builder.compile().invoke(start, config={"recursion_limit": 10})
    except Exception as e:  # noqa: BLE001 - recorded, never treated as governed
        error = f"{type(e).__name__}: {e}"
    trace = _enforcement(gate.trace)
    return {
        "variant": variant,
        "node": node,
        "handler_calls": len(executions),
        "sha256_before": before,
        "sha256_after": sha256_file(watch),
        "trace_entries": len(gate.trace),
        "trace": trace,
        "label": "ERROR_DEGRADED" if error else ("NOT_EVALUATED" if not gate.trace else "UNEXPECTED_GOVERNED"),
        "surface": "none",
        "error": error,
    }


# ── Scenario set ────────────────────────────────────────────────────────────

BASELINE_FALLBACK_BLOCK = (
    "    try:\n"
    "        return classify(request, ROUTER_DEADLINE_S)\n"
    "    except TimeoutError:\n"
    "        return FALLBACK_ROUTE\n"
)


LITERAL_EDIT = (
    "ROUTER_DEADLINE_S = 5.0\n",
    "DISABLE_ROUTER_TIMEOUT = True\nROUTER_DEADLINE_S = None if DISABLE_ROUTER_TIMEOUT else 5.0\n",
)
FALLBACK_REMOVAL_EDIT = (BASELINE_FALLBACK_BLOCK, "    return classify(request, ROUTER_DEADLINE_S)\n")


def scripts(root: Path) -> dict:
    """Agent scripts. Edit scenarios pass an absolute in-project path (the form
    the live fixture proves); the documented relative form is measured too."""
    a, b = case_by_id("A").content, case_by_id("B").content
    absolute = str(root / TARGET)
    return {
        "governed_b_then_a": [write_call(b, "w1"), write_call(a, "w2"), DONE],
        "direct_a": [write_call(a, "w1"), DONE],
        "edit_introduces_literal": [edit_call(*LITERAL_EDIT, "e1", file_path=absolute), DONE],
        "edit_removes_fallback": [edit_call(*FALLBACK_REMOVAL_EDIT, "e1", file_path=absolute), DONE],
        "edit_relative_path_literal": [edit_call(*LITERAL_EDIT, "e1"), DONE],
    }


def _fresh(prefix: str):
    tmp = tempfile.TemporaryDirectory(prefix=prefix)
    return tmp, build_baseline(Path(tmp.name) / "fixture")


def run_all() -> dict:
    assert_pinned()
    out: dict = {}
    for name, key, governed in (
        ("governed_b_then_a", "governed_b_then_a", True),
        ("unguided_b_then_a", "governed_b_then_a", False),
        ("direct_a_governed", "direct_a", True),
        ("edit_introduces_literal", "edit_introduces_literal", True),
        ("edit_removes_fallback", "edit_removes_fallback", True),
        ("edit_relative_path_literal", "edit_relative_path_literal", True),
    ):
        tmp, base = _fresh(f"ods-agent-{name}-")
        with tmp:
            out[name] = run_agent(base.root, scripts(base.root)[key], governed)
            out[name]["baseline_sha256"] = base.baseline_sha256

    tmp, base = _fresh("ods-agent-outside-")
    with tmp:
        outside = Path(tmp.name) / "outside" / "src" / "router.py"
        script = [write_call(case_by_id("B").content, "o1", file_path=str(outside)), DONE]
        out["write_outside_project_dir"] = run_agent(base.root, script, True, watch_path=str(outside))

    tmp, base = _fresh("ods-graph-6a-")
    with tmp:
        out["embedded_6a"] = run_embedded(base.root, scripts(base.root)["governed_b_then_a"])

    for variant in ("function_node", "tool_node"):
        tmp, base = _fresh(f"ods-graph-6b-{variant}-")
        with tmp:
            out[f"raw_6b_{variant}"] = run_raw_node(base.root, case_by_id("B").content, variant)
    return out


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2, default=str))

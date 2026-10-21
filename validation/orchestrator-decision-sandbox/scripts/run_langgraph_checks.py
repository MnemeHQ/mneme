"""Agent / pre-mutation scenarios through the shipped LangChain middleware.

Uses MnemeLangChain + create_agent exactly as documented in
docs/integrations/langchain-langgraph.md, with a scripted offline model.
Also contrasts an embedded governed agent (6A) with raw graph nodes (6B).
No new interception mechanism is built here.

Supported-path scenarios pass absolute in-project paths (the form the
pinned live fixture proves). Relative paths are measured separately, from
pinned process cwds, because before MnemeHQ/mneme#573 the hook materialized
them against the process cwd; after #573 they resolve against the event cwd
(project_dir on this middleware path).
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
    QUERY,
    BlockerError,
    assert_pinned,
    assert_repo_mneme,
    build_baseline,
    case_by_id,
    pinned_process,
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
EVALUATED_ACTIONS = ("deny", "allow", "warn")


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


def write_call(content: str, call_id: str, file_path: str) -> dict:
    return call("write_file", {"file_path": file_path, "content": content}, call_id)


def edit_call(old: str, new: str, call_id: str, file_path: str) -> dict:
    return call("edit_file", {"file_path": file_path, "old_string": old, "new_string": new}, call_id)


DONE = {"content": "done"}


def make_file_tools(root: Path, executions: list, turn: list):
    """Local-file contract tools plus one unmapped writer.

    Relative paths resolve against the fixture root, as the documented
    contract describes. Each execution is stamped with the model turn.
    """

    def resolve(file_path: str) -> Path:
        p = Path(file_path)
        return p if p.is_absolute() else root / p

    def record(name: str, file_path: str) -> None:
        executions.append({"tool": name, "turn": turn[0], "path": file_path})

    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file."""
        target = resolve(file_path)
        record("write_file", file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
        return f"wrote {file_path}"

    @tool
    def edit_file(file_path: str, old_string: str, new_string: str) -> str:
        """Replace old_string with new_string in an existing file."""
        target = resolve(file_path)
        record("edit_file", file_path)
        text = target.read_bytes().decode("utf-8")
        if old_string not in text:
            raise ValueError("old_string not found")
        target.write_bytes(text.replace(old_string, new_string, 1).encode("utf-8"))
        return f"edited {file_path}"

    @tool
    def save_text(file_path: str, text: str) -> str:
        """Save text to a file (a custom tool outside the governed tool map)."""
        target = resolve(file_path)
        record("save_text", file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        return f"saved {file_path}"

    return [write_file, edit_file, save_text]


def _text(message) -> str:
    c = message.content
    return c if isinstance(c, str) else json.dumps(c)


def _enforcement(trace) -> list:
    return [
        {
            "tool": e.get("tool"),
            "action": e.get("action"),
            "verdict": e.get("verdict"),
            "evaluated": e.get("action") in EVALUATED_ACTIONS,
        }
        for e in trace
        if e.get("kind") == "enforcement"
    ]


def _validate_script(script: list) -> None:
    for spec in script:
        if len(spec.get("tool_calls") or []) > 1:
            raise BlockerError("one tool call per model turn is required for attribution")


def _attempt_rows(script, executions, snapshots, messages, enforcement, governed):
    """One row per scripted tool call, paired with the gate event of its turn.

    Pairing is by order, which is exact because _validate_script allows one
    tool call per turn and the middleware records one event per call.
    """
    tool_messages = {m.tool_call_id: _text(m) for m in messages if isinstance(m, ToolMessage)}
    rows = []
    gate_events = iter(enforcement)
    for turn, spec in enumerate(script):
        for tc in spec.get("tool_calls") or []:
            event = next(gate_events, None) if governed else None
            if not governed:
                label = "NOT_EVALUATED"
            elif event is None:
                label = "ERROR_DEGRADED"
            else:
                label = ACTION_LABEL.get(event["action"], "ERROR_DEGRADED")
            rows.append(
                {
                    "attempt": turn + 1,
                    "tool": tc["name"],
                    "handler_calls": sum(1 for e in executions if e["turn"] == turn),
                    "sha256_before": snapshots.get(turn),
                    "sha256_after": snapshots.get(turn + 1),
                    "mneme_action": event["action"] if event else None,
                    "mneme_verdict": event["verdict"] if event else None,
                    "label": label,
                    "surface": "middleware_pre_tool" if governed else "none",
                    "tool_message": tool_messages.get(tc["id"], ""),
                }
            )
    return rows, len(list(gate_events))


def _harness(root: Path, script: list, governed: bool, watch: Path):
    _validate_script(script)
    executions: list = []
    turn = [0]
    snapshots: dict = {}

    def on_turn(index):
        turn[0] = index
        snapshots[index] = sha256_file(watch)

    model = ScriptedChatModel(script, on_turn=on_turn)
    tools = make_file_tools(root, executions, turn)
    gate = None
    if governed:
        gate = MnemeLangChain(project_dir=str(root), mode="strict")
        _assert_memory(gate, root)
    agent = create_agent(model=model, tools=tools, middleware=gate.build_middleware() if gate else [])
    return agent, gate, model, executions, snapshots


def _assert_memory(gate, root: Path) -> None:
    """Memory authority: the gate must resolve exactly the fixture's memory."""
    expected = (root / ".mneme" / "project_memory.json").resolve()
    seen = gate.context_for_task(QUERY).memory_path
    if seen is None or Path(seen).resolve() != expected:
        raise BlockerError(f"middleware memory is {seen}, expected {expected}")


def _post_run_memory(gate, root: Path) -> None:
    expected = (root / ".mneme" / "project_memory.json").resolve()
    paths = {e.get("memory_path") for e in gate.trace if e.get("kind") == "context_injection"}
    if not paths or any(p is None or Path(p).resolve() != expected for p in paths):
        raise BlockerError(f"context injections used memory {paths}, expected {expected}")


def _result(script, governed, watch, gate, model, executions, snapshots, messages, root, extra=None):
    if gate is not None:
        _post_run_memory(gate, root)
    enforcement = _enforcement(gate.trace) if gate else []
    attempts, unmatched = _attempt_rows(script, executions, snapshots, messages, enforcement, governed)
    final = watch.read_bytes().decode("utf-8") if watch.is_file() else ""
    final_oracle = oracle.evaluate(final) if watch.suffix == ".py" else None
    out = {
        "governed": governed,
        "attempts": attempts,
        "unmatched_enforcement_events": unmatched,
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


def run_agent(root: Path, script: list, governed: bool, watch: Path | None = None) -> dict:
    watch = watch or root / TARGET
    agent, gate, model, executions, snapshots = _harness(root, script, governed, watch)
    result = agent.invoke({"messages": [HumanMessage(content=PROMPT)]}, config={"recursion_limit": 25})
    return _result(script, governed, watch, gate, model, executions, snapshots, result["messages"], root)


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
        script, True, watch, gate, model, executions, snapshots, result["messages"], root,
        extra={"node": "governed_agent", "embedding_mode": "direct-add-node"},
    )


def run_raw_node(root: Path, content: str, variant: str) -> dict:
    """6B: a raw graph path writes the same file without create_agent middleware.

    A MnemeLangChain gate exists in-process for the same project, but nothing
    routes this path through it. This confirms there is no implicit
    interception; the expected outcome is NOT_EVALUATED.
    """
    from langgraph.graph import END, START, MessagesState, StateGraph

    watch = root / TARGET
    target = str(watch)
    executions: list = []
    gate = MnemeLangChain(project_dir=str(root), mode="strict")
    gate.build_middleware()  # available, deliberately not wired into this graph
    write_file = make_file_tools(root, executions, [0])[0]
    before = sha256_file(watch)
    builder = StateGraph(MessagesState)
    error = None

    if variant == "function_node":

        def raw_writer(state):
            write_file.invoke({"file_path": target, "content": content})
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
                        {"name": "write_file", "args": {"file_path": target, "content": content}, "id": "raw1", "type": "tool_call"}
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
    final = watch.read_bytes().decode("utf-8") if watch.is_file() else ""
    end_state = oracle.evaluate(final)
    return {
        "variant": variant,
        "node": node,
        "handler_calls": len(executions),
        "sha256_before": before,
        "sha256_after": sha256_file(watch),
        "final_oracle_accept": end_state.accept,
        "trace_entries": len(gate.trace),
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
    a, b = case_by_id("A").content, case_by_id("B").content
    absolute = str(root / TARGET)
    return {
        "governed_b_then_a": [write_call(b, "w1", absolute), write_call(a, "w2", absolute), DONE],
        "direct_a": [write_call(a, "w1", absolute), DONE],
        "edit_introduces_literal": [edit_call(*LITERAL_EDIT, "e1", absolute), DONE],
        "edit_removes_fallback": [edit_call(*FALLBACK_REMOVAL_EDIT, "e1", absolute), DONE],
        "relative_write_literal": [write_call(b, "r1", TARGET), DONE],
        "relative_edit_literal": [edit_call(*LITERAL_EDIT, "r1", TARGET), DONE],
        "unmapped_tool_literal": [call("save_text", {"file_path": absolute, "text": b}, "u1"), DONE],
    }


# name -> (script key, governed, process cwd: "empty", "decoy" or "partial_decoy")
AGENT_SCENARIOS = {
    "governed_b_then_a": ("governed_b_then_a", True, "empty"),
    "unguided_b_then_a": ("governed_b_then_a", False, "empty"),
    "direct_a_governed": ("direct_a", True, "empty"),
    "edit_introduces_literal": ("edit_introduces_literal", True, "empty"),
    "edit_removes_fallback": ("edit_removes_fallback", True, "empty"),
    "relative_write_literal_empty_cwd": ("relative_write_literal", True, "empty"),
    "relative_write_literal_decoy_cwd": ("relative_write_literal", True, "decoy"),
    "relative_write_literal_partial_decoy_cwd": ("relative_write_literal", True, "partial_decoy"),
    "relative_edit_literal_empty_cwd": ("relative_edit_literal", True, "empty"),
    "unmapped_tool_literal": ("unmapped_tool_literal", True, "empty"),
}


def _fresh(prefix: str):
    tmp = tempfile.TemporaryDirectory(prefix=prefix)
    return tmp, build_baseline(Path(tmp.name) / "fixture")


def run_all() -> dict:
    """Run every agent/graph scenario from a pinned, empty process cwd.

    The "decoy" cwd holds a src/router.py identical to case B, standing in for
    an unrelated checkout the host process happens to run from. The
    "partial_decoy" cwd holds a file that shares B's forbidden lines but
    differs elsewhere (added after #573; pre-fix it produced a trusted PASS
    in an independent reviewer's probe).
    """
    assert_pinned()
    assert_repo_mneme()
    b = case_by_id("B").content
    out: dict = {}
    with tempfile.TemporaryDirectory(prefix="ods-cwd-") as cwd_root:
        empty = Path(cwd_root) / "empty"
        decoy = Path(cwd_root) / "decoy"
        partial = Path(cwd_root) / "partial_decoy"
        empty.mkdir()
        (decoy / "src").mkdir(parents=True)
        (decoy / "src" / "router.py").write_bytes(b.encode("utf-8"))
        (partial / "src").mkdir(parents=True)
        partial_text = b.replace('"""Synthetic routing validator', '"""Unrelated router in another checkout', 1)
        if partial_text == b or "DISABLE_ROUTER_TIMEOUT = True" not in partial_text:
            raise BlockerError("partial decoy must differ from case B while keeping its forbidden lines")
        (partial / "src" / "router.py").write_bytes(partial_text.encode("utf-8"))
        cwds = {"empty": empty, "decoy": decoy, "partial_decoy": partial}

        for name, (key, governed, cwd) in AGENT_SCENARIOS.items():
            tmp, base = _fresh(f"ods-agent-{name}-")
            with tmp, pinned_process(cwds[cwd]):
                out[name] = run_agent(base.root, scripts(base.root)[key], governed)
                out[name]["baseline_sha256"] = base.baseline_sha256
                out[name]["process_cwd"] = cwd

        tmp, base = _fresh("ods-agent-outside-")
        with tmp, pinned_process(empty):
            outside = Path(tmp.name) / "outside" / "src" / "router.py"
            script = [write_call(b, "o1", str(outside)), DONE]
            out["write_outside_project_dir"] = run_agent(base.root, script, True, watch=outside)
            out["write_outside_project_dir"]["process_cwd"] = "empty"

        tmp, base = _fresh("ods-graph-6a-")
        with tmp, pinned_process(empty):
            out["embedded_6a"] = run_embedded(base.root, scripts(base.root)["governed_b_then_a"])

        for variant in ("function_node", "tool_node"):
            tmp, base = _fresh(f"ods-graph-6b-{variant}-")
            with tmp, pinned_process(empty):
                out[f"raw_6b_{variant}"] = run_raw_node(base.root, b, variant)
    return out


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2, default=str))

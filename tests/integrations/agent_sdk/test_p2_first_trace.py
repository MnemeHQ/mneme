"""T-08 P2-first: selection recording in the Agent SDK and LangChain traces.

Charter §5.2.4 item 1 (freeze amendment change 4): the trace keys
``selection_reason``, ``selection_source`` and ``walk`` appear on every trace
record that follows a selection, and on no record written without one.
``GateResult`` and ``ContextInjection`` and every hook output stay unchanged.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from mneme.integrations.agent_sdk import ContextInjection, GateResult, MnemeAgentSdk
from mneme.integrations.langchain import MnemeLangChain
from mneme.integrations.memory_selection import (
    DISCOVERED,
    NO_MEMORY_ON_PATH,
    OVERRIDE_IGNORED,
    OVERRIDE_MISSING,
)
from tests.integrations.check_contract import check_result_for

KEYS = {"selection_reason", "selection_source", "walk"}
MEMORY = {"meta": {"name": "p2-first-trace", "description": "fixture", "version": "0.1.0",
                   "owner": "test", "created": "2026-11-17"},
          "decisions": [{
    "id": "store_001", "decision": "SQLite only", "rationale": "single file",
    "scope": ["storage"], "constraints": ["no postgres"], "anti_patterns": ["psycopg2"],
}]}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE"):
        monkeypatch.delenv(name, raising=False)


def _mem(d: Path) -> Path:
    p = d / ".mneme" / "project_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(MEMORY), encoding="utf-8")
    return p


def _runner(verdict="PASS"):
    return lambda command, **_: check_result_for(command, verdict)


@pytest.fixture
def layout(tmp_path):
    base = tmp_path.resolve()
    project = base / "project"
    mem = _mem(project)
    foreign = _mem(base / "foreign")
    plain = base / "plain"
    plain.mkdir()
    return {"base": base, "project": project, "mem": mem, "foreign": foreign, "plain": plain}


def _write(path: Path):
    return {"file_path": str(path), "content": "x = 1\n"}


def test_gate_record_carries_selection_keys_row2(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    sdk = MnemeAgentSdk(project_dir=layout["project"], check_runner=_runner())
    sdk.evaluate_mutation("Write", _write(layout["project"] / "a.py"))
    rec = sdk.trace[-1]
    assert rec["selection_reason"] == OVERRIDE_IGNORED
    assert rec["selection_source"] == "discovered"
    assert rec["walk"] == "unbounded"


def test_no_memory_record_carries_selection_keys(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["base"] / "nope.json"))
    sdk = MnemeAgentSdk(project_dir=layout["plain"], check_runner=_runner())
    result = sdk.evaluate_mutation("Write", _write(layout["plain"] / "a.py"))
    assert result.reason == "no project memory", "existing reason strings are unchanged"
    rec = sdk.trace[-1]
    assert (rec["selection_reason"], rec["selection_source"]) == (OVERRIDE_MISSING, "none")


def test_record_without_selection_has_no_keys(layout):
    sdk = MnemeAgentSdk(project_dir=layout["project"], check_runner=_runner())
    sdk.evaluate_mutation("Write", _write(layout["project"] / "a.py"))
    sdk.evaluate_mutation("Read", {"file_path": "a.py"})
    assert KEYS <= set(sdk.trace[0])
    assert not KEYS & set(sdk.trace[-1]), "a skip before selection must not inherit stale keys"


def test_context_record_carries_selection_keys(layout):
    sdk = MnemeAgentSdk(project_dir=layout["project"], check_runner=_runner())
    sdk.context_for_task("storage choice")
    assert sdk.trace[-1]["selection_reason"] == DISCOVERED
    sdk2 = MnemeAgentSdk(project_dir=layout["plain"], check_runner=_runner())
    sdk2.context_for_task("storage choice")
    assert sdk2.trace[-1]["selection_reason"] == NO_MEMORY_ON_PATH
    assert sdk2.trace[-1]["outcome"] == "NO_MEMORY"


def test_explicit_memory_record(layout):
    sdk = MnemeAgentSdk(project_dir=layout["plain"], memory=layout["mem"], check_runner=_runner())
    sdk.evaluate_mutation("Write", _write(layout["plain"] / "a.py"))
    rec = sdk.trace[-1]
    assert (rec["selection_source"], rec["selection_reason"], rec["walk"]) == ("explicit", None, None)


def test_result_objects_unchanged():
    assert [f.name for f in dataclasses.fields(GateResult)] == [
        "action", "tool_name", "file_path", "reason", "verdict", "evaluation_complete", "payload"]
    assert [f.name for f in dataclasses.fields(ContextInjection)] == [
        "query", "text", "decision_ids", "memory_path"]


def test_pre_tool_use_output_has_no_selection_field(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    sdk = MnemeAgentSdk(project_dir=layout["project"], check_runner=_runner())
    out = sdk.pre_tool_use({"tool_name": "Write", "tool_input": _write(layout["project"] / "a.py")})
    assert out == {}


def test_langchain_unmapped_skip_has_no_keys(layout):
    gate = MnemeLangChain(project_dir=layout["project"], check_runner=_runner())
    gate.evaluate_tool_call("write_file", {"file_path": "a.py", "content": "x = 1\n"})
    gate.evaluate_tool_call("not_a_tool", {})
    assert KEYS <= set(gate.trace[0])
    assert not KEYS & set(gate.trace[-1])


def test_langchain_annotation_gap_carries_keys(layout, monkeypatch):
    pytest.importorskip("langchain")
    pytest.importorskip("langgraph")
    from langchain.agents.middleware.types import ToolCallRequest
    from langgraph.types import Command

    from tests.integrations.check_contract import violation

    def runner(command, **kwargs):
        return check_result_for(command, "WARN", violations=[
            violation("WARN", decision_id="store_001", rule="no postgres", trigger="postgres")])

    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    gate = MnemeLangChain(project_dir=layout["project"], mode="warn", check_runner=runner)
    mw = gate.build_middleware()[1]
    request = ToolCallRequest(
        tool_call={"name": "write_file", "args": {"file_path": "db.py", "content": "import psycopg2\n"},
                   "id": "c1", "type": "tool_call"},
        tool=None, state={"messages": []}, runtime=None)
    mw.wrap_tool_call(request, lambda r: Command(update=None, goto="x"))
    gaps = [e for e in gate.trace if e.get("annotation") == "skipped"]
    assert gaps and gaps[0]["selection_reason"] == OVERRIDE_IGNORED


# ── Concurrency: the selection belongs to the call, not to a shared slot ─────


def test_threaded_calls_keep_their_own_selection(layout, monkeypatch):
    """A selection-free call on another thread must not strip a pending record."""
    import threading

    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    in_check = threading.Event()
    release = threading.Event()

    def slow_runner(command, **kwargs):
        in_check.set()
        release.wait(5)
        return check_result_for(command, "PASS")

    sdk = MnemeAgentSdk(project_dir=layout["project"], check_runner=slow_runner)
    writer = threading.Thread(target=sdk.evaluate_mutation,
                              args=("Write", _write(layout["project"] / "a.py")))
    writer.start()
    assert in_check.wait(5)
    sdk.evaluate_mutation("Read", {"file_path": "a.py"})  # no selection
    release.set()
    writer.join(5)
    write_records = [r for r in sdk.trace if r.get("tool") == "Write"]
    read_records = [r for r in sdk.trace if r.get("tool") == "Read"]
    assert write_records and write_records[-1]["selection_reason"] == OVERRIDE_IGNORED
    assert read_records and not KEYS & set(read_records[-1])


def test_langchain_async_unmapped_call_does_not_strip_annotation_keys(layout, monkeypatch):
    pytest.importorskip("langchain")
    pytest.importorskip("langgraph")
    import asyncio

    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolMessage
    from langgraph.types import Command

    from tests.integrations.check_contract import violation

    def runner(command, **kwargs):
        return check_result_for(command, "WARN", violations=[
            violation("WARN", decision_id="store_001", rule="no postgres", trigger="postgres")])

    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    gate = MnemeLangChain(project_dir=layout["project"], mode="warn", check_runner=runner)
    mw = gate.build_middleware()[1]

    def request(name, args, call_id):
        return ToolCallRequest(tool_call={"name": name, "args": args, "id": call_id,
                                          "type": "tool_call"},
                               tool=None, state={"messages": []}, runtime=None)

    async def slow_handler(_r):
        await asyncio.sleep(0.1)
        return Command(update=None, goto="x")

    async def quick_handler(_r):
        return ToolMessage(content="ok", tool_call_id="c2")

    async def scenario():
        mapped = asyncio.create_task(mw.awrap_tool_call(
            request("write_file", {"file_path": "db.py", "content": "import psycopg2\n"}, "c1"),
            slow_handler))
        await asyncio.sleep(0.02)
        await mw.awrap_tool_call(request("web_search", {"q": "x"}, "c2"), quick_handler)
        await mapped

    asyncio.run(scenario())
    gaps = [e for e in gate.trace if e.get("annotation") == "skipped"]
    assert gaps and gaps[0]["selection_reason"] == OVERRIDE_IGNORED

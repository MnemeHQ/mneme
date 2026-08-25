"""Live pinned fixture: governed LangChain agent loops on real checks.

Unlike ``test_adapter.py``, these tests run the actual agent loop through
``langchain.agents.create_agent`` with Mneme's middleware installed and
invoke the REAL ``mneme check`` subprocess against a real project memory.
The chat model is scripted and offline; no provider keys are used.

Requires the ``langchain`` extra (skipped when absent). Run with::

    <venv-python> -m pytest tests/integrations/langchain/test_live_fixture.py

with the repository root importable (e.g. PYTHONPATH=<repo-root>).
"""

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("langchain")
pytest.importorskip("langgraph")

from langchain.agents import create_agent  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from mneme.integrations.langchain import MnemeLangChain  # noqa: E402

MEMORY = {
    "meta": {
        "name": "langchain-live-project",
        "description": "Fixture for langchain live-loop tests",
        "version": "0.1.0",
        "owner": "test",
        "created": "2026-08-25",
    },
    "items": [],
    "decisions": [
        {
            "id": "store_001",
            "decision": "Use SQLite for local storage and database access",
            "rationale": "single-file portability",
            "scope": ["storage", "database"],
            "constraints": ["no postgres"],
            "anti_patterns": ["psycopg2"],
        },
    ],
}

FORBIDDEN = "import psycopg2\n"
BENIGN = "x = 1\n"


class ScriptedChatModel(BaseChatModel):
    """Deterministic offline stand-in: emits a tool call, then finishes."""

    responses: list = []
    index: int = 0

    def __init__(self, responses, **kwargs):
        super().__init__(responses=list(responses), **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        spec = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        msg = AIMessage(
            content=spec.get("content", ""), tool_calls=spec.get("tool_calls") or []
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


def call(name: str, args: dict, call_id: str) -> dict:
    return {
        "content": "",
        "tool_calls": [{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    }


def make_write_file(events):
    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file inside the sandbox directory."""
        target = Path(file_path)
        events.append(("tool_exec", str(target)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {target.name}"

    return write_file


def make_edit_file(events):
    @tool
    def edit_file(file_path: str, old_string: str, new_string: str) -> str:
        """Replace old_string with new_string in an existing file."""
        target = Path(file_path)
        events.append(("tool_exec", str(target)))
        text = target.read_text(encoding="utf-8")
        if old_string not in text:
            raise ValueError("old_string not found")
        target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return f"edited {target.name}"

    return edit_file


def make_read_file(events):
    @tool
    def read_file(file_path: str) -> str:
        """Read a file from the sandbox directory."""
        events.append(("tool_exec", file_path))
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except OSError:
            return "(missing)"

    return read_file


def build_agent(project_dir, events, responses, mode=None, check_runner=None):
    model = ScriptedChatModel(responses)
    tools = [
        make_write_file(events),
        make_edit_file(events),
        make_read_file(events),
    ]
    mneme = MnemeLangChain(
        project_dir=project_dir, mode=mode, check_runner=check_runner
    )
    agent = create_agent(
        model=model,
        tools=tools,
        middleware=mneme.build_middleware(),
    )
    return agent, mneme


def drive(agent, prompt="add the database module"):
    return agent.invoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"recursion_limit": 25},
    )


def drive_async(agent, prompt="add the database module"):
    return asyncio.run(
        agent.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"recursion_limit": 25},
        )
    )


def tool_texts(result) -> list:
    out = []
    for m in result["messages"]:
        if isinstance(m, ToolMessage):
            c = m.content
            out.append(c if isinstance(c, str) else json.dumps(c))
    return out


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(MEMORY), encoding="utf-8"
    )
    return tmp_path


class TestLiveGovernedLoop:
    def test_forbidden_write_blocked_before_execution(self, project, tmp_path):
        sandbox = tmp_path / "sb1"
        sandbox.mkdir()
        events = []
        agent, gate = build_agent(
            project,
            events,
            [
                call(
                    "write_file",
                    {"file_path": str(sandbox / "db.py"), "content": FORBIDDEN},
                    "c1",
                ),
                {"content": "done"},
            ],
        )
        result = drive(agent)
        assert events == [], "denied mutation must never execute"
        texts = "\n".join(tool_texts(result))
        assert "[mneme] DENIED" in texts
        assert "store_001" in texts
        enforcement = [e for e in gate.trace if e["kind"] == "enforcement"]
        assert enforcement and enforcement[0]["action"] == "deny"
        assert not list(sandbox.rglob("*"))

    def test_compliant_write_executes_exactly_once(self, project, tmp_path):
        sandbox = tmp_path / "sb2"
        sandbox.mkdir()
        events = []
        agent, _ = build_agent(
            project,
            events,
            [
                call(
                    "write_file",
                    {"file_path": str(sandbox / "util.py"), "content": BENIGN},
                    "c2",
                ),
                {"content": "done"},
            ],
        )
        result = drive(agent)
        assert len([e for e in events if e[0] == "tool_exec"]) == 1
        assert (sandbox / "util.py").read_text(encoding="utf-8") == BENIGN
        assert not any("[mneme]" in t for t in tool_texts(result))

    def test_edit_blames_only_introduced_delta(self, project, tmp_path):
        sandbox = tmp_path / "sb3"
        sandbox.mkdir()
        seeded = sandbox / "db.py"
        seeded.write_text(FORBIDDEN + "x = 1\n", encoding="utf-8")
        events = []

        # Pre-existing violation stays unblamed: benign delta passes.
        agent, _ = build_agent(
            project,
            events,
            [
                call(
                    "edit_file",
                    {
                        "file_path": str(seeded),
                        "old_string": "x = 1",
                        "new_string": "y = 2",
                    },
                    "c3",
                ),
                {"content": "done"},
            ],
        )
        result = drive(agent)
        assert any(e[0] == "tool_exec" for e in events)
        assert seeded.read_text(encoding="utf-8") == FORBIDDEN + "y = 2\n"
        assert not any("[mneme] DENIED" in t for t in tool_texts(result))

        # Introducing the same literal IS denied.
        events2 = []
        agent2, _ = build_agent(
            project,
            events2,
            [
                call(
                    "edit_file",
                    {
                        "file_path": str(seeded),
                        "old_string": "y = 2",
                        "new_string": "y = 3\nimport psycopg2",
                    },
                    "c4",
                ),
                {"content": "done"},
            ],
        )
        result2 = drive(agent2)
        assert events2 == [], "introducing violation must never execute"
        assert any("[mneme] DENIED" in t for t in tool_texts(result2))
        assert seeded.read_text(encoding="utf-8") == FORBIDDEN + "y = 2\n"

    def test_warn_mode_executes_and_flags_visibly(self, project, tmp_path):
        sandbox = tmp_path / "sb5"
        sandbox.mkdir()
        events = []
        agent, _ = build_agent(
            project,
            events,
            [
                call(
                    "write_file",
                    {"file_path": str(sandbox / "db.py"), "content": FORBIDDEN},
                    "c5",
                ),
                {"content": "done"},
            ],
            mode="warn",
        )
        result = drive(agent)
        assert any(e[0] == "tool_exec" for e in events), "warn mode must not block"
        texts = "\n".join(tool_texts(result))
        assert "[mneme] WARN" in texts
        assert "not blocked" in texts

    def test_async_parity_for_denial(self, project, tmp_path):
        sandbox = tmp_path / "sb6"
        sandbox.mkdir()
        events = []
        agent, gate = build_agent(
            project,
            events,
            [
                call(
                    "write_file",
                    {"file_path": str(sandbox / "db.py"), "content": FORBIDDEN},
                    "c6",
                ),
                {"content": "done"},
            ],
        )
        result = drive_async(agent)
        assert events == []
        assert any("[mneme] DENIED" in t for t in tool_texts(result))
        enforcement = [e for e in gate.trace if e["kind"] == "enforcement"]
        assert enforcement[0]["action"] == "deny"

    def test_context_injection_reaches_model(self, project, tmp_path):
        captured = []

        class RecordingModel(ScriptedChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                captured.append(list(messages))
                return super()._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )

        sandbox = tmp_path / "sb7"
        sandbox.mkdir()
        events = []
        model = RecordingModel(
            [
                call(
                    "write_file",
                    {"file_path": str(sandbox / "util.py"), "content": BENIGN},
                    "c7",
                ),
                {"content": "done"},
            ]
        )
        mneme = MnemeLangChain(project_dir=project)
        agent = create_agent(
            model=model,
            tools=[make_write_file(events)],
            middleware=mneme.build_middleware(),
        )
        drive(agent, prompt="sqlite storage database decision please")
        system_texts = [
            m.content for m in captured[0] if type(m).__name__ == "SystemMessage"
        ]
        assert any("[Mneme decisions applied]" in c for c in system_texts)
        assert any("store_001" in c for c in system_texts)

    def test_embedded_subgraph_still_governed(self, project, tmp_path):
        from langgraph.graph import END, START, MessagesState, StateGraph

        sandbox = tmp_path / "sb8"
        sandbox.mkdir()
        events = []
        inner_agent, gate = build_agent(
            project,
            events,
            [
                call(
                    "write_file",
                    {"file_path": str(sandbox / "db.py"), "content": FORBIDDEN},
                    "c8",
                ),
                {"content": "done"},
            ],
        )
        builder = StateGraph(MessagesState)
        builder.add_node("governed_agent", inner_agent)
        builder.add_edge(START, "governed_agent")
        builder.add_edge("governed_agent", END)
        parent = builder.compile()

        result = parent.invoke(
            {"messages": [HumanMessage(content="add the database module")]},
            config={"recursion_limit": 25},
        )
        assert events == []
        all_texts = [
            m.content if isinstance(m.content, str) else json.dumps(m.content)
            for m in result["messages"]
        ]
        assert any("[mneme] DENIED" in t for t in all_texts)
        enforcement = [e for e in gate.trace if e["kind"] == "enforcement"]
        assert enforcement[0]["action"] == "deny"

    def test_read_only_tool_zero_checker_calls(self, project, tmp_path):
        sandbox = tmp_path / "sb9"
        sandbox.mkdir()
        target = sandbox / "notes.txt"
        target.write_text(BENIGN, encoding="utf-8")
        events = []

        checker_calls = []

        def exploding_runner(command, **kwargs):
            checker_calls.append(command)
            raise AssertionError("checker must not be called for read-only tools")

        model = ScriptedChatModel(
            [
                call("read_file", {"file_path": str(target)}, "c9"),
                {"content": "done"},
            ]
        )
        mneme = MnemeLangChain(
            project_dir=project, check_runner=exploding_runner
        )
        agent = create_agent(
            model=model,
            tools=[make_read_file(events)],
            middleware=mneme.build_middleware(),
        )
        result = drive(agent)
        assert any(e[0] == "tool_exec" for e in events)
        assert checker_calls == [], "zero checker calls required"
        enforcement = [e for e in mneme.trace if e["kind"] == "enforcement"]
        assert enforcement and all(e["action"] == "skip" for e in enforcement)
        assert not any("[mneme]" in t for t in tool_texts(result))


class TestModelRequestPreservation:
    """Injection must touch only the system message."""

    def _middleware(self, project):
        mneme = MnemeLangChain(project_dir=project)
        return mneme.build_middleware()[0]

    def _request(self, system_message, model_settings=None):
        from langchain.agents.middleware.types import ModelRequest

        return ModelRequest(
            model=ScriptedChatModel([{"content": "ok"}]),
            messages=[HumanMessage(content="sqlite storage database decision")],
            system_message=system_message,
            model_settings=model_settings,
        )

    def test_model_settings_survive_injection(self, project):
        ctx = self._middleware(project)
        request = self._request(SystemMessage(content="base"), {"temperature": 0.3})
        out = ctx._with_decisions(request)
        assert out is not request
        assert out.model_settings == {"temperature": 0.3}
        assert isinstance(out.system_message.content, str)
        assert out.system_message.content.startswith("base\n")
        assert "[Mneme decisions applied]" in out.system_message.content

    def test_structured_system_content_preserved_as_blocks(self, project):
        ctx = self._middleware(project)
        original = [
            {"type": "text", "text": "rule one"},
            {"type": "text", "text": "rule two"},
        ]
        out = ctx._with_decisions(self._request(SystemMessage(content=original)))
        content = out.system_message.content
        assert isinstance(content, list)
        assert content[:2] == original
        assert len(content) == 3
        assert "[Mneme decisions applied]" in content[2]["text"]

    def test_no_injection_returns_request_untouched(self, tmp_path):
        ctx = MnemeLangChain(project_dir=tmp_path).build_middleware()[0]
        request = self._request(SystemMessage(content="base"))
        assert ctx._with_decisions(request) is request


class TestCommandResultAnnotation:
    """WARN/UNEVALUATED must survive the Command half of the handler contract."""

    def _gate_warn(self, project):
        def runner(command, **kwargs):
            return FakeCompleted(
                verdict_json(
                    "WARN",
                    violations=[
                        {
                            "decision_id": "store_001",
                            "severity": "WARN",
                            "rule": "no postgres",
                            "trigger": "postgres",
                        }
                    ],
                )
            )

        return MnemeLangChain(project_dir=project, mode="warn", check_runner=runner)

    def _gate_deny(self, project):
        def runner(command, **kwargs):
            return FakeCompleted(
                verdict_json("FAIL", violations=[{"decision_id": "store_001", "severity": "FAIL", "rule": "psycopg2", "trigger": "psycopg2"}])
            )

        return MnemeLangChain(project_dir=project, check_runner=runner)

    def _request(self, call_id="cx"):
        from langchain.agents.middleware.types import ToolCallRequest

        return ToolCallRequest(
            tool_call={
                "name": "write_file",
                "args": {"file_path": "db.py", "content": FORBIDDEN},
                "id": call_id,
                "type": "tool_call",
            },
            tool=None,
            state={"messages": []},
            runtime=None,
        )

    def _command_handler(self, calls):
        def handler(request):
            calls.append(request)
            from langgraph.types import Command

            return Command(
                update={
                    "messages": [
                        ToolMessage(content="wrote db.py", tool_call_id=request.tool_call["id"])
                    ],
                    "extra_state": "keep-me",
                },
                goto="review_node",
            )

        return handler

    def _async_command_handler(self, calls):
        from langgraph.types import Command

        async def handler(request):
            calls.append(request)
            return Command(
                update={
                    "messages": [
                        ToolMessage(content="wrote db.py", tool_call_id=request.tool_call["id"])
                    ],
                    "extra_state": "keep-me",
                },
                goto="review_node",
            )

        return handler

    def _gate_middleware(self, gate):
        return gate.build_middleware()[1]

    def test_sync_warn_command_keeps_goto_and_gains_marker(self, project):
        mw = self._gate_middleware(self._gate_warn(project))
        calls = []
        out = mw.wrap_tool_call(self._request(), self._command_handler(calls))
        assert len(calls) == 1
        from langgraph.types import Command

        assert isinstance(out, Command)
        assert out.goto == "review_node"
        assert out.update["extra_state"] == "keep-me"
        msg = out.update["messages"][0]
        assert msg.content.startswith("wrote db.py\n[mneme] WARN")

    def test_sync_fail_open_command_carries_unevaluated(self, project):
        # Force the fail-open path: checker transport dies before a verdict.
        def broken(command, **kwargs):
            raise OSError("spawn failed")

        gate = MnemeLangChain(project_dir=project, check_runner=broken)
        mw = self._gate_middleware(gate)
        calls = []
        out = mw.wrap_tool_call(self._request(), self._command_handler(calls))
        from langgraph.types import Command

        assert isinstance(out, Command)
        assert out.goto == "review_node"
        msg = out.update["messages"][0]
        assert msg.content.startswith("wrote db.py\n[mneme] UNEVALUATED")
        assert "NOT checked" in msg.content

    def test_sync_deny_short_circuits_command_handlers_too(self, project):
        mw = self._gate_middleware(self._gate_deny(project))
        calls = []
        out = mw.wrap_tool_call(self._request(), self._command_handler(calls))
        assert calls == [], "denied call must never reach the handler"
        from langchain_core.messages import ToolMessage

        assert isinstance(out, ToolMessage)
        assert "[mneme] DENIED" in out.content

    def test_async_parity_for_command_annotation(self, project):
        mw = self._gate_middleware(self._gate_warn(project))
        calls = []
        out = asyncio.run(
            mw.awrap_tool_call(self._request(), self._async_command_handler(calls))
        )
        from langgraph.types import Command

        assert len(calls) == 1
        assert isinstance(out, Command)
        assert out.goto == "review_node"
        assert "[mneme] WARN" in out.update["messages"][0].content

        def broken(command, **kwargs):
            raise OSError("spawn failed")

        mw2 = self._gate_middleware(MnemeLangChain(project_dir=project, check_runner=broken))
        calls2 = []
        out2 = asyncio.run(
            mw2.awrap_tool_call(self._request(), self._async_command_handler(calls2))
        )
        assert isinstance(out2, Command)
        assert "[mneme] UNEVALUATED" in out2.update["messages"][0].content

    def test_unrecognized_command_update_recorded_not_silent(self, project):
        gate = self._gate_warn(project)
        mw = gate.build_middleware()[1]

        from langgraph.types import Command

        def opaque_handler(request):
            return Command(update=None, goto="review_node")

        out = mw.wrap_tool_call(self._request(), opaque_handler)
        assert isinstance(out, Command)
        assert out.update is None
        gaps = [e for e in gate.trace if e.get("annotation") == "skipped"]
        assert gaps and gaps[0]["action"] == "warn"


# ── small local helpers ─────────────────────────────────────────────────────


def verdict_json(verdict, *, complete=True, violations=None):
    payload = {
        "schema": SCHEMA_LIVE,
        "verdict": verdict,
        "violations": violations or [],
        "evaluation_complete": complete,
    }
    return json.dumps(payload)


SCHEMA_LIVE = "mneme.check/v1"


class FakeCompleted:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0

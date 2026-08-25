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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
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

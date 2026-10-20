"""#571: ``project_dir`` resolves relative ``write_file`` / ``edit_file`` paths.

Runs the shared matrix through the plain-Python adapter (no langchain import)
and once through the real middleware, with the host process cwd elsewhere.
"""
from mneme.integrations.langchain import MnemeLangChain
from tests.integrations.relative_path_matrix import RelativePathMatrix
from tests.integrations.relative_paths import FORBIDDEN, VIOLATING


class TestLangChainRelativePaths(RelativePathMatrix):
    WRITE = "write_file"
    EDIT = "edit_file"

    def evaluate(self, layout, runner, tool, tool_input):
        gate = MnemeLangChain(project_dir=str(layout.project), mode="strict", check_runner=runner)
        return gate.evaluate_tool_call(tool, tool_input)


class TestLiveMiddlewareRelativePath:
    """The #570 shape end to end: a real agent loop whose tool resolves the
    relative path against ``project_dir`` while the process cwd holds an
    identical decoy. The write must be denied before the handler runs."""

    def test_relative_write_with_identical_decoy_denied_before_handler(
        self, tmp_path, monkeypatch
    ):
        import pytest

        pytest.importorskip("langchain")
        pytest.importorskip("langgraph")
        from langchain.agents import create_agent
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool

        from tests.integrations.langchain.test_live_fixture import ScriptedChatModel, call
        from tests.integrations.relative_paths import TARGET, make_layout

        layout = make_layout(tmp_path, monkeypatch)
        layout.decoy(VIOLATING)
        before = layout.real().read_bytes()
        handler_runs = []

        @tool
        def write_file(file_path: str, content: str) -> str:
            """Write content to a file under the project root."""
            handler_runs.append(file_path)
            target = layout.project / file_path
            target.write_text(content, encoding="utf-8")
            return "wrote"

        gate = MnemeLangChain(project_dir=str(layout.project), mode="strict")
        agent = create_agent(
            model=ScriptedChatModel([
                call("write_file", {"file_path": TARGET, "content": VIOLATING}, "c1"),
                {"content": "done"},
            ]),
            tools=[write_file],
            middleware=gate.build_middleware(),
        )
        result = agent.invoke(
            {"messages": [HumanMessage(content="update the router")]},
            config={"recursion_limit": 10},
        )

        assert handler_runs == []
        assert layout.real().read_bytes() == before
        tool_text = " ".join(str(m.content) for m in result["messages"] if m.type == "tool")
        assert "[mneme] DENIED" in tool_text
        assert FORBIDDEN in tool_text or "router_001" in tool_text

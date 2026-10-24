import argparse
import asyncio
import io
import json
import time

from mcp import Client

from mneme import cli as mneme_cli
from mneme.decision_mcp import (
    APPROVED_TOOLS,
    TOOL_APPLICABLE_TO,
    TOOL_GET,
    TOOL_PROPOSE,
    TOOL_PROPOSE_BATCH,
    TOOL_SEARCH,
    TOOL_TRACE,
    build_server_from_parts,
)
from mneme.decision_proposal_store import InMemoryDecisionProposalStore
from mneme.integrations.claude_code import hook as claude_hook
from mneme.integrations.codex_cli import hook as codex_hook
from mneme.integrations.kiro import hook as kiro_hook
from mneme.usage import cli as usage_cli
from mneme.usage.contracts import Operation
from mneme.usage.store import UsageStore


def test_cli_closed_mapping_covers_substantive_commands_and_excludes_admin(monkeypatch):
    seen = []
    monkeypatch.setattr("mneme.usage.cli.record_cli", seen.append)
    cases = {
        ("init", None): Operation.CLI_INIT,
        ("setup", None): Operation.CLI_SETUP,
        ("list_decisions", None): Operation.CLI_LIST_DECISIONS,
        ("add_decision", None): Operation.CLI_ADD_DECISION,
        ("test_query", None): Operation.CLI_TEST_QUERY,
        ("check", None): Operation.CLI_CHECK,
        ("audit", None): Operation.CLI_AUDIT,
        ("protect", "list"): Operation.CLI_PROTECT_LIST,
        ("protect", "status"): Operation.CLI_PROTECT_STATUS,
        ("protect", "validate"): Operation.CLI_PROTECT_VALIDATE,
        ("protect", "activate"): Operation.CLI_PROTECT_ACTIVATE,
        ("cursor", "generate"): Operation.CLI_CURSOR_GENERATE,
        ("adr", "import"): Operation.CLI_ADR_IMPORT,
        ("eventcatalog", "import"): Operation.CLI_EVENTCATALOG_IMPORT,
        ("decision-index", "migrate"): Operation.CLI_DECISION_INDEX_MIGRATE,
        ("decision", "proposals"): Operation.CLI_DECISION_PROPOSALS,
        ("decision", "show"): Operation.CLI_DECISION_SHOW,
        ("decision", "accept"): Operation.CLI_DECISION_ACCEPT,
        ("decision", "reject"): Operation.CLI_DECISION_REJECT,
    }
    for (command, child), operation in cases.items():
        values = {"cmd": command}
        if command == "protect":
            values["protect_cmd"] = child
        elif command == "cursor":
            values["cursor_cmd"] = child
        elif command == "adr":
            values["adr_cmd"] = child
        elif command == "eventcatalog":
            values["ec_cmd"] = child
        elif command == "decision-index":
            values["decision_index_cmd"] = child
        elif command == "decision":
            values["decision_cmd"] = child
        mneme_cli._record_cli_usage(argparse.Namespace(**values))
        assert seen[-1] == operation

    count = len(seen)
    for excluded in ("usage", "benchmark", "research", "decision-mcp"):
        mneme_cli._record_cli_usage(argparse.Namespace(cmd=excluded))
    assert len(seen) == count


def test_cli_measurement_failure_cannot_change_completed_result(monkeypatch, capsys):
    class Parser:
        @staticmethod
        def parse_args(_argv):
            return argparse.Namespace(cmd="init", func=lambda _args: print("same") or 7)

    monkeypatch.setattr(mneme_cli, "_build_parser", Parser)
    monkeypatch.setattr(
        "mneme.usage.cli.record_cli",
        lambda _operation: (_ for _ in ()).throw(OSError("no")),
    )
    assert mneme_cli.main([]) == 7
    captured = capsys.readouterr()
    assert captured.out == "same\n"
    assert captured.err == ""


def _mcp_calls(server):
    candidate = {
        "title": "Prefer JSON",
        "statement": "Use JSON for local state.",
        "provenance": {
            "producer_name": "test",
            "producer_type": "agent",
            "source_reference": "test-run",
        },
    }

    async def run():
        async with Client(server) as client:
            await client.call_tool(TOOL_PROPOSE, {"candidate": candidate})
            await client.call_tool(
                TOOL_PROPOSE_BATCH, {"candidates": [{**candidate, "title": "Second"}]}
            )
            await client.call_tool(TOOL_GET, {"record_id": "missing"})
            await client.call_tool(TOOL_SEARCH, {})
            await client.call_tool(TOOL_APPLICABLE_TO, {})
            await client.call_tool(TOOL_TRACE, {"record_id": "missing"})
            return [tool.name for tool in (await client.list_tools()).tools]

    return asyncio.run(run())


def test_exact_six_mcp_handlers_are_measured_without_expanding_surface(monkeypatch):
    seen = []
    monkeypatch.setattr("mneme.usage.cli.record_mcp", seen.append)
    server = build_server_from_parts(InMemoryDecisionProposalStore())
    names = _mcp_calls(server)
    assert tuple(names) == APPROVED_TOOLS
    assert seen == [
        Operation.MCP_PROPOSE,
        Operation.MCP_PROPOSE_BATCH,
        Operation.MCP_GET,
        Operation.MCP_SEARCH,
        Operation.MCP_APPLICABLE_TO,
        Operation.MCP_TRACE,
    ]


def test_mcp_measurement_failure_does_not_change_response(monkeypatch):
    monkeypatch.setattr(
        "mneme.usage.cli.record_mcp",
        lambda _operation: (_ for _ in ()).throw(OSError("no")),
    )
    server = build_server_from_parts(InMemoryDecisionProposalStore())

    async def run():
        async with Client(server) as client:
            return await client.call_tool(TOOL_GET, {"record_id": "missing"})

    result = asyncio.run(run())
    assert json.loads(result.content[0].text) == {
        "record_type": "not_found",
        "record_id": "missing",
    }


def test_hook_boundaries_count_only_supported_parsed_events(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr("mneme.usage.cli.record_hook", seen.append)

    claude_payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "cwd": str(tmp_path),
        "tool_input": {},
    }
    assert claude_hook.main(stdin=io.StringIO(json.dumps(claude_payload))) == 0
    assert claude_hook.main(stdin=io.StringIO("not-json"), stderr=io.StringIO()) == 0

    codex_payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {},
    }
    assert codex_hook.main(stdin=io.StringIO(json.dumps(codex_payload))) == 0

    kiro_payload = {
        "hook_event_name": "preToolUse",
        "tool_name": "read",
        "tool_input": {},
    }
    assert kiro_hook.main(stdin=io.StringIO(json.dumps(kiro_payload))) == 0

    assert seen == [
        Operation.HOOK_CLAUDE_CODE_PRE_TOOL_USE,
        Operation.HOOK_CODEX_CLI_PRE_TOOL_USE,
        Operation.HOOK_KIRO_PRE_TOOL_USE,
    ]


def test_hook_child_process_suppresses_internal_cli_counter():
    env = claude_hook._child_env()
    assert env["MNEME_USAGE_INTERNAL_HOOK_CHECK"] == "1"


def test_claude_and_codex_session_and_stop_hooks_are_measured(monkeypatch):
    seen = []
    monkeypatch.setattr("mneme.usage.cli.record_hook", seen.append)
    monkeypatch.setattr(claude_hook, "session_start_event", lambda *_args: 0)
    monkeypatch.setattr(claude_hook, "stop_event", lambda *_args: 0)
    monkeypatch.setattr(
        codex_hook.stop_audit, "handle_session_start", lambda *_args, **_kwargs: 0
    )
    monkeypatch.setattr(
        codex_hook.stop_audit, "handle_stop", lambda *_args, **_kwargs: 0
    )

    for module, event_name in (
        (claude_hook, "SessionStart"),
        (claude_hook, "Stop"),
        (codex_hook, "SessionStart"),
        (codex_hook, "Stop"),
    ):
        assert (
            module.main(
                stdin=io.StringIO(json.dumps({"hook_event_name": event_name})),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            == 0
        )

    assert seen == [
        Operation.HOOK_CLAUDE_CODE_SESSION_START,
        Operation.HOOK_CLAUDE_CODE_STOP,
        Operation.HOOK_CODEX_CLI_SESSION_START,
        Operation.HOOK_CODEX_CLI_STOP,
    ]


def test_invalid_hook_envelopes_are_not_measured(monkeypatch):
    seen = []
    monkeypatch.setattr("mneme.usage.cli.record_hook", seen.append)
    invalid = json.dumps({"hook_event_name": "PreToolUse"})
    assert claude_hook.main(stdin=io.StringIO(invalid), stderr=io.StringIO()) == 0
    assert codex_hook.main(stdin=io.StringIO(invalid), stderr=io.StringIO()) == 0
    assert kiro_hook.main(stdin=io.StringIO(invalid), stderr=io.StringIO()) == 0
    assert seen == []


def test_hook_measurement_failure_preserves_wire_output(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "mneme.usage.cli.record_hook",
        lambda _operation: (_ for _ in ()).throw(OSError("no")),
    )
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "cwd": str(tmp_path),
        "tool_input": {},
    }
    stdout = io.StringIO()
    stderr = io.StringIO()
    assert (
        claude_hook.main(
            stdin=io.StringIO(json.dumps(payload)), stdout=stdout, stderr=stderr
        )
        == 0
    )
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_enabled_boundaries_persist_each_closed_operation(monkeypatch, tmp_path):
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    store = UsageStore()
    assert usage_cli.enable(store, stdout=io.StringIO()) == 0

    assert mneme_cli.main(["init", "--path", str(tmp_path / "memory.json")]) == 0

    async def call_mcp():
        async with Client(
            build_server_from_parts(InMemoryDecisionProposalStore())
        ) as client:
            await client.call_tool(TOOL_GET, {"record_id": "missing"})

    asyncio.run(call_mcp())

    hook_cases = (
        (
            claude_hook,
            {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        ),
        (
            codex_hook,
            {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        ),
        (
            kiro_hook,
            {"hook_event_name": "preToolUse", "tool_name": "read", "tool_input": {}},
        ),
    )
    for module, payload in hook_cases:
        assert (
            module.main(
                stdin=io.StringIO(json.dumps(payload)),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            == 0
        )

    state = store.read(unix_seconds=time.time())
    assert state is not None
    assert {aggregate.operation for aggregate in state.counters} == {
        Operation.CLI_INIT,
        Operation.MCP_GET,
        Operation.HOOK_CLAUDE_CODE_PRE_TOOL_USE,
        Operation.HOOK_CODEX_CLI_PRE_TOOL_USE,
        Operation.HOOK_KIRO_PRE_TOOL_USE,
    }

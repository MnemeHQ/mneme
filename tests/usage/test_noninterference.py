import argparse
import contextlib
import io
import json
import socket
import time
from pathlib import Path

from mcp import Client

from mneme import cli as mneme_cli
from mneme.decision_mcp import TOOL_GET, build_server_from_parts
from mneme.decision_proposal_store import InMemoryDecisionProposalStore
from mneme.integrations.claude_code import hook as claude_hook
from mneme.integrations.codex_cli import hook as codex_hook
from mneme.integrations.kiro import hook as kiro_hook
from mneme.usage import cli as usage_cli
from mneme.usage.contracts import ExecutionContext, Operation, Surface
from mneme.usage.store import UsageStore


def _capture_main(arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = mneme_cli.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def _usage_dir(local_app_data: Path) -> Path:
    return local_app_data / "Mneme" / "usage"


def test_default_off_cli_mcp_and_hooks_create_no_usage_state(monkeypatch, tmp_path):
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    project_memory = tmp_path / "project_memory.json"
    assert mneme_cli.main(["init", "--path", str(project_memory)]) == 0

    async def call_mcp():
        async with Client(
            build_server_from_parts(InMemoryDecisionProposalStore())
        ) as client:
            await client.call_tool(TOOL_GET, {"record_id": "missing"})

    import asyncio

    asyncio.run(call_mcp())
    claude_hook.main(
        stdin=io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Read",
                    "cwd": str(tmp_path),
                    "tool_input": {},
                }
            )
        ),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    codex_hook.main(
        stdin=io.StringIO(
            json.dumps(
                {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}}
            )
        ),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    kiro_hook.main(
        stdin=io.StringIO(
            json.dumps(
                {"hook_event_name": "preToolUse", "tool_name": "read", "tool_input": {}}
            )
        ),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert not _usage_dir(local).exists()


def test_u1_paths_make_no_dns_or_socket_attempts(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("U1 attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    store = UsageStore(tmp_path / "usage")
    assert usage_cli.enable(store, stdout=io.StringIO()) == 0
    assert store.try_increment(
        unix_seconds=time.time(),
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )
    assert usage_cli.status(store, stdout=io.StringIO()) == 0
    assert usage_cli.preview(store, stdout=io.StringIO()) == 0
    assert usage_cli.disable(store, stdout=io.StringIO()) == 0
    assert usage_cli.purge(store, stdout=io.StringIO()) == 0


def test_cli_check_output_and_project_memory_are_identical_when_enabled(
    monkeypatch, tmp_path
):
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    memory = tmp_path / "project_memory.json"
    memory.write_text(
        json.dumps({"meta": {"name": "test", "description": "test"}, "decisions": []}),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.py"
    input_path.write_text("print('ok')\n", encoding="utf-8")
    arguments = [
        "check",
        "--memory",
        str(memory),
        "--input",
        str(input_path),
        "--query",
        "test",
        "--json",
    ]
    before_memory = memory.read_bytes()
    disabled = _capture_main(arguments)
    assert usage_cli.enable(UsageStore(), stdout=io.StringIO()) == 0
    enabled = _capture_main(arguments)
    assert enabled == disabled
    assert memory.read_bytes() == before_memory


def test_internal_hook_check_marker_suppresses_cli_measurement(monkeypatch):
    called = []
    monkeypatch.setattr("mneme.usage.cli.UsageStore", lambda: called.append(True))
    monkeypatch.setenv(usage_cli.INTERNAL_HOOK_CHECK_ENV, "1")
    assert usage_cli.record_cli(Operation.CLI_CHECK) is False
    assert called == []


def test_benchmark_and_research_are_not_product_active(monkeypatch):
    seen = []
    monkeypatch.setattr("mneme.usage.cli.record_cli", seen.append)
    mneme_cli._record_cli_usage(argparse.Namespace(cmd="benchmark"))
    mneme_cli._record_cli_usage(argparse.Namespace(cmd="research"))
    assert seen == []

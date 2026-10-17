"""MNEME_HOOK_CHECK_TRANSPORT: benchmark-only switch, PreToolUse path only."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import mneme.integrations.claude_code.hook as hook
from mneme.integrations.claude_code.hook import resolve_transport

from .test_stop_boundary import _run, _session_start, _stop_event, repo  # noqa: F401

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"


@pytest.mark.parametrize("value,expected", [
    (None, "subprocess"),
    ("", "subprocess"),
    ("bogus", "subprocess"),
    ("inprocess", "inprocess"),
    (" INPROCESS ", "inprocess"),
    ("subprocess", "subprocess"),
])
def test_resolve_transport(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(hook._TRANSPORT_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(hook._TRANSPORT_ENV_VAR, value)
    assert resolve_transport() == expected


def test_stop_path_never_uses_inprocess(repo, monkeypatch):  # noqa: F811
    monkeypatch.setenv(hook._TRANSPORT_ENV_VAR, "inprocess")

    def boom(argv):
        raise AssertionError("Stop path must stay on the subprocess transport")

    monkeypatch.setattr(hook, "_invoke_check_inprocess", boom)
    assert _run(_session_start(repo))[0] == 0
    (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
    rc, _, out = _run(_stop_event(repo))
    assert rc == 0
    assert json.loads(out)["decision"] == "block"


def test_inprocess_timeout_fails_open(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    target = tmp_path / "storage_db.py"
    envelope = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": str(tmp_path),
        "tool_input": {"file_path": str(target), "content": "import psycopg2\n"},
    })
    env = hook._child_env()
    env.update({
        hook._TRANSPORT_ENV_VAR: "inprocess",
        "MNEME_HOOK_CHECK_TIMEOUT_TEST": "1",
        "MNEME_HOOK_TEST_STALL_SECONDS": "5",
    })
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c",
         "from mneme.integrations.claude_code.hook import cli_main; cli_main()"],
        input=envelope, capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    elapsed_s = time.perf_counter() - start
    assert proc.returncode == 0
    assert "failing open" in proc.stderr.lower()
    assert elapsed_s < 4


def test_hook_import_does_not_load_inprocess_machinery():
    # The default subprocess path must not pay for the benchmark-only transport.
    probe = (
        "import sys, mneme.integrations.claude_code.hook; "
        "print('mneme.integrations.claude_code.inprocess_check' in sys.modules)"
    )
    proc = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                          text=True, env=hook._child_env())
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False"

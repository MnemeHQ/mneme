import json
import io
import subprocess
import sys
from unittest.mock import patch, MagicMock
import pytest
from mneme.integrations.claude_code.hook import main


def _envelope(tool="Edit", cwd="/nonexistent", file_path="/nonexistent/x.py"):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "cwd": cwd,
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
    })


# --- Task 6: no-memory and non-mutating-tool paths ---

def test_no_memory_returns_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    rc = main(stdin=io.StringIO(_envelope(cwd=str(tmp_path), file_path=str(tmp_path / "x.py"))))
    assert rc == 0


def test_non_mutating_tool_returns_zero(tmp_path):
    rc = main(stdin=io.StringIO(_envelope(tool="Read", cwd=str(tmp_path))))
    assert rc == 0


# --- Task 7: subprocess invocation + fail-open boundary ---

def _project_with_memory(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text('{"decisions": []}')
    target = tmp_path / "x.py"
    target.write_text("import os\n", encoding="utf-8")
    return mem, target


def _edit_envelope(tmp_path, target):
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": str(target),
            "old_string": "import os",
            "new_string": "import psycopg2",
        },
    })


def test_strict_fail_returns_two(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=2, stdout="FAIL: violates mneme_001", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake) as mrun:
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 2
    args = mrun.call_args.args[0]
    assert args[0] == sys.executable
    assert args[1] == "-m"
    assert args[2] == "mneme"
    assert args[3] == "check"
    assert "--memory" in args and str(mem) in args
    assert "--mode" in args


def test_strict_warn_returncode_blocks(tmp_path):
    """In strict mode, mneme check returncode 1 (WARN) should block."""
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=1, stdout="WARN", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 2


def test_warn_mode_never_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=0, stdout="WARN", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0


def test_mneme_not_on_path_fails_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    err = io.StringIO()
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run",
        side_effect=FileNotFoundError("mneme"),
    ):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)), stderr=err)
    assert rc == 0
    assert "mneme" in err.getvalue().lower()


def test_subprocess_oserror_fails_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run",
        side_effect=OSError("permission denied"),
    ):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0


def test_subprocess_timeout_fails_open(tmp_path):
    mem, target = _project_with_memory(tmp_path)
    with patch(
        "mneme.integrations.claude_code.hook.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="mneme", timeout=10),
    ):
        rc = main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    assert rc == 0


# --- Regression: subprocess must use sys.executable -m, not bare "mneme" ---
# On Windows (Microsoft Store Python) the Scripts directory may not be on PATH
# when Claude Code launches mneme-hook.exe. Using sys.executable -m mneme
# guarantees the child process shares the same Python environment as the hook.

def test_subprocess_uses_sys_executable_not_bare_mneme(tmp_path):
    """Hook must invoke `sys.executable -m mneme check`, never `mneme check`."""
    mem, target = _project_with_memory(tmp_path)
    fake = MagicMock(returncode=0, stdout="", stderr="")
    with patch("mneme.integrations.claude_code.hook.subprocess.run", return_value=fake) as mrun:
        main(stdin=io.StringIO(_edit_envelope(tmp_path, target)))
    cmd = mrun.call_args.args[0]
    assert cmd[0] == sys.executable, (
        f"Expected sys.executable ({sys.executable!r}) as first arg, got {cmd[0]!r}. "
        "Bare 'mneme' breaks on Windows when Scripts is not on PATH."
    )
    assert cmd[1] == "-m"
    assert cmd[2] == "mneme"
    assert cmd[3] == "check"


# --- Additional fail-open boundaries at the main() level ---

def test_malformed_event_fails_open():
    """A non-JSON / malformed envelope must never block; main returns 0."""
    with patch("mneme.integrations.claude_code.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO("this is not json{"))
    assert rc == 0
    mrun.assert_not_called()


def test_materialize_failure_fails_open(tmp_path):
    """When proposed content cannot be reconstructed (old_string not in file),
    main fails open and never shells out to mneme check."""
    mem, target = _project_with_memory(tmp_path)  # target contains "import os\n"
    envelope = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": str(target),
            "old_string": "THIS_STRING_IS_NOT_IN_THE_FILE",
            "new_string": "x",
        },
    })
    with patch("mneme.integrations.claude_code.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO(envelope))
    assert rc == 0
    mrun.assert_not_called()

"""Parity of the benchmark-only in-process check with the subprocess check.

The in-process runner must hand the hook exactly what the ``mneme check``
child process would: same exit code, same JSON verdict, and the same
crash shape, so ``assess_verdict`` takes the same branch either way.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import mneme.integrations.claude_code.hook as hook
from mneme.integrations.claude_code.inprocess_check import run_check_inprocess

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"


@pytest.fixture
def project(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    target = tmp_path / "storage_db.py"
    target.write_text("# placeholder\n", encoding="utf-8")
    return tmp_path, mem, target


def _argv(tmp_path, mem, target, content):
    inp = tmp_path / "proposed.txt"
    inp.write_text(content, encoding="utf-8")
    return [
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "edit to storage_db.py",
        "--mode", "strict",
        "--json",
        "--target-path", str(target),
    ]


def _subprocess(argv):
    return subprocess.run(
        [sys.executable, "-m", "mneme", *argv],
        capture_output=True,
        text=True,
        env=hook._child_env(),
    )


def test_inprocess_matches_subprocess_blocked(project):
    tmp_path, mem, target = project
    argv = _argv(tmp_path, mem, target, "import psycopg2\n")
    sub = _subprocess(argv)
    inp = run_check_inprocess(argv)
    assert inp.returncode == sub.returncode
    assert json.loads(inp.stdout) == json.loads(sub.stdout)
    assert json.loads(inp.stdout)["verdict"] in {"WARN", "FAIL"}


def test_inprocess_matches_subprocess_allowed(project):
    tmp_path, mem, target = project
    argv = _argv(tmp_path, mem, target, "import sqlite3\n")
    sub = _subprocess(argv)
    inp = run_check_inprocess(argv)
    assert inp.returncode == sub.returncode == 0
    assert json.loads(inp.stdout) == json.loads(sub.stdout)


def test_inprocess_crash_matches_subprocess_shape(project):
    tmp_path, mem, target = project
    mem.write_text("{ this is not valid json", encoding="utf-8")
    argv = _argv(tmp_path, mem, target, "import psycopg2\n")
    sub = _subprocess(argv)
    inp = run_check_inprocess(argv)
    assert inp.returncode != 0 and sub.returncode != 0
    assert inp.stdout == ""
    assert "Traceback" in inp.stderr
    assert hook.assess_verdict(inp.stdout, inp.returncode, "strict").payload is None


def test_inprocess_systemexit_becomes_returncode():
    result = run_check_inprocess(["check", "--no-such-flag"])
    assert result.returncode == 2


def test_inprocess_does_not_touch_real_streams(project):
    tmp_path, mem, target = project
    before = (sys.stdout, sys.stderr)
    run_check_inprocess(_argv(tmp_path, mem, target, "import psycopg2\n"))
    assert (sys.stdout, sys.stderr) == before


def test_inprocess_uses_hook_package_tree():
    import mneme.cli

    assert Path(mneme.cli.__file__).resolve().parents[1] == hook._PACKAGE_ROOT


@pytest.mark.parametrize("raised,expected_rc,expected_err", [
    (SystemExit(None), 0, ""),
    (SystemExit("bad thing"), 1, "bad thing"),
    (SystemExit(3), 3, ""),
])
def test_inprocess_systemexit_matches_interpreter(monkeypatch, raised, expected_rc, expected_err):
    import mneme.cli

    def fake_main(argv):
        raise raised

    monkeypatch.setattr(mneme.cli, "main", fake_main)
    result = run_check_inprocess(["check"])
    assert result.returncode == expected_rc
    assert expected_err in result.stderr


def test_inprocess_none_return_is_zero(monkeypatch):
    import mneme.cli

    monkeypatch.setattr(mneme.cli, "main", lambda argv: None)
    assert run_check_inprocess(["check"]).returncode == 0

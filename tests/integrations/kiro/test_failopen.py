"""Fail-open boundaries, mode resolution, and child invocation contract."""
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mneme.integrations.kiro.hook import main

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"
VIOLATION = "legacy_client.connect("


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)


def _project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _envelope(cwd, path="f.py", content="x\n"):
    return json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(cwd),
        "tool_name": "fs_write",
        "tool_input": {"path": path, "content": content},
    })


def _verdict(verdict="FAIL", evaluation_complete=True):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": verdict,
        "mode": "strict",
        "violations": [{
            "decision_id": "test_002",
            "severity": verdict,
            "rule_type": "FORBID_LITERAL",
            "rule": VIOLATION,
            "trigger": VIOLATION,
        }],
        "freshness": [],
    }
    if not evaluation_complete:
        payload["evaluation_complete"] = False
        payload["applicability"] = [{
            "decision_id": "test_003",
            "rule_type": "FORBID_LITERAL",
            "rule_value": "EXPERIMENTAL_MARKER_XY",
            "outcome": "UNKNOWN",
            "reason": "outside policy root",
        }]
    return json.dumps(payload)


def _gate(tmp_path, stdout="", stderr="", exc=None, envelope=None):
    fake = MagicMock(returncode=0, stdout=stdout, stderr=stderr)
    out, err = io.StringIO(), io.StringIO()

    def _runner(command, **kwargs):
        if exc is not None:
            raise exc
        return fake

    with patch("mneme.integrations.kiro.hook.subprocess.run", _runner):
        rc = main(stdin=io.StringIO(envelope or _envelope(tmp_path)), stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


# --- modes ---

def test_strict_mode_blocks_warn_verdict(tmp_path):
    project = _project(tmp_path)
    rc, out, err = _gate(project, stdout=_verdict("WARN"))
    assert rc != 0
    assert out == ""


def test_strict_mode_blocks_fail_verdict_with_reason_on_stderr(tmp_path):
    project = _project(tmp_path)
    rc, out, err = _gate(project, stdout=_verdict("FAIL"))
    assert rc != 0
    assert VIOLATION in err or "test_002" in err
    assert out == ""


def test_warn_mode_returns_zero_and_surfaces_warning_to_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    project = _project(tmp_path)
    rc, out, _ = _gate(project, stdout=_verdict("FAIL"))
    assert rc == 0
    assert "[mneme] WARN" in out
    assert "test_002" in out or VIOLATION in out


def test_invalid_hook_mode_falls_back_to_strict(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "bogus")
    project = _project(tmp_path)
    rc, _, _ = _gate(project, stdout=_verdict("FAIL"))
    assert rc != 0


def test_pass_verdict_does_not_weaken_kiro_permission_flow(tmp_path):
    """PASS emits nothing: Kiro's own permission prompts stay in effect."""
    project = _project(tmp_path)
    rc, out, _ = _gate(project, stdout=_verdict("PASS"))
    assert rc == 0
    assert out == ""


# --- no memory -> quiet allow ---

def test_no_project_memory_quiet_zero(tmp_path):
    rc, out, _ = _gate(tmp_path, envelope=_envelope(tmp_path))
    assert rc == 0
    assert out == ""


# --- fail-open boundaries, all visibly ---

def test_subprocess_timeout_fails_open_visibly(tmp_path):
    project = _project(tmp_path)
    rc, out, _ = _gate(
        project, exc=subprocess.TimeoutExpired(cmd="mneme", timeout=10)
    )
    assert rc == 0
    assert "UNEVALUATED" in out


def test_subprocess_oserror_fails_open_visibly(tmp_path):
    project = _project(tmp_path)
    rc, out, _ = _gate(project, exc=OSError("permission denied"))
    assert rc == 0
    assert "UNEVALUATED" in out


def test_interpreter_missing_fails_open_visibly(tmp_path):
    project = _project(tmp_path)
    rc, out, _ = _gate(project, exc=FileNotFoundError(sys.executable))
    assert rc == 0
    assert "UNEVALUATED" in out


def test_unparseable_verdict_fails_open_visibly(tmp_path):
    project = _project(tmp_path)
    rc, out, err = _gate(
        project,
        stdout="Traceback (most recent call last): ...",
        stderr="crash detail",
    )
    assert rc == 0
    assert "UNEVALUATED" in out
    assert "crash detail" in err


def test_wrong_schema_verdict_is_not_trusted(tmp_path):
    """JSON without the mneme.check/v1 schema is not a verdict; a bare exit
    code is never one either."""
    project = _project(tmp_path)
    bogus = json.dumps({"verdict": "FAIL"})
    rc, out, _ = _gate(project, stdout=bogus)
    assert rc == 0
    assert "UNEVALUATED" in out


def test_stale_cli_detected_and_reported_visibly(tmp_path):
    project = _project(tmp_path)
    stale = "unrecognized arguments: --json --target-path"
    rc, out, err = _gate(project, stderr=stale)
    assert rc == 0
    assert "ENFORCEMENT IS INACTIVE" in err
    assert "UNEVALUATED" in out


def test_incomplete_applicability_fails_open_visibly(tmp_path):
    project = _project(tmp_path)
    rc, out, err = _gate(project, stdout=_verdict(evaluation_complete=False))
    assert rc == 0
    assert "UNEVALUATED" in out
    assert "unknown" in err.lower()


def test_materialization_failure_fails_open_visibly(tmp_path):
    from mneme.integrations.claude_code.hook import MaterializeError
    project = _project(tmp_path)
    out, err = io.StringIO(), io.StringIO()
    with patch(
        "mneme.integrations.kiro.hook.introduced_content",
        side_effect=MaterializeError("cannot read target"),
    ), patch("mneme.integrations.kiro.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO(_envelope(project)), stderr=err, stdout=out)
    assert rc == 0
    assert "UNEVALUATED" in out.getvalue()
    mrun.assert_not_called()


# --- diagnostics are ASCII-safe ---

def test_diagnostics_are_ascii(tmp_path):
    project = _project(tmp_path)
    rc, out, err = _gate(project, stdout=_verdict())
    assert (out + err).isascii()


# --- child invocation contract ---

def test_check_invocation_contract(tmp_path):
    """sys.executable -m mneme check with memory/query/mode/json options and
    the resolved absolute --target-path."""
    project = _project(tmp_path)
    mem = tmp_path / ".mneme" / "project_memory.json"
    commands = []

    def _runner(command, **kwargs):
        commands.append(list(command))
        return MagicMock(returncode=0, stdout="", stderr="")

    envelope = json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(tmp_path),
        "tool_name": "write",
        "tool_input": {"path": "abs_check.py", "content": "a\n"},
    })
    with patch("mneme.integrations.kiro.hook.subprocess.run", _runner):
        main(stdin=io.StringIO(envelope), stderr=io.StringIO())

    command = commands[0]
    assert command[:4] == [sys.executable, "-m", "mneme", "check"]
    assert command[command.index("--memory") + 1] == str(mem)
    assert command[command.index("--query") + 1] == "edit to abs_check.py"
    assert "--json" in command and "--mode" in command
    target = Path(command[command.index("--target-path") + 1])
    assert target.is_absolute()


def test_child_env_pins_package_root(tmp_path):
    from mneme.integrations.claude_code.hook import _child_env as expected_env
    from mneme.integrations.kiro.hook import _child_env as kiro_env
    # The Kiro hook reuses the Claude hook's pinned-PYTHONPATH environment.
    assert kiro_env is expected_env

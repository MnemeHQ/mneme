"""M1c tests: Codex gate delegation to the existing mneme check contract.

All checks run through an injectable runner; no real subprocess is spawned.
The frozen R0 fixture supplies the proposal; a temporary governed project
supplies memory discovery.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mneme.integrations.codex_cli.gate import (
    DENY,
    FAIL_OPEN,
    PASS,
    SKIP,
    WARN,
    codex_deny_output,
    evaluate_apply_patch,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FROZEN = "pretooluse_applypatch_addfile_allow.json"


def _verdict_stdout(verdict="PASS", **overrides):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": verdict,
        "mode": "strict",
        "violations": [],
        "freshness": [],
        "evaluation_complete": True,
    }
    payload.update(overrides)
    return json.dumps(payload)


class RecordingRunner:
    """Stands in for subprocess.run; records the invocation."""

    def __init__(self, stdout="", stderr="", returncode=0, raise_exc=None):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.raise_exc = raise_exc
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.raise_exc is not None:
            raise self.raise_exc
        return subprocess.CompletedProcess(
            command, self.returncode, stdout=self.stdout, stderr=self.stderr
        )

    @property
    def last(self):
        return self.calls[-1]


def _governed_project(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text('{"decisions": []}', encoding="utf-8")
    return tmp_path, memory


def _evaluate(tmp_path, runner, mode=None, fixture=FROZEN):
    return evaluate_apply_patch(
        json.loads((FIXTURES / fixture).read_text(encoding="utf-8")),
        cwd=str(tmp_path),
        mode=mode,
        check_runner=runner,
    )


# 1. Frozen Add File payload -> exact mneme check invocation ------------------


def test_frozen_payload_produces_exact_invocation(tmp_path, monkeypatch):
    project, memory = _governed_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout("PASS"))
    result = _evaluate(project, runner)

    assert len(runner.calls) == 1
    command, kwargs = runner.last
    assert command[0] == sys.executable
    assert command[1:5] == ["-m", "mneme", "check", "--memory"]
    assert command[5] == str(memory)
    assert command[6] == "--input"
    input_path = Path(command[7])
    assert "--query" in command
    assert command[command.index("--query") + 1] == "edit to probe_target.py"
    assert command[command.index("--mode") + 1] == "strict"
    assert "--json" in command
    assert command[command.index("--target-path") + 1] == str(project / "probe_target.py")
    # Temp input materialized the introduced content and was cleaned up.
    assert not input_path.exists()
    assert result.action == PASS


# 2. PASS -> no permission override -------------------------------------------


def test_pass_returns_pass_with_no_deny_output(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    result = _evaluate(project, RecordingRunner(stdout=_verdict_stdout("PASS")))
    assert result.action == PASS
    assert codex_deny_output(result) is None


# 3. Strict violation -> proven deny ------------------------------------------


def test_strict_violation_denies_with_mneme_reason(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    violation = [{
        "decision_id": "storage_json",
        "decision_text": "Use JSON storage only",
        "severity": "FAIL",
        "rule": "introduce ORM",
        "trigger": "ORM",
        "input_path": "probe_target.py",
    }]
    runner = RecordingRunner(
        stdout=_verdict_stdout("FAIL", violations=violation)
    )
    result = _evaluate(project, runner)

    assert result.action == DENY
    assert "[storage_json]" in result.reason and "ORM" in result.reason

    wire = codex_deny_output(result)
    assert wire == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": result.reason,
        }
    }


def test_warn_mode_violation_is_non_blocking(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout("FAIL"))
    result = _evaluate(project, runner, mode="warn")
    assert result.action == WARN
    assert codex_deny_output(result) is None


# 4. UNKNOWN / malformed / timeout never becomes PASS -------------------------


def test_incomplete_evaluation_fails_open_with_applicability_reason(
    tmp_path, monkeypatch
):
    project, _ = _governed_project(tmp_path, monkeypatch)
    runner = RecordingRunner(
        stdout=_verdict_stdout(
            "PASS",
            evaluation_complete=False,
            applicability=[{
                "decision_id": "d1",
                "rule_type": "path",
                "rule_value": "**/db/**",
                "outcome": "UNKNOWN",
                "reason": "unmatched",
            }],
        )
    )
    result = _evaluate(project, runner)
    assert result.action == FAIL_OPEN
    assert result.evaluation_complete is False
    assert "unknown" in result.reason.lower()
    assert codex_deny_output(result) is None


def test_malformed_verdict_json_fails_open(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    result = _evaluate(project, RecordingRunner(stdout="Traceback (most recent call last):"))
    assert result.action == FAIL_OPEN


def test_wrong_schema_fails_open(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    result = _evaluate(project, RecordingRunner(stdout=_verdict_stdout().replace(
        "mneme.check/v1", "mneme.check/v2"
    )))
    assert result.action == FAIL_OPEN


def test_timeout_fails_open(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    runner = RecordingRunner(raise_exc=subprocess.TimeoutExpired(cmd="x", timeout=10))
    result = _evaluate(project, runner)
    assert result.action == FAIL_OPEN


def test_launch_failure_fails_open(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    for exc in (FileNotFoundError("python"), OSError("boom")):
        result = _evaluate(project, RecordingRunner(raise_exc=exc))
        assert result.action == FAIL_OPEN


def test_parse_failure_fails_open_as_not_evaluated(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    payload = json.loads((FIXTURES / FROZEN).read_text(encoding="utf-8"))
    payload["tool_input"]["command"] = (
        "*** Begin Patch\n*** Update File: probe_target.py\n@@ -1 +1 @@\n*** End Patch"
    )
    result = evaluate_apply_patch(payload, cwd=str(project), check_runner=RecordingRunner())
    assert result.action == FAIL_OPEN
    assert "proposal not evaluated" in result.reason


# 5. Target path propagation ----------------------------------------------------


def test_absolute_target_path_reaches_target_path_flag(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout())
    _evaluate(project, runner)
    command, _ = runner.last
    assert command[command.index("--target-path") + 1] == str(
        project / "probe_target.py"
    )


# 6. Temp input always cleaned up ------------------------------------------------


def test_temp_file_cleaned_up_on_runner_exception(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    runner = RecordingRunner(raise_exc=subprocess.TimeoutExpired(cmd="x", timeout=1))
    _evaluate(project, runner)
    # The failed call's temp file must not survive.
    command, _ = runner.last
    assert not Path(command[command.index("--input") + 1]).exists()


# SKIP paths ---------------------------------------------------------------------


def test_no_project_memory_skips(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    empty = tmp_path / "not-governed"
    empty.mkdir()
    result = _evaluate(empty, RecordingRunner(stdout=_verdict_stdout()))
    assert result.action == SKIP


def test_blank_introduced_content_skips(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    payload = json.loads((FIXTURES / FROZEN).read_text(encoding="utf-8"))
    payload["tool_input"]["command"] = (
        "*** Begin Patch\n*** Add File: blank.py\n+\n+\n*** End Patch"
    )
    result = evaluate_apply_patch(
        payload, cwd=str(project), check_runner=RecordingRunner(stdout=_verdict_stdout())
    )
    assert result.action == SKIP


# --- M1e-d: Update File path --------------------------------------------------


def _update_payload(tmp_path, command):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {"command": command},
    }


def _seeded_project(tmp_path, monkeypatch, seed='def existing():\n    return 1\n'):
    project, memory = _governed_project(tmp_path, monkeypatch)
    (project / "service.py").write_text(seed, encoding="utf-8")
    return project


def _update_command(path, body="@@\n def existing():\n-    return 1\n+    return 42\n"):
    return f"*** Begin Patch\n*** Update File: {path}\n{body}*** End Patch"


def test_update_introducing_violation_denies_with_real_target_path(
        tmp_path, monkeypatch):
    project = _seeded_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout("FAIL"))
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(project / "service.py")),
        cwd=str(project), check_runner=runner)
    assert result.action == DENY
    command, _ = runner.last
    assert command[command.index("--target-path") + 1] == str(project / "service.py")


def test_compliant_update_passes_and_sends_snapshot_delta(tmp_path, monkeypatch):
    project = _seeded_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout("PASS"))
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(project / "service.py")),
        cwd=str(project), check_runner=runner)
    assert result.action == PASS
    command, _ = runner.last
    input_path = Path(command[command.index("--input") + 1])
    assert not input_path.exists()  # consumed and cleaned up


def test_update_warn_mode_is_non_blocking(tmp_path, monkeypatch):
    project = _seeded_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout("FAIL"))
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(project / "service.py")),
        cwd=str(project), mode="warn", check_runner=runner)
    assert result.action == WARN


def test_update_target_outside_root_fails_open_not_evaluated(
        tmp_path, monkeypatch):
    project = _seeded_project(tmp_path, monkeypatch)
    outside = tmp_path.parent / "elsewhere.py"
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(outside)),
        cwd=str(project), check_runner=RecordingRunner())
    assert result.action == FAIL_OPEN
    assert "escapes" in result.reason
    assert "not evaluated" in result.reason


def test_update_missing_file_fails_open_not_evaluated(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(project / "missing.py")),
        cwd=str(project), check_runner=RecordingRunner())
    assert result.action == FAIL_OPEN
    assert "could not be read" in result.reason


def test_update_non_utf8_file_fails_open_not_evaluated(tmp_path, monkeypatch):
    project, _ = _governed_project(tmp_path, monkeypatch)
    target = project / "service.py"
    target.write_bytes(b"\xff\xfe\x00bad")
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(target)),
        cwd=str(project), check_runner=RecordingRunner())
    assert result.action == FAIL_OPEN
    assert "not evaluated" in result.reason


def test_update_parser_mismatch_fails_open_not_evaluated(tmp_path, monkeypatch):
    project = _seeded_project(
        tmp_path, monkeypatch, seed="def existing():\n    return UNRELATED\n")
    result = evaluate_apply_patch(
        _update_payload(project, _update_command(project / "service.py")),
        cwd=str(project), check_runner=RecordingRunner())
    assert result.action == FAIL_OPEN
    assert "proposal not evaluated" in result.reason


def test_relative_update_path_resolves_inside_root(tmp_path, monkeypatch):
    project = _seeded_project(tmp_path, monkeypatch)
    runner = RecordingRunner(stdout=_verdict_stdout("PASS"))
    result = evaluate_apply_patch(
        _update_payload(project, _update_command("service.py")),
        cwd=str(project), check_runner=runner)
    assert result.action == PASS
    command, _ = runner.last
    assert command[command.index("--target-path") + 1] == str(project / "service.py")


def test_blank_only_update_skips(tmp_path, monkeypatch):
    project = _seeded_project(tmp_path, monkeypatch)
    cmd = _update_command(
        project / "service.py",
        "@@\n def existing():\n-    return 1\n+\n+\n+def third():\n+    return 3\n")
    # make it blank-only: additions that are all blank
    cmd = ("*** Begin Patch\n*** Update File: "
           + str(project / "service.py").replace(chr(92), chr(92))
           + "\n@@\n def existing():\n-    return 1\n+\n*** End Patch")
    result = evaluate_apply_patch(
        _update_payload(project, cmd), cwd=str(project),
        check_runner=RecordingRunner(stdout=_verdict_stdout()))
    assert result.action == SKIP

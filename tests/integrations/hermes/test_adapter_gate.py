"""H2 enforcement tests: Hermes payloads through the shared Mneme check path."""

import json
from types import SimpleNamespace

import pytest

from mneme.integrations.hermes import adapter
from mneme.integrations.hermes.adapter import ACTION_DENY, ACTION_SKIP, MnemeHermes, directive_for


def _verdict(verdict="FAIL", evaluation_complete=True):
    stdout = json.dumps(
        {
            "schema": "mneme.check/v1",
            "verdict": verdict,
            "mode": "strict",
            "evaluation_complete": evaluation_complete,
            "violations": (
                [
                    {
                        "decision_id": "D1",
                        "decision_text": "never do the bad thing",
                        "severity": "FAIL",
                        "rule": "no forbidden token",
                        "trigger": "FORBIDDEN_TOKEN",
                        "kind": "literal",
                        "rule_type": "FORBID_LITERAL",
                        "input_path": "",
                        "selector": "",
                    }
                ]
                if verdict != "PASS"
                else []
            ),
            "applicability": [],
            "freshness": [],
        }
    )
    if not evaluation_complete:
        stdout = json.dumps(
            {
                "schema": "mneme.check/v1",
                "verdict": "WARN",
                "mode": "strict",
                "evaluation_complete": False,
                "violations": [],
                "applicability": [
                    {
                        "decision_id": "D2",
                        "rule_type": "FORBID_LITERAL",
                        "rule_value": "X",
                        "outcome": "UNKNOWN",
                        "reason": "path applicability unknown",
                    }
                ],
                "freshness": [],
            }
        )
    return SimpleNamespace(returncode=2 if verdict != "PASS" else 0, stdout=stdout, stderr="")


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text(
        json.dumps(
            {
                "version": 1,
                "decisions": [
                    {
                        "id": "D1",
                        "decision": "never do the bad thing",
                        "rules": [{"type": "FORBID_LITERAL", "value": "FORBIDDEN_TOKEN"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(adapter, "find_memory", lambda start: mem)
    return MnemeHermes(project_dir=str(tmp_path))


def _runner(result=None, error=None):
    def run(*args, **kwargs):
        if error is not None:
            raise error
        return result

    return run


class TestWriteFileGate:
    def test_violating_write_denies_with_block_directive(self, tmp_path, gate):
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call(
            "write_file",
            {"path": str(tmp_path / "new.py"), "content": "x = FORBIDDEN_TOKEN\n"},
            cwd=str(tmp_path),
        )
        assert result.action == ACTION_DENY
        assert "FORBIDDEN_TOKEN" in result.reason
        assert directive_for(result) == {"action": "block", "message": result.reason}

    def test_compliant_write_passes_without_directive(self, tmp_path, gate):
        gate._check_runner = _runner(_verdict("PASS"))
        result = gate.evaluate_tool_call(
            "write_file", {"path": str(tmp_path / "new.py"), "content": "ok = True\n"},
            cwd=str(tmp_path),
        )
        assert result.action == adapter.ACTION_ALLOW
        assert directive_for(result) is None

    def test_pre_tool_call_hook_emits_block(self, tmp_path, gate):
        gate._check_runner = _runner(_verdict("FAIL"))
        payload = gate.pre_tool_call(
            tool_name="write_file",
            args={"path": str(tmp_path / "new.py"), "content": "FORBIDDEN_TOKEN\n"},
        )
        assert payload["action"] == "block"
        assert payload["message"]


class TestPatchReplaceGate:
    def test_replacement_introducing_violation_is_caught(self, tmp_path, gate):
        target = tmp_path / "svc.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call(
            "patch",
            {
                "mode": "replace",
                "path": str(target),
                "old_string": "return 1",
                "new_string": "return FORBIDDEN_TOKEN",
            },
            cwd=str(tmp_path),
        )
        assert result.action == ACTION_DENY

    def test_unmatched_old_string_fails_open(self, tmp_path, gate):
        target = tmp_path / "svc.py"
        target.write_text("a = 1\n", encoding="utf-8")
        seen = {}

        def runner(command, **kwargs):
            seen["called"] = True
            return _verdict("PASS")

        gate._check_runner = runner
        result = gate.evaluate_tool_call(
            "patch",
            {"mode": "replace", "path": str(target), "old_string": "NOPE", "new_string": "x"},
            cwd=str(tmp_path),
        )
        assert result.action == adapter.ACTION_FAIL_OPEN
        assert "called" not in seen


class TestV4APatchGate:
    def test_add_file_operation_is_checked(self, tmp_path, gate):
        patch_text = (
            "*** Begin Patch\n"
            "*** Add File: probe_target.py\n"
            "+x = FORBIDDEN_TOKEN\n"
            "*** End Patch"
        )
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call("patch", {"mode": "patch", "patch": patch_text},
                                        cwd=str(tmp_path))
        assert result.action == ACTION_DENY
        assert result.file_path.endswith("probe_target.py")

    def test_update_file_uses_current_snapshot(self, tmp_path, gate):
        target = tmp_path / "svc.py"
        target.write_text("def existing():\n    return 1\n", encoding="utf-8")
        patch_text = (
            "*** Begin Patch\n"
            f"*** Update File: {target}\n"
            "@@\n"
            " def existing():\n"
            "-    return 1\n"
            "+    return FORBIDDEN_TOKEN\n"
            "*** End Patch"
        )
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call("patch", {"mode": "patch", "patch": patch_text},
                                        cwd=str(tmp_path))
        assert result.action == ACTION_DENY

    def test_delete_only_patch_introduces_nothing(self, tmp_path, gate):
        patch_text = "*** Begin Patch\n*** Delete File: gone.py\n*** End Patch"

        def runner(command, **kwargs):
            raise AssertionError("check must not run for a pure deletion")

        gate._check_runner = runner
        result = gate.evaluate_tool_call("patch", {"mode": "patch", "patch": patch_text},
                                        cwd=str(tmp_path))
        assert result.action == adapter.ACTION_ALLOW

    def test_unparseable_patch_fails_open(self, gate):
        result = gate.evaluate_tool_call(
            "patch", {"mode": "patch", "patch": "*** Begin Patch\n*** Nonsense\n"}, cwd="."
        )
        assert result.action == adapter.ACTION_FAIL_OPEN
        assert "unparseable" in result.reason

    def test_missing_update_snapshot_is_disclosed_not_guessed(self, tmp_path, gate):
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: does_not_exist.py\n"
            "@@\n"
            "-old\n"
            "+new\n"
            "*** End Patch"
        )

        def runner(command, **kwargs):
            # The unevaluated operation must fail open before any check runs.
            raise AssertionError("no check should run on an unavailable snapshot")

        gate._check_runner = runner
        result = gate.evaluate_tool_call("patch", {"mode": "patch", "patch": patch_text},
                                        cwd=str(tmp_path))
        assert result.action == adapter.ACTION_FAIL_OPEN
        assert "unevaluated" in result.reason


class TestTerminalPreflight:
    def test_class_a_heredoc_write_is_checked(self, tmp_path, gate):
        command = f"cat > {tmp_path / 'out.txt'} << 'EOF'\nFORBIDDEN_TOKEN\nEOF"
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call("terminal", {"command": command}, cwd=str(tmp_path))
        assert result.action == ACTION_DENY

    def test_non_heredoc_command_passes_unevaluated(self, tmp_path, gate):
        def runner(command, **kwargs):
            raise AssertionError("class B/C commands must not be checked pre-execution")

        gate._check_runner = runner
        result = gate.evaluate_tool_call(
            "terminal", {"command": "echo FORBIDDEN_TOKEN > leak.txt"}, cwd=str(tmp_path)
        )
        assert result.action == ACTION_SKIP
        assert "classified" in result.reason

    def test_workdir_used_for_relative_targets(self, tmp_path, gate):
        workdir = tmp_path / "sub"
        workdir.mkdir()
        command = "cat > out.txt << 'EOF'\nFORBIDDEN_TOKEN\nEOF"
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call(
            "terminal", {"command": command, "workdir": str(workdir)}, cwd=str(tmp_path)
        )
        assert result.action == ACTION_DENY
        assert result.file_path == str(workdir / "out.txt")


class TestUnevaluatedSurfaces:
    @pytest.mark.parametrize("tool,args", [
        ("execute_code", {"code": "open('x.py','w').write('FORBIDDEN_TOKEN')"}),
        ("process", {"command": "python gen.py", "action": "start"}),
        ("read_file", {"path": "x"}),
    ])
    def test_never_claims_governance_over_bypass_surfaces(self, gate, tool, args):
        result = gate.evaluate_tool_call(tool, args, cwd=".")
        assert result.action == ACTION_SKIP


class TestFailureSemantics:
    def test_check_launch_failure_fails_open(self, tmp_path, gate):
        gate._check_runner = _runner(error=OSError("no interpreter"))
        result = gate.evaluate_tool_call(
            "write_file", {"path": str(tmp_path / "n.py"), "content": "x\n"}, cwd=str(tmp_path)
        )
        assert result.action == adapter.ACTION_FAIL_OPEN

    def test_unparseable_verdict_fails_open(self, tmp_path, gate):
        gate._check_runner = _runner(SimpleNamespace(returncode=1, stdout="boom", stderr=""))
        result = gate.evaluate_tool_call(
            "write_file", {"path": str(tmp_path / "n.py"), "content": "x\n"}, cwd=str(tmp_path)
        )
        assert result.action == adapter.ACTION_FAIL_OPEN

    def test_incomplete_evaluation_fails_open(self, tmp_path, gate):
        gate._check_runner = _runner(_verdict(evaluation_complete=False))
        result = gate.evaluate_tool_call(
            "write_file", {"path": str(tmp_path / "n.py"), "content": "x\n"}, cwd=str(tmp_path)
        )
        assert result.action == adapter.ACTION_FAIL_OPEN
        assert result.evaluation_complete is False

    def test_no_project_memory_has_no_opinion(self, tmp_path, monkeypatch):
        monkeypatch.setattr(adapter, "find_memory", lambda start: None)
        gate = MnemeHermes(project_dir=str(tmp_path))
        result = gate.evaluate_tool_call(
            "write_file", {"path": "x.py", "content": "FORBIDDEN_TOKEN\n"}, cwd=str(tmp_path)
        )
        assert result.action == ACTION_SKIP


class TestModeSemantics:
    def test_warn_mode_flags_but_does_not_block(self, tmp_path, gate, monkeypatch):
        monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
        gate._check_runner = _runner(_verdict("FAIL"))
        result = gate.evaluate_tool_call(
            "write_file", {"path": str(tmp_path / "n.py"), "content": "x\n"}, cwd=str(tmp_path)
        )
        assert result.action == adapter.ACTION_WARN
        assert directive_for(result) is None

    def test_strict_is_default(self, tmp_path, gate, monkeypatch):
        monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
        seen = {}
        gate._check_runner = lambda command, **kw: seen.update(
            mode=command[command.index("--mode") + 1]
        ) or _verdict("PASS")
        gate.evaluate_tool_call(
            "write_file", {"path": str(tmp_path / "n.py"), "content": "x\n"}, cwd=str(tmp_path)
        )
        assert seen["mode"] == "strict"


class TestCheckInvocation:
    def test_invokes_shared_cli_contract(self, tmp_path, gate):
        seen = {}
        gate._check_runner = lambda command, **kwargs: seen.update(
            command=command, **kwargs
        ) or _verdict("PASS")
        path = str(tmp_path / "n.py")
        gate.evaluate_tool_call("write_file", {"path": path, "content": "x\n"}, cwd=str(tmp_path))
        cmd = seen["command"]
        assert cmd[1:3] == ["-m", "mneme"]
        assert "--json" in cmd
        assert "--target-path" in cmd
        assert path in cmd
        assert seen["timeout"] == adapter._CHECK_TIMEOUT_SECONDS

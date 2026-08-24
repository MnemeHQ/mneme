"""Gate tests: verdict translation through the shared Mneme enforcement path."""

import json
from types import SimpleNamespace

import pytest

from mneme.integrations.antigravity import adapter


def _write_event(tmp_path, content="FORBIDDEN_TOKEN here\n"):
    return adapter.ToolEvent(
        tool_name="Write",
        file_path=str(tmp_path / "new.py"),
        cwd=str(tmp_path),
        tool_input={"file_path": str(tmp_path / "new.py"), "content": content},
    )


def _hook_input(event):
    return json.dumps(
        {
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": event.file_path,
                    "CodeContent": event.tool_input["content"],
                },
            },
            "workspacePaths": [event.cwd],
        }
    )


def _verdict(verdict="FAIL", evaluation_complete=True):
    return SimpleNamespace(
        returncode=2 if verdict != "PASS" else 0,
        stdout=json.dumps(
            {
                "schema": "mneme.check/v1",
                "verdict": verdict,
                "mode": "strict",
                "evaluation_complete": evaluation_complete,
                "violations": [
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
                ],
                "applicability": [],
                "freshness": [],
            }
        )
        if evaluation_complete or verdict == "PASS"
        else json.dumps(
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
        ),
        stderr="",
    )


@pytest.fixture()
def memory(tmp_path, monkeypatch):
    """A minimal governed project: one typed literal rule."""
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir()
    mem.write_text(
        json.dumps(
            {
                "version": 1,
                "decisions": [
                    {
                        "id": "D1",
                        "text": "never do the bad thing",
                        "rules": [{"type": "FORBID_LITERAL", "value": "FORBIDDEN_TOKEN"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(adapter, "find_memory", lambda start: mem)
    return mem


class _FakeIO:
    def __init__(self, data=""):
        self.data = data

    def read(self):
        return self.data

    def write(self, text):
        self.data += text
        return len(text)


def _invoke(raw, check_runner=None):
    stdin, stdout, stderr = _FakeIO(raw), _FakeIO(), _FakeIO()
    code = adapter.main(stdin=stdin, stderr=stderr, stdout=stdout, check_runner=check_runner)
    return code, stdout.data, stderr.data


def _runner(result=None, error=None):
    def run(*args, **kwargs):
        if error is not None:
            raise error
        return result

    return run


class TestVerdictTranslation:
    def test_compliant_mutation_is_not_blocked(self, tmp_path, memory):
        code, out, _ = _invoke(
            _hook_input(_write_event(tmp_path, "clean = True\n")),
            check_runner=_runner(_verdict("PASS")),
        )
        assert code == 0
        assert json.loads(out) == {}

    def test_violating_mutation_is_denied_with_reason(self, tmp_path, memory):
        code, out, _ = _invoke(
            _hook_input(_write_event(tmp_path)),
            check_runner=_runner(_verdict("FAIL")),
        )
        assert code == 0
        payload = json.loads(out)
        assert payload["decision"] == "deny"
        assert "D1" in payload["reason"]
        assert "FORBIDDEN_TOKEN" in payload["reason"]

    def test_block_response_is_the_only_active_decision(self, tmp_path, memory):
        """PASS must not emit decision=allow: that would auto-grant in Antigravity."""
        _, out, _ = _invoke(
            _hook_input(_write_event(tmp_path, "ok\n")),
            check_runner=_runner(_verdict("PASS")),
        )
        assert "allow" not in json.loads(out)


class TestFailureSemantics:
    def test_unparseable_verdict_fails_open_visibly(self, tmp_path, memory):
        crash = SimpleNamespace(returncode=1, stdout="Traceback...", stderr="boom")
        code, out, err = _invoke(
            _hook_input(_write_event(tmp_path)),
            check_runner=_runner(crash),
        )
        assert code == 0
        assert json.loads(out) == {}
        assert "Failing open" in err

    def test_check_launch_failure_fails_open(self, tmp_path, memory):
        code, out, err = _invoke(
            _hook_input(_write_event(tmp_path)),
            check_runner=_runner(error=OSError("no interpreter")),
        )
        assert code == 0
        assert json.loads(out) == {}
        assert "could not run" in err

    def test_incomplete_evaluation_fails_open(self, tmp_path, memory):
        code, out, err = _invoke(
            _hook_input(_write_event(tmp_path)),
            check_runner=_runner(_verdict(evaluation_complete=False)),
        )
        assert code == 0
        assert json.loads(out) == {}
        assert "unknown" in err

    def test_malformed_hook_input_fails_open(self, memory):
        code, out, err = _invoke("not json")
        assert code == 0
        assert json.loads(out) == {}
        assert "bad hook event" in err


class TestModeSemantics:
    def test_warn_mode_never_blocks(self, tmp_path, memory, monkeypatch):
        monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
        code, out, err = _invoke(
            _hook_input(_write_event(tmp_path)),
            check_runner=_runner(_verdict("FAIL")),
        )
        assert code == 0
        assert "decision" not in json.loads(out)
        assert "not blocked" in err

    def test_strict_is_default(self, tmp_path, memory, monkeypatch):
        monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
        seen = {}

        def runner(command, **kwargs):
            seen["mode"] = command[command.index("--mode") + 1]
            return _verdict("PASS")

        _, _, _ = _invoke(_hook_input(_write_event(tmp_path)), check_runner=runner)
        assert seen["mode"] == "strict"


class TestNoOpinionPaths:
    def test_read_only_tool_emits_empty_object(self, memory):
        raw = json.dumps(
            {"toolCall": {"name": "view_file", "args": {"AbsolutePath": "x"}}}
        )
        code, out, _ = _invoke(raw)
        assert code == 0
        assert json.loads(out) == {}

    def test_no_memory_has_no_opinion(self, tmp_path, monkeypatch):
        monkeypatch.setattr(adapter, "find_memory", lambda start: None)
        code, out, _ = _invoke(_hook_input(_write_event(tmp_path)))
        assert code == 0
        assert json.loads(out) == {}


class TestCheckInvocation:
    def test_invokes_shared_cli_contract(self, tmp_path, memory):
        seen = {}

        def runner(command, **kwargs):
            seen.update(kwargs)
            seen["command"] = command
            return _verdict("PASS")

        event = _write_event(tmp_path)
        _invoke(_hook_input(event), check_runner=runner)
        cmd = seen["command"]
        assert cmd[1:3] == ["-m", "mneme"]
        assert "--json" in cmd
        assert "--target-path" in cmd
        assert event.file_path in cmd
        assert seen["timeout"] == adapter._CHECK_TIMEOUT_SECONDS


class TestAdapterIndependence:
    def test_adapter_does_not_depend_on_decision_retriever(self):
        """Enforcement glue must stay retrieval-free (retrieval/enforcement separation)."""
        import ast
        from pathlib import Path

        source = Path(adapter.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = {a.name for a in node.names}
                assert "DecisionRetriever" not in names
                assert node.module != "mneme.decision_retriever"
                assert not node.module.startswith("mneme.context_builder")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    assert "retriever" not in a.name

    def test_every_exit_path_emits_parseable_json(self, memory):
        for raw in ("not json", "", "{}", "null"):
            _, out, _ = _invoke(raw)
            if out:
                json.loads(out)

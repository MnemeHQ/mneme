"""Deterministic tests for the LangChain integration.

The model boundary does not exist at this layer and the ``mneme check``
subprocess is replaced by an injectable ``check_runner`` returning crafted
verdict payloads, so no API, CLI, or network access occurs. LangChain is
NOT required for these tests: only the plain-Python adapter surface.
"""

import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.langchain import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    ACTION_WARN,
    MnemeLangChain,
)

SCHEMA = "mneme.check/v1"

MEMORY = {
    "meta": {
        "name": "langchain-test-project",
        "description": "Fixture for langchain integration tests",
        "version": "0.1.0",
        "owner": "test",
        "created": "2026-08-25",
    },
    "items": [],
    "decisions": [
        {
            "id": "store_001",
            "decision": "Use SQLite for local storage and database access",
            "rationale": "single-file portability",
            "scope": ["storage", "database"],
            "constraints": ["no postgres"],
            "anti_patterns": ["psycopg2"],
        },
    ],
}


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def verdict_payload(verdict: str, *, complete: bool = True, violations=None):
    payload = {
        "schema": SCHEMA,
        "verdict": verdict,
        "violations": violations or [],
        "evaluation_complete": complete,
    }
    if not complete:
        payload["applicability"] = [
            {
                "decision_id": "scoped_001",
                "rule_type": "FORBID_LITERAL",
                "rule_value": "install legacy-client",
                "outcome": "UNKNOWN",
                "reason": "input path outside policy root",
            }
        ]
    return json.dumps(payload)


FAIL_VIOLATION = {
    "decision_id": "store_001",
    "severity": "FAIL",
    "rule": "psycopg2",
    "trigger": "psycopg2",
}


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(MEMORY), encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def make_gate(project, runner, **kwargs):
    return MnemeLangChain(project_dir=project, check_runner=runner, **kwargs)


class TestContextPath:
    def test_relevant_decisions_injected_before_work(self, project):
        gate = make_gate(project, lambda *a, **k: completed())
        injection = gate.context_for_task("sqlite storage database decision")
        assert injection.decision_ids == ["store_001"]
        assert "[Mneme decisions applied]" in injection.text
        assert "store_001" in injection.text

    def test_trace_distinguishes_context_from_enforcement(self, project):
        gate = make_gate(project, lambda *a, **k: completed(verdict_payload("PASS")))
        gate.context_for_task("sqlite storage")
        gate.evaluate_tool_call(
            "edit_file",
            {"file_path": str(project / "app.py"), "old_string": "x = 1", "new_string": "y = 2"},
        )
        kinds = [e["kind"] for e in gate.trace]
        assert kinds == ["context_injection", "enforcement"]


class TestWriteTranslation:
    def test_forbidden_write_blocked_with_target_path(self, project):
        seen = {}

        def runner(command, **kwargs):
            seen["command"] = command
            input_path = command[command.index("--input") + 1]
            seen["checked_content"] = Path(input_path).read_text(encoding="utf-8")
            return completed(
                verdict_payload("FAIL", violations=[FAIL_VIOLATION])
            )

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call(
            "write_file",
            {"file_path": str(project / "db.py"), "content": "import psycopg2\n"},
        )
        assert result.action == ACTION_DENY
        assert result.verdict == "FAIL"
        assert "store_001" in result.reason
        assert "--target-path" in seen["command"]
        assert seen["command"][seen["command"].index("--target-path") + 1] == str(
            project / "db.py"
        )
        assert seen["checked_content"] == "import psycopg2\n"

    def test_compliant_write_passes_with_single_check(self, project):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return completed(verdict_payload("PASS"))

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call(
            "write_file",
            {"file_path": str(project / "util.py"), "content": "x = 1\n"},
        )
        assert result.action == ACTION_ALLOW
        assert len(calls) == 1


class TestEditTranslation:
    def test_edit_introduces_delta_only_not_preexisting_text(self, project):
        seed = project / "db.py"
        seed.write_text(
            "import psycopg2\nx = 1\n", encoding="utf-8"
        )  # pre-existing violation on disk
        seen = {}

        def runner(command, **kwargs):
            input_path = command[command.index("--input") + 1]
            seen["checked_content"] = Path(input_path).read_text(encoding="utf-8")
            return completed(verdict_payload("PASS"))

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call(
            "edit_file",
            {
                "file_path": str(seed),
                "old_string": "x = 1",
                "new_string": "y = 2",
            },
        )
        # The introduced delta ("y = 2") is checked; the pre-existing
        # forbidden import must NOT be attributed to this edit (ADR-018).
        assert result.action == ACTION_ALLOW
        assert seen["checked_content"] == "y = 2"

    def test_edit_introducing_violation_is_denied(self, project):
        def runner(command, **kwargs):
            return completed(verdict_payload("FAIL", violations=[FAIL_VIOLATION]))

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call(
            "edit_file",
            {
                "file_path": str(project / "app.py"),
                "old_string": "x = 1",
                "new_string": "import psycopg2\nx = 1",
            },
        )
        assert result.action == ACTION_DENY

    def test_materialize_failure_fails_open(self, project):
        gate = make_gate(project, lambda *a, **k: completed())
        result = gate.evaluate_tool_call(
            "edit_file",
            {
                "file_path": str(project / "app.py"),
                "old_string": "not-there",
                "new_string": "z",
            },
        )
        assert result.action == ACTION_FAIL_OPEN
        assert "cannot materialize" in result.reason


class TestVerdictPolicy:
    def write(self, project, content="x = 1\n"):
        return {"file_path": str(project / "out.py"), "content": content}

    def test_warn_mode_flags_without_blocking_decision(self, project, monkeypatch):
        monkeypatch.setenv("MNEME_HOOK_MODE", "warn")

        def runner(command, **kwargs):
            assert "warn" in command
            return completed(
                verdict_payload(
                    "WARN",
                    violations=[
                        {"decision_id": "store_001", "severity": "WARN", "rule": "no postgres", "trigger": "postgres"}
                    ],
                )
            )

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call("write_file", self.write(project))
        assert result.action == ACTION_WARN

    def test_explicit_strict_overrides_env(self, project, monkeypatch):
        monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
        calls = {}

        def runner(command, **kwargs):
            calls["mode"] = command[command.index("--mode") + 1]
            return completed(verdict_payload("FAIL", violations=[FAIL_VIOLATION]))

        gate = make_gate(project, runner, mode="strict")
        assert gate.evaluate_tool_call("write_file", self.write(project)).action == ACTION_DENY
        assert calls["mode"] == "strict"

    def test_unknown_evaluation_never_becomes_pass(self, project):
        def runner(command, **kwargs):
            return completed(verdict_payload("PASS", complete=False))

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call("write_file", self.write(project))
        assert result.action == ACTION_FAIL_OPEN
        assert result.evaluation_complete is False
        assert "unknown" in result.reason.lower()

    def test_unparseable_verdict_fails_open_visibly(self, project):
        def runner(command, **kwargs):
            return completed("Traceback (most recent call last): ...", returncode=1)

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call("write_file", self.write(project))
        assert result.action == ACTION_FAIL_OPEN
        assert "no parseable verdict" in result.reason

    def test_operational_failure_fails_open(self, project):
        def runner(command, **kwargs):
            raise OSError("spawn failed")

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call("write_file", self.write(project))
        assert result.action == ACTION_FAIL_OPEN
        assert "could not run mneme check" in result.reason


class TestClosedSurface:
    def test_unlisted_tools_skipped_with_zero_checker_calls(self, project):
        ran = []
        gate = make_gate(project, lambda *a, **k: ran.append(1) or completed())
        for tool_name in ("read_file", "ls", "glob", "grep", "execute", "bash"):
            result = gate.evaluate_tool_call(tool_name, {})
            assert result.action == ACTION_SKIP
            assert result.reason == "not a governed langchain file tool"
        assert not ran
        skips = [e for e in gate.trace if e.get("action") == ACTION_SKIP]
        assert len(skips) == 6

    def test_no_memory_skips_mapped_tool_without_checker_call(self, tmp_path):
        ran = []

        def runner(command, **kwargs):
            ran.append(command)
            return completed(verdict_payload("PASS"))

        gate = MnemeLangChain(project_dir=tmp_path, check_runner=runner)
        result = gate.evaluate_tool_call(
            "write_file", {"file_path": "f.py", "content": "x"}
        )
        assert result.action == ACTION_SKIP
        assert not ran

    def test_non_dict_args_treated_as_empty(self, project):
        ran = []

        def runner(command, **kwargs):
            ran.append(command)
            return completed(verdict_payload("PASS"))

        gate = make_gate(project, runner)
        result = gate.evaluate_tool_call("write_file", None)
        assert result.action == ACTION_SKIP
        assert not ran

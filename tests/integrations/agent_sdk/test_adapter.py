"""Deterministic tests for the Claude Agent SDK integration.

The model boundary is fully faked: the ``mneme check`` subprocess is
replaced by an injectable ``check_runner`` returning crafted verdict
payloads, so no API, CLI, or network access occurs.
"""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.agent_sdk import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    ACTION_WARN,
    MnemeAgentSdk,
)

SCHEMA = "mneme.check/v1"

MEMORY = {
    "meta": {
        "name": "sdk-test-project",
        "description": "Fixture for agent-sdk integration tests",
        "version": "0.1.0",
        "owner": "test",
        "created": "2026-08-21",
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
        {
            "id": "api_001",
            "decision": "HTTP client layer uses stdlib urllib only",
            "rationale": "no third-party HTTP dependencies",
            "scope": ["http", "client", "network"],
            "constraints": [],
            "anti_patterns": [],
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


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(MEMORY), encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def make_integration(project, runner):
    return MnemeAgentSdk(project_dir=project, check_runner=runner)


class TestContextPath:
    def test_relevant_decisions_injected_before_work(self, project):
        sdk = make_integration(project, lambda *a, **k: completed())
        injection = sdk.context_for_task("sqlite storage database decision")
        assert injection.decision_ids == ["store_001"]
        assert "[Mneme decisions applied]" in injection.text
        assert "store_001" in injection.text

    def test_uses_existing_retrieval_implementation(self, project):
        """Injection must come from the existing DecisionRetriever path."""
        from mneme.context_builder import format_decisions
        from mneme.decision_retriever import DecisionRetriever
        from mneme.memory_store import MemoryStore

        sdk = make_integration(project, lambda *a, **k: completed())
        query = "http client network"
        injection = sdk.context_for_task(query)

        store = MemoryStore(project / ".mneme" / "project_memory.json")
        store.load()
        expected = DecisionRetriever(store.decisions()).retrieve(query)
        assert injection.text == format_decisions(expected)
        assert injection.decision_ids == [
            s.decision.id for s in expected if s.score > 0.0
        ]

    def test_user_prompt_submit_shapes_additional_context(self, project):
        sdk = make_integration(project, lambda *a, **k: completed())
        out = sdk.user_prompt_submit({"prompt": "sqlite storage database"})
        assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert "store_001" in out["hookSpecificOutput"]["additionalContext"]

    def test_no_memory_yields_empty_injection(self, tmp_path):
        sdk = make_integration(tmp_path, lambda *a, **k: completed())
        injection = sdk.context_for_task("anything")
        assert injection.text == ""
        assert injection.decision_ids == []
        assert injection.memory_path is None

    def test_trace_distinguishes_context_from_enforcement(self, project):
        sdk = make_integration(project, lambda *a, **k: completed())
        sdk.context_for_task("sqlite storage")
        sdk.evaluate_mutation(
            "Edit",
            {"file_path": str(project / "app.py"), "old_string": "x = 1", "new_string": "y = 2"},
            cwd=str(project),
        )
        kinds = [e["kind"] for e in sdk.trace]
        assert kinds == ["context_injection", "enforcement"]


class TestEnforcementPath:
    def edit(self, project, new="y = 2"):
        return {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(project / "app.py"),
                "old_string": "x = 1",
                "new_string": new,
            },
            "cwd": str(project),
        }

    def test_compliant_mutation_passes(self, project):
        seen = {}

        def runner(command, **kwargs):
            seen["command"] = command
            return completed(verdict_payload("PASS"))

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(**self.edit(project))
        assert result.action == ACTION_ALLOW
        assert result.verdict == "PASS"
        assert "--json" in seen["command"]
        assert "--mode" in seen["command"]

    def test_violating_mutation_denied_with_actionable_reason(self, project):
        reason_text = (
            "mneme: FAIL - architectural decision violated\n"
            '  [store_001] FAIL "psycopg2" - trigger: psycopg2'
        )

        def runner(command, **kwargs):
            return completed(
                verdict_payload(
                    "FAIL",
                    violations=[
                        {
                            "decision_id": "store_001",
                            "severity": "FAIL",
                            "rule": "psycopg2",
                            "trigger": "psycopg2",
                        }
                    ],
                )
                + "\n"
            )  # stderr empty; reason comes from payload formatting

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(**self.edit(project))
        assert result.action == ACTION_DENY
        assert result.verdict == "FAIL"
        assert "store_001" in result.reason and "psycopg2" in result.reason

        sdk_out = sdk.pre_tool_use(self.edit(project))
        assert sdk_out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "store_001" in sdk_out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_target_path_applicability_preserved(self, project):
        captured = {}

        def runner(command, **kwargs):
            captured.update(zip(command, command[1:]))
            return completed(verdict_payload("PASS"))

        sdk = make_integration(project, runner)
        sdk.evaluate_mutation(**self.edit(project))
        assert captured["--target-path"] == str(project / "app.py")

    def test_unknown_evaluation_never_becomes_pass(self, project):
        def runner(command, **kwargs):
            return completed(verdict_payload("PASS", complete=False))

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(**self.edit(project))
        assert result.action == ACTION_FAIL_OPEN
        assert result.evaluation_complete is False
        assert "PATH_APPLICABILITY_UNKNOWN" in result.reason or "unknown" in result.reason.lower()

        sdk_out = sdk.pre_tool_use(self.edit(project))
        assert "permissionDecision" not in sdk_out.get("hookSpecificOutput", {})
        assert "NOT checked" in sdk_out["hookSpecificOutput"]["additionalContext"]

    def test_unparseable_verdict_fails_open_visibly(self, project):
        def runner(command, **kwargs):
            return completed("Traceback (most recent call last): ...", returncode=1)

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(**self.edit(project))
        assert result.action == ACTION_FAIL_OPEN
        assert "no parseable verdict" in result.reason

    def test_operational_failure_fails_open(self, project):
        def runner(command, **kwargs):
            raise OSError("spawn failed")

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(**self.edit(project))
        assert result.action == ACTION_FAIL_OPEN
        assert "could not run mneme check" in result.reason

    def test_warn_mode_flags_without_blocking(self, project, monkeypatch):
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

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(**self.edit(project))
        assert result.action == ACTION_WARN

        sdk_out = sdk.pre_tool_use(self.edit(project))
        assert "permissionDecision" not in sdk_out["hookSpecificOutput"]
        assert "WARN" in sdk_out["hookSpecificOutput"]["additionalContext"]

    def test_strict_mode_env_default_blocks(self, project, monkeypatch):
        monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
        calls = {}

        def runner(command, **kwargs):
            calls["mode"] = command[command.index("--mode") + 1]
            return completed(verdict_payload("FAIL"))

        sdk = make_integration(project, runner)
        assert sdk.evaluate_mutation(**self.edit(project)).action == ACTION_DENY
        assert calls["mode"] == "strict"

    def test_non_mutating_tool_skipped(self, project):
        sdk = make_integration(project, lambda *a, **k: completed())
        result = sdk.evaluate_mutation("Read", {"file_path": "app.py"})
        assert result.action == ACTION_SKIP

    def test_no_memory_skipped(self, tmp_path):
        sdk = make_integration(tmp_path, lambda *a, **k: completed())
        result = sdk.evaluate_mutation("Write", {"file_path": "f.py", "content": "x"})
        assert result.action == ACTION_SKIP

    def test_materialize_failure_fails_open(self, project):
        sdk = make_integration(project, lambda *a, **k: completed())
        result = sdk.evaluate_mutation(
            "Edit",
            {"file_path": str(project / "app.py"), "old_string": "not-there", "new_string": "z"},
            cwd=str(project),
        )
        assert result.action == ACTION_FAIL_OPEN
        assert "cannot materialize" in result.reason

    def test_pure_deletion_skipped(self, project):
        ran = []

        def runner(command, **kwargs):
            ran.append(command)
            return completed(verdict_payload("PASS"))

        sdk = make_integration(project, runner)
        result = sdk.evaluate_mutation(
            "Edit",
            {"file_path": str(project / "app.py"), "old_string": "x = 1\n", "new_string": ""},
            cwd=str(project),
        )
        assert result.action == ACTION_SKIP
        assert not ran


class TestSdkWiring:
    def test_hooks_callable_shapes_without_sdk_types(self, project):
        """Core callbacks are plain dicts and need no claude_agent_sdk."""
        sdk = make_integration(project, lambda *a, **k: completed(verdict_payload("PASS")))
        out = sdk.pre_tool_use(
            {"tool_name": "Read", "tool_input": {"file_path": "app.py"}, "cwd": str(project)}
        )
        assert out == {}

    def test_hooks_factory_binds_matchers(self, project):
        pytest.importorskip("claude_agent_sdk")

        async def drive(gated, new_content):
            matcher = gated.hooks()["PreToolUse"][0]
            return await matcher.hooks[0](
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": str(project / "app.py"),
                        "old_string": "x = 1",
                        "new_string": new_content,
                    },
                    "cwd": str(project),
                },
                None,
                None,
            )

        # Trusted PASS verdict: the wired callback has no opinion.
        passing = make_integration(
            project, lambda *a, **k: completed(verdict_payload("PASS"))
        )
        assert asyncio.run(drive(passing, "y = 2")) == {}

        # Trusted FAIL verdict: the wired callback denies with the reason.
        def fail_runner(command, **kwargs):
            return completed(
                verdict_payload(
                    "FAIL",
                    violations=[
                        {
                            "decision_id": "store_001",
                            "severity": "FAIL",
                            "rule": "psycopg2",
                            "trigger": "psycopg2",
                        }
                    ],
                )
            )

        denying = make_integration(project, fail_runner)
        out = asyncio.run(drive(denying, "import psycopg2\ny = 2"))
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "store_001" in out["hookSpecificOutput"]["permissionDecisionReason"]

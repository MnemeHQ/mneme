"""Option 1B through the Claude Agent SDK gate.

The deny, pass and relative-path rows of the proposal's section 6.1, with the
reference custom tool routing its proposals through
``MnemeAgentSdk.evaluate_mutation("Write", ..., cwd=root)``; plus a pin of
the documented empty-``cwd`` behavior (``docs/integrations/agent-sdk.md``).
No runtime change; the reference tool lives in
``tests/integrations/custom_tool_reference.py``.
"""
import hashlib
import json
from pathlib import Path

import pytest

from mneme.integrations.agent_sdk import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    MnemeAgentSdk,
)
from tests.integrations.agent_sdk.test_adapter import MEMORY
from tests.integrations.check_contract import check_result_for, violation
from tests.integrations.custom_tool_reference import (
    DENY_TAG,
    ReferenceFileTool,
    agent_sdk_evaluator,
)
from tests.integrations.relative_paths import (
    FORBIDDEN,
    TARGET,
    VIOLATING,
    RecordingRunner,
    make_layout,
)

FAIL_VIOLATION = violation("FAIL", decision_id="store_001", rule="psycopg2")


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(MEMORY), encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def stub(verdict, calls, **kwargs):
    def runner(command, **_):
        calls.append(list(command))
        return check_result_for(command, verdict, **kwargs)

    return runner


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_self_proposal_deny_prevents_mutation(project):
    calls = []
    sdk = MnemeAgentSdk(project_dir=project, check_runner=stub("FAIL", calls, violations=[FAIL_VIOLATION]))
    tool = ReferenceFileTool(agent_sdk_evaluator(sdk, str(project)), project)
    before = digest(project / "app.py")

    outcome = tool.save_text("app.py", "x = 1\nimport psycopg2\n")

    assert outcome.mneme_action == ACTION_DENY
    assert outcome.mutated is False
    assert digest(project / "app.py") == before
    assert len(calls) == 1
    assert calls[0][calls[0].index("--target-path") + 1] == str((project / "app.py").resolve())
    assert outcome.text.startswith(f"{DENY_TAG} - ")
    assert "store_001" in outcome.text


def test_self_proposal_pass_executes(project):
    calls = []
    sdk = MnemeAgentSdk(project_dir=project, check_runner=stub("PASS", calls))
    tool = ReferenceFileTool(agent_sdk_evaluator(sdk, str(project)), project)

    outcome = tool.save_text("util.py", "y = 2\n")

    assert outcome.mneme_action == ACTION_ALLOW
    assert outcome.mutated is True
    assert (project / "util.py").read_bytes() == b"y = 2\n"
    assert len(calls) == 1
    assert "[mneme]" not in outcome.text


def test_self_proposal_relative_path_uses_project_dir(tmp_path, monkeypatch):
    layout = make_layout(tmp_path, monkeypatch)
    decoy = layout.decoy(VIOLATING)
    decoy_before = decoy.read_bytes()
    before = layout.real().read_bytes()
    runner = RecordingRunner()
    sdk = MnemeAgentSdk(project_dir=layout.project, mode="strict", check_runner=runner)
    tool = ReferenceFileTool(agent_sdk_evaluator(sdk, str(layout.project)), layout.project)

    outcome = tool.save_text(TARGET, VIOLATING)

    assert outcome.mneme_action == ACTION_DENY
    assert len(runner.sent) == 1
    assert runner.sent[0].target_path == str(layout.real().resolve())
    assert FORBIDDEN in runner.sent[0].content
    assert layout.real().read_bytes() == before
    assert decoy.read_bytes() == decoy_before


class TestEmptyCwdRelativePathDocumented:
    """``docs/integrations/agent-sdk.md``: with an empty ``cwd``, relative
    paths stay relative to the process cwd. Characterizes, does not endorse:
    the reference tool always submits an absolute canonical path."""

    def test_empty_cwd_relative_path_documented(self, tmp_path, monkeypatch):
        layout = make_layout(tmp_path, monkeypatch)
        # Identical decoy in the process cwd is the snapshot: nothing is
        # introduced, so the gate skips without a checker call.
        layout.decoy(VIOLATING)
        runner = RecordingRunner()
        sdk = MnemeAgentSdk(project_dir=layout.project, mode="strict", check_runner=runner)

        result = sdk.evaluate_mutation(
            "Write", {"file_path": TARGET, "content": VIOLATING}, cwd=""
        )

        assert result.action == ACTION_SKIP
        assert result.reason == "no non-blank introduced lines"
        assert runner.sent == []

    def test_empty_cwd_target_path_stays_relative(self, tmp_path, monkeypatch):
        layout = make_layout(tmp_path, monkeypatch)
        runner = RecordingRunner()
        sdk = MnemeAgentSdk(project_dir=layout.project, mode="strict", check_runner=runner)

        result = sdk.evaluate_mutation(
            "Write", {"file_path": TARGET, "content": VIOLATING}, cwd=""
        )

        # Not joined to project_dir: the CLI resolves it against the process
        # cwd, outside the policy root, so the scoped rule is UNKNOWN.
        assert runner.sent[0].target_path == TARGET
        assert result.action == ACTION_FAIL_OPEN
        assert result.evaluation_complete is False

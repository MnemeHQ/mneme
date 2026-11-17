"""T-08 P2-first: every charter §4 consumer selects memory through the resolver.

Charter §5.2.6 (§7.5 consumer parity; freeze amendment changes 2-3): each of
the eleven consumers calls ``resolve_memory`` directly from its unchanged
start point and acts on the selection it returns. A spy replaces the
resolver in each consumer's module and forces "nothing selected"; every
consumer must ask it, from the expected start, and then behave as having no
memory. One resolver means one precedence rule for all of them.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mneme.integrations.memory_selection import NO_MEMORY_ON_PATH, MemorySelection

NOTHING = MemorySelection(path=None, source="none", reason=NO_MEMORY_ON_PATH, walk="unbounded")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path):
    root = tmp_path.resolve() / "project"
    (root / ".mneme").mkdir(parents=True)
    (root / ".mneme" / "project_memory.json").write_text("{}", encoding="utf-8")
    return root


def _spy(monkeypatch, module):
    calls = []

    def spy(start):
        calls.append(Path(start))
        return NOTHING

    monkeypatch.setattr(module, "resolve_memory", spy)
    return calls


def _never_check(*_a, **_k):
    raise AssertionError("no check may run when nothing is selected")


def test_claude_code_direct_write(monkeypatch, project):
    from mneme.integrations.claude_code import hook
    calls = _spy(monkeypatch, hook)
    monkeypatch.setattr(hook, "_invoke_check", _never_check)
    env = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(project),
           "tool_input": {"file_path": str(project / "a.py"), "content": "x = 1\n"}}
    assert hook.handle_event(env, stderr=io.StringIO(), stdout=io.StringIO()) == 0
    assert calls == [project]


def test_claude_code_bash(monkeypatch, project):
    from mneme.integrations.claude_code import hook
    calls = _spy(monkeypatch, hook)
    monkeypatch.setattr(hook, "_invoke_check", _never_check)
    env = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(project),
           "tool_input": {"command": "cat > a.py <<'EOF'\nx = 1\nEOF"}}
    assert hook.handle_event(env, stderr=io.StringIO(), stdout=io.StringIO()) == 0
    assert calls == [project]


@pytest.mark.parametrize("event", ["SessionStart", "Stop"])
def test_claude_code_lifecycle(monkeypatch, project, event):
    from mneme.integrations.claude_code import hook
    calls = _spy(monkeypatch, hook)
    out = io.StringIO()
    env = {"hook_event_name": event, "cwd": str(project), "session_id": "s"}
    assert hook.handle_event(env, stderr=io.StringIO(), stdout=out) == 0
    assert calls == [project] and out.getvalue() == ""


def test_codex_gate(monkeypatch, project):
    from mneme.integrations.codex_cli import gate
    calls = _spy(monkeypatch, gate)
    result = gate.evaluate_apply_patch({}, cwd=str(project), check_runner=_never_check)
    assert (result.action, result.reason) == (gate.SKIP, "no project memory")
    assert calls == [project]


def test_codex_stop_audit(monkeypatch, project):
    from mneme.integrations.codex_cli import stop_audit
    calls = _spy(monkeypatch, stop_audit)
    out = io.StringIO()
    assert stop_audit.handle_stop({"cwd": str(project)}, stderr=io.StringIO(), stdout=out) == 0
    assert stop_audit.ensure_session_baseline({"cwd": str(project)}) is None
    assert calls == [project, project] and out.getvalue() == ""


def test_kiro(monkeypatch, project):
    from mneme.integrations.kiro import hook as kiro
    calls = _spy(monkeypatch, kiro)
    raw = json.dumps({"hook_event_name": "preToolUse", "cwd": str(project), "tool_name": "fs_write",
                      "tool_input": {"path": str(project / "a.py"), "content": "x = 1\n"}})
    out = io.StringIO()
    assert kiro.main(stdin=io.StringIO(raw), stderr=io.StringIO(), stdout=out) == 0
    assert calls == [project] and out.getvalue() == ""


def test_antigravity(monkeypatch, project):
    from mneme.integrations.antigravity import adapter
    calls = _spy(monkeypatch, adapter)
    raw = json.dumps({"toolCall": {"name": "write_to_file", "args": {
        "TargetFile": str(project / "a.py"), "CodeContent": "x = 1\n"}},
        "workspacePaths": [str(project)]})
    out = io.StringIO()
    assert adapter.main(stdin=io.StringIO(raw), stderr=io.StringIO(), stdout=out,
                        check_runner=_never_check) == 0
    assert calls == [project] and json.loads(out.getvalue()) == {}


def test_agent_sdk(monkeypatch, project):
    from mneme.integrations.agent_sdk import adapter
    calls = _spy(monkeypatch, adapter)
    sdk = adapter.MnemeAgentSdk(project_dir=project, check_runner=_never_check)
    result = sdk.evaluate_mutation("Write", {"file_path": str(project / "a.py"), "content": "x\n"})
    assert result.reason == "no project memory"
    assert calls == [project]
    assert sdk.trace[-1]["walk"] == "unbounded"


def test_langchain(monkeypatch, project):
    from mneme.integrations.agent_sdk import adapter
    from mneme.integrations.langchain import MnemeLangChain
    calls = _spy(monkeypatch, adapter)
    gate = MnemeLangChain(project_dir=project, check_runner=_never_check)
    result = gate.evaluate_tool_call("write_file", {"file_path": "a.py", "content": "x\n"})
    assert result.reason == "no project memory"
    assert calls == [project]


def test_hermes(monkeypatch, project):
    from mneme.integrations.hermes import adapter
    calls = _spy(monkeypatch, adapter)
    gate = adapter.MnemeHermes(project_dir=project)
    injection = gate.context_for_turn("anything")
    assert injection.memory_path is None
    assert calls == [project]

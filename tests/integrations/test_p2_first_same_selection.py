"""T-08 P2-first §7.8: for the same selected memory, outputs are unchanged.

Charter §5.2.6 and freeze amendment change 7: for every consumer, hook
output, exit code, ``GateResult`` and ``ContextInjection`` are identical to
what the same selected memory produces without an override. The only
exceptions are the H1 notices and the Agent SDK/LangChain trace keys.

Each test runs one consumer twice on one layout: row 1 (the repository
memory, no override) and row 2 (the same memory, with a foreign
``MNEME_MEMORY`` that P2-first ignores). The selection is the same, so after
removing the notice the outputs must match exactly, including the
``--memory`` argument the checker receives.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.integrations.check_contract import check_result, check_result_for

MEMORY = {"meta": {"name": "same-selection", "description": "fixture", "version": "0.1.0",
                   "owner": "test", "created": "2026-11-17"},
          "decisions": [{"id": "store_001", "decision": "SQLite only", "rationale": "one file",
                         "scope": ["storage"], "constraints": ["no postgres"],
                         "anti_patterns": ["psycopg2"]}]}
NOTICE = "OVERRIDE_IGNORED"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_CHECK_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)


def _mem(d: Path) -> Path:
    p = d / ".mneme" / "project_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(MEMORY), encoding="utf-8")
    return p


@pytest.fixture
def layout(tmp_path):
    base = tmp_path.resolve()
    repo = base / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    mem = _mem(repo)
    foreign = _mem(base / "foreign")
    return {"base": base, "repo": repo, "mem": mem, "foreign": foreign}


def _both(monkeypatch, layout, run):
    """Run ``run()`` as row 1, then as row 2, each with fresh session state."""
    results = []
    for n, override in enumerate((None, str(layout["foreign"]))):
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(layout["base"] / f"state{n}"))
        if override is None:
            monkeypatch.delenv("MNEME_MEMORY", raising=False)
        else:
            monkeypatch.setenv("MNEME_MEMORY", override)
        results.append(run())
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    return results


def _memory_args(commands):
    """The ``--memory`` argument of each recorded check (temp names vary)."""
    return [c[c.index("--memory") + 1] for c in commands]


def _strip_notice(stdout: str) -> str:
    return "".join(line for line in stdout.splitlines(keepends=True) if NOTICE not in line)


# ── Claude Code (four consumers) ─────────────────────────────────────────────


def _hook(envelope, response):
    from mneme.integrations.claude_code import hook
    calls = []

    def invoke(memory, rel, target, content, stderr=None, **kw):
        calls.append(str(memory))
        return response

    out, err = io.StringIO(), io.StringIO()
    with patch.object(hook, "_invoke_check", invoke):
        rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue(), calls


@pytest.mark.parametrize("verdict", ["PASS", "FAIL"])
def test_claude_code_direct_write(monkeypatch, layout, verdict):
    env = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(layout["repo"]),
           "tool_input": {"file_path": str(layout["repo"] / "a.py"), "content": "x = 1\n"}}
    (rc1, out1, err1, m1), (rc2, out2, err2, m2) = _both(
        monkeypatch, layout, lambda: _hook(env, check_result(verdict)))
    assert (rc1, err1, m1) == (rc2, err2, m2)
    assert m1 == [str(layout["mem"])]
    assert out1 == _strip_notice(out2)
    assert (NOTICE in out2) == (rc2 == 0)


def test_claude_code_bash(monkeypatch, layout):
    env = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(layout["repo"]),
           "tool_input": {"command": "cat > b.py <<'EOF'\nx = 1\nEOF"}}
    (rc1, out1, err1, m1), (rc2, out2, err2, m2) = _both(
        monkeypatch, layout, lambda: _hook(env, check_result("PASS")))
    assert (rc1, err1, m1) == (rc2, err2, m2)
    assert out1 == _strip_notice(out2)


@pytest.mark.parametrize("event", ["SessionStart", "Stop"])
def test_claude_code_lifecycle(monkeypatch, layout, event):
    env = {"hook_event_name": event, "cwd": str(layout["repo"]), "session_id": "s",
           "source": "startup", "stop_hook_active": False}
    (rc1, out1, err1, m1), (rc2, out2, err2, m2) = _both(
        monkeypatch, layout, lambda: _hook(env, check_result("PASS")))
    assert (rc1, err1, m1) == (rc2, err2, m2)
    assert out1 == _strip_notice(out2)


# ── Other consumers ──────────────────────────────────────────────────────────


def test_codex_gate(monkeypatch, layout):
    from mneme.integrations.codex_cli.gate import evaluate_apply_patch
    fixture = Path(__file__).parent / "codex_cli" / "fixtures" / "pretooluse_applypatch_addfile_allow.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    def run():
        commands = []

        def runner(command, **kw):
            commands.append([str(c) for c in command])
            return check_result_for(command, "PASS")

        result = evaluate_apply_patch(payload, cwd=str(layout["repo"]), check_runner=runner)
        mems = [c[c.index("--memory") + 1] for c in commands]
        return result, mems

    (r1, m1), (r2, m2) = _both(monkeypatch, layout, run)
    assert r1 == r2 and m1 == m2 == [str(layout["mem"])]


def test_codex_stop_audit(monkeypatch, layout):
    from mneme.integrations.codex_cli import stop_audit

    def run():
        out, err = io.StringIO(), io.StringIO()
        rc = stop_audit.handle_stop({"cwd": str(layout["repo"]), "session_id": "s"},
                                    stderr=err, stdout=out)
        return rc, out.getvalue(), err.getvalue()

    r1, r2 = _both(monkeypatch, layout, run)
    assert r1 == r2


def test_kiro(monkeypatch, layout):
    from mneme.integrations.kiro import hook as kiro
    raw = json.dumps({"hook_event_name": "preToolUse", "cwd": str(layout["repo"]),
                      "tool_name": "fs_write",
                      "tool_input": {"path": str(layout["repo"] / "k.py"), "content": "x = 1\n"}})

    def run():
        out, err = io.StringIO(), io.StringIO()
        rc = kiro.main(stdin=io.StringIO(raw), stderr=err, stdout=out)
        return rc, out.getvalue(), err.getvalue()

    r1, r2 = _both(monkeypatch, layout, run)
    assert r1 == r2


def test_antigravity(monkeypatch, layout):
    from mneme.integrations.antigravity import adapter
    raw = json.dumps({"toolCall": {"name": "write_to_file", "args": {
        "TargetFile": str(layout["repo"] / "g.py"), "CodeContent": "x = 1\n"}},
        "workspacePaths": [str(layout["repo"])]})

    def run():
        commands = []

        def runner(command, **kw):
            commands.append([str(c) for c in command])
            return check_result_for(command, "PASS")

        out, err = io.StringIO(), io.StringIO()
        rc = adapter.main(stdin=io.StringIO(raw), stderr=err, stdout=out, check_runner=runner)
        return rc, out.getvalue(), err.getvalue(), _memory_args(commands)

    r1, r2 = _both(monkeypatch, layout, run)
    assert r1 == r2


def _runner_recording():
    commands = []

    def runner(command, **kw):
        commands.append([str(c) for c in command])
        return check_result_for(command, "PASS")
    return runner, commands


def test_agent_sdk(monkeypatch, layout):
    from mneme.integrations.agent_sdk import MnemeAgentSdk

    def run():
        runner, commands = _runner_recording()
        sdk = MnemeAgentSdk(project_dir=layout["repo"], check_runner=runner)
        gate = sdk.evaluate_mutation("Write", {"file_path": str(layout["repo"] / "s.py"),
                                               "content": "x = 1\n"})
        context = sdk.context_for_task("storage")
        hook_out = sdk.pre_tool_use({"tool_name": "Write", "tool_input": {
            "file_path": str(layout["repo"] / "s.py"), "content": "x = 1\n"}})
        return gate, context, hook_out, _memory_args(commands)

    r1, r2 = _both(monkeypatch, layout, run)
    assert r1 == r2


def test_langchain(monkeypatch, layout):
    from mneme.integrations.langchain import MnemeLangChain

    def run():
        runner, commands = _runner_recording()
        gate = MnemeLangChain(project_dir=layout["repo"], check_runner=runner)
        result = gate.evaluate_tool_call("write_file", {"file_path": "l.py", "content": "x = 1\n"})
        context = gate.context_for_task("storage")
        return result, context, _memory_args(commands)

    r1, r2 = _both(monkeypatch, layout, run)
    assert r1 == r2


def test_hermes(monkeypatch, layout):
    from mneme.integrations.hermes.adapter import MnemeHermes

    def run():
        runner, commands = _runner_recording()
        gate = MnemeHermes(project_dir=layout["repo"], check_runner=runner)
        context = gate.context_for_turn("storage")
        result = gate.evaluate_tool_call("write_file", {"path": str(layout["repo"] / "h.py"),
                                                        "content": "x = 1\n"})
        return context, result, _memory_args(commands)

    r1, r2 = _both(monkeypatch, layout, run)
    assert r1 == r2

"""T-08 P2-first: H1 host notices for rows 2 and 7 (charter §5.2.4 items 2-5).

Each notice is emitted only in its probed shape and only when the event's
output would otherwise fit that shape; otherwise it is suppressed and the
event's existing output is unchanged. Rows 1, 6 and 8 never produce one.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from mneme import availability_authority as aa
from mneme.availability_authority import UNVERIFIABLE
from mneme.integrations.claude_code import hook
from mneme.integrations.claude_code.availability import unverifiable_context
from tests.integrations.check_contract import check_result
from tests.integrations.claude_code.test_availability_c2b_am1 import project  # noqa: F401

MEM = {"decisions": []}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_CHECK_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)


def _mem(d: Path) -> Path:
    p = d / ".mneme" / "project_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(MEM), encoding="utf-8")
    return p


def _git(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    return d


def _objects(stdout: str) -> list:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _run(envelope, response=None):
    out, err = io.StringIO(), io.StringIO()
    if response is None:
        rc = hook.handle_event(envelope, stderr=err, stdout=out)
    else:
        with patch.object(hook, "_invoke_check", return_value=response):
            rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def _write(target: Path, content: str = "x = 1\n"):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(target.parent),
            "tool_input": {"file_path": str(target), "content": content}}


def _bash(cwd: Path, target: Path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(cwd),
            "tool_input": {"command": f"cat > {target.name} <<'EOF'\nx = 1\nEOF"}}


def _pretool(text_has: str):
    def check(obj):
        hso = obj["hookSpecificOutput"]
        assert set(obj) == {"hookSpecificOutput"}
        assert set(hso) == {"hookEventName", "additionalContext"}
        assert hso["hookEventName"] == "PreToolUse"
        assert text_has in hso["additionalContext"]
    return check


@pytest.fixture
def layout(tmp_path):
    base = tmp_path.resolve()
    repo = _git(base / "repo")
    _mem(repo)
    foreign = _mem(base / "foreign")
    plain = base / "plain"
    plain.mkdir()
    assert hook.find_memory(plain) is None
    return {"base": base, "repo": repo, "foreign": foreign, "plain": plain}


# ── H1a direct write ─────────────────────────────────────────────────────────


def test_h1a_row2_pass_emits_one_notice(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    rc, out, err = _run(_write(layout["repo"] / "app.py"), check_result("PASS"))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1 and out.count("\n") == 1
    _pretool("OVERRIDE_IGNORED")(objs[0])


def test_h1a_row7_emits_one_notice(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["base"] / "nope.json"))
    rc, out, err = _run(_write(layout["plain"] / "app.py"))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    _pretool("OVERRIDE_MISSING")(objs[0])


def test_h1a_rows_1_6_8_emit_nothing(layout, monkeypatch):
    assert _run(_write(layout["repo"] / "app.py"), check_result("PASS"))[1] == ""
    assert _run(_write(layout["plain"] / "app.py"))[1] == ""
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    assert _run(_write(layout["plain"] / "app.py"), check_result("PASS"))[1] == ""


def test_h1a_suppressed_on_warn_defer(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, out, _ = _run(_write(layout["repo"] / "app.py"), check_result("FAIL", "warn"))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    assert objs[0]["hookSpecificOutput"]["permissionDecision"] == "defer"
    assert "OVERRIDE_IGNORED" not in out


def test_h1a_suppressed_on_exit_2(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    rc, out, err = _run(_write(layout["repo"] / "app.py"), check_result("FAIL"))
    assert rc == 2
    assert out == ""
    assert "OVERRIDE_IGNORED" not in err


def test_h1a_shares_one_object_with_proceed_note(project, tmp_path, monkeypatch):  # noqa: F811
    root = project(UNVERIFIABLE, aa.DNS)
    other = tmp_path / "foreign.json"
    other.write_text(json.dumps(MEM), encoding="utf-8")
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    rc, out, _ = _run(_write(root / "service.py"), check_result("PASS"))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1 and out.count("\n") == 1
    hso = objs[0]["hookSpecificOutput"]
    assert set(hso) == {"hookEventName", "additionalContext"}
    text = hso["additionalContext"]
    assert text.startswith(unverifiable_context(aa.DNS, False))
    assert "OVERRIDE_IGNORED" in text


def test_h1a_proceed_note_alone_unchanged(project):  # noqa: F811
    root = project(UNVERIFIABLE, aa.DNS)
    rc, out, _ = _run(_write(root / "service.py"), check_result("PASS"))
    assert _objects(out) == [{"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": unverifiable_context(aa.DNS, False)}}]


# ── H1a Bash ─────────────────────────────────────────────────────────────────


def test_h1a_bash_heredoc_row2_emits_notice(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    rc, out, _ = _run(_bash(layout["repo"], layout["repo"] / "gen.py"), check_result("PASS"))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    _pretool("OVERRIDE_IGNORED")(objs[0])


def test_h1a_bash_unreconstructable_command_selects_nothing(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    env = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(layout["repo"]),
           "tool_input": {"command": "ls -la"}}
    rc, out, _ = _run(env)
    assert rc == 0 and out == ""


# ── H1b SessionStart ─────────────────────────────────────────────────────────


def _session(cwd: Path, source="startup"):
    return {"hook_event_name": "SessionStart", "cwd": str(cwd), "session_id": "s1",
            "source": source}


def _sessionstart(text_has: str):
    def check(obj):
        assert set(obj) == {"hookSpecificOutput"}
        hso = obj["hookSpecificOutput"]
        assert set(hso) == {"hookEventName", "additionalContext"}
        assert hso["hookEventName"] == "SessionStart"
        assert text_has in hso["additionalContext"]
    return check


def test_h1b_row7_emits_notice(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["base"] / "nope.json"))
    rc, out, _ = _run(_session(layout["plain"]))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    _sessionstart("OVERRIDE_MISSING")(objs[0])


def test_h1b_row2_with_stored_baseline_emits_notice(layout, monkeypatch, tmp_path):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
    rc, out, _ = _run(_session(layout["repo"]))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    _sessionstart("OVERRIDE_IGNORED")(objs[0])


def test_h1b_suppressed_beside_plain_text_line(layout, monkeypatch):
    """A non-Git memory root makes SessionStart write its plain-text line."""
    nogit = layout["base"] / "nogit"
    _mem(nogit)
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    rc, out, _ = _run(_session(nogit))
    assert rc == 0
    assert out.startswith("mneme-hook: session baseline")
    assert "OVERRIDE_IGNORED" not in out
    assert "{" not in out


# ── H1c Stop ─────────────────────────────────────────────────────────────────


def _stop(cwd: Path):
    return {"hook_event_name": "Stop", "cwd": str(cwd), "session_id": "s1",
            "stop_hook_active": False}


def test_h1c_row7_emits_top_level_system_message(layout, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(layout["base"] / "nope.json"))
    rc, out, _ = _run(_stop(layout["plain"]))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    assert set(objs[0]) == {"systemMessage"}
    assert "OVERRIDE_MISSING" in objs[0]["systemMessage"]


def test_h1c_suppressed_beside_stop_feedback(layout, monkeypatch):
    """A non-Git memory root makes Stop emit its own feedback object."""
    nogit = layout["base"] / "nogit"
    _mem(nogit)
    monkeypatch.setenv("MNEME_MEMORY", str(layout["foreign"]))
    rc, out, _ = _run(_stop(nogit))
    assert rc == 0
    objs = _objects(out)
    assert len(objs) == 1
    assert objs[0]["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert "OVERRIDE_IGNORED" not in out


def test_h1c_row1_emits_nothing(layout):
    rc, out, _ = _run(_stop(layout["plain"]))
    assert rc == 0 and out == ""

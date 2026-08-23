"""ADR-021: hook wiring contract for the expanded coverage surface.

Both the flat template and the plugin bundle must register:
  PreToolUse matcher Edit|Write|MultiEdit|Bash
  SessionStart (baseline capture)
  Stop (session-delta backstop)
All entries use exec-form direct invocation of mneme-hook.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIGS = [
    ROOT / "integrations" / "claude-code" / "hooks.json",
    ROOT / "integrations" / "claude-code-plugin" / "hooks" / "hooks.json",
]


def _hooks(path):
    return json.loads(path.read_text(encoding="utf-8"))["hooks"]


def test_both_configs_exist():
    for path in CONFIGS:
        assert path.is_file(), f"missing {path}"


def test_pre_tool_use_covers_bash_and_direct_tools():
    for path in CONFIGS:
        pre = _hooks(path)["PreToolUse"]
        matchers = [g.get("matcher", "") for g in pre]
        combined = "|".join(matchers)
        for tool in ("Edit", "Write", "MultiEdit", "Bash"):
            assert tool in combined, f"{path}: PreToolUse must cover {tool}"


def test_stop_event_registered():
    for path in CONFIGS:
        stop = _hooks(path).get("Stop")
        assert stop, f"{path}: Stop boundary missing"
        cmds = [h["command"] for g in stop for h in g["hooks"]]
        assert "mneme-hook" in cmds


def test_session_start_event_registered():
    for path in CONFIGS:
        start = _hooks(path).get("SessionStart")
        assert start, f"{path}: SessionStart baseline capture missing"
        cmds = [h["command"] for g in start for h in g["hooks"]]
        assert "mneme-hook" in cmds


def test_all_handlers_exec_form():
    for path in CONFIGS:
        for event, groups in _hooks(path).items():
            for g in groups:
                for h in g["hooks"]:
                    assert h["command"] == "mneme-hook"
                    if "args" in h:
                        assert h["args"] == []
                    for banned in ("&&", ";", "$(", "|"):
                        assert banned not in h["command"]

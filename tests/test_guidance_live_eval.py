import json
from pathlib import Path

import pytest

from mneme.guidance_live_eval import (
    CaptureError,
    apply_tool_call,
    build_blinded_artifact,
    capture_attempts,
    external_tool_accesses,
    mechanism_isolation_violations,
    parse_events,
)


def _tool(name, tool_id, **tool_input):
    return {
        "type": "tool_use",
        "id": tool_id,
        "name": name,
        "input": tool_input,
    }


def _assistant(message_id, *blocks, timestamp="2026-08-13T20:00:01Z"):
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": "claude-sonnet-5",
            "content": list(blocks),
        },
    }


def test_first_attempt_is_combined_and_frozen_before_hook_feedback(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    auth = workspace / "src" / "auth.py"
    sessions = workspace / "src" / "sessions.py"
    auth.parent.mkdir()
    pristine = {
        "src/auth.py": "def auth():\n    raise NotImplementedError\n",
        "src/sessions.py": "class Store:\n    pass\n",
    }
    events = [
        {
            "type": "user",
            "timestamp": "2026-08-13T20:00:00Z",
            "message": {"content": "task"},
        },
        _assistant(
            "first",
            _tool(
                "Edit", "edit-1", file_path=str(auth),
                old_string="    raise NotImplementedError",
                new_string="    return 'cookie'", replace_all=False,
            ),
            _tool(
                "Write", "write-1", file_path=str(sessions),
                content="class Store:\n    backend = 'sqlite'\n",
            ),
        ),
        {
            "type": "system",
            "subtype": "hook_response",
            "hook_name": "PreToolUse:Edit",
            "outcome": "error",
        },
        _assistant(
            "retry",
            _tool(
                "Edit", "edit-2", file_path=str(auth),
                old_string="    raise NotImplementedError",
                new_string="    return 'retry'", replace_all=False,
            ),
            timestamp="2026-08-13T20:00:03Z",
        ),
    ]

    captured = capture_attempts(events, pristine, workspace)

    assert len(captured["attempts"]) == 2
    assert captured["attempts"][0]["message_id"] == "first"
    assert captured["first_attempt_capture_error"] is None
    assert "return 'cookie'" in captured["first_attempt_diff"]
    assert "backend = 'sqlite'" in captured["first_attempt_diff"]
    assert "return 'retry'" not in captured["first_attempt_diff"]
    assert "$WORKSPACE" in json.dumps(captured["first_attempt_tool_calls"])


def test_discovery_metrics_stop_before_first_mutating_message(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.py"
    pristine = {"target.py": "old\n"}
    events = [
        _assistant(
            "read",
            _tool("Glob", "glob-1", pattern="**/*"),
            _tool("Read", "read-1", file_path=str(workspace / ".mneme" / "project_memory.json")),
        ),
        _assistant(
            "edit",
            _tool("Write", "write-1", file_path=str(target), content="new\n"),
            _tool("Read", "read-after", file_path=str(workspace / "README.md")),
        ),
    ]

    captured = capture_attempts(events, pristine, workspace)

    assert captured["tool_calls_before_first_attempt"] == 2
    assert captured["tool_calls_through_first_attempt"] == 4
    assert len(captured["discovery_calls_before_first_attempt"]) == 2
    assert len(captured["policy_discovery_before_first_attempt"]) == 1
    assert "read-after" not in json.dumps(captured["discovery_calls_before_first_attempt"])


def test_workspace_escape_fails_materialization_and_isolation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "policy.json"
    events = [_assistant("escape", _tool("Read", "read-1", file_path=str(outside)))]

    assert len(external_tool_accesses(events, workspace)) == 1
    assert mechanism_isolation_violations(
        events, workspace, "baseline", True,
    ) == ["1 model filesystem call(s) escaped the workspace"]

    with pytest.raises(CaptureError, match="escapes workspace"):
        apply_tool_call(
            {}, _tool("Write", "write-1", file_path=str(outside), content="x"),
            workspace,
        )


def test_baseline_context_and_control_context_are_isolation_failures(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    events = [{
        "type": "system",
        "subtype": "hook_response",
        "output": "DECISION [ADR-STORAGE]: use SQLite",
    }]

    assert mechanism_isolation_violations(
        events, workspace, "baseline", True,
    ) == ["baseline received prompt-time decision context"]
    assert mechanism_isolation_violations(
        events, workspace, "treatment", False,
    ) == ["control prompt received policy context"]


def test_blinded_artifact_excludes_arm_and_operational_metadata(tmp_path):
    task = {
        "id": "storage-1",
        "prompt": "Add persistence for user sessions.",
        "target": "src/sessions.py",
        "governed": True,
        "expected_condition": "Use SQLite.",
    }
    capture = {
        "first_attempt_tool_calls": [{"name": "Write", "input": {"content": "sqlite"}}],
        "first_attempt_diff": "+sqlite\n",
        "first_attempt_capture_error": None,
    }
    artifact = build_blinded_artifact(
        blind_id="review-opaque", task=task, capture=capture,
    )
    serialized = json.dumps(artifact, sort_keys=True)

    assert "review-opaque" in serialized
    for forbidden in (
        '"arm"', "treatment", "baseline", "injected_decision_ids",
        "hook_events", "total_cost_usd", "run_directory",
    ):
        assert forbidden not in serialized


def test_parse_events_ignores_non_json_lines():
    assert parse_events('noise\n{"type":"assistant"}\n') == [
        {"type": "assistant"}
    ]


def test_mechanism_plugin_has_guidance_only():
    root = (
        Path(__file__).resolve().parents[1] / "tests" / "fixtures"
        / "guidance_confirmatory" / "mechanism_plugin"
    )
    hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert set(hooks["hooks"]) == {"UserPromptSubmit"}
    command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert command["command"] == "mneme-guidance-hook"


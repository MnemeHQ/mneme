import json
import pytest
from mneme.integrations.claude_code.hook import parse_event, ToolEvent


def test_parse_edit_event():
    raw = json.dumps({
        "session_id": "abc",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/repo",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/repo/app.py",
            "old_string": "def f(): pass",
            "new_string": "def f(): return 1",
        },
    })
    event = parse_event(raw)
    assert isinstance(event, ToolEvent)
    assert event.tool_name == "Edit"
    assert event.file_path == "/repo/app.py"
    assert event.tool_input["old_string"] == "def f(): pass"
    assert event.tool_input["new_string"] == "def f(): return 1"


def test_parse_write_event():
    raw = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "cwd": "/repo",
        "tool_input": {"file_path": "/repo/new.py", "content": "x = 1\n"},
    })
    event = parse_event(raw)
    assert event.tool_name == "Write"
    assert event.tool_input["content"] == "x = 1\n"


def test_parse_multiedit_event():
    raw = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "MultiEdit",
        "cwd": "/repo",
        "tool_input": {
            "file_path": "/repo/a.py",
            "edits": [
                {"old_string": "a", "new_string": "b"},
                {"old_string": "c", "new_string": "d"},
            ],
        },
    })
    event = parse_event(raw)
    assert event.tool_name == "MultiEdit"
    assert len(event.tool_input["edits"]) == 2


from mneme.integrations.claude_code.hook import should_check


def test_should_check_only_mutating_tools():
    assert should_check("Edit") is True
    assert should_check("Write") is True
    assert should_check("MultiEdit") is True
    assert should_check("Read") is False
    assert should_check("Bash") is False
    assert should_check("Glob") is False

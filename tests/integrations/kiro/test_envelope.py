"""Envelope parser tests, pinned to the Phase A evidence.

The envelope shape mirrors the documented Kiro v1 hook event
(kiro.dev/docs/hooks/types/, MCP example): ``hook_event_name``, ``cwd``,
``session_id``, ``tool_name``, ``tool_input``. The native write tool's
``tool_input`` carries ``path`` and the full proposed ``content``
(observed Kiro CLI shape; see docs/integrations/kiro-hook-spec.md for the
documented-versus-observed status). No field name here is invented.
"""
import io
import json

from mneme.integrations.kiro.hook import (
    is_write_tool,
    main,
    normalize_to_tool_event,
    parse_kiro_envelope,
)


def _write_envelope(tool="fs_write", cwd="/repo", path="src/app.py", content="x = 1\n"):
    return json.dumps({
        "hook_event_name": "preToolUse",
        "session_id": "abc123",
        "cwd": cwd,
        "tool_name": tool,
        "tool_input": {"path": path, "content": content},
    })


# --- parse_kiro_envelope ---

def test_parses_documented_envelope():
    payload = parse_kiro_envelope(_write_envelope())
    assert payload["hook_event_name"] == "preToolUse"
    assert payload["tool_name"] == "fs_write"
    assert payload["cwd"] == "/repo"
    assert payload["session_id"] == "abc123"


def test_malformed_json_raises():
    import pytest
    with pytest.raises(json.JSONDecodeError):
        parse_kiro_envelope("this is not json{")


def test_non_object_payload_raises():
    import pytest
    with pytest.raises(KeyError):
        parse_kiro_envelope(json.dumps([1, 2, 3]))


def test_missing_event_name_raises():
    import pytest
    with pytest.raises(KeyError):
        parse_kiro_envelope(json.dumps({"tool_name": "fs_write"}))


# --- tool recognition: only documented names ---

def test_write_tool_names():
    assert is_write_tool("write")
    assert is_write_tool("fs_write")
    assert is_write_tool("fsWrite")


def test_non_write_tools_rejected():
    assert not is_write_tool("shell")
    assert not is_write_tool("execute_bash")
    assert not is_write_tool("read")
    assert not is_write_tool("@mcp/write_file")


# --- normalize_to_tool_event ---

def test_normalizes_fs_write_to_whole_content_write():
    event, unhandled = normalize_to_tool_event(json.loads(_write_envelope()))
    assert unhandled is None
    assert event is not None
    assert event.tool_name == "Write"
    assert event.file_path == "src/app.py"
    assert event.cwd == "/repo"
    assert event.tool_input["file_path"] == "src/app.py"
    assert event.tool_input["content"] == "x = 1\n"


def test_all_documented_aliases_normalize():
    for tool in ("write", "fs_write", "fsWrite"):
        event, unhandled = normalize_to_tool_event(json.loads(_write_envelope(tool=tool)))
        assert unhandled is None
        assert event is not None, tool


def test_non_pretooluse_events_are_skipped():
    payload = json.loads(_write_envelope())
    payload["hook_event_name"] = "postToolUse"
    event, unhandled = normalize_to_tool_event(payload)
    assert event is None
    assert unhandled is None


def test_shell_tool_is_never_normalized():
    """PreToolUse(shell) fires for redirections and scripts; this gate does
    not parse shell commands (documented unsupported surface)."""
    payload = json.loads(_write_envelope())
    payload["tool_name"] = "shell"
    payload["tool_input"] = {"command": "echo x > file.txt"}
    event, unhandled = normalize_to_tool_event(payload)
    assert event is None
    assert unhandled is None


def test_missing_tool_input_degrades_to_empty_strings():
    payload = json.loads(_write_envelope())
    del payload["tool_input"]
    event, unhandled = normalize_to_tool_event(payload)
    assert unhandled is None
    assert event is not None
    assert event.file_path == ""
    assert event.tool_input["content"] == ""


def test_non_string_path_and_content_are_tolerated():
    payload = json.loads(_write_envelope())
    payload["tool_input"] = {"path": 42, "content": None}
    event, unhandled = normalize_to_tool_event(payload)
    assert unhandled is None
    assert event is not None
    assert event.file_path == ""
    assert event.tool_input["content"] == ""


def test_observed_cli_2_19_2_envelope_with_file_text():
    """CLI 2.19.2 (kiro-cli-chat 2.19.2) sends tool_input with 'file_text' instead
    of 'content' for fs_write create. This regression fixture captures the exact
    live envelope structure observed during manual reproduction on 2026-08-26
    (note: CLI 2.x omits session_id)."""
    envelope = {
        "hook_event_name": "preToolUse",
        "cwd": "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live",
        "tool_name": "fs_write",
        "tool_input": {
            "command": "create",
            "path": "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live\\test_block.md",
            "file_text": "pip install mneme-hq"
        }
    }
    event, unhandled = normalize_to_tool_event(envelope)
    assert unhandled is None
    assert event is not None
    assert event.tool_name == "Write"
    assert event.file_path == "C:\\Users\\hi\\AppData\\Local\\Temp\\opencode\\kiro-live\\test_block.md"
    assert event.tool_input["content"] == "pip install mneme-hq"


def test_cli_2_19_2_envelope_requires_create_command():
    """The file_text key is only honored with tool_name='fs_write' and command='create'.
    Other commands (edit, replace) or write tool aliases do not assume file_text,
    ensuring unsupported legacy operations fail open visibly via unhandled reason."""
    envelope = {
        "hook_event_name": "preToolUse",
        "cwd": "/repo",
        "tool_name": "fs_write",
        "tool_input": {
            "command": "edit",
            "path": "/repo/src/app.py",
            "file_text": "new content"
        }
    }
    event, unhandled = normalize_to_tool_event(envelope)
    assert event is None
    assert unhandled is not None
    assert "unsupported legacy write shape: fs_write command='edit' with file_text" in unhandled

    # Also confirm other aliases like 'write' or 'fsWrite' with file_text fail open visibly
    envelope_alias = {
        "hook_event_name": "preToolUse",
        "cwd": "/repo",
        "tool_name": "write",
        "tool_input": {
            "command": "create",
            "path": "/repo/src/app.py",
            "file_text": "new content"
        }
    }
    event_alias, unhandled_alias = normalize_to_tool_event(envelope_alias)
    assert event_alias is None
    assert unhandled_alias is not None
    assert "unsupported legacy write shape: write with file_text" in unhandled_alias


# --- main(): malformed envelopes fail open quietly, unsupported shapes fail open visibly ---

def test_main_unsupported_legacy_edit_fails_open_visibly(tmp_path):
    from unittest.mock import patch
    envelope = json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(tmp_path),
        "tool_name": "fs_write",
        "tool_input": {
            "command": "edit",
            "path": str(tmp_path / "app.py"),
            "file_text": "import os"
        }
    })
    stdout = io.StringIO()
    with patch("mneme.integrations.kiro.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO(envelope), stdout=stdout, stderr=io.StringIO())
    assert rc == 0
    mrun.assert_not_called()
    assert "[mneme] UNEVALUATED - failing open, this mutation was NOT checked: unsupported legacy write shape: fs_write command='edit' with file_text" in stdout.getvalue()


# --- main(): malformed envelopes fail open quietly ---

def test_main_bad_json_returns_zero_without_checking(tmp_path):
    from unittest.mock import patch
    with patch("mneme.integrations.kiro.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO("not json{"), stderr=io.StringIO())
    assert rc == 0
    mrun.assert_not_called()


def test_main_post_tool_use_returns_zero(tmp_path):
    from unittest.mock import patch
    payload = json.loads(_write_envelope(cwd=str(tmp_path)))
    payload["hook_event_name"] = "postToolUse"
    with patch("mneme.integrations.kiro.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO(json.dumps(payload)), stderr=io.StringIO())
    assert rc == 0
    mrun.assert_not_called()


def test_main_shell_tool_returns_zero_without_parsing_command(tmp_path):
    """A shell redirection must not be interpreted as a write (no shell
    parsing in this integration)."""
    from unittest.mock import patch
    envelope = json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(tmp_path),
        "tool_name": "shell",
        "tool_input": {"command": f"echo legacy_client.connect( > {tmp_path}/a.py"},
    })
    with patch("mneme.integrations.kiro.hook.subprocess.run") as mrun:
        rc = main(stdin=io.StringIO(envelope), stderr=io.StringIO())
    assert rc == 0
    mrun.assert_not_called()

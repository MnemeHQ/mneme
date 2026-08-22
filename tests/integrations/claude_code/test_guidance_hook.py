"""UserPromptSubmit guidance adapter contract and fail-open behavior."""

import io
import json
from unittest.mock import patch

from mneme.integrations.claude_code.guidance_hook import (
    guidance_enabled,
    main,
    parse_prompt_event,
)


def _envelope(cwd, prompt="Add session storage"):
    return json.dumps({
        "session_id": "abc",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": str(cwd),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    })


def _project(tmp_path):
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "storage",
            "decision": "Use SQLite session storage",
            "scope": ["storage", "session"],
            "constraints": ["no postgres"],
        }],
    }), encoding="utf-8")
    return memory


def test_parse_prompt_event():
    event = parse_prompt_event(_envelope("/repo"))
    assert event.cwd == "/repo"
    assert event.prompt == "Add session storage"


def test_guidance_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MNEME_GUIDANCE", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_GUIDANCE", raising=False)
    assert guidance_enabled() is False


def test_explicit_env_overrides_plugin_option(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_GUIDANCE", "true")
    monkeypatch.setenv("MNEME_GUIDANCE", "false")
    assert guidance_enabled() is False


def test_plugin_option_can_enable_guidance(monkeypatch):
    monkeypatch.delenv("MNEME_GUIDANCE", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_GUIDANCE", "true")
    assert guidance_enabled() is True


def test_disabled_hook_does_not_read_or_emit(monkeypatch):
    monkeypatch.setenv("MNEME_GUIDANCE", "false")
    out = io.StringIO()
    assert main(stdin=io.StringIO("not json"), stdout=out) == 0
    assert out.getvalue() == ""


def test_enabled_hook_emits_additional_context(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    err = io.StringIO()
    rc = main(
        stdin=io.StringIO(_envelope(tmp_path)),
        stdout=out,
        stderr=err,
    )
    assert rc == 0
    payload = json.loads(out.getvalue())
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "UserPromptSubmit"
    assert "DECISION [storage]" in specific["additionalContext"]
    assert err.getvalue() == ""


def test_low_signal_prompt_emits_no_stdout(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    assert main(
        stdin=io.StringIO(_envelope(tmp_path, prompt="yes")), stdout=out,
    ) == 0
    assert out.getvalue() == ""


def test_missing_memory_emits_no_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    assert main(stdin=io.StringIO(_envelope(tmp_path)), stdout=out) == 0
    assert out.getvalue() == ""


def test_invalid_envelope_fails_open_without_stdout(monkeypatch):
    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    err = io.StringIO()
    assert main(stdin=io.StringIO("{"), stdout=out, stderr=err) == 0
    assert out.getvalue() == ""
    assert "Continuing without guidance" in err.getvalue()


def test_stdin_read_error_fails_open_without_stdout(monkeypatch):
    class Unreadable:
        def read(self):
            raise OSError("stdin unavailable")

    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    err = io.StringIO()
    assert main(stdin=Unreadable(), stdout=out, stderr=err) == 0
    assert out.getvalue() == ""
    assert "Continuing without guidance" in err.getvalue()


def test_guidance_error_fails_open_without_stdout(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    err = io.StringIO()
    with patch(
        "mneme.integrations.claude_code.guidance_hook.build_guidance",
        side_effect=RuntimeError("boom"),
    ):
        rc = main(
            stdin=io.StringIO(_envelope(tmp_path)), stdout=out, stderr=err,
        )
    assert rc == 0
    assert out.getvalue() == ""
    assert "RuntimeError: boom" in err.getvalue()


def test_memory_discovery_error_fails_open_without_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_GUIDANCE", "true")
    out = io.StringIO()
    err = io.StringIO()
    with patch(
        "mneme.integrations.claude_code.guidance_hook.find_memory",
        side_effect=OSError("unreadable cwd"),
    ):
        rc = main(
            stdin=io.StringIO(_envelope(tmp_path)), stdout=out, stderr=err,
        )
    assert rc == 0
    assert out.getvalue() == ""
    assert "OSError: unreadable cwd" in err.getvalue()

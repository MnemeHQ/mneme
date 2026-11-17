"""Unit-level contract tests for the OpenCode S1 bridge.

These tests exercise the bridge's own normalization and authority checks. They do
not run the checker; the offline integration suite does that.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mneme.integrations.opencode import bridge


def request(**overrides):
    payload = {
        "tool": "write",
        "path": "src/handlers/new_handler.py",
        "content": "VALUE = 1\n",
        "session_directory": None,
        "session_id": "ses_test",
        "call_id": "call_1",
        "agent": "test",
        "message_id": "msg_1",
        "event_id": "evt_1",
        "host_version": "2.3.0",
    }
    payload.update(overrides)
    return bridge.Request(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"tool": "write"},
        {"tool": "write", "input": []},
        {"tool": "write", "input": {}},
        {"tool": "write", "input": {"path": "x.py", "content": 1}},
        {"tool": "write", "input": {"path": "x.py"}, "sessionDirectory": 1},
    ],
)
def test_parse_request_rejects_bad_shapes(payload):
    with pytest.raises(bridge.EvaluationError):
        bridge.parse_request(payload)


def test_parse_request_preserves_host_identifiers():
    parsed = bridge.parse_request(
        {
            "tool": "write",
            "input": {"path": "x.py", "content": "VALUE = 1\n"},
            "sessionDirectory": "/tmp/project",
            "sessionID": "ses_1",
            "callID": "call_1",
            "agent": "agent",
            "messageID": "msg_1",
            "eventID": "evt_1",
            "hostVersion": "2.3.0",
        }
    )
    assert parsed.session_id == "ses_1"
    assert parsed.call_id == "call_1"
    assert parsed.agent == "agent"
    assert parsed.message_id == "msg_1"
    assert parsed.event_id == "evt_1"
    assert parsed.host_version == "2.3.0"


def test_resolve_target_relative_and_absolute(s1_fixture):
    relative = bridge.resolve_target(
        request(session_directory=str(s1_fixture.root))
    )
    absolute = bridge.resolve_target(
        request(
            session_directory=str(s1_fixture.root),
            path=str(s1_fixture.root / "src" / "handlers" / "new_handler.py"),
        )
    )
    assert relative == absolute


def test_resolve_target_requires_session_directory():
    with pytest.raises(bridge.EvaluationError):
        bridge.resolve_target(request(session_directory=None))


def test_resolve_target_rejects_outside_root(s1_fixture):
    with pytest.raises(bridge.EvaluationError):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path="../../escape.py",
            )
        )
    with pytest.raises(bridge.EvaluationError):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path=str(s1_fixture.root.parent / "escape.py"),
            )
        )


def test_resolve_target_rejects_non_python(s1_fixture):
    with pytest.raises(bridge.UnsupportedError, match="non_python_target"):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path="src/handlers/new_handler.txt",
            )
        )


def test_resolve_target_rejects_existing(s1_fixture):
    existing = s1_fixture.root / "src" / "handlers" / "existing.py"
    existing.write_text("VALUE = 0\n", encoding="utf-8")
    with pytest.raises(bridge.UnsupportedError, match="existing_target"):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path="src/handlers/existing.py",
            )
        )


def test_resolve_target_rejects_symlink_parent(s1_fixture):
    link = s1_fixture.root / "linked"
    try:
        link.symlink_to(s1_fixture.root / "src", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(bridge.UnsupportedError, match="symlink_target"):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path="linked/handlers/new_handler.py",
            )
        )


def test_authority_matches_fixture(s1_fixture):
    authority = bridge.load_authority(str(s1_fixture.authority))
    bridge._match_authority(s1_fixture.memory, authority)


@pytest.mark.parametrize(
    "field,value",
    [
        ("decision_version_id", "dver-00000000000000000000000000000000"),
        ("rule_id", "ADR-001:FORBID_LITERAL:00000000000000000000000000000000"),
        ("rule_value", "psycopg"),
        ("rule_scope", "src/**"),
        ("decision_id", "ADR-999"),
    ],
)
def test_authority_mismatch_raises(s1_fixture, field, value):
    authority = bridge.load_authority(str(s1_fixture.authority))
    wrong = dataclasses.replace(authority, **{field: value})
    with pytest.raises(bridge.BridgeConfigError):
        bridge._match_authority(s1_fixture.memory, wrong)


def test_authority_file_requires_all_fields(tmp_path):
    path = tmp_path / "authority.json"
    path.write_text('{"decision_id": "ADR-001"}\n', encoding="utf-8")
    with pytest.raises(bridge.BridgeConfigError):
        bridge.load_authority(str(path))


def test_authority_missing_file(tmp_path):
    with pytest.raises(bridge.BridgeConfigError):
        bridge.load_authority(str(tmp_path / "missing.json"))


def test_memory_schema_is_reported(s1_fixture):
    assert bridge._memory_schema(s1_fixture.memory) == "mneme.decision-index/v2"

"""Unit-level contract tests for the OpenCode S1 bridge.

These tests exercise the bridge's own normalization and authority checks. They do
not run the checker; the offline integration suite does that.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess

import pytest

from mneme.integrations.opencode import bridge

BRIDGE_SCHEMA = "mneme.opencode.bridge/v1"


def valid_payload():
    return {
        "schema": BRIDGE_SCHEMA,
        "tool": "write",
        "input": {"path": "src/handlers/new_handler.py", "content": "VALUE = 1\n"},
        "sessionDirectory": None,
        "sessionID": "ses_test",
        "callID": "call_1",
        "agent": "test",
        "messageID": "msg_1",
        "eventID": "evt_1",
        "hostVersion": "2.3.0",
    }


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
        {"schema": BRIDGE_SCHEMA},
        {"schema": BRIDGE_SCHEMA, "tool": "write"},
        {"schema": BRIDGE_SCHEMA, "tool": "write", "input": []},
        {"schema": BRIDGE_SCHEMA, "tool": "write", "input": {}},
        {
            "schema": BRIDGE_SCHEMA,
            "tool": "write",
            "input": {"path": "x.py", "content": 1},
        },
        {
            "schema": BRIDGE_SCHEMA,
            "tool": "write",
            "input": {"path": "x.py"},
            "sessionDirectory": 1,
        },
    ],
)
def test_parse_request_rejects_bad_shapes(payload):
    with pytest.raises(bridge.EvaluationError):
        bridge.parse_request(payload)


def test_parse_request_accepts_the_exact_bridge_schema():
    parsed = bridge.parse_request(valid_payload())
    assert parsed.tool == "write"
    assert parsed.path == "src/handlers/new_handler.py"


def test_parse_request_rejects_a_missing_schema():
    payload = valid_payload()
    payload.pop("schema")
    with pytest.raises(bridge.EvaluationError, match="schema_missing"):
        bridge.parse_request(payload)


@pytest.mark.parametrize(
    "schema",
    [
        "mneme.opencode.bridge/v2",
        "mneme.opencode.bridge/v1 ",
        "",
        1,
        True,
    ],
)
def test_parse_request_rejects_a_mismatched_schema(schema):
    payload = valid_payload()
    payload["schema"] = schema
    with pytest.raises(bridge.EvaluationError, match="schema_mismatch"):
        bridge.parse_request(payload)


def test_parse_request_preserves_host_identifiers():
    parsed = bridge.parse_request(valid_payload())
    assert parsed.session_id == "ses_test"
    assert parsed.call_id == "call_1"
    assert parsed.agent == "test"
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


def test_resolve_target_rejects_relative_escape(s1_fixture):
    with pytest.raises(bridge.EvaluationError, match="target_outside_session_directory"):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path="../../escape.py",
            )
        )


def test_resolve_target_allows_absolute_outside_root(tmp_path, project_factory):
    session = tmp_path / "session"
    session.mkdir()
    sibling = project_factory()
    target = sibling.root / "src" / "handlers" / "new_handler.py"
    resolved = bridge.resolve_target(
        request(session_directory=str(session), path=str(target))
    )
    assert resolved == target.resolve()


def test_resolve_target_rejects_absolute_symlink(tmp_path, s1_fixture):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = outside / "linked"
    try:
        link.symlink_to(s1_fixture.root / "src", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(bridge.UnsupportedError, match="symlink_target"):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path=str(link / "handlers" / "new_handler.py"),
            )
        )


def test_resolve_target_missing_parent_is_unsupported(s1_fixture):
    with pytest.raises(bridge.UnsupportedError, match="target_parent_missing"):
        bridge.resolve_target(
            request(
                session_directory=str(s1_fixture.root),
                path="src/handlers/missing/new_handler.py",
            )
        )


def test_identity_missing_requires_all_six_host_ids():
    complete = request()
    assert bridge._identity_missing(complete) == []
    incomplete = request(
        session_id="",
        call_id="",
        agent="",
        message_id="",
        event_id="",
    )
    assert bridge._identity_missing(incomplete) == [
        "sessionID",
        "callID",
        "agent",
        "messageID",
        "eventID",
    ]


def test_evidence_projects_canonical_records_verbatim(s1_fixture):
    authority = bridge.load_authority(str(s1_fixture.authority))
    applicability = (
        {
            "decision_id": s1_fixture.decision_id,
            "rule_id": s1_fixture.rule_id,
            "decision_version_id": s1_fixture.version_id,
            "outcome": "APPLIED",
            "input_path": "src/handlers/new_handler.py",
        },
    )
    violations = (
        {
            "decision_id": s1_fixture.decision_id,
            "rule_id": s1_fixture.rule_id,
            "decision_version_id": s1_fixture.version_id,
            "rule_type": "FORBID_LITERAL",
            "severity": "FAIL",
            "input_path": "src/handlers/new_handler.py",
        },
    )
    outcome = bridge.Outcome(
        decision=bridge.BLOCK,
        reason="literal_violation",
        claim=bridge.EXECUTION_OBSERVED,
        observation_state="TRUSTED_COMPLETE",
        applicability="APPLIED",
        target=str(s1_fixture.root / "src" / "handlers" / "new_handler.py"),
        memory=str(s1_fixture.memory),
        applicability_records=applicability,
        violations=violations,
        violated_rule_ids=(s1_fixture.rule_id,),
    )
    evidence = bridge._evidence(
        request(session_directory=str(s1_fixture.root)),
        authority,
        outcome,
        "strict",
        "default",
        False,
    )
    assert evidence["applicability"] == list(applicability)
    assert evidence["violations"] == list(violations)
    assert evidence["violated_rule_ids"] == [s1_fixture.rule_id]
    assert evidence["event"]["tool"] == "write"
    assert evidence["host_witness"] is None
    assert evidence["identity"]["complete"] is True


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


def test_legacy_fail_without_canonical_literal_identity_does_not_block(
    s1_fixture, monkeypatch
):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": "FAIL",
        "mode": "strict",
        "evaluation_complete": True,
        "applicability": [
            {
                "decision_id": s1_fixture.decision_id,
                "rule_type": "FORBID_LITERAL",
                "rule_value": "psycopg2",
                "rule_index": 0,
                "path_scoped": True,
                "input_path": "src/handlers/new_handler.py",
                "outcome": "APPLIED",
                "selector": "include_paths",
                "reason": "include_path_matched",
                "rule_id": s1_fixture.rule_id,
                "decision_version_id": s1_fixture.version_id,
            }
        ],
        # Legacy-only violation shape: no canonical rule_type or rule_id.
        "violations": [
            {
                "decision_id": s1_fixture.decision_id,
                "decision_text": "legacy literal violation",
                "severity": "FAIL",
                "rule": "psycopg2",
                "trigger": "psycopg2",
                "kind": "literal",
            }
        ],
        "freshness": [],
    }
    proc = subprocess.CompletedProcess(
        args=[],
        returncode=2,
        stdout=json.dumps(payload),
        stderr="",
    )
    monkeypatch.setattr(bridge, "_invoke_check", lambda *args, **kwargs: proc)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_MODE", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    monkeypatch.delenv("MNEME_MEMORY", raising=False)

    authority = bridge.load_authority(str(s1_fixture.authority))
    outcome = bridge.evaluate(request(session_directory=str(s1_fixture.root)), authority)

    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "fail_without_canonical_literal_violation"
    assert outcome.claim == bridge.NO_CLAIM
    assert outcome.violated_rule_ids == ()


def test_incoherent_checker_payload_is_unevaluated(s1_fixture, monkeypatch):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": "FAIL",
        "mode": "strict",
        "evaluation_complete": True,
        "applicability": [],
        "violations": [],
        "freshness": [],
    }
    proc = subprocess.CompletedProcess(
        args=[], returncode=2, stdout=json.dumps(payload), stderr=""
    )
    monkeypatch.setattr(bridge, "_invoke_check", lambda *args, **kwargs: proc)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_MODE", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    authority = bridge.load_authority(str(s1_fixture.authority))
    outcome = bridge.evaluate(request(session_directory=str(s1_fixture.root)), authority)
    assert outcome.decision == bridge.UNEVALUATED
    assert "inconsistent verdict payload" in outcome.reason
    assert outcome.claim == bridge.NO_CLAIM


def test_incomplete_checker_payload_is_unevaluated(s1_fixture, monkeypatch):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": "PASS",
        "mode": "strict",
        "evaluation_complete": False,
        "applicability": [
            {
                "decision_id": s1_fixture.decision_id,
                "rule_type": "FORBID_LITERAL",
                "rule_value": "psycopg2",
                "outcome": "UNKNOWN",
                "rule_id": s1_fixture.rule_id,
                "decision_version_id": s1_fixture.version_id,
            }
        ],
        "violations": [],
        "freshness": [],
    }
    proc = subprocess.CompletedProcess(
        args=[], returncode=2, stdout=json.dumps(payload), stderr=""
    )
    monkeypatch.setattr(bridge, "_invoke_check", lambda *args, **kwargs: proc)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_MODE", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    authority = bridge.load_authority(str(s1_fixture.authority))
    outcome = bridge.evaluate(request(session_directory=str(s1_fixture.root)), authority)
    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "evaluation_incomplete"
    assert outcome.observation_state == "INCOMPLETE"
    assert outcome.claim == bridge.NO_CLAIM

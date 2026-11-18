"""Unit-level contract tests for the OpenCode S1 bridge.

These tests exercise the bridge's own normalization and authority checks. They do
not run the checker; the offline integration suite does that.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.opencode import bridge

BRIDGE_SCHEMA = "mneme.opencode.bridge/v1"

PLUGIN_SOURCE = (
    Path(__file__).resolve().parents[3] / "integrations" / "opencode-plugin" / "index.ts"
)


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


SECONDARY_RULE_ID = "ADR-002:FORBID_LITERAL:" + "a" * 32
SECONDARY_VERSION_ID = "dver-" + "1" * 32
MISMATCHED_VERSION_ID = "dver-" + "2" * 32


def _applicability_entry(
    fixture, rule_id, version_id, *, rule_value="psycopg2"
):
    return {
        "decision_id": "ADR-002" if rule_id == SECONDARY_RULE_ID else fixture.decision_id,
        "rule_type": "FORBID_LITERAL",
        "rule_value": rule_value,
        "rule_index": 0,
        "path_scoped": True,
        "input_path": "src/handlers/new_handler.py",
        "outcome": "APPLIED",
        "selector": "include_paths",
        "reason": "include_path_matched",
        "rule_id": rule_id,
        "decision_version_id": version_id,
    }


def _literal_violation(rule_id, version_id, *, kind="typed_rule"):
    return {
        "decision_id": "ADR-002",
        "decision_text": "secondary literal violation",
        "severity": "FAIL",
        "rule": "forbidden_secondary",
        "trigger": "forbidden_secondary",
        "kind": kind,
        "rule_type": "FORBID_LITERAL",
        "rule_id": rule_id,
        "decision_version_id": version_id,
    }


def _evaluate_with_payload(fixture, monkeypatch, applicability, violations):
    payload = {
        "schema": "mneme.check/v1",
        "verdict": "FAIL",
        "mode": "strict",
        "evaluation_complete": True,
        "applicability": applicability,
        "violations": violations,
        "freshness": [],
    }
    proc = subprocess.CompletedProcess(
        args=[], returncode=2, stdout=json.dumps(payload), stderr=""
    )
    monkeypatch.setattr(bridge, "_invoke_check", lambda *args, **kwargs: proc)
    for name in ("CLAUDE_PLUGIN_OPTION_MODE", "MNEME_HOOK_MODE", "MNEME_MEMORY"):
        monkeypatch.delenv(name, raising=False)
    authority = bridge.load_authority(str(fixture.authority))
    return bridge.evaluate(
        request(session_directory=str(fixture.root)), authority
    )


def test_linked_secondary_literal_violation_blocks(s1_fixture, monkeypatch):
    applicability = [
        _applicability_entry(
            s1_fixture, s1_fixture.rule_id, s1_fixture.version_id
        ),
        _applicability_entry(
            s1_fixture,
            SECONDARY_RULE_ID,
            SECONDARY_VERSION_ID,
            rule_value="forbidden_secondary",
        ),
    ]
    outcome = _evaluate_with_payload(
        s1_fixture,
        monkeypatch,
        applicability,
        [_literal_violation(SECONDARY_RULE_ID, SECONDARY_VERSION_ID)],
    )

    assert outcome.decision == bridge.BLOCK
    assert outcome.claim == bridge.EXECUTION_OBSERVED
    assert outcome.violated_rule_ids == (SECONDARY_RULE_ID,)


def test_literal_violation_without_applied_entry_is_unevaluated(
    s1_fixture, monkeypatch
):
    applicability = [
        _applicability_entry(
            s1_fixture, s1_fixture.rule_id, s1_fixture.version_id
        )
    ]
    outcome = _evaluate_with_payload(
        s1_fixture,
        monkeypatch,
        applicability,
        [_literal_violation(SECONDARY_RULE_ID, SECONDARY_VERSION_ID)],
    )

    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "fail_without_canonical_literal_violation"
    assert outcome.claim == bridge.NO_CLAIM
    assert outcome.violated_rule_ids == ()


def test_literal_violation_with_mismatched_version_is_unevaluated(
    s1_fixture, monkeypatch
):
    applicability = [
        _applicability_entry(
            s1_fixture, s1_fixture.rule_id, s1_fixture.version_id
        ),
        _applicability_entry(
            s1_fixture,
            SECONDARY_RULE_ID,
            SECONDARY_VERSION_ID,
            rule_value="forbidden_secondary",
        ),
    ]
    outcome = _evaluate_with_payload(
        s1_fixture,
        monkeypatch,
        applicability,
        [_literal_violation(SECONDARY_RULE_ID, MISMATCHED_VERSION_ID)],
    )

    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "fail_without_canonical_literal_violation"
    assert outcome.claim == bridge.NO_CLAIM
    assert outcome.violated_rule_ids == ()


def test_untyped_literal_violation_does_not_block(s1_fixture, monkeypatch):
    applicability = [
        _applicability_entry(
            s1_fixture, s1_fixture.rule_id, s1_fixture.version_id
        ),
        _applicability_entry(
            s1_fixture,
            SECONDARY_RULE_ID,
            SECONDARY_VERSION_ID,
            rule_value="forbidden_secondary",
        ),
    ]
    outcome = _evaluate_with_payload(
        s1_fixture,
        monkeypatch,
        applicability,
        [
            _literal_violation(
                SECONDARY_RULE_ID, SECONDARY_VERSION_ID, kind="literal"
            )
        ],
    )

    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "fail_without_canonical_literal_violation"
    assert outcome.claim == bridge.NO_CLAIM


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


# --- U-19: plugin read surface ------------------------------------------------
#
# The plugin is TypeScript executed by the host, so these are source-contract
# guards. They are supplementary only: the host-visible warning itself is
# verified at runtime by independent revalidation (I-16 / RT-1..RT-4), not here.


def plugin_source() -> str:
    return PLUGIN_SOURCE.read_text(encoding="utf-8")


def test_plugin_emits_canonical_warn_diagnostic():
    """A warn-mode allow produces the canonical host-visible line."""
    src = plugin_source()
    assert 'decision.decision === "allow"' in src
    assert 'decision.reason === "warn_mode_violation"' in src
    assert 'console.error("Mneme WARN: warn_mode_violation")' in src


def test_plugin_enforcement_control_is_decision_only():
    """The only throw is gated on `decision === "block"`."""
    src = plugin_source()
    throws = [line for line in src.splitlines() if "throw new Error" in line]
    assert len(throws) == 1
    assert src.index(throws[0]) > src.index('decision.decision === "block"')
    assert "reason ===" not in throws[0]


def test_plugin_does_not_parse_decision_payload():
    """No decision field beyond `decision` and `reason` is read."""
    src = plugin_source()
    for field in (
        "decision.evidence",
        "decision.violations",
        "decision.applicability",
        "decision.claim",
        "decision.host_witness",
    ):
        assert field not in src


def test_plugin_reason_is_diagnostic_only():
    """`reason` is compared once, for the warn diagnostic, and never to gate."""
    src = plugin_source()
    assert src.count("reason ===") == 1
    assert 'decision.reason === "warn_mode_violation"' in src

# --- E1 edit surface: input normalisation and precondition mapping ----------

SCHEMA = "mneme.opencode.bridge/v1"


def _payload(root, path, old, new, *, replace_all=None, tool="edit"):
    raw = {"path": path, "oldString": old, "newString": new}
    if replace_all is not None:
        raw["replaceAll"] = replace_all
    return {
        "schema": SCHEMA,
        "tool": tool,
        "input": raw,
        "sessionDirectory": str(root),
        "sessionID": "ses_test",
        "callID": "call_1",
        "agent": "test",
        "messageID": "msg_1",
        "eventID": "evt_1",
        "hostVersion": "2.3.0",
    }


AUTHORITY = bridge.Authority(
    decision_id="ADR-001",
    decision_version_id="dver-test",
    rule_id="ADR-001:FORBID_LITERAL:test",
    rule_value="psycopg2",
    rule_scope="src/handlers/**",
)


def _evaluate(payload):
    return bridge.evaluate(bridge.parse_request(payload), AUTHORITY)


def test_edit_input_is_normalised(tmp_path):
    """E1-U1: host camelCase maps to the canonical snake_case keys."""
    payload = _payload(tmp_path, "src/handlers/a.py", "A = 1", "A = 2", replace_all=True)
    request = bridge.parse_request(payload)
    assert request.tool == "edit"
    assert request.old_string == "A = 1"
    assert request.new_string == "A = 2"
    assert request.replace_all is True


def test_replace_all_defaults_to_false(tmp_path):
    payload = _payload(tmp_path, "src/handlers/a.py", "A = 1", "A = 2")
    assert bridge.parse_request(payload).replace_all is False


def test_ambiguous_old_string_is_unevaluated(tmp_path):
    """E1-U2: multiple matches without replaceAll mirror the host refusal."""
    target = tmp_path / "src" / "handlers" / "dup.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\nMIDDLE = 0\nVALUE = 1\n", encoding="utf-8")

    outcome = _evaluate(_payload(tmp_path, "src/handlers/dup.py", "VALUE = 1", "VALUE = 2"))
    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "ambiguous_old_string"
    assert outcome.claim == bridge.NO_CLAIM
    assert outcome.materialisation["occurrences"] == 2
    assert outcome.materialisation["ambiguous"] is True
    assert outcome.materialisation["replacement_count"] == 1


def test_ambiguous_with_replace_all_proceeds(tmp_path):
    """E1-U2b: replaceAll opts into every occurrence."""
    target = tmp_path / "src" / "handlers" / "dup.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\nMIDDLE = 0\nVALUE = 1\n", encoding="utf-8")

    outcome = _evaluate(
        _payload(tmp_path, "src/handlers/dup.py", "VALUE = 1", "VALUE = 2", replace_all=True)
    )
    # Memory resolution fails in a bare tmp tree, but the ambiguity gate is past.
    assert outcome.reason != "ambiguous_old_string"
    assert outcome.materialisation["replacement_count"] == -1
    assert outcome.materialisation["ambiguous"] is False


def test_missing_old_string_is_unevaluated(tmp_path):
    """E1-U3: absent oldString maps to unevaluated, never a block."""
    target = tmp_path / "src" / "handlers" / "present.py"
    target.parent.mkdir(parents=True)
    target.write_text("ALPHA = 1\n", encoding="utf-8")

    outcome = _evaluate(_payload(tmp_path, "src/handlers/present.py", "ABSENT", "X"))
    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "old_string_not_found"
    assert outcome.claim == bridge.NO_CLAIM
    assert outcome.materialisation["occurrences"] == 0


def test_identical_replacement_is_skip(tmp_path):
    """E1-U4: an empty introduced delta is a skip, not a block."""
    target = tmp_path / "src" / "handlers" / "same.py"
    target.parent.mkdir(parents=True)
    target.write_text("SAME = 1\n", encoding="utf-8")

    outcome = _evaluate(_payload(tmp_path, "src/handlers/same.py", "SAME = 1", "SAME = 1"))
    assert outcome.decision == bridge.SKIP
    assert outcome.reason == "empty_introduced_content"
    assert outcome.claim == bridge.NO_CLAIM


def test_non_python_target_is_unsupported(tmp_path):
    """E1-U5: only .py targets are in scope."""
    target = tmp_path / "notes.txt"
    target.write_text("A = 1\n", encoding="utf-8")

    outcome = _evaluate(_payload(tmp_path, "notes.txt", "A = 1", "A = 2"))
    assert outcome.decision == bridge.UNSUPPORTED
    assert outcome.reason == "non_python_target"
    assert outcome.claim == bridge.NO_CLAIM


def test_missing_target_is_unsupported(tmp_path):
    """E1-U6: edit requires an existing target."""
    outcome = _evaluate(_payload(tmp_path, "src/handlers/absent.py", "A", "B"))
    assert outcome.decision == bridge.UNSUPPORTED
    assert outcome.reason == "target_missing"
    assert outcome.claim == bridge.NO_CLAIM


def test_edit_without_strings_is_unevaluated(tmp_path):
    """Incomplete edit payloads never enforce."""
    target = tmp_path / "src" / "handlers" / "a.py"
    target.parent.mkdir(parents=True)
    target.write_text("A = 1\n", encoding="utf-8")
    payload = _payload(tmp_path, "src/handlers/a.py", "A = 1", "A = 2")
    del payload["input"]["oldString"]

    outcome = _evaluate(payload)
    assert outcome.decision == bridge.UNEVALUATED
    assert outcome.reason == "non_complete_edit"


def test_write_surface_unchanged(tmp_path):
    """E1-U8: the S1 write path still maps to the same reasons."""
    payload = {
        "schema": SCHEMA,
        "tool": "write",
        "input": {"path": "src/handlers/new.py", "content": ""},
        "sessionDirectory": str(tmp_path),
        "sessionID": "s", "callID": "c", "agent": "a",
        "messageID": "m", "eventID": "e", "hostVersion": "2.3.0",
    }
    outcome = _evaluate(payload)
    assert outcome.decision == bridge.SKIP
    assert outcome.reason == "empty_content"

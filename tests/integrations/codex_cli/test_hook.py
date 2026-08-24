"""M1d-b unit tests: GateResult -> Codex wire mapping and entrypoint behavior.

The live transport proof against the pinned binary lives in
validation/codex-cli/probe/run_m1db_live.py; these tests pin the production
mapping itself.
"""
import io
import json
import sys
from pathlib import Path

from mneme.integrations.codex_cli.gate import (
    DENY,
    FAIL_OPEN,
    PASS,
    SKIP,
    WARN,
    GateResult,
)
from mneme.integrations.codex_cli.hook import (
    UNEVALUATED_CONTEXT_PREFIX,
    WARN_CONTEXT_PREFIX,
    main,
    map_result,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FROZEN = "pretooluse_applypatch_addfile_allow.json"


def _result(action, reason=""):
    return GateResult(action=action, reason=reason, target_path="x.py")


def _payload_with_command(command):
    payload = json.loads((FIXTURES / FROZEN).read_text(encoding="utf-8"))
    payload["tool_input"]["command"] = command
    return payload


# --- map_result: only proven shapes ---


def test_pass_and_skip_map_to_no_output():
    assert map_result(_result(PASS)) is None
    assert map_result(_result(SKIP)) is None


def test_deny_maps_to_r0_proven_shape():
    wire = map_result(_result(DENY, "mneme: FAIL - violated"))
    assert wire == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "mneme: FAIL - violated",
        }
    }


def test_warn_maps_to_m1da_proven_context():
    wire = map_result(_result(WARN, "some warning"))
    text = wire["hookSpecificOutput"]["additionalContext"]
    assert text.startswith(WARN_CONTEXT_PREFIX)
    assert "some warning" in text
    body = json.dumps(wire)
    assert "permissionDecision" not in body
    assert '"allow"' not in body and '"ask"' not in body


def test_fail_open_maps_to_unevaluated_context():
    wire = map_result(_result(FAIL_OPEN, "proposal not evaluated (boom)"))
    text = wire["hookSpecificOutput"]["additionalContext"]
    assert text.startswith(UNEVALUATED_CONTEXT_PREFIX)
    assert "NOT evaluated" in text
    assert "permissionDecision" not in json.dumps(wire)


# --- main() end-to-end over a real governed project ---


def _governed_project(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "decisions": [{
            "id": "ADR-T",
            "decision": "No forbidden tokens",
            "rules": [{"type": "FORBID_LITERAL", "value": "FORBIDDEN_TOKEN_XYZ"}],
        }],
    }), encoding="utf-8")
    return tmp_path


def _run_main(payload, project):
    envelope = dict(payload)
    # Override unconditionally: fixtures carry NORMALIZED_CWD placeholders,
    # and resolving those would walk up into an unrelated governed project.
    envelope["cwd"] = str(project)
    out = io.StringIO()
    code = main(stdin=io.StringIO(json.dumps(envelope)), stdout=out,
                stderr=io.StringIO())
    raw = out.getvalue().strip()
    return code, (json.loads(raw) if raw else None)


def test_main_compliant_payload_is_silent(tmp_path, monkeypatch):
    project = _governed_project(tmp_path, monkeypatch)
    code, wire = _run_main(_payload_with_command(
        "*** Begin Patch\n*** Add File: probe_target.py\n+def ok():\n+    return 1\n*** End Patch"
    ), project)
    assert code == 0 and wire is None


def test_main_violating_strict_payload_denies(tmp_path, monkeypatch):
    project = _governed_project(tmp_path, monkeypatch)
    code, wire = _run_main(_payload_with_command(
        '*** Begin Patch\n*** Add File: probe_target.py\n+x = "FORBIDDEN_TOKEN_XYZ"\n*** End Patch'
    ), project)
    assert code == 0
    assert wire["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_warn_mode_emits_nonblocking_context(tmp_path, monkeypatch):
    project = _governed_project(tmp_path, monkeypatch)
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    code, wire = _run_main(_payload_with_command(
        '*** Begin Patch\n*** Add File: probe_target.py\n+x = "FORBIDDEN_TOKEN_XYZ"\n*** End Patch'
    ), project)
    assert code == 0
    assert wire["hookSpecificOutput"]["additionalContext"].startswith(WARN_CONTEXT_PREFIX)
    assert "permissionDecision" not in json.dumps(wire)


def test_main_malformed_memory_fails_open_visibly(tmp_path, monkeypatch):
    project = _governed_project(tmp_path, monkeypatch)
    memory = project / ".mneme" / "project_memory.json"
    memory.write_text("{ this is not json", encoding="utf-8")
    code, wire = _run_main(_payload_with_command(
        "*** Begin Patch\n*** Add File: probe_target.py\n+def ok():\n+    return 1\n*** End Patch"
    ), project)
    assert code == 0
    text = wire["hookSpecificOutput"]["additionalContext"]
    assert text.startswith(UNEVALUATED_CONTEXT_PREFIX)
    assert "NOT evaluated" in text

"""M1g-b tests: Delete File transport recognition.

Policy statement (frozen): Delete File is recognized by the Codex
transport, but current Mneme edit-gate policy does not block pure deletions
because ADR-018 governs introduced content. A parsed Delete resolves to
SKIP by design. Any delete-policy semantics (e.g., forbidding deletion of
governed artifacts) would be a new enforcement semantic outside this
integration.
"""
import json
from pathlib import Path

import pytest

from mneme.integrations.codex_cli.gate import (
    DENY,
    PASS,
    SKIP,
    evaluate_apply_patch,
)
from mneme.integrations.codex_cli.patch_parser import (
    CodexPatchParseError,
    parse_patch_operations,
    patch_operation_specs,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DELETE_FIXTURE = "pretooluse_applypatch_deletefile_allow.json"


REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = REPO_ROOT / "validation" / "codex-cli" / "evidence" / "runs"
DELETE_RUN = "20260824T202758Z-deletefile"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _delete_command(path="service.py"):
    return f"*** Begin Patch\n*** Delete File: {path}\n*** End Patch"


def _project_with_seed(tmp_path, monkeypatch, seed="def existing():\n    return 1\n"):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    project = tmp_path
    (project / ".mneme").mkdir(parents=True)
    (project / ".mneme" / "project_memory.json").write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "decisions": [{
            "id": "ADR-D",
            "decision": "The forbidden token must not appear.",
            "rules": [{"type": "FORBID_LITERAL",
                       "value": "FORBIDDEN_TOKEN_XYZ"}],
        }],
    }), encoding="utf-8")
    if seed is not None:
        (project / "service.py").write_text(seed, encoding="utf-8")
    return project


def _pass_runner():
    import subprocess

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
            "schema": "mneme.check/v1", "verdict": "PASS", "mode": "strict",
            "violations": [], "freshness": [], "evaluation_complete": True}),
            stderr="")
    return run


def _fail_runner():
    import subprocess

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps({
            "schema": "mneme.check/v1", "verdict": "FAIL", "mode": "strict",
            "violations": [{
                "decision_id": "ADR-D", "severity": "FAIL",
                "rule": "FORBIDDEN_TOKEN_XYZ",
                "trigger": "FORBIDDEN_TOKEN_XYZ",
                "decision_text": "The forbidden token must not appear.",
                "input_path": "helper.py"}],
            "freshness": [], "evaluation_complete": True}), stderr="")
    return run


# --- frozen grammar ------------------------------------------------------------


def test_fixture_provenance_and_header_only_grammar():
    fixture = _load(DELETE_FIXTURE)
    source_dir = (EVIDENCE / DELETE_RUN / "events-allow" / "events")
    index = [json.loads(l) for l in
             (source_dir / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    entry = next(e for e in index if e["hook_event_name"] == "PreToolUse")
    observed = json.loads((source_dir / entry["file"]).read_text(encoding="utf-8"))
    root = chr(92).join(["C:", "dev", "mneme", ".worktrees",
                         "feat-codex-cli-enforcement", "validation",
                         "codex-cli", "probe", "sandbox", "repo"])
    observed["session_id"] = "NORMALIZED_SESSION_ID"
    observed["turn_id"] = "NORMALIZED_TURN_ID"
    observed["transcript_path"] = "NORMALIZED_TRANSCRIPT_PATH"
    observed["cwd"] = observed["cwd"].replace(
        root, chr(92).join(["C:", "codex-probe-sandbox"]))
    import re
    observed["tool_use_id"] = re.sub(
        r"exec-.*", "exec-NORMALIZED_TOOL_USE_ID", observed["tool_use_id"])
    assert fixture == observed

    command = fixture["tool_input"]["command"]
    assert command == "*** Begin Patch\n*** Delete File: service.py\n*** End Patch"


def test_specs_and_operations_for_standalone_delete():
    specs = patch_operation_specs(_delete_command())
    assert specs == [("delete", "service.py")]
    ops = parse_patch_operations(_delete_command())
    assert len(ops) == 1
    assert ops[0].kind == "delete"
    assert ops[0].target_path == "service.py"
    assert ops[0].introduced_content == ""


# --- malformed / unobserved forms ------------------------------------------------


def test_delete_with_body_content_is_malformed():
    """Header-level validation (specs) passes; full-grammar validation in
    parse_patch_operations rejects any body content."""
    command = ("*** Begin Patch\n*** Delete File: service.py\n"
               "-leftover line\n*** End Patch")
    assert patch_operation_specs(command) == [("delete", "service.py")]
    with pytest.raises(CodexPatchParseError, match="header-only"):
        parse_patch_operations(command)


def test_absolute_delete_rejected_unobserved_form():
    with pytest.raises(CodexPatchParseError, match="workspace-relative"):
        patch_operation_specs(_delete_command("C:\\x\\service.py"))


def test_traversal_delete_rejected():
    with pytest.raises(CodexPatchParseError, match="traverse"):
        patch_operation_specs(_delete_command("..\\service.py"))


def test_empty_delete_path_rejected():
    with pytest.raises(CodexPatchParseError, match="empty target path"):
        patch_operation_specs("*** Begin Patch\n*** Delete File: \n*** End Patch")


# --- gate semantics ----------------------------------------------------------------


def test_standalone_delete_skips_by_design(tmp_path, monkeypatch):
    project = _project_with_seed(tmp_path, monkeypatch)
    result = evaluate_apply_patch(
        {"tool_name": "apply_patch", "cwd": str(project),
         "tool_input": {"command": _delete_command()}},
        cwd=str(project), check_runner=_pass_runner())
    assert result.action == SKIP


def test_delete_does_not_suppress_sibling_violation(tmp_path, monkeypatch):
    """Delete + violating Add: the violation still denies the whole patch."""
    project = _project_with_seed(tmp_path, monkeypatch)
    command = ("*** Begin Patch\n*** Delete File: service.py\n"
               "*** Add File: helper.py\n"
               '+x = "FORBIDDEN_TOKEN_XYZ"\n*** End Patch')
    result = evaluate_apply_patch(
        {"tool_name": "apply_patch", "cwd": str(project),
         "tool_input": {"command": command}},
        cwd=str(project), check_runner=_fail_runner())
    assert result.action == DENY
    assert "helper.py" in result.reason


def test_delete_does_not_suppress_sibling_compliance(tmp_path, monkeypatch):
    """Delete + compliant Update: the Update is still governed normally."""
    project = _project_with_seed(tmp_path, monkeypatch)
    command = ("*** Begin Patch\n*** Delete File: service.py\n"
               "*** Update File: other.py\n@@\n-a\n+b\n*** End Patch")
    # other.py must exist for the Update snapshot:
    (project / "other.py").write_text("a\n", encoding="utf-8")
    result = evaluate_apply_patch(
        {"tool_name": "apply_patch", "cwd": str(project),
         "tool_input": {"command": command}},
        cwd=str(project), check_runner=_pass_runner())
    assert result.action == PASS


def test_delete_plus_violating_update_denies(tmp_path, monkeypatch):
    project = _project_with_seed(tmp_path, monkeypatch)
    (project / "other.py").write_text("a\n", encoding="utf-8")
    command = ("*** Begin Patch\n*** Delete File: service.py\n"
               "*** Update File: other.py\n@@\n-a\n"
               '+b = "FORBIDDEN_TOKEN_XYZ"\n*** End Patch')
    result = evaluate_apply_patch(
        {"tool_name": "apply_patch", "cwd": str(project),
         "tool_input": {"command": command}},
        cwd=str(project), check_runner=_fail_runner())
    assert result.action == DENY


# The bundled-call deny shape proven in M1d-b/M1f-c remains the only wire
# mapping; SKIP produces no output.
def test_skip_maps_to_no_wire_output():
    from mneme.integrations.codex_cli.hook import map_result
    from mneme.integrations.codex_cli.gate import GateResult
    assert map_result(GateResult(action=SKIP)) is None

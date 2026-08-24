"""M1f-c tests: bundled apply_patch evaluation and aggregation.

Precedence frozen at M1f-b: DENY > FAIL_OPEN > WARN > PASS/SKIP. A definite
violation anywhere denies the whole call, but the reason must disclose every
operation that was not evaluated.
"""
import json
from pathlib import Path

import pytest

from mneme.integrations.codex_cli.gate import (
    DENY,
    FAIL_OPEN,
    PASS,
    SKIP,
    WARN,
    evaluate_apply_patch,
)
from mneme.integrations.codex_cli.patch_parser import (
    CodexPatchParseError,
    parse_patch_operations,
    patch_operation_specs,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _project(tmp_path, monkeypatch, seed="def existing():\n    return 1\n"):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    project = tmp_path
    (project / ".mneme").mkdir(parents=True, exist_ok=True)
    (project / ".mneme" / "project_memory.json").write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "decisions": [{
            "id": "ADR-M",
            "decision": "The forbidden token must not appear.",
            "rules": [{"type": "FORBID_LITERAL",
                       "value": "FORBIDDEN_TOKEN_XYZ"}],
        }],
    }), encoding="utf-8")
    (project / "service.py").write_text(seed, encoding="utf-8")
    return project


def _bundle(update_body=None, add_path="helper.py",
            add_lines=("+def assist():", "+    return 7")):
    parts = ["*** Begin Patch"]
    if update_body is not None:
        parts.append(f"*** Update File: service.py")
        parts.extend(update_body)
    if add_path is not None:
        parts.append(f"*** Add File: {add_path}")
        parts.extend(add_lines)
    parts.append("*** End Patch")
    return "\n".join(parts)


GOOD_UPDATE = ["@@", " def existing():", "-    return 1", "+    return 42"]
BAD_UPDATE = [
    "@@", " def existing():", "-    return 1",
    '+    return "FORBIDDEN_TOKEN_XYZ"',
]


def _evaluate(project, command, mode=None, runner=None):
    return evaluate_apply_patch(
        {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
         "cwd": str(project), "tool_input": {"command": command}},
        cwd=str(project), mode=mode,
        check_runner=runner or _PassRunner())


class _PassRunner:
    def __init__(self, verdict="PASS"):
        self.verdict = verdict

    def __call__(self, command, **kwargs):
        import subprocess
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({
                "schema": "mneme.check/v1", "verdict": self.verdict,
                "mode": "strict", "violations": [], "freshness": [],
                "evaluation_complete": True}), stderr="")


def _fail_runner():
    """Runner returning a FAIL verdict payload."""
    import subprocess
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps({
            "schema": "mneme.check/v1", "verdict": "FAIL", "mode": "strict",
            "violations": [{
                "decision_id": "ADR-M", "severity": "FAIL",
                "rule": "FORBIDDEN_TOKEN_XYZ", "trigger": "FORBIDDEN_TOKEN_XYZ",
                "decision_text": "The forbidden token must not appear.",
                "input_path": "service.py"}],
            "freshness": [], "evaluation_complete": True}), stderr="")
    return run


# --- parser level ----------------------------------------------------------------


def test_multifile_fixture_parses_to_two_ordered_operations():
    payload = json.loads(
        (FIXTURES / "pretooluse_applypatch_multifile_allow.json")
        .read_text(encoding="utf-8"))
    command = payload["tool_input"]["command"]
    specs = patch_operation_specs(command)
    assert specs == [("update", "service.py"), ("add", "helper.py")]

    ops = parse_patch_operations(command, snapshots={"service.py":
        "MAX_LIMIT = 10\n\n\ndef existing():\n    return 1\n\n\ndef second():"
        "\n    return 2\n"})
    assert [o.kind for o in ops] == ["update", "add"]
    assert ops[0].target_path == "service.py"
    assert ops[0].introduced_content == "    return 42"
    assert ops[1].introduced_content == "def assist():\n    return 7\n"


def test_unknown_operation_in_bundle_rejects_whole_proposal():
    command = ("*** Begin Patch\n*** Update File: a.py\n@@\n+x\n"
               "*** Delete File: b.py\n*** End Patch")
    with pytest.raises(CodexPatchParseError, match="Delete File"):
        patch_operation_specs(command)


def test_absolute_add_rejected_evidence_contract():
    command = ("*** Begin Patch\n*** Add File: C:\\x.py\n+hi\n*** End Patch")
    with pytest.raises(CodexPatchParseError):
        patch_operation_specs(command)


# --- gate level -------------------------------------------------------------------


def test_compliant_bundle_passes_both_operations(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    result = _evaluate(project, _bundle(update_body=GOOD_UPDATE))
    assert result.action == PASS


def test_violating_update_denies_entire_bundle(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    result = _evaluate(project, _bundle(update_body=BAD_UPDATE),
                       runner=_fail_runner())
    assert result.action == DENY
    assert "operation 1 (service.py)" in result.reason


def test_violating_add_denies_entire_bundle(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    command = _bundle(update_body=GOOD_UPDATE,
                      add_lines=('+x = "FORBIDDEN_TOKEN_XYZ"',))
    result = evaluate_apply_patch(
        {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
         "cwd": str(project), "tool_input": {"command": command}},
        cwd=str(project), check_runner=_fail_runner())
    assert result.action == DENY
    assert "operation 2 (helper.py)" in result.reason


def test_deny_plus_unevaluated_discloses_the_unevaluated_operation(
        tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    # Op 1 violates; op 2's snapshot is unreadable -> per-op FAIL_OPEN.
    command = ("*** Begin Patch\n*** Update File: service.py\n@@\n"
               " def existing():\n-    return 1\n"
               '+    return "FORBIDDEN_TOKEN_XYZ"\n'
               "*** Update File: ghost.py\n@@\n-a\n+b\n*** End Patch")
    result = _evaluate(project, command, runner=_fail_runner())
    assert result.action == DENY
    assert "NOT EVALUATED" in result.reason
    assert "ghost.py" in result.reason
    # The known violation must not hide the unevaluated operation:
    assert "FORBIDDEN_TOKEN_XYZ" in result.reason


def test_fail_open_outranks_warn(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    # Op 1 would warn (warn mode); op 2 targets an escaping path ->
    # whole proposal unevaluable before checks.
    command = ("*** Begin Patch\n*** Update File: service.py\n@@\n"
               " def existing():\n-    return 1\n+    return 42\n"
               "*** Update File: ..\\outside.py\n@@\n-a\n+b\n*** End Patch")
    result = _evaluate(project, command, mode="warn")
    assert result.action == FAIL_OPEN


def test_warn_bundle_aggregates(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    result = _evaluate(project, _bundle(update_body=BAD_UPDATE), mode="warn",
                       runner=_fail_runner())
    assert result.action == WARN
    assert "operation 1" in result.reason


def test_malformed_second_operation_makes_whole_proposal_unevaluable(
        tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    command = ("*** Begin Patch\n*** Add File: ok.py\n+fine\n"
               "*** Delete File: other.py\n*** End Patch")
    result = _evaluate(project, command)
    assert result.action == FAIL_OPEN
    assert "proposal not evaluated" in result.reason


def test_blank_only_add_within_bundle_skips_that_operation(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    command = _bundle(update_body=GOOD_UPDATE,
                      add_lines=("+", "+"))
    result = _evaluate(project, command)
    assert result.action == PASS

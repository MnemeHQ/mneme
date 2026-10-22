"""ADR-034 G1 consumer matrix (charter §8.C item 6).

The Claude Code hook, the Claude Agent SDK and LangChain, each driven through
its real entry point and the real ``mneme check`` (in-process transport), on
a project whose canonical memory holds a global ``FORBID_LITERAL`` rule and a
``FORBID_NUMERIC_ABOVE`` rule applicable to ``src/**``.

At the edit gate the checker sees delta input, which is never complete
source, so the numeric rule is always MATCHER_UNEVALUATED /
INCOMPLETE_SOURCE_INPUT. Nothing here claims pre-write numeric detection:

- (a) open availability: a trusted literal violation still blocks in strict
  mode next to the numeric incompleteness (M-a); warn mode stays
  non-blocking; unknown-only proceeds with a visible diagnostic;
- (b) authorized closed availability: an ordinary nonempty edit on an APPLIED
  numeric path is refused as EVALUATION_INCOMPLETE; EXCLUDED and empty
  events are not blocked by the numeric rule;
- (c) mixed: the refusal keeps the literal violation evidence and never calls
  the numeric rule violated;
- (d) contradictory payloads are untrusted; historical payloads unchanged.
"""
from __future__ import annotations

import copy
import io
import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.agent_sdk import (
    ACTION_ALLOW,
    ACTION_DENY,
    ACTION_FAIL_OPEN,
    ACTION_SKIP,
    ACTION_WARN,
    MnemeAgentSdk,
)
from mneme.integrations.claude_code import availability, hook
from mneme.integrations.claude_code.inprocess_check import run_check_inprocess
from mneme.integrations.langchain import MnemeLangChain
from mneme.numeric_rule import NumericContract
from mneme.rule_identity import rule_id_for
from mneme.schemas import Rule
from tests.canonical_fixtures import canonical_document

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NUMERIC = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="5", unit="seconds", symbol="ROUTER_DEADLINE_S",
        call_function="classify", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
NUMERIC_ID = rule_id_for("ADR-034T", NUMERIC)

LITERAL_EDIT = "import psycopg2\nROUTER_DEADLINE_S = 3\n"
NUMERIC_ONLY_EDIT = "ROUTER_DEADLINE_S = 3\n"


def _memory_document() -> dict:
    return canonical_document({
        "meta": {"name": "numeric-consumers", "description": "ADR-034 G1"},
        "items": [],
        "decisions": [
            {"id": "LIT-1", "decision": "Do not use psycopg2", "rationale": "r",
             "scope": ["storage"],
             "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
             "created_at": "2026-10-22", "updated_at": "2026-10-22",
             "status": "active"},
            {"id": "ADR-034T", "decision": "Router deadline at most 5 seconds",
             "rationale": "r", "scope": ["router"],
             "rules": [{"type": NUMERIC.type, "value": NUMERIC.value,
                        "include_paths": ["src/**"]}],
             "created_at": "2026-10-22", "updated_at": "2026-10-22",
             "status": "active"},
        ],
    })


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", "inprocess")
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(_memory_document()), encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def closed(project, monkeypatch):
    """An authorized closed availability declaration (ADR-033 C2b)."""
    (project / ".mneme" / "availability.json").write_bytes(
        (FIXTURES / "availability_policy" / "v1" / "valid.json").read_bytes()
    )
    monkeypatch.setattr(availability, "live_verifier", lambda _d: ("AUTHORIZED", ""))
    return project


def _hook(project: Path, rel: str, content: str, *, tool="Write", **extra):
    target = project / rel
    tool_input = {"file_path": str(target), "content": content} | extra
    envelope = {
        "hook_event_name": "PreToolUse", "tool_name": tool,
        "cwd": str(project), "tool_input": tool_input,
    }
    out, err = io.StringIO(), io.StringIO()
    rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def _runner(command, **_kwargs) -> subprocess.CompletedProcess:
    return run_check_inprocess(list(command[3:]))


def _sdk(project: Path, mode: str) -> MnemeAgentSdk:
    return MnemeAgentSdk(project_dir=project, mode=mode, check_runner=_runner)


def _langchain(project: Path, mode: str) -> MnemeLangChain:
    return MnemeLangChain(project_dir=str(project), mode=mode, check_runner=_runner)


# ── (a) open availability ────────────────────────────────────────────────────


def test_a_hook_strict_literal_violation_still_blocks(project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    rc, _, err = _hook(project, "src/router.py", LITERAL_EDIT)
    assert rc == 2
    assert "psycopg2" in err
    assert "numeric typed rule(s) not evaluated on this input" in err
    assert f"{NUMERIC_ID}: MATCHER_UNEVALUATED (INCOMPLETE_SOURCE_INPUT)" in err


def test_a_hook_warn_mode_stays_non_blocking(project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, out, err = _hook(project, "src/router.py", LITERAL_EDIT)
    assert rc == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "defer"
    assert "INCOMPLETE_SOURCE_INPUT" in err


def test_a_hook_unknown_only_proceeds_with_visible_diagnostic(project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    rc, out, err = _hook(project, "src/router.py", NUMERIC_ONLY_EDIT)
    assert rc == 0 and out == ""
    assert "numeric typed rule(s) not evaluated on this input" in err
    assert "path applicability is unknown" not in err


def test_a_hook_numeric_rule_never_blocks_a_value_above_max_at_the_gate(project, monkeypatch):
    """No pre-write numeric detection is claimed: delta input is unevaluated."""
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    rc, _, err = _hook(project, "src/router.py", "ROUTER_DEADLINE_S = 600\n")
    assert rc == 0
    assert "INCOMPLETE_SOURCE_INPUT" in err


@pytest.mark.parametrize("adapter", ["sdk", "langchain"])
@pytest.mark.parametrize("mode,content,action", [
    ("strict", LITERAL_EDIT, ACTION_DENY),
    ("warn", LITERAL_EDIT, ACTION_WARN),
    ("strict", NUMERIC_ONLY_EDIT, ACTION_FAIL_OPEN),
    ("warn", NUMERIC_ONLY_EDIT, ACTION_FAIL_OPEN),
])
def test_a_sdk_and_langchain_follow_m_a(project, adapter, mode, content, action):
    target = str(project / "src" / "router.py")
    if adapter == "sdk":
        result = _sdk(project, mode).evaluate_mutation(
            "Write", {"file_path": target, "content": content}, cwd=str(project)
        )
    else:
        result = _langchain(project, mode).evaluate_tool_call(
            "write_file", {"file_path": target, "content": content}, cwd=str(project)
        )
    assert result.action == action
    assert result.evaluation_complete is False
    assert "INCOMPLETE_SOURCE_INPUT" in result.reason
    if action in (ACTION_DENY, ACTION_WARN):
        assert "psycopg2" in result.reason


def test_a_sdk_pre_tool_use_denies_with_both_facts(project):
    output = _sdk(project, "strict").pre_tool_use({
        "tool_name": "Write",
        "tool_input": {"file_path": str(project / "src" / "router.py"),
                       "content": LITERAL_EDIT},
        "cwd": str(project),
    })
    specific = output["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "psycopg2" in specific["permissionDecisionReason"]
    assert "INCOMPLETE_SOURCE_INPUT" in specific["permissionDecisionReason"]


def test_a_excluded_path_keeps_complete_literal_behavior(project):
    target = str(project / "docs" / "notes.md")
    sdk = _sdk(project, "strict")
    clean = sdk.evaluate_mutation("Write", {"file_path": target, "content": "notes\n"})
    assert clean.action == ACTION_ALLOW and clean.evaluation_complete is True
    hit = sdk.evaluate_mutation("Write", {"file_path": target, "content": "psycopg2\n"})
    assert hit.action == ACTION_DENY and hit.evaluation_complete is True


def test_a_legacy_incomplete_payload_keeps_fail_open_semantics():
    """No numeric records: path-UNKNOWN plus FAIL is unchanged (fails open)."""
    golden = json.loads(
        (FIXTURES / "numeric_g1" / "no_numeric_golden.json").read_text(encoding="utf-8")
    )
    record = golden["path_unknown_with_fail_strict"]
    payload = hook.assess_verdict(record["stdout"], record["exit"], "strict").payload
    assert payload["verdict"] == "FAIL" and payload["evaluation_complete"] is False
    assert hook.mixed_violation_actionable(payload) is False


# ── (b) authorized closed availability ───────────────────────────────────────


def test_b_closed_refuses_nonempty_edit_on_applied_numeric_path(closed, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    rc, _, err = _hook(closed, "src/router.py", NUMERIC_ONLY_EDIT)
    assert rc == 2
    assert "evaluation=INCOMPLETE; operational refusal." in err
    assert f"{NUMERIC_ID} MATCHER_UNEVALUATED (INCOMPLETE_SOURCE_INPUT)" in err
    assert availability.refusal_category("AUTHORIZED", "INCOMPLETE") == "EVALUATION_INCOMPLETE"


def test_b_closed_refuses_even_in_warn_mode(closed, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, _, err = _hook(closed, "src/router.py", NUMERIC_ONLY_EDIT)
    assert rc == 2 and "operational refusal" in err


def test_b_closed_excluded_path_is_not_blocked_by_the_numeric_rule(closed, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    rc, _, err = _hook(closed, "docs/notes.md", "ROUTER_DEADLINE_S = 3\n")
    assert rc == 0
    assert "evaluation=TRUSTED_COMPLETE; availability did not refuse." in err


def test_b_closed_empty_event_keeps_its_skip(closed, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    target = closed / "src" / "router.py"
    target.write_text("ROUTER_DEADLINE_S = 3\nkeep = 1\n", encoding="utf-8")
    rc, _, err = _hook(
        closed, "src/router.py", "", tool="Edit",
        old_string="keep = 1\n", new_string="",
    )
    assert rc == 0
    assert "evaluation=SKIPPED; availability did not refuse." in err


# ── (c) mixed: literal violation plus incompleteness under closed routing ────


def test_c_closed_refusal_keeps_literal_violation_evidence(closed, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    rc, _, err = _hook(closed, "src/router.py", LITERAL_EDIT)
    assert rc == 2
    assert "operational refusal" in err
    assert "1 violation(s) matched in a partial evaluation" in err
    assert "LIT-1" in err
    assert "numeric rule(s) unevaluated on this input" in err
    assert "ADR-034T:" not in err.split("violation(s) matched")[1].split("\n")[0]


# ── (d) contradictions and historical payloads ───────────────────────────────


def _real_payload(project: Path, content: str, mode="strict"):
    source = project / "src" / "router.py"
    source.write_text(content, encoding="utf-8")
    proc = run_check_inprocess([
        "check", "--memory", str(project / ".mneme" / "project_memory.json"),
        "--source-file", str(source), "--query", "router", "--mode", mode, "--json",
    ])
    return json.loads(proc.stdout), proc.returncode


def _numeric(payload):
    return next(i for i in payload["applicability"] if i["rule_type"] == NUMERIC.type)


TAMPERS = {
    "missing_matcher_field": lambda p: _numeric(p).pop("matcher_status"),
    "invalid_status": lambda p: _numeric(p).update(matcher_status="DONE"),
    "status_outcome_contradiction": lambda p: _numeric(p).update(matcher_outcome="NO_VIOLATION"),
    "complete_flag_contradiction": lambda p: p.update(evaluation_complete=True),
    "wrong_primary_reason": lambda p: _numeric(p).update(primary_reason="UNRECOGNIZED_FORM"),
    "dropped_unknown_sources": lambda p: _numeric(p).update(unknown_sources=[]),
    "malformed_unknown_source": lambda p: _numeric(p)["unknown_sources"][0].update(line=0),
    "foreign_subject_digest": lambda p: _numeric(p).update(subject_sha256="f" * 64),
    "missing_subject": lambda p: p.pop("subject"),
    "violation_without_outcome": lambda p: p["violations"].clear(),
    "matcher_on_excluded_trace": lambda p: _numeric(p).update(outcome="EXCLUDED"),
}


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_d_contradictory_numeric_payloads_are_untrusted(project, name):
    payload, code = _real_payload(project, "ROUTER_DEADLINE_S = 60\n")
    assert hook.assess_verdict(json.dumps(payload), code, "strict").payload is not None
    tampered = copy.deepcopy(payload)
    TAMPERS[name](tampered)
    assessment = hook.assess_verdict(json.dumps(tampered), code, "strict")
    assert assessment.payload is None and assessment.inconsistent, name


def test_d_recognized_payload_cannot_hide_unknown_sources(project):
    payload, code = _real_payload(
        project, "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"
    )
    assert _numeric(payload)["matcher_status"] == "RECOGNIZED"
    tampered = copy.deepcopy(payload)
    _numeric(tampered)["unknown_sources"] = [
        {"kind": "call", "line": 3, "reason": "SOURCE_NOT_FOUND"}
    ]
    assert hook.assess_verdict(json.dumps(tampered), code, "strict").payload is None


def test_d_historical_payloads_unchanged():
    golden = json.loads(
        (FIXTURES / "numeric_g1" / "no_numeric_golden.json").read_text(encoding="utf-8")
    )
    for name, record in golden.items():
        mode = "warn" if name.endswith("_warn") else "strict"
        assessment = hook.assess_verdict(record["stdout"], record["exit"], mode)
        assert assessment.payload == json.loads(record["stdout"]), name


@pytest.fixture
def git_project(project, monkeypatch, tmp_path_factory):
    state = tmp_path_factory.mktemp("session-state")
    monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(state))
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(
        ["git", "-C", str(project), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    return project


def _session(project: Path, event: str):
    envelope = {"hook_event_name": event, "session_id": "s-1", "cwd": str(project)}
    if event == "SessionStart":
        envelope["source"] = "startup"
    out, err = io.StringIO(), io.StringIO()
    rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def test_a_stop_backstop_keeps_literal_violation_actionable(git_project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    assert _session(git_project, "SessionStart")[0] == 0
    (git_project / "src" / "router.py").write_text(LITERAL_EDIT, encoding="utf-8")
    rc, out, err = _session(git_project, "Stop")
    assert rc == 0
    decision = json.loads(out)
    assert decision["decision"] == "block" and "psycopg2" in decision["reason"]
    assert "INCOMPLETE_SOURCE_INPUT" in err


def test_a_stop_backstop_unknown_only_is_visible_not_blocking(git_project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    assert _session(git_project, "SessionStart")[0] == 0
    (git_project / "src" / "router.py").write_text("ROUTER_DEADLINE_S = 600\n", encoding="utf-8")
    rc, out, err = _session(git_project, "Stop")
    assert rc == 0
    feedback = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "incomplete rule-path evaluation" in feedback
    assert "INCOMPLETE_SOURCE_INPUT" in err


def test_unmapped_langchain_tool_is_still_skipped(project):
    result = _langchain(project, "strict").evaluate_tool_call("read_file", {})
    assert result.action == ACTION_SKIP

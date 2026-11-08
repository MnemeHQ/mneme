"""ADR-034 §7b: per-rule relevant-enforcement attribution (owner ruling D1).

Pinned regressions of the layer1-freeze amendment "authorize the ADR-034 D1
evidence-validator and D2 matcher changes", Change 1: every row of the §7b
table, no inheritance between rules, an existential event-level value that
never implies completeness, and hook outcomes the validator cannot change.

The hook is driven through its real entry point and the real ``mneme
check`` (in-process transport) on a project whose memory holds a global
``FORBID_LITERAL`` rule and two ``FORBID_NUMERIC_ABOVE`` rules (A and B)
applicable to ``src/**``. Built only from the public contract; no G2-1
validation material is used or implied. Nothing here is an enforcement or
validation claim.
"""
from __future__ import annotations

import ast
import copy
import inspect
import io
import json
from pathlib import Path

import pytest

from mneme.integrations.claude_code import availability, hook
from mneme.numeric_rule import NumericContract
from mneme.rule_identity import rule_id_for
from mneme.schemas import Rule
from tests.canonical_fixtures import canonical_document

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HOST = ("2.1.303", "ab" * 32)
RULE_A = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="5", unit="seconds", symbol="ROUTER_DEADLINE_S",
        call_function="classify", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
RULE_B = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="3", unit="attempts", symbol="RETRY_LIMIT",
        call_function="retry", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
A_ID = rule_id_for("ADR-034A", RULE_A)
B_ID = rule_id_for("ADR-034B", RULE_B)

A_ABOVE = "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"
A_WITHIN = "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"
B_ABOVE = "RETRY_LIMIT = 9\ndef go(x):\n    return retry(x, 1)\n"
B_WITHIN = "RETRY_LIMIT = 2\ndef go(x):\n    return retry(x, 1)\n"
LITERAL = "import psycopg2\n"


def _numeric(decision_id: str, rule: Rule) -> dict:
    return {
        "id": decision_id, "decision": f"{decision_id} numeric bound", "rationale": "r",
        "scope": ["router"],
        "rules": [{"type": rule.type, "value": rule.value,
                   "include_paths": list(rule.include_paths)}],
        "created_at": "2026-10-26", "updated_at": "2026-10-26", "status": "active",
    }


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_EVIDENCE_LOG", "MNEME_HOOK_EVIDENCE_HOST_VERSION",
                 "MNEME_HOOK_EVIDENCE_HOST_SHA256"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", "inprocess")
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    document = canonical_document({
        "meta": {"name": "numeric-d1", "description": "ADR-034 §7b"},
        "items": [],
        "decisions": [
            {"id": "LIT-1", "decision": "Do not use psycopg2", "rationale": "r",
             "scope": ["storage"],
             "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
             "created_at": "2026-10-26", "updated_at": "2026-10-26",
             "status": "active"},
            _numeric("ADR-034A", RULE_A),
            _numeric("ADR-034B", RULE_B),
        ],
    })
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture
def closed(project, monkeypatch):
    """An authorized closed availability declaration (ADR-033 C2b)."""
    (project / ".mneme" / "availability.json").write_bytes(
        (FIXTURES / "availability_policy" / "v1" / "valid.json").read_bytes()
    )
    monkeypatch.setattr(availability, "live_verifier", lambda _d: ("AUTHORIZED", ""))
    return project


@pytest.fixture
def evidence(project, monkeypatch, tmp_path_factory):
    log = tmp_path_factory.mktemp("evidence") / "events.jsonl"
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(log))
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_VERSION", HOST[0])
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_SHA256", HOST[1])
    return log


def _hook(project: Path, content: str, rel: str = "src/new.py"):
    envelope = {
        "hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(project),
        "tool_input": {"file_path": str(project / rel), "content": content},
        "session_id": "sess-1", "tool_use_id": "toolu_1",
    }
    out, err = io.StringIO(), io.StringIO()
    rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


def _record(project: Path, log: Path, content: str) -> tuple:
    rc, _, err = _hook(project, content)
    record, = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return rc, err, record


def _matcher(record: dict, rule_id: str) -> tuple:
    rule, = [r for r in record["rules"] if r["rule_id"] == rule_id]
    return rule["matcher_status"], rule["matcher_outcome"]


def _attribution(record: dict) -> tuple:
    return (
        hook.relevant_enforcement_observed(record, HOST),
        hook.relevant_enforcement_per_rule(record, HOST),
        hook.recorded_evaluation_complete(record),
    )


# ── §7b table, one test per row (real hook runs) ────────────────────────────


def test_row1_violation_refused_other_rule_unevaluated(project, evidence):
    rc, _, record = _record(project, evidence, A_ABOVE)
    assert rc == 2 and record["hook_outcome"] == "refused"
    assert record["disposition"] == {"mode": "strict", "cause": "numeric_violation"}
    assert _matcher(record, A_ID) == ("RECOGNIZED", "VIOLATION")
    assert _matcher(record, B_ID)[0] == "MATCHER_UNEVALUATED"
    assert _attribution(record) == (True, {A_ID: True, B_ID: False}, False)


def test_row2_violation_refused_other_rule_recognized_clean(project, evidence):
    rc, _, record = _record(project, evidence, A_ABOVE + B_WITHIN)
    assert rc == 2 and record["hook_outcome"] == "refused"
    assert _matcher(record, A_ID) == ("RECOGNIZED", "VIOLATION")
    assert _matcher(record, B_ID) == ("RECOGNIZED", "NO_VIOLATION")
    assert _attribution(record) == (True, {A_ID: True, B_ID: False}, True)


def test_row3_both_recognized_clean_event_proceeds(project, evidence):
    rc, _, record = _record(project, evidence, A_WITHIN + B_WITHIN)
    assert rc == 0 and record["hook_outcome"] == "proceeded"
    assert record["disposition"]["cause"] == "no_violation"
    assert _attribution(record) == (True, {A_ID: True, B_ID: True}, True)


def test_row4_refusal_only_from_an_unrelated_control(closed, evidence):
    """A violated, but closed availability refused (no numeric attribution)."""
    rc, err, record = _record(closed, evidence, A_ABOVE)
    assert rc == 2 and record["hook_outcome"] == "refused"
    assert "evaluation=INCOMPLETE; operational refusal." in err
    assert record["disposition"]["cause"] == "availability_refusal"
    assert _matcher(record, A_ID) == ("RECOGNIZED", "VIOLATION")
    assert _matcher(record, B_ID)[0] == "MATCHER_UNEVALUATED"
    assert _attribution(record) == (False, {A_ID: False, B_ID: False}, False)


def test_row4_refusal_only_from_a_non_numeric_rule(project, evidence):
    """The same row with the refusal attributed to another rule's block."""
    _, _, record = _record(project, evidence, A_ABOVE)
    record = copy.deepcopy(record)
    record["violations"].append({"rule_id": "LIT-1:FORBID_LITERAL:0", "rule_type": "FORBID_LITERAL"})
    record["disposition"]["cause"] = "other_rule"
    assert _attribution(record) == (False, {A_ID: False, B_ID: False}, False)


def test_literal_refusal_with_clean_and_unevaluated_numeric_rules(project, evidence):
    rc, err, record = _record(project, evidence, LITERAL + A_WITHIN)
    assert rc == 2 and "LIT-1" in err
    assert record["disposition"]["cause"] == "other_rule"
    assert _attribution(record) == (False, {A_ID: False, B_ID: False}, False)


# ── More than one rule decided ──────────────────────────────────────────────


def test_both_violated_strict_refusal_is_relevant_for_both(project, evidence):
    rc, _, record = _record(project, evidence, A_ABOVE + B_ABOVE)
    assert rc == 2
    assert _attribution(record) == (True, {A_ID: True, B_ID: True}, True)


def test_violation_deferred_in_warn_with_other_rule_clean(project, evidence, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, _, record = _record(project, evidence, A_WITHIN + B_ABOVE)
    assert rc == 0 and record["hook_outcome"] == "deferred"
    assert _attribution(record) == (True, {A_ID: False, B_ID: True}, True)


def test_clean_rule_with_other_unevaluated_proceeds_fail_open(project, evidence):
    """A fail-open proceed is the availability policy's, never A's PASS."""
    rc, _, record = _record(project, evidence, A_WITHIN)
    assert rc == 0 and record["disposition"]["cause"] == "fail_open"
    assert _attribution(record) == (False, {A_ID: False, B_ID: False}, False)


# ── No inheritance between rules ────────────────────────────────────────────


@pytest.fixture
def row2(project, evidence):
    _, _, record = _record(project, evidence, A_ABOVE + B_WITHIN)
    assert hook.relevant_enforcement_per_rule(record, HOST) == {A_ID: True, B_ID: False}
    return record


def _rule(record: dict, rule_id: str) -> dict:
    return next(r for r in record["rules"] if r["rule_id"] == rule_id)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(matcher_status="MATCHER_UNEVALUATED", matcher_outcome="UNEVALUATED",
                       primary_reason="SOURCE_NOT_FOUND"),
    lambda r: r.update(applicability="EXCLUDED"),
    lambda r: r.update(matcher_status="PARTIAL"),
    lambda r: r.update(decision_version_id=""),
], ids=["unevaluated", "excluded", "incoherent", "no_version"])
def test_undecided_rule_never_inherits_relevance(row2, mutation):
    mutation(_rule(row2, B_ID))
    assert hook.relevant_enforcement_per_rule(row2, HOST) == {A_ID: True, B_ID: False}
    assert hook.relevant_enforcement_observed(row2, HOST)


def test_decided_rule_loses_nothing_from_an_undecided_neighbour(row2):
    _rule(row2, A_ID).update(matcher_status="MATCHER_UNEVALUATED",
                             matcher_outcome="UNEVALUATED", primary_reason="SOURCE_NOT_FOUND")
    row2["violations"] = []
    # With no numeric violation left, the refusal is no rule's own outcome.
    assert hook.relevant_enforcement_per_rule(row2, HOST) == {A_ID: False, B_ID: False}
    assert not hook.relevant_enforcement_observed(row2, HOST)


def test_unrelated_rule_added_to_a_relevant_event_is_false(row2):
    extra = copy.deepcopy(_rule(row2, B_ID))
    extra["rule_id"] = "ADR-034C:FORBID_NUMERIC_ABOVE:0"
    row2["rules"].append(extra)
    assert hook.relevant_enforcement_per_rule(row2, HOST) == {
        A_ID: True, B_ID: False, extra["rule_id"]: False,
    }


@pytest.mark.parametrize("name,mutation", [
    ("carrier_digest", lambda r: r.update(carrier_sha256="0" * 64)),
    ("rule_digest", lambda r: _rule(r, B_ID).update(subject_sha256="0" * 64)),
    ("rule_governed_path", lambda r: _rule(r, B_ID).update(governed_path="src/other.py")),
    ("duplicate_rule_id", lambda r: _rule(r, B_ID).update(rule_id=A_ID)),
    ("rule_without_id", lambda r: _rule(r, B_ID).update(rule_id="")),
    ("unreported_violation", lambda r: _rule(r, B_ID).update(matcher_outcome="VIOLATION")),
    ("host", lambda r: r["host"].update(version="9.9.9")),
    ("untrusted", lambda r: r["checker"].update(trusted=False)),
    ("bad_cause", lambda r: r["disposition"].update(cause="unknown")),
])
def test_a_broken_common_binding_makes_every_rule_false(row2, name, mutation):
    mutation(row2)
    assert not any(hook.relevant_enforcement_per_rule(row2, HOST).values())
    assert not hook.relevant_enforcement_observed(row2, HOST)


@pytest.mark.parametrize("record", [None, {}, [], "x", {"rules": None}, {"rules": [1]}])
def test_malformed_records_have_no_relevant_rule(record):
    assert hook.relevant_enforcement_per_rule(record, HOST) == {}
    assert not hook.relevant_enforcement_observed(record, HOST)
    assert hook.recorded_evaluation_complete(record) is None


# ── The event-level value never implies completeness ────────────────────────


def test_event_level_relevance_is_independent_of_completeness(project, evidence):
    rc, _, record = _record(project, evidence, A_ABOVE)
    assert hook.relevant_enforcement_observed(record, HOST) is True
    assert hook.recorded_evaluation_complete(record) is False
    assert record["checker"]["evaluation_complete"] is False


@pytest.mark.parametrize("content", [A_ABOVE, A_WITHIN, A_ABOVE + B_WITHIN, A_WITHIN + B_WITHIN])
def test_completeness_is_the_checker_value_as_reported(project, evidence, content):
    _, _, record = _record(project, evidence, content)
    complete = hook.recorded_evaluation_complete(record)
    assert complete is record["checker"]["evaluation_complete"]
    assert complete is all(r["matcher_status"] == "RECOGNIZED" for r in record["rules"])


def test_untrusted_completeness_is_not_reported(row2):
    row2["checker"]["trusted"] = False
    assert hook.recorded_evaluation_complete(row2) is None
    row2["checker"]["trusted"] = True
    row2["checker"]["evaluation_complete"] = "yes"
    assert hook.recorded_evaluation_complete(row2) is None


# ── Hook outcomes unchanged ─────────────────────────────────────────────────


@pytest.mark.parametrize("content", [
    A_ABOVE, A_WITHIN, A_ABOVE + B_WITHIN, A_WITHIN + B_WITHIN, A_ABOVE + B_ABOVE,
    LITERAL + A_WITHIN, LITERAL + A_ABOVE + B_ABOVE,
])
@pytest.mark.parametrize("mode", ["strict", "warn"])
def test_evidence_seam_never_changes_the_hook_outcome(
    project, monkeypatch, tmp_path_factory, content, mode,
):
    monkeypatch.setenv("MNEME_HOOK_MODE", mode)
    unset = _hook(project, content)
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(tmp_path_factory.mktemp("e") / "e.jsonl"))
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_VERSION", HOST[0])
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_SHA256", HOST[1])
    assert _hook(project, content) == unset


def _calls_named(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
        for n in ast.walk(node)
    )


@pytest.mark.parametrize("validator", [
    "relevant_enforcement_observed", "relevant_enforcement_per_rule",
    "recorded_evaluation_complete", "_common_bindings_hold", "_disposition_attributable",
])
def test_validator_is_never_on_the_hook_decision_path(validator):
    """Evidence-only (§7b.4): no hook code path consults the validator."""
    tree = ast.parse(inspect.getsource(hook))
    validators = {
        "relevant_enforcement_observed", "relevant_enforcement_per_rule",
        "recorded_evaluation_complete", "_common_bindings_hold", "_disposition_attributable",
    }
    callers = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and _calls_named(node, validator)
    }
    assert callers <= validators

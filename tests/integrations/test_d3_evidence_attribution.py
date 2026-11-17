"""ADR-034 §7c: evidence attribution of non-numeric refusals (owner rulings D3).

Pinned regressions of the accepted D3 proposal
(docs/plans/2026-10-27-adr-034-d3-literal-attribution-proposal.md §5, items
1-7) and the §7c.3 malformed-identity tests. The hook's evidence record
names every violation a trusted, coherent payload reports, with or without a
``proposed_new_source`` subject. Those identities are attribution only: they
never support "relevant enforcement observed", and blocking is unchanged.

The hook is driven through its real entry point and the real ``mneme
check`` (in-process transport). Built only from the public contract with
synthetic fixtures; no G2-1 validation material is used or implied. Nothing
here is an enforcement or validation claim.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest

from mneme.integrations.claude_code import hook
from mneme.integrations.claude_code.hook import VerdictAssessment, _RoutedWrite
from mneme.numeric_rule import NumericContract
from mneme.rule_identity import rule_id_for
from mneme.schemas import Rule
from tests.canonical_fixtures import canonical_document

HOST = ("2.1.303", "ab" * 32)
LITERAL = Rule(type="FORBID_LITERAL", value="psycopg2")
LIT_ID = rule_id_for("LIT-1", LITERAL)
NUMERIC = Rule(
    type="FORBID_NUMERIC_ABOVE",
    value=NumericContract(
        max="5", unit="seconds", symbol="ROUTER_DEADLINE_S",
        call_function="classify", call_position=1,
    ).canonical_value(),
    include_paths=("src/**",),
)
NUMERIC_ID = rule_id_for("ADR-034T", NUMERIC)

LITERAL_SOURCE = "import psycopg2\n"
ABOVE = "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"
WITHIN = "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"


def _literal_decision() -> dict:
    return {"id": "LIT-1", "decision": "Do not use psycopg2", "rationale": "r",
            "scope": ["storage"],
            "rules": [{"type": LITERAL.type, "value": LITERAL.value}],
            "created_at": "2026-10-27", "updated_at": "2026-10-27",
            "status": "active"}


def _numeric_decision(include: str) -> dict:
    return {"id": "ADR-034T", "decision": "Router deadline at most 5 seconds",
            "rationale": "r", "scope": ["router"],
            "rules": [{"type": NUMERIC.type, "value": NUMERIC.value,
                       "include_paths": [include]}],
            "created_at": "2026-10-27", "updated_at": "2026-10-27",
            "status": "active"}


@pytest.fixture(autouse=True)
def hook_env(monkeypatch):
    """A clean hook environment, set before any project or evidence fixture."""
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_EVIDENCE_LOG", "MNEME_HOOK_EVIDENCE_HOST_VERSION",
                 "MNEME_HOOK_EVIDENCE_HOST_SHA256"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MNEME_HOOK_CHECK_TRANSPORT", "inprocess")
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")


def _make_project(root: Path, monkeypatch, decisions: list) -> Path:
    document = canonical_document({
        "meta": {"name": "d3", "description": "ADR-034 §7c"},
        "items": [], "decisions": decisions,
    })
    (root / ".mneme").mkdir(parents=True)
    (root / ".mneme" / "project_memory.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    (root / "src").mkdir()
    return root


@pytest.fixture
def literal_only(tmp_path, monkeypatch):
    """Memory with only a ``FORBID_LITERAL`` rule (proposal §5 item 1)."""
    return _make_project(tmp_path / "literal_only", monkeypatch, [_literal_decision()])


@pytest.fixture
def numeric_elsewhere(tmp_path, monkeypatch):
    """Literal plus a numeric rule with no APPLIED record for ``src/`` (item 2)."""
    return _make_project(
        tmp_path / "numeric_elsewhere", monkeypatch,
        [_literal_decision(), _numeric_decision("lib/**")],
    )


@pytest.fixture
def numeric_applies(tmp_path, monkeypatch):
    """Literal plus a numeric rule applicable to ``src/**`` (subject records)."""
    return _make_project(
        tmp_path / "numeric_applies", monkeypatch,
        [_literal_decision(), _numeric_decision("src/**")],
    )


@pytest.fixture
def evidence(monkeypatch, tmp_path_factory):
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


def _records(log: Path) -> list:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _pre_d3(record: dict) -> dict:
    """The record the pre-D3 builder produced for the same event.

    Before §7c, ``violations`` was filled only inside the
    ``proposed_new_source`` subject branch; every other field is unchanged.
    """
    legacy = copy.deepcopy(record)
    if legacy["checker"]["subject"] is None:
        legacy["violations"] = []
    return legacy


def _assert_literal_attribution_only(record: dict) -> None:
    """The proposal §5 item 1 record shape, apart from outcome and mode."""
    assert record["schema"] == "mneme.hook_evidence/v1"
    assert record["checker"]["trusted"] is True
    assert record["checker"]["subject"] is None
    assert record["rules"] == []
    assert record["violations"] == [{"rule_id": LIT_ID, "rule_type": "FORBID_LITERAL"}]
    assert record["disposition"]["cause"] == "other_rule"
    assert hook.relevant_enforcement_per_rule(record, HOST) == {}
    assert hook.relevant_enforcement_observed(record, HOST) is False


# ── proposal §5 items 1-3: literal refusals are named ───────────────────────


def test_item1_literal_only_refusal_names_the_literal_rule(literal_only, evidence):
    rc, out, err = _hook(literal_only, LITERAL_SOURCE)
    assert rc == 2 and out == "" and "LIT-1" in err
    assert not (literal_only / "src" / "new.py").exists()
    record, = _records(evidence)
    _assert_literal_attribution_only(record)
    assert record["hook_outcome"] == "refused"
    assert record["disposition"]["mode"] == "strict"
    # Completeness is reported exactly as the checker reported it.
    assert record["checker"]["evaluation_complete"] is True
    assert hook.recorded_evaluation_complete(record) == hook.recorded_evaluation_complete(
        _pre_d3(record)
    )


def test_item2_numeric_rule_without_applicability_gives_the_same_record(
    numeric_elsewhere, literal_only, evidence, tmp_path_factory, monkeypatch,
):
    rc, _, err = _hook(numeric_elsewhere, LITERAL_SOURCE)
    assert rc == 2 and "LIT-1" in err and "ADR-034T" not in err
    record, = _records(evidence)
    _assert_literal_attribution_only(record)
    assert record["hook_outcome"] == "refused"
    assert not any(
        item.get("rule_type") == NUMERIC.type and item.get("outcome") == "APPLIED"
        for item in record["rules"]
    )

    log = tmp_path_factory.mktemp("item1") / "events.jsonl"
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(log))
    _hook(literal_only, LITERAL_SOURCE)
    baseline, = _records(log)
    for key in ("checker", "rules", "violations", "hook_outcome", "disposition"):
        assert record[key] == baseline[key]


def test_item3_literal_violation_in_warn_defers_and_is_named(
    literal_only, evidence, monkeypatch,
):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, out, _ = _hook(literal_only, LITERAL_SOURCE)
    decision = json.loads(out)["hookSpecificOutput"]
    assert rc == 0 and decision["permissionDecision"] == "defer"
    assert "LIT-1" in decision["permissionDecisionReason"]
    record, = _records(evidence)
    _assert_literal_attribution_only(record)
    assert record["hook_outcome"] == "deferred"
    assert record["disposition"]["mode"] == "warn"


# ── proposal §5 item 4: untrusted payloads carry nothing ────────────────────


def _corrupt_violation(payload: dict) -> None:
    del payload["violations"][0]["decision_id"]


def _mode_mismatch(payload: dict) -> None:
    payload["mode"] = "warn"


def _not_json(_payload: dict) -> str:
    return "not json"


@pytest.mark.parametrize("tamper", [_corrupt_violation, _mode_mismatch, _not_json])
def test_item4_untrusted_or_inconsistent_payload_keeps_violations_empty(
    literal_only, evidence, monkeypatch, tamper,
):
    real = hook._invoke_check_inprocess

    def tampered(argv):
        proc = real(argv)
        payload = json.loads(proc.stdout)
        replaced = tamper(payload)
        proc.stdout = replaced if isinstance(replaced, str) else json.dumps(payload)
        return proc

    monkeypatch.setattr(hook, "_invoke_check_inprocess", tampered)
    _hook(literal_only, LITERAL_SOURCE)
    record, = _records(evidence)
    assert record["checker"]["trusted"] is False
    assert record["checker"]["problem"]
    assert record["violations"] == []
    assert hook.relevant_enforcement_observed(record, HOST) is False


def test_item4_missing_assessment_keeps_violations_empty():
    event = hook.ToolEvent(tool_name="Write", file_path="src/new.py", cwd=".", tool_input={})
    routed = _RoutedWrite(target="src/new.py", carrier=b"", carrier_sha256="0" * 64)
    record = hook.build_evidence_record(event, {}, routed, "proceeded")
    assert record["checker"]["trusted"] is False
    assert record["violations"] == []


# ── proposal §5 item 5: records with a subject are byte-identical ───────────


@pytest.mark.parametrize("content", [ABOVE, WITHIN, LITERAL_SOURCE + WITHIN,
                                     LITERAL_SOURCE + ABOVE])
def test_item5_subject_records_are_byte_identical(numeric_applies, evidence, content):
    _hook(numeric_applies, content)
    record, = _records(evidence)
    assert record["checker"]["subject"]["input_kind"] == "proposed_new_source"
    assert json.dumps(record, sort_keys=True) == json.dumps(_pre_d3(record), sort_keys=True)


def test_item5_mixed_literal_and_numeric_record_is_unchanged(numeric_applies, evidence):
    _hook(numeric_applies, LITERAL_SOURCE + ABOVE)
    record, = _records(evidence)
    assert sorted(record["violations"], key=lambda v: v["rule_type"]) == [
        {"rule_id": LIT_ID, "rule_type": "FORBID_LITERAL"},
        {"rule_id": NUMERIC_ID, "rule_type": NUMERIC.type},
    ]
    assert hook.relevant_enforcement_per_rule(record, HOST) == {NUMERIC_ID: True}


# ── proposal §5 item 6: hook output parity ──────────────────────────────────


def _pre_d3_builder(real):
    def build(*args, **kwargs):
        return _pre_d3(real(*args, **kwargs))
    return build


@pytest.mark.parametrize("fixture", ["literal_only", "numeric_elsewhere", "numeric_applies"])
@pytest.mark.parametrize("mode", ["strict", "warn"])
@pytest.mark.parametrize("content", [LITERAL_SOURCE, ABOVE, WITHIN, LITERAL_SOURCE + ABOVE])
def test_item6_outputs_are_byte_identical_with_and_without_the_log(
    request, monkeypatch, tmp_path_factory, fixture, mode, content,
):
    project = request.getfixturevalue(fixture)
    monkeypatch.setenv("MNEME_HOOK_MODE", mode)
    unset = _hook(project, content)

    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_VERSION", HOST[0])
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_HOST_SHA256", HOST[1])
    log = tmp_path_factory.mktemp("parity") / "events.jsonl"
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(log))
    assert _hook(project, content) == unset
    post, = _records(log)

    # Before/after: the pre-D3 builder yields the same outputs.
    legacy_log = tmp_path_factory.mktemp("parity_pre_d3") / "events.jsonl"
    monkeypatch.setenv("MNEME_HOOK_EVIDENCE_LOG", str(legacy_log))
    monkeypatch.setattr(hook, "build_evidence_record",
                        _pre_d3_builder(hook.build_evidence_record))
    assert _hook(project, content) == unset
    pre, = _records(legacy_log)
    assert pre == _pre_d3(post)

    monkeypatch.delenv("MNEME_HOOK_EVIDENCE_LOG")
    assert _hook(project, content) == unset


# ── proposal §5 item 7: relevance is unchanged ──────────────────────────────


def _validators(record: dict) -> tuple:
    return (
        hook.relevant_enforcement_per_rule(record, HOST),
        hook.relevant_enforcement_observed(record, HOST),
        hook.recorded_evaluation_complete(record),
    )


@pytest.mark.parametrize("fixture", ["literal_only", "numeric_elsewhere", "numeric_applies"])
@pytest.mark.parametrize("content", [LITERAL_SOURCE, ABOVE, WITHIN, LITERAL_SOURCE + ABOVE])
def test_item7_validators_identical_with_and_without_new_identities(
    request, evidence, fixture, content,
):
    project = request.getfixturevalue(fixture)
    _hook(project, content)
    record, = _records(evidence)
    assert _validators(record) == _validators(_pre_d3(record))


def test_item7_crafted_subject_without_numeric_rule_stays_empty(numeric_applies, evidence):
    """A record with a subject but no numeric rule stays ``{}`` / ``False``."""
    _hook(numeric_applies, LITERAL_SOURCE + WITHIN)
    record, = _records(evidence)
    crafted = copy.deepcopy(record)
    crafted["rules"] = []
    crafted["violations"] = [{"rule_id": LIT_ID, "rule_type": "FORBID_LITERAL"}]
    assert hook.relevant_enforcement_per_rule(crafted, HOST) == {}
    assert hook.relevant_enforcement_observed(crafted, HOST) is False
    stripped = copy.deepcopy(crafted)
    stripped["violations"] = []
    assert _validators(crafted)[:2] == _validators(stripped)[:2]


def test_item7_literal_identity_never_makes_a_numeric_rule_relevant(numeric_applies, evidence):
    """§7b.1 no inheritance: a literal refusal is not the numeric rule's."""
    _hook(numeric_applies, LITERAL_SOURCE + WITHIN)
    record, = _records(evidence)
    assert {"rule_id": LIT_ID, "rule_type": "FORBID_LITERAL"} in record["violations"]
    assert record["disposition"]["cause"] == "other_rule"
    assert hook.relevant_enforcement_per_rule(record, HOST) == {NUMERIC_ID: False}


# ── §7c.3: a malformed identity attributes nothing ──────────────────────────
#
# Design: entries are copied verbatim (no filtering), so records that already
# carry a subject stay byte-identical (proposal §5 item 5) and the record
# never rewrites the checker's report. A copied entry whose rule_id is
# missing, empty or not a string names no rule. Every consumer in hook.py
# reads rule identities only through a non-empty string rule_id, so such an
# entry is unattributed there.

_MISSING = object()
MALFORMED = [
    pytest.param(_MISSING, id="missing"),
    pytest.param("", id="empty"),
    pytest.param(7, id="non-string"),
    pytest.param(None, id="none"),
]


def _malformed_entry(rule_id) -> dict:
    entry = {"decision_id": "LIT-1", "decision_text": "Do not use psycopg2",
             "severity": "FAIL", "rule": "FORBID_LITERAL psycopg2",
             "trigger": "psycopg2", "kind": "typed_rule",
             "rule_type": "FORBID_LITERAL"}
    if rule_id is not _MISSING:
        entry["rule_id"] = rule_id
    return entry


def _routed_with(payload: dict) -> tuple:
    event = hook.ToolEvent(tool_name="Write", file_path="src/new.py", cwd=".", tool_input={})
    routed = _RoutedWrite(
        target="src/new.py", carrier=b"", carrier_sha256="0" * 64,
        assessment=VerdictAssessment(payload=payload), mode="strict", cause="other_rule",
    )
    return event, routed


def _attributed_rule_ids(record: dict) -> set:
    """Rules a record attributes: identities with a non-empty string rule_id."""
    return {
        v["rule_id"] for v in record["violations"]
        if isinstance(v.get("rule_id"), str) and v["rule_id"]
    }


@pytest.mark.parametrize("rule_id", MALFORMED)
def test_7c3_malformed_identity_without_subject_attributes_nothing(rule_id):
    payload = {"verdict": "FAIL", "mode": "strict", "evaluation_complete": True,
               "violations": [_malformed_entry(rule_id)]}
    event, routed = _routed_with(payload)
    record = hook.build_evidence_record(event, {}, routed, "refused")
    entry, = record["violations"]
    # Verbatim: the record never invents an identity for the entry.
    assert entry == {"rule_id": None if rule_id is _MISSING else rule_id,
                     "rule_type": "FORBID_LITERAL"}
    assert _attributed_rule_ids(record) == set()
    assert hook.relevant_enforcement_per_rule(record, HOST) == {}
    assert hook.relevant_enforcement_observed(record, HOST) is False


@pytest.mark.parametrize("rule_id", MALFORMED)
def test_7c3_malformed_identity_beside_a_numeric_rule_attributes_nothing(
    numeric_applies, evidence, rule_id,
):
    """A malformed literal entry never changes any numeric rule's relevance."""
    _hook(numeric_applies, ABOVE)
    record, = _records(evidence)
    assert hook.relevant_enforcement_per_rule(record, HOST) == {NUMERIC_ID: True}
    with_malformed = copy.deepcopy(record)
    with_malformed["violations"].append(
        {"rule_id": None if rule_id is _MISSING else rule_id, "rule_type": "FORBID_LITERAL"}
    )
    assert _validators(with_malformed) == _validators(record)
    assert _attributed_rule_ids(with_malformed) == {NUMERIC_ID}


@pytest.mark.parametrize("rule_id", MALFORMED)
def test_7c3_malformed_identity_through_the_real_hook(
    literal_only, evidence, monkeypatch, rule_id,
):
    """A trusted payload whose literal violation lacks a usable rule_id."""
    real = hook._invoke_check_inprocess

    def malformed(argv):
        proc = real(argv)
        payload = json.loads(proc.stdout)
        violation, = payload["violations"]
        if rule_id is _MISSING:
            del violation["rule_id"]
        else:
            violation["rule_id"] = rule_id
        proc.stdout = json.dumps(payload)
        return proc

    monkeypatch.setattr(hook, "_invoke_check_inprocess", malformed)
    rc, _, err = _hook(literal_only, LITERAL_SOURCE)
    record, = _records(evidence)
    # The consumer trust checks admit the payload, and blocking is unchanged.
    assert record["checker"]["trusted"] is True
    assert rc == 2 and "LIT-1" in err
    assert record["violations"] == [
        {"rule_id": None if rule_id is _MISSING else rule_id, "rule_type": "FORBID_LITERAL"}
    ]
    assert _attributed_rule_ids(record) == set()
    assert hook.relevant_enforcement_per_rule(record, HOST) == {}
    assert hook.relevant_enforcement_observed(record, HOST) is False

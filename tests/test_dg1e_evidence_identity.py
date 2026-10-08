"""DG1E: canonical evidence identity through the runtime (ADR-031 §10).

- One ``rule_id`` algorithm (ADR-030 §7) everywhere: persisted bindings, the
  D0 adapter (Decision MCP ``--adr-dir``), and the enforcement trace.
- The canonical ``decision_version_id`` reaches the trace only from the
  persisted Decision Index; every other source leaves it empty, so evidence
  identity fails closed there.
- Verdicts are unchanged: identity is additive output only.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

import mneme.decision_index_persistence as persistence
from mneme import rule_identity
from mneme.cli import main
from mneme.conflict_detector import ConflictDetector
from mneme.decision_governance import (
    EvidenceIdentity,
    evidence_identity_of,
)
from mneme.decision_index import decisions_to_canonical
from mneme.decision_index_persistence import load_decision_index_from_memory_file
from mneme.decision_mcp import load_canonical_index_from_adr_dir
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import Severity, Violation, check_prompt
from mneme.memory_store import MemoryStore
from mneme.path_selectors import RuleEvaluation, SelectorOutcome
from mneme.rule_identity import rule_id_for, rule_id_of
from mneme.schemas import Decision, Rule
from tests.canonical_fixtures import canonical_document


def _decisions(path) -> list[Decision]:
    store = MemoryStore(path)
    store.load()
    return store.decisions()

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
LIVE_PRE_D1 = FIXTURES / "d1_parity" / "pre_d1_live_project_memory.json"
_POSITIONAL = re.compile(r":\d+$")

# The live fixture's only typed rule: a global FORBID_LITERAL on ADR-005.
# The literal is read from the fixture rather than repeated here.
_RULE_DECISION = "ADR-005"


def _fixture_forbidden_literal() -> str:
    document = canonical_document(json.loads(LIVE_PRE_D1.read_text(encoding="utf-8")))
    [rule] = [
        r for r in document["decision_index"]["rules"]
        if r["decision_id"] == _RULE_DECISION
    ]
    assert rule["applicability"] == {}
    return rule["rule_payload"]["value"]


_FORBIDDEN = _fixture_forbidden_literal()


def _canonical_memory(tmp_path: Path) -> Path:
    document = canonical_document(json.loads(LIVE_PRE_D1.read_text(encoding="utf-8")))
    path = tmp_path / ".mneme" / "project_memory.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(json.dumps(document).encode("utf-8"))
    return path


def _section_less_memory(tmp_path: Path) -> Path:
    path = tmp_path / ".mneme" / "project_memory.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(LIVE_PRE_D1.read_bytes())
    return path


def _enforce(decisions: list[Decision], text: str):
    scored = DecisionRetriever(decisions).retrieve(text)
    return check_prompt(text, scored, top=3)


# ── one rule-id algorithm ───────────────────────────────────────────────────


def test_persistence_reexports_the_single_rule_identity() -> None:
    assert persistence.rule_id_of is rule_identity.rule_id_of
    assert persistence.rule_id_for is rule_identity.rule_id_for


@pytest.mark.parametrize(
    "memory",
    [REPO / ".mneme" / "project_memory.json", "migrated-live"],
    ids=["repo-memory", "migrated-live"],
)
def test_runtime_rule_id_equals_persisted_rule_id(memory, tmp_path: Path) -> None:
    path = _canonical_memory(tmp_path) if memory == "migrated-live" else memory
    index = load_decision_index_from_memory_file(path)
    decisions = {d.id: d for d in _decisions(path)}
    for record in index.records:
        if record.lifecycle_status != "active":
            continue
        runtime = decisions[record.decision_id]
        assert runtime.version_id == record.version_id != ""
        assert tuple(rule_id_for(runtime.id, rule) for rule in runtime.rules) == (
            record.derived_rule_ids
        )


@pytest.mark.parametrize(
    "corpus",
    [REPO / "docs" / "adr", FIXTURES / "adrs_literal", FIXTURES / "adrs_e2e_clean"],
    ids=lambda p: p.name,
)
def test_adr_dir_view_uses_canonical_rule_ids_without_version_identity(corpus: Path) -> None:
    index = load_canonical_index_from_adr_dir(corpus)
    for rule in index.rules:
        assert rule.rule_id == rule_id_of(
            rule.decision_id, rule.rule_type, rule.rule_payload["value"], rule.applicability
        )
        assert not _POSITIONAL.search(rule.rule_id)
    assert all(record.version_id == "" for record in index.records)


def test_d0_adapter_rule_ids_are_order_independent() -> None:
    first = Rule(type="FORBID_LITERAL", value="alpha")
    second = Rule(type="FORBID_LITERAL", value="beta", include_paths=("src/**",))
    forward = decisions_to_canonical([Decision(id="D", decision="d", rules=[first, second])])
    reverse = decisions_to_canonical([Decision(id="D", decision="d", rules=[second, first])])
    assert set(forward.records[0].derived_rule_ids) == set(reverse.records[0].derived_rule_ids)


def test_d0_adapter_rejects_duplicate_identical_rules_like_persistence() -> None:
    rule = Rule(type="FORBID_LITERAL", value="alpha")
    with pytest.raises(ValueError, match="duplicate identical rule"):
        decisions_to_canonical([Decision(id="D", decision="d", rules=[rule, rule])])


# ── projection carries version identity without changing equality ──────────


_V_A = "dver-" + "a" * 32
_V_B = "dver-" + "b" * 32
_DIGEST = "0123456789abcdef" * 2


def test_different_versions_are_different_decision_evidence() -> None:
    # Same behavior, different canonical version: different evidence.
    a = Decision(id="D", decision="d", version_id=_V_A)
    b = Decision(id="D", decision="d", version_id=_V_B)
    assert a != b
    assert a == Decision(id="D", decision="d", version_id=_V_A)


def test_trace_equality_includes_version_and_rule_identity() -> None:
    base = {
        "decision_id": "D",
        "rule_type": "FORBID_LITERAL",
        "rule_value": "x",
        "rule_index": 0,
        "path_scoped": False,
        "outcome": SelectorOutcome.APPLIED,
        "input_path": None,
        "rule_id": f"D:FORBID_LITERAL:{_DIGEST}",
    }
    assert RuleEvaluation(**base, decision_version_id=_V_A) != RuleEvaluation(
        **base, decision_version_id=_V_B
    )
    assert RuleEvaluation(**base, decision_version_id=_V_A) == RuleEvaluation(
        **base, decision_version_id=_V_A
    )
    other_rule = {**base, "rule_id": f"D:FORBID_LITERAL:{'f' * 32}"}
    assert RuleEvaluation(**base) != RuleEvaluation(**other_rule)


def test_violation_equality_includes_version_identity() -> None:
    base = {
        "decision_id": "D",
        "decision_text": "d",
        "severity": Severity.FAIL,
        "rule": "x",
        "trigger": "x",
        "kind": "typed_rule",
        "rule_type": "FORBID_LITERAL",
        "rule_id": f"D:FORBID_LITERAL:{_DIGEST}",
    }
    assert Violation(**base, decision_version_id=_V_A) != Violation(
        **base, decision_version_id=_V_B
    )


# ── enforcement trace ───────────────────────────────────────────────────────


def test_canonical_memory_trace_carries_complete_evidence_identity(tmp_path: Path) -> None:
    path = _canonical_memory(tmp_path)
    index = load_decision_index_from_memory_file(path)
    [record] = [r for r in index.records if r.decision_id == _RULE_DECISION]
    [canonical_rule_id] = record.derived_rule_ids

    result = _enforce(_decisions(path), f"run {_FORBIDDEN} now")
    assert result.verdict == Severity.FAIL
    [evaluation] = [e for e in result.applicability if e.decision_id == _RULE_DECISION]
    assert evaluation.rule_id == canonical_rule_id
    assert evaluation.decision_version_id == record.version_id
    assert evidence_identity_of(evaluation).complete

    [violation] = [v for v in result.violations if v.kind == "typed_rule"]
    assert violation.rule_id == canonical_rule_id
    assert violation.decision_version_id == record.version_id
    assert evidence_identity_of(violation).complete


def test_section_less_memory_has_rule_identity_but_fails_closed(tmp_path: Path) -> None:
    path = _section_less_memory(tmp_path)
    result = _enforce(_decisions(path), f"run {_FORBIDDEN} now")
    [evaluation] = [e for e in result.applicability if e.decision_id == _RULE_DECISION]
    assert evaluation.rule_id == rule_id_of(_RULE_DECISION, "FORBID_LITERAL", _FORBIDDEN, {})
    assert evaluation.decision_version_id == ""
    identity = evidence_identity_of(evaluation)
    assert not identity.complete
    assert identity.missing == ("decision_version_id",)


def test_verdicts_do_not_depend_on_evidence_identity(tmp_path: Path) -> None:
    decisions = _decisions(_canonical_memory(tmp_path))
    stripped = [replace(d, version_id="") for d in decisions]
    for text in (f"run {_FORBIDDEN} now", "nothing to see here", "add a postgres orm"):
        with_identity = _enforce(decisions, text)
        without = _enforce(stripped, text)
        assert with_identity.verdict == without.verdict
        assert [
            (v.decision_id, v.severity, v.rule, v.trigger, v.kind, v.rule_id)
            for v in with_identity.violations
        ] == [
            (v.decision_id, v.severity, v.rule, v.trigger, v.kind, v.rule_id)
            for v in without.violations
        ]
        assert [
            (e.decision_id, e.rule_index, e.outcome, e.rule_id)
            for e in with_identity.applicability
        ] == [
            (e.decision_id, e.rule_index, e.outcome, e.rule_id)
            for e in without.applicability
        ]


def test_conflict_detector_trace_carries_identity(tmp_path: Path) -> None:
    path = _canonical_memory(tmp_path)
    index = load_decision_index_from_memory_file(path)
    [record] = [r for r in index.records if r.decision_id == _RULE_DECISION]
    result = ConflictDetector().evaluate(
        f"just {_FORBIDDEN}", _decisions(path)
    )
    [evaluation] = [e for e in result.applicability if e.decision_id == _RULE_DECISION]
    assert evaluation.rule_id == record.derived_rule_ids[0]
    assert evaluation.decision_version_id == record.version_id
    assert evidence_identity_of(evaluation).complete


def test_check_json_reports_canonical_identity(tmp_path: Path, capsys) -> None:
    path = _canonical_memory(tmp_path)
    index = load_decision_index_from_memory_file(path)
    [record] = [r for r in index.records if r.decision_id == _RULE_DECISION]
    introduced = tmp_path / "input.txt"
    introduced.write_text(f"run {_FORBIDDEN}", encoding="utf-8")
    code = main([
        "check", "--memory", str(path), "--input", str(introduced),
        "--query", "install mneme", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code != 0
    [item] = [a for a in payload["applicability"] if a["decision_id"] == _RULE_DECISION]
    assert item["rule_id"] == record.derived_rule_ids[0]
    assert item["decision_version_id"] == record.version_id
    [violation] = [v for v in payload["violations"] if v["kind"] == "typed_rule"]
    assert violation["rule_id"] == item["rule_id"]
    assert violation["decision_version_id"] == record.version_id


# ── EvidenceIdentity semantics ──────────────────────────────────────────────


def test_identity_requires_all_fields_and_decision_owned_rule() -> None:
    rule = f"D:FORBID_LITERAL:{_DIGEST}"
    assert EvidenceIdentity("D", _V_A, rule).complete
    assert EvidenceIdentity("D", "", rule).missing == ("decision_version_id",)
    assert EvidenceIdentity("D", _V_A, "").missing == ("rule_id",)
    foreign = EvidenceIdentity("D", _V_A, f"E:FORBID_LITERAL:{_DIGEST}")
    assert not foreign.missing
    assert not foreign.rule_owned_by_decision
    assert foreign.malformed == ("rule_id",)
    assert not foreign.complete
    # A prefix match must be on the whole decision id.
    assert not EvidenceIdentity("D", _V_A, f"DX:FORBID_LITERAL:{_DIGEST}").complete


@pytest.mark.parametrize(
    "version_id",
    ["dver-1", "dver-" + "a" * 31, "dver-" + "a" * 33, "dver-" + "A" * 32, "v-" + "a" * 32, _V_A + "\n"],
)
def test_malformed_version_ids_are_incomplete(version_id: str) -> None:
    identity = EvidenceIdentity("D", version_id, f"D:FORBID_LITERAL:{_DIGEST}")
    assert identity.malformed == ("decision_version_id",)
    assert not identity.complete


@pytest.mark.parametrize(
    "rule_id",
    [
        "D:FORBID_LITERAL:abc",
        "D:FORBID_LITERAL:0",
        f"D:FORBID_LITERAL:{'a' * 31}",
        f"D:FORBID_LITERAL:{'A' * 32}",
        f"D:UNKNOWN_TYPE:{_DIGEST}",
        f"D:{_DIGEST}",
        f"D:FORBID_LITERAL:{_DIGEST}:extra",
    ],
)
def test_malformed_rule_ids_are_incomplete(rule_id: str) -> None:
    identity = EvidenceIdentity("D", _V_A, rule_id)
    assert identity.malformed == ("rule_id",)
    assert not identity.complete


def test_real_canonical_identities_are_well_formed(tmp_path: Path) -> None:
    path = _canonical_memory(tmp_path)
    index = load_decision_index_from_memory_file(path)
    for record in index.records:
        for rule_id in record.derived_rule_ids:
            identity = EvidenceIdentity(record.decision_id, record.version_id, rule_id)
            assert identity.complete, identity


def test_legacy_prose_violation_identity_is_incomplete(tmp_path: Path) -> None:
    decision = Decision(id="D", decision="d", anti_patterns=["mongodb"], version_id=_V_A)
    result = _enforce([decision], "use mongodb here")
    [violation] = result.violations
    assert violation.kind == "anti_pattern"
    assert violation.rule_id is None
    assert "rule_id" in evidence_identity_of(violation).missing
    assert not evidence_identity_of(violation).complete

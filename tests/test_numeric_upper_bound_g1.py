"""ADR-034 G1: ``FORBID_NUMERIC_ABOVE`` whole-file numeric audit.

Pinned regression matrix of the accepted behavioral charter
(docs/plans/2026-10-22-adr-034-g1-behavioral-charter.md §8.C), items 1-5 and
7-9. Item 6 (hook, Agent SDK, LangChain) lives in
``tests/integrations/test_numeric_upper_bound_consumers.py``.

Built only from the public contract: ADR-034, the charter, the frozen
criteria's set R (R1-R18) and the 17 confirmed interpretations (AMB-01..17)
of the public corpus freeze record. No held-out case is used or implied.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mneme import numeric_rule
from mneme.adr_constraints import ConstraintParseError, parse_constraints_section
from mneme.cli import main
from mneme.conflict_detector import (
    ConflictDetector,
    NumericRuleNoncoverageError,
    noncoverage_note,
)
from mneme.decision_index_persistence import (
    APPLICABILITY_FEATURE,
    DECISION_INDEX_SCHEMA,
    NUMERIC_UPPER_BOUND_FEATURE,
    SUPPORTED_SEMANTIC_FEATURES,
    DecisionIndexMigrationRequired,
    DecisionIndexPersistenceError,
    append_initial_canonical_decision,
    empty_decision_index_section,
    load_persisted_decision_index,
)
from mneme.decision_projection import project_canonical_index
from mneme.enforcer import assess_governability, assess_protection
from mneme.integrations.claude_code.hook import assess_verdict
from mneme.memory_store import MemoryStore
from mneme.numeric_rule import NumericContract, NumericContractError
from mneme.rule_identity import rule_id_for, rule_id_of
from mneme.schemas import Decision, Rule
from tests.canonical_fixtures import canonical_document, v1_document

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "numeric_g1"

ROUTER = NumericContract(
    max="5",
    unit="seconds",
    symbol="ROUTER_DEADLINE_S",
    call_function="classify",
    call_position=1,
)
SRC = ("src/**",)


# ── helpers ──────────────────────────────────────────────────────────────────


def _rule(contract: NumericContract = ROUTER, include=SRC, exclude=()) -> Rule:
    return Rule(
        type="FORBID_NUMERIC_ABOVE",
        value=contract.canonical_value(),
        include_paths=include,
        exclude_paths=exclude,
    )


def _rule_record(rule: Rule) -> dict:
    record = {"type": rule.type, "value": rule.value}
    if rule.include_paths is not None:
        record["include_paths"] = list(rule.include_paths)
    if rule.exclude_paths:
        record["exclude_paths"] = list(rule.exclude_paths)
    return record


def _project(tmp_path: Path, rules_by_decision: dict[str, list[Rule]]) -> Path:
    """A canonical v2 project memory built by the migration transform."""
    legacy = {
        "meta": {"name": "numeric-g1", "description": "ADR-034 G1 tests"},
        "items": [],
        "decisions": [
            {
                "id": decision_id,
                "decision": f"Decision {decision_id}",
                "rationale": "test",
                "scope": ["router"],
                "rules": [_rule_record(rule) for rule in rules],
                "created_at": "2026-10-22",
                "updated_at": "2026-10-22",
                "status": "active",
            }
            for decision_id, rules in rules_by_decision.items()
        ],
    }
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text(json.dumps(canonical_document(legacy)), encoding="utf-8")
    return memory


def _write(tmp_path: Path, rel: str, text: str | bytes) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_bytes(textwrap.dedent(text).encode("utf-8"))
    return path


def _check(tmp_path, capsys, *, source=None, input_file=None, target=None,
           mode="strict", json_out=True, memory=None):
    memory = memory or tmp_path / ".mneme" / "project_memory.json"
    argv = ["check", "--memory", str(memory), "--query", "router", "--mode", mode]
    if source is not None:
        argv += ["--source-file", str(source)]
    if input_file is not None:
        argv += ["--input", str(input_file)]
    if target is not None:
        argv += ["--target-path", str(target)]
    if json_out:
        argv.append("--json")
    code = main(argv)
    captured = capsys.readouterr()
    if json_out and captured.out:
        return code, json.loads(captured.out), captured
    return code, None, captured


def _numeric_trace(payload: dict) -> dict:
    traces = [
        item for item in payload["applicability"]
        if item["rule_type"] == "FORBID_NUMERIC_ABOVE"
    ]
    assert len(traces) == 1
    return traces[0]


def _audit(tmp_path, capsys, contract: NumericContract, source: str, **kw):
    _project(tmp_path, {"ADR-001": [_rule(contract)]})
    path = _write(tmp_path, "src/module.py", source)
    return _check(tmp_path, capsys, source=path, **kw)


ADR_TEMPLATE = """\
---
id: ADR-001
title: "Router deadline"
status: accepted
priority: normal
date: 2026-10-22
scope: router
---

# ADR-001

## Constraints

- FORBID_NUMERIC_ABOVE:
{body}
"""

VALID_BODY = """\
    language: python
    symbol: ROUTER_DEADLINE_S
    call:
      function: classify
      position: 1
    max: {max}
    inclusive: true
    unit: seconds
    include_paths:
      - "src/**"
"""


def _parse(body: str):
    return parse_constraints_section(ADR_TEMPLATE.format(body=body))


# ── §8.C.1 authoring and persistence ─────────────────────────────────────────


@pytest.mark.parametrize("raw,canonical", [
    ("5", "5"),
    ("5.0", "5"),
    ("5.000", "5"),
    ("2.50", "2.5"),
    ("0.75", "0.75"),
    ("0.1", "0.1"),
    ("123456789012345678", "123456789012345678"),
    ("1.123456789", "1.123456789"),
])
def test_max_grammar_accepts_and_canonicalizes_textually(raw, canonical):
    directive, = _parse(VALID_BODY.format(max=raw))
    assert json.loads(directive.value)["max"] == canonical


@pytest.mark.parametrize("raw", [
    '"5"', "'5'", "05", "0x5", "0o5", "1_000", ".5", "5.", "5e0", "5.0e0",
    "-5", "+5", ".inf", ".nan", "true", "null", "~", "0", "0.0", "0.000",
    "1234567890123456789", "1.1234567890", "[5]", "{a: 5}",
])
def test_max_grammar_rejects_raw_spellings(raw):
    with pytest.raises(ConstraintParseError):
        _parse(VALID_BODY.format(max=raw))


@pytest.mark.parametrize("body", [
    VALID_BODY.format(max=5).replace("    language: python\n", "    language: java\n"),
    VALID_BODY.format(max=5).replace("    language: python\n", ""),
    VALID_BODY.format(max=5).replace("inclusive: true", "inclusive: false"),
    VALID_BODY.format(max=5).replace("inclusive: true", "inclusive: yes"),
    VALID_BODY.format(max=5).replace("inclusive: true", "inclusive: True"),
    VALID_BODY.format(max=5).replace("inclusive: true", 'inclusive: "true"'),
    VALID_BODY.format(max=5).replace("    inclusive: true\n", ""),
    VALID_BODY.format(max=5).replace("unit: seconds", 'unit: ""'),
    VALID_BODY.format(max=5).replace("    unit: seconds\n", ""),
    VALID_BODY.format(max=5).replace("symbol: ROUTER_DEADLINE_S", "symbol: 1st"),
    VALID_BODY.format(max=5).replace("symbol: ROUTER_DEADLINE_S", "symbol: class"),
    VALID_BODY.format(max=5).replace("function: classify", "function: obj.classify"),
    VALID_BODY.format(max=5).replace("position: 1", "position: -1"),
    VALID_BODY.format(max=5).replace("position: 1", 'position: "1"'),
    VALID_BODY.format(max=5).replace("position: 1", "position: 01"),
    VALID_BODY.format(max=5).replace("position: 1", "position: 1.0"),
    VALID_BODY.format(max=5).replace("      position: 1\n", ""),
    VALID_BODY.format(max=5).replace("      position: 1\n", "      position: 1\n      keyword: t\n"),
    VALID_BODY.format(max=5).replace(
        "    symbol: ROUTER_DEADLINE_S\n    call:\n      function: classify\n      position: 1\n", ""
    ),
    VALID_BODY.format(max=5).replace('    include_paths:\n      - "src/**"\n', ""),
    VALID_BODY.format(max=5) + "    tolerance: 0.1\n",
    VALID_BODY.format(max=5) + "    max: 6\n",
])
def test_authoring_rejects_invalid_structure(body):
    with pytest.raises(ConstraintParseError):
        _parse(body)


def test_scalar_form_is_an_authoring_error():
    with pytest.raises(ConstraintParseError):
        parse_constraints_section("## Constraints\n- FORBID_NUMERIC_ABOVE: 5\n")


def test_canonical_json_bytes_match_adr_034():
    directive, = _parse(VALID_BODY.format(max=5))
    assert directive.value == (
        '{"call":{"function":"classify","position":1},"inclusive":true,'
        '"language":"python","max":"5","symbol":"ROUTER_DEADLINE_S",'
        '"unit":"seconds","v":1}'
    )
    assert directive.include_paths == ("src/**",)


@pytest.mark.parametrize("value", [
    ' {"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"5","unit":"seconds","v":1}',
    '{"inclusive":true,"call":{"function":"classify","position":1},"language":"python","max":"5","unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":5,"unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"5.0","unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"05","unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"0","unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"5","unit":"seconds","v":2}',
    '{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"5","unit":"seconds","v":true}',
    '{"call":{"function":"classify","position":true},"inclusive":true,"language":"python","max":"5","unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"inclusive":false,"language":"python","max":"5","unit":"seconds","v":1}',
    '{"call":{"function":"classify","position":1},"extra":1,"inclusive":true,"language":"python","max":"5","unit":"seconds","v":1}',
    '{"inclusive":true,"language":"python","max":"5","unit":"seconds","v":1}',
    "not json",
])
def test_stored_value_strict_validation_never_rewrites(value):
    with pytest.raises(NumericContractError):
        numeric_rule.parse_rule_value(value)
    with pytest.raises(ValueError):
        Rule(type="FORBID_NUMERIC_ABOVE", value=value, include_paths=SRC)


def test_numeric_rule_has_no_global_form():
    with pytest.raises(ValueError):
        Rule(type="FORBID_NUMERIC_ABOVE", value=ROUTER.canonical_value())


def _document_with(rule: Rule) -> dict:
    return canonical_document({
        "meta": {"name": "t", "description": "t"},
        "items": [],
        "decisions": [{
            "id": "ADR-001", "decision": "Router deadline", "rationale": "r",
            "scope": ["router"], "rules": [_rule_record(rule)],
            "created_at": "2026-10-22", "updated_at": "2026-10-22",
            "status": "active",
        }],
    })


def test_v2_feature_is_declared_when_numeric_rule_persists():
    document = _document_with(_rule())
    section = document["decision_index"]
    assert section["schema"] == "mneme.decision-index/v2"
    assert section["semantic_features"] == [NUMERIC_UPPER_BOUND_FEATURE]
    assert NUMERIC_UPPER_BOUND_FEATURE == numeric_rule.SEMANTIC_FEATURE


def test_feature_is_absent_without_numeric_rules():
    document = canonical_document({
        "meta": {"name": "t", "description": "t"}, "items": [],
        "decisions": [{"id": "D", "decision": "d", "rules": [
            {"type": "FORBID_LITERAL", "value": "x"}]}],
    })
    assert document["decision_index"]["semantic_features"] == []


def test_round_trip_is_byte_stable_through_parse_compile_persist_load_project(tmp_path):
    from mneme.adr_compiler import adrs_to_decisions
    from mneme.adr_parser import parse_adr_file
    from mneme.decision_index import adrs_to_canonical

    adr_path = tmp_path / "ADR-001-router.md"
    adr_path.write_text(
        ADR_TEMPLATE.format(body=VALID_BODY.format(max="5.000")), encoding="utf-8"
    )
    adr = parse_adr_file(adr_path)
    decision, = adrs_to_decisions([adr])
    compiled, = decision.rules
    canonical, = adrs_to_canonical([adr]).rules
    assert canonical.rule_payload == {"value": compiled.value}
    assert canonical.rule_id == rule_id_for("ADR-001", compiled)

    document, created = append_initial_canonical_decision(
        {"meta": {"name": "t", "description": "t"},
         "decision_index": empty_decision_index_section(), "decisions": []},
        decision_id="ADR-001", statement="Router deadline", rationale="r",
        context_scope=["router"], constraints=[], anti_patterns=[],
        rules=[compiled], source_evidence=[], occurrence_source_identity=["t"],
        created_at="2026-10-22", updated_at="2026-10-22", lifecycle_status="active",
    )
    assert created
    persisted = json.loads(json.dumps(document))
    stored, = persisted["decision_index"]["rules"]
    assert stored["rule_payload"]["value"] == compiled.value
    assert stored["rule_id"] == canonical.rule_id
    assert persisted["decision_index"]["semantic_features"] == [
        NUMERIC_UPPER_BOUND_FEATURE
    ]
    projected, = project_canonical_index(
        load_persisted_decision_index(persisted["decision_index"])
    )
    assert projected.rules == [compiled]
    assert projected.rules[0].value.encode() == compiled.value.encode()
    assert rule_id_for("ADR-001", projected.rules[0]) == canonical.rule_id


def test_loader_never_rewrites_malformed_persisted_value():
    document = _document_with(_rule())
    section = document["decision_index"]
    section["rules"][0]["rule_payload"]["value"] = section["rules"][0][
        "rule_payload"]["value"].replace('"max":"5"', '"max":"5.0"')
    before = copy.deepcopy(section)
    with pytest.raises(DecisionIndexPersistenceError):
        load_persisted_decision_index(section)
    assert section == before


def test_v1_memory_with_numeric_rule_is_refused():
    with pytest.raises(DecisionIndexPersistenceError):
        load_persisted_decision_index(v1_document(_document_with(_rule()))["decision_index"])


def test_v2_without_feature_declaration_is_refused():
    section = _document_with(_rule())["decision_index"]
    section["semantic_features"] = []
    with pytest.raises(DecisionIndexPersistenceError, match="numeric_upper_bound_rule"):
        load_persisted_decision_index(section)


def test_old_reader_refuses_v2_memory_declaring_the_feature(monkeypatch):
    """A reader without the feature refuses the document; never drops rules."""
    from mneme import decision_index_persistence as persistence

    assert SUPPORTED_SEMANTIC_FEATURES >= {APPLICABILITY_FEATURE, NUMERIC_UPPER_BOUND_FEATURE}
    monkeypatch.setattr(
        persistence, "SUPPORTED_SEMANTIC_FEATURES", frozenset({APPLICABILITY_FEATURE})
    )
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported semantic_features"):
        load_persisted_decision_index(_document_with(_rule())["decision_index"])


def test_old_rule_model_refuses_the_type():
    """The pre-ADR-034 rule model has no such type: construction fails closed."""
    from mneme import schemas

    assert "FORBID_NUMERIC_ABOVE" in schemas.VALID_RULE_TYPES
    with pytest.raises(ValueError):
        Rule(type="FORBID_NUMERIC_ABOVEX", value="x")


@pytest.mark.parametrize("change", ["schema_v1", "drop_feature"])
def test_downgrade_is_refused(change):
    section = _document_with(_rule())["decision_index"]
    if change == "schema_v1":
        section["schema"] = DECISION_INDEX_SCHEMA
        section.pop("semantic_features")
    else:
        section["semantic_features"].remove(NUMERIC_UPPER_BOUND_FEATURE)
    with pytest.raises(DecisionIndexPersistenceError):
        load_persisted_decision_index(section)


def test_writer_refuses_numeric_rule_into_v1_section():
    base = {"meta": {"name": "t", "description": "t"},
            "decision_index": empty_decision_index_section(), "decisions": []}
    base["decision_index"]["schema"] = DECISION_INDEX_SCHEMA
    base["decision_index"].pop("semantic_features")
    with pytest.raises(DecisionIndexMigrationRequired):
        append_initial_canonical_decision(
            base, decision_id="ADR-001", statement="s", rationale="r",
            context_scope=[], constraints=[], anti_patterns=[], rules=[_rule()],
            source_evidence=[], occurrence_source_identity=["t"],
            created_at="", updated_at="", lifecycle_status="active",
        )


def test_section_less_legacy_memory_cannot_use_the_type(tmp_path):
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "decisions": [{"id": "ADR-001", "decision": "d",
                       "rules": [_rule_record(_rule())]}],
    }), encoding="utf-8")
    with pytest.raises(DecisionIndexMigrationRequired):
        MemoryStore(memory).load()


# ── §8.C.2 golden rule ids ───────────────────────────────────────────────────


@pytest.mark.parametrize("decision_id,rule_type,value,applicability,expected", [
    # ADR-005's install-command literal, split so this file does not trip it.
    ("ADR-005", "FORBID_LITERAL", "pip install " + "mneme", {},
     "ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333"),
    ("ADR-001", "FORBID_NUMERIC_ABOVE", ROUTER.canonical_value(),
     {"include_paths": ["src/**"]},
     "ADR-001:FORBID_NUMERIC_ABOVE:29b880066c98c7db4abb997f7cbbb096"),
    ("ADR-001", "FORBID_NUMERIC_ABOVE",
     NumericContract(max="5", unit="seconds", symbol="ROUTER_DEADLINE_S").canonical_value(),
     {"include_paths": ["src/**"]},
     "ADR-001:FORBID_NUMERIC_ABOVE:19aa8ed962b7e693ffe3d71804cf4c7c"),
    ("ADR-001", "FORBID_NUMERIC_ABOVE",
     NumericContract(max="2.5", unit="seconds", call_function="classify",
                     call_position=1).canonical_value(),
     {"include_paths": ["src/**"]},
     "ADR-001:FORBID_NUMERIC_ABOVE:e74969fb22bd8988d5fae6133a8b7a57"),
])
def test_adr_034_golden_vectors(decision_id, rule_type, value, applicability, expected):
    assert rule_id_of(decision_id, rule_type, value, applicability) == expected


def test_persisted_adr_005_literal_id_is_unchanged():
    repo_memory = Path(__file__).resolve().parents[1] / ".mneme" / "project_memory.json"
    rules = json.loads(repo_memory.read_text(encoding="utf-8"))["decision_index"]["rules"]
    assert "ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333" in {
        r["rule_id"] for r in rules
    }


def test_semantic_change_changes_identity():
    base = rule_id_for("ADR-001", _rule())
    assert rule_id_for("ADR-001", _rule()) == base
    for changed in (
        NumericContract(max="6", unit="seconds", symbol="ROUTER_DEADLINE_S",
                        call_function="classify", call_position=1),
        NumericContract(max="5", unit="ms", symbol="ROUTER_DEADLINE_S",
                        call_function="classify", call_position=1),
        NumericContract(max="5", unit="seconds", symbol="ROUTER_DEADLINE_S",
                        call_function="classify", call_position=0),
    ):
        assert rule_id_for("ADR-001", _rule(changed)) != base
    assert rule_id_for("ADR-001", _rule(include=("lib/**",))) != base


# ── §8.C.3 numeric semantics: R1-R18 through the shipped check path ─────────

R_VECTORS = [
    ("R1", "0.1 + 0.2", "0.3", "VIOLATION", None),
    ("R2", "0.3", "0.3", "NO_VIOLATION", None),
    ("R3", "5.000000000000001", "5", "VIOLATION", None),
    ("R4", "5.0000000000000001", "5", "NO_VIOLATION", None),
    ("R5", "10 / 2", "5", "NO_VIOLATION", None),
    ("R6", "4.5 + 0.5", "5", "NO_VIOLATION", None),
    ("R7", "1 / 3 * 15", "5", "NO_VIOLATION", None),
    ("R8", "11 // 2", "5", "NO_VIOLATION", None),
    ("R9", "-1 % 6", "5", "NO_VIOLATION", None),
    ("R10", "2 ** 3", "5", "VIOLATION", None),
    ("R11", "2 ** 65", "5", "UNEVALUATED", "UNRECOGNIZED_FORM"),
    ("R12", "10 ** 31", "5", "UNEVALUATED", "UNRECOGNIZED_FORM"),
    ("R13", "1e308 * 10", "5", "UNEVALUATED", "UNRECOGNIZED_FORM"),
    ("R14", "1 / 0", "5", "UNEVALUATED", "UNRECOGNIZED_FORM"),
    ("R15", "2 ** 2", "4", "NO_VIOLATION", None),
    ("R16", "0.1", "0.1", "VIOLATION", None),
    ("R17", "4 ** 0.5", "5", "UNEVALUATED", "UNRECOGNIZED_FORM"),
    ("R18", "2 ** 2.0", "5", "UNEVALUATED", "UNRECOGNIZED_FORM"),
]


@pytest.mark.parametrize("case,expr,max_,outcome,reason", R_VECTORS, ids=[r[0] for r in R_VECTORS])
def test_set_r_vectors(tmp_path, capsys, case, expr, max_, outcome, reason):
    assert sys.version_info[:3] == (3, 12, 10), "set R is pinned to CPython 3.12.10"
    contract = NumericContract(max=max_, unit="u", symbol="LIMIT")
    code, payload, _ = _audit(tmp_path, capsys, contract, f"LIMIT = {expr}\n")
    trace = _numeric_trace(payload)
    assert trace["matcher_outcome"] == outcome
    assert trace["primary_reason"] == reason
    assert payload["verdict"] == ("FAIL" if outcome == "VIOLATION" else "PASS")
    assert payload["evaluation_complete"] is (outcome != "UNEVALUATED")
    assert code == (2 if outcome != "NO_VIOLATION" else 0)


def test_r16_diagnostic_states_strict_comparison(tmp_path, capsys):
    contract = NumericContract(max="0.1", unit="u", symbol="LIMIT")
    _, payload, _ = _audit(tmp_path, capsys, contract, "LIMIT = 0.1\n")
    details = payload["violations"][0]["numeric"]
    assert details["value"] == "0.1"
    assert details["value_exact"].startswith("0.1000000000000000055511")
    assert details["max"] == "0.1"
    assert "no implicit tolerance" in details["comparison"]


@pytest.mark.parametrize("expr", [
    "None", "True", "False", '"5"', "b'5'", "0", "-1", "0.0", "-0.5",
    "1e309", "-1e309", "1j", "(1, 2)", "[3]", "~3", "not 3", "3 << 1",
    "3 @ 1", "abs(3)", "BASE * 2", "int('3')", "f'{3}'", "3 if x else 4",
    "(-8) ** 0.5", "0 ** -1", "10 ** 30 * 10", "1e200 ** 2", "2 ** True",
])
def test_unrecognized_or_disabled_values_are_never_judged(tmp_path, capsys, expr):
    contract = NumericContract(max="5", unit="u", symbol="LIMIT")
    _, payload, _ = _audit(tmp_path, capsys, contract, f"LIMIT = {expr}\n")
    trace = _numeric_trace(payload)
    assert trace["matcher_status"] == "MATCHER_UNEVALUATED"
    assert trace["primary_reason"] == "UNRECOGNIZED_FORM"


@pytest.mark.parametrize("expr,outcome", [
    ("2 ** -1", "NO_VIOLATION"),
    ("10 ** 30", "VIOLATION"),
    ("(2 + 3) * 1", "NO_VIOLATION"),
    ("+6", "VIOLATION"),
    ("-(-6)", "VIOLATION"),
    ("0x5", "NO_VIOLATION"),
    ("5_0", "VIOLATION"),
    ("2.5 * 2", "NO_VIOLATION"),
])
def test_recognized_literal_arithmetic(tmp_path, capsys, expr, outcome):
    contract = NumericContract(max="5", unit="u", symbol="LIMIT")
    _, payload, _ = _audit(tmp_path, capsys, contract, f"LIMIT = {expr}\n")
    assert _numeric_trace(payload)["matcher_outcome"] == outcome


def test_parse_failure_on_a_complete_file(tmp_path, capsys):
    """AMB-10."""
    code, payload, _ = _audit(tmp_path, capsys, ROUTER, "def broken(:\n    pass\n")
    trace = _numeric_trace(payload)
    assert trace["matcher_status"] == "MATCHER_UNEVALUATED"
    assert trace["primary_reason"] == "PARSE_FAILURE"
    assert trace["unknown_sources"] == [{"kind": "module", "line": 1, "reason": "PARSE_FAILURE"}]
    assert code == 2


def test_source_is_never_executed(tmp_path, capsys):
    marker = tmp_path / "executed.txt"
    source = (
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
        "raise SystemExit(7)\n"
        "LIMIT = 3\n"
    )
    contract = NumericContract(max="5", unit="u", symbol="LIMIT")
    code, payload, _ = _audit(tmp_path, capsys, contract, source)
    assert not marker.exists()
    assert _numeric_trace(payload)["matcher_outcome"] == "NO_VIOLATION"
    assert code == 0


def test_compile_warnings_never_reach_stderr(tmp_path, capsys):
    contract = NumericContract(max="5", unit="u", symbol="LIMIT")
    _, payload, captured = _audit(tmp_path, capsys, contract, 'P = "\\d"\nLIMIT = 3\n')
    assert captured.err == ""
    assert _numeric_trace(payload)["matcher_outcome"] == "NO_VIOLATION"


# ── §8.C.4 source discovery ──────────────────────────────────────────────────

SYMBOL_ONLY = NumericContract(max="5", unit="s", symbol="ROUTER_DEADLINE_S")
CALL_ONLY = NumericContract(max="5", unit="s", call_function="classify", call_position=1)


def _status(tmp_path, capsys, contract, source):
    _, payload, _ = _audit(tmp_path, capsys, contract, source)
    trace = _numeric_trace(payload)
    return trace["matcher_status"], trace["matcher_outcome"], trace["primary_reason"], trace, payload


@pytest.mark.parametrize("contract,source,expected", [
    # symbol only
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S = 3\n", ("RECOGNIZED", "NO_VIOLATION", None)),
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S: float = 9.5\n", ("RECOGNIZED", "VIOLATION", None)),
    (SYMBOL_ONLY, "OTHER = 60\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")),
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S = 3\nROUTER_DEADLINE_S = 4\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S = 3\nROUTER_DEADLINE_S += 1\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S = 3\ndef f():\n    global ROUTER_DEADLINE_S\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S = 3\ndef f(ROUTER_DEADLINE_S=9):\n    pass\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    # AMB-08: assigned in two conditional branches.
    (SYMBOL_ONLY, "if FAST:\n    ROUTER_DEADLINE_S = 1\nelse:\n    ROUTER_DEADLINE_S = 2\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    # AMB-17: reads elsewhere are neither rebinding nor a source.
    (SYMBOL_ONLY, "ROUTER_DEADLINE_S = 3\nretry(timeout=ROUTER_DEADLINE_S)\nprint(ROUTER_DEADLINE_S)\n",
     ("RECOGNIZED", "NO_VIOLATION", None)),
    # Derived constant.
    (SYMBOL_ONLY, "BASE = 2\nROUTER_DEADLINE_S = BASE * 3\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "UNRECOGNIZED_FORM")),
    # Comment, string and docstring look-alikes are not sources.
    (SYMBOL_ONLY, '"""ROUTER_DEADLINE_S = 60"""\n# ROUTER_DEADLINE_S = 60\nX = "ROUTER_DEADLINE_S = 60"\nROUTER_DEADLINE_S = 5\n',
     ("RECOGNIZED", "NO_VIOLATION", None)),
    # call only
    (CALL_ONLY, "def run(x):\n    return classify(x, 2)\n", ("RECOGNIZED", "NO_VIOLATION", None)),
    (CALL_ONLY, "def run(x):\n    return classify(x, 9)\n", ("RECOGNIZED", "VIOLATION", None)),
    (CALL_ONLY, "def run(x):\n    return other(x, 9)\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")),
    # AMB-01: a single unaliased module-level import is the declaration.
    (CALL_ONLY, "from labels import classify\nclassify(x, 2)\n", ("RECOGNIZED", "NO_VIOLATION", None)),
    (CALL_ONLY, "from labels import classify\nclassify = wrap(classify)\nclassify(x, 2)\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    # AMB-02: governed value passed by keyword -> positional source absent.
    (CALL_ONLY, "classify(x, timeout=9)\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")),
    # AMB-03: calls inside function and method bodies count.
    (CALL_ONLY, "class R:\n    def go(self):\n        return classify(self, 9)\n",
     ("RECOGNIZED", "VIOLATION", None)),
    # AMB-04: explicit keywords for other parameters do not defeat the source.
    (CALL_ONLY, "classify(x, 3, retries=99)\n", ("RECOGNIZED", "NO_VIOLATION", None)),
    # AMB-05: star-args.
    (CALL_ONLY, "classify(*args)\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "UNRECOGNIZED_FORM")),
    (CALL_ONLY, "classify(x, 3, **opts)\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "UNRECOGNIZED_FORM")),
    # AMB-06: only called through an alias.
    (CALL_ONLY, "from labels import classify as cl\ncl(x, 9)\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")),
    # AMB-07: shadowed by a parameter defaulting to the function.
    (CALL_ONLY, "def classify(a, b):\n    pass\ndef h(x, classify=classify):\n    return classify(x, 2)\nclassify(x, 3)\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    # The function escapes as a value.
    (CALL_ONLY, "handlers = [classify]\nclassify(x, 2)\n",
     ("MATCHER_UNEVALUATED", "UNEVALUATED", "AMBIGUOUS_BINDING")),
    # Attribute calls are not direct bare-name calls.
    (CALL_ONLY, "labels.classify(x, 9)\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")),
    # Too few positional arguments.
    (CALL_ONLY, "classify(x)\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")),
    # A bare name in call-only mode is a derived value.
    (CALL_ONLY, "T = 3\nclassify(x, T)\n", ("MATCHER_UNEVALUATED", "UNEVALUATED", "UNRECOGNIZED_FORM")),
])
def test_source_discovery(tmp_path, capsys, contract, source, expected):
    status, outcome, reason, _, _ = _status(tmp_path, capsys, contract, source)
    assert (status, outcome, reason) == expected


def test_symbol_and_call_are_independent_sources(tmp_path, capsys):
    """AMB-15: in symbol+call mode the symbol is a source in its own right."""
    status, outcome, _, trace, payload = _status(
        tmp_path, capsys, ROUTER,
        "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n",
    )
    assert (status, outcome) == ("RECOGNIZED", "VIOLATION")
    assert payload["violations"][0]["numeric"]["exceeding_sources"] == [
        {"kind": "symbol", "line": 1, "value": "60", "value_exact": "60"}
    ]


def test_symbol_argument_resolves_to_the_symbol_value(tmp_path, capsys):
    _, _, _, _, payload = _status(
        tmp_path, capsys, ROUTER,
        "ROUTER_DEADLINE_S = 9\nclassify(x, ROUTER_DEADLINE_S)\n",
    )
    assert [s["kind"] for s in payload["violations"][0]["numeric"]["exceeding_sources"]] == [
        "symbol", "call",
    ]


def test_both_declared_sources_are_required(tmp_path, capsys):
    status, outcome, reason, trace, _ = _status(
        tmp_path, capsys, ROUTER, "ROUTER_DEADLINE_S = 3\n"
    )
    assert (status, outcome, reason) == ("MATCHER_UNEVALUATED", "UNEVALUATED", "SOURCE_NOT_FOUND")
    assert trace["unknown_sources"] == [{"kind": "call", "line": None, "reason": "SOURCE_NOT_FOUND"}]


def test_multi_call_scope_every_site_is_inspected(tmp_path, capsys):
    source = (
        "def a(x):\n    return classify(x, 2)\n"
        "def b(x):\n    return classify(x, 4)\n"
        "def c(x):\n    return classify(x, 7)\n"
    )
    _, _, _, _, payload = _status(tmp_path, capsys, CALL_ONLY, source)
    details = payload["violations"][0]["numeric"]
    assert details["exceeding_sources"] == [
        {"kind": "call", "line": 6, "value": "7", "value_exact": "7"}
    ]


def test_partial_keeps_unknown_source_evidence_and_fails(tmp_path, capsys):
    """AMB-12: the unknown source is identified by kind, 1-based line, reason."""
    source = (
        "def a(x):\n    return classify(x, 2)\n"
        "def b(x):\n    return classify(x, 9)\n"
        "def c(x):\n    return classify(x, timeout=1)\n"
    )
    code, payload, _ = _audit(tmp_path, capsys, CALL_ONLY, source)
    trace = _numeric_trace(payload)
    assert trace["matcher_status"] == "PARTIAL"
    assert trace["matcher_outcome"] == "VIOLATION"
    assert trace["primary_reason"] == "SOURCE_NOT_FOUND"
    assert trace["unknown_sources"] == [{"kind": "call", "line": 6, "reason": "SOURCE_NOT_FOUND"}]
    assert payload["verdict"] == "FAIL"
    assert payload["evaluation_complete"] is False
    assert code == 2


def test_reason_priority_lists_all_and_scores_the_first():
    contract = ROUTER
    source = b"ROUTER_DEADLINE_S = 1\nROUTER_DEADLINE_S = 2\nclassify(x, BASE)\n"
    result = numeric_rule.evaluate_source(contract, source)
    assert [u.reason for u in result.unknown_sources] == [
        "AMBIGUOUS_BINDING", "UNRECOGNIZED_FORM",
    ]
    assert result.primary_reason == "AMBIGUOUS_BINDING"
    result = numeric_rule.evaluate_source(contract, b"classify(x, BASE)\n")
    assert [u.reason for u in result.unknown_sources] == [
        "SOURCE_NOT_FOUND", "UNRECOGNIZED_FORM",
    ]
    assert result.primary_reason == "SOURCE_NOT_FOUND"
    assert numeric_rule.REASON_PRIORITY == (
        "INCOMPLETE_SOURCE_INPUT", "PARSE_FAILURE", "AMBIGUOUS_BINDING",
        "SOURCE_NOT_FOUND", "UNRECOGNIZED_FORM",
    )


@pytest.mark.parametrize("text", [
    "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n",
    "ROUTER_DEADLINE_S = 60\n",
    "this is a prompt, not python",
])
def test_non_source_input_is_incomplete_before_parsing(tmp_path, capsys, text):
    """AMB-09 / N2: --input is never complete source, even when it parses."""
    _project(tmp_path, {"ADR-001": [_rule()]})
    inp = _write(tmp_path, "src/router.py", text)
    code, payload, _ = _check(tmp_path, capsys, input_file=inp)
    trace = _numeric_trace(payload)
    assert trace["matcher_status"] == "MATCHER_UNEVALUATED"
    assert trace["primary_reason"] == "INCOMPLETE_SOURCE_INPUT"
    assert trace["unknown_sources"] == [
        {"kind": "input", "line": None, "reason": "INCOMPLETE_SOURCE_INPUT"}
    ]
    assert payload["verdict"] == "PASS" and payload["evaluation_complete"] is False
    assert payload["subject"]["input_kind"] == "unverified_input"
    assert code == 2


def test_delta_with_claimed_target_path_is_incomplete(tmp_path, capsys):
    _project(tmp_path, {"ADR-001": [_rule()]})
    delta = _write(tmp_path, "delta.txt", "ROUTER_DEADLINE_S = 3\n")
    _, payload, _ = _check(
        tmp_path, capsys, input_file=delta, target=tmp_path / "src" / "router.py"
    )
    trace = _numeric_trace(payload)
    assert trace["outcome"] == "APPLIED"
    assert trace["primary_reason"] == "INCOMPLETE_SOURCE_INPUT"


@pytest.mark.parametrize("rel,include,exclude", [
    ("src/vendor/router.py", SRC, ("src/vendor/**",)),
    ("lib/router.py", SRC, ()),
])
def test_excluded_paths_produce_no_matching_claim(tmp_path, capsys, rel, include, exclude):
    """AMB-16: exclude selector and missing every include are both EXCLUDED."""
    _project(tmp_path, {"ADR-001": [_rule(include=include, exclude=exclude)]})
    path = _write(tmp_path, rel, "ROUTER_DEADLINE_S = 60\nclassify(x, 60)\n")
    code, payload, _ = _check(tmp_path, capsys, source=path)
    trace = _numeric_trace(payload)
    assert trace["outcome"] == "EXCLUDED"
    assert "matcher_status" not in trace
    assert payload["verdict"] == "PASS" and payload["evaluation_complete"] is True
    assert code == 0


def test_applicability_unknown_is_path_dimension_only(tmp_path, capsys):
    _project(tmp_path, {"ADR-001": [_rule()]})
    inp = _write(tmp_path, "x.txt", "ROUTER_DEADLINE_S = 3\n")
    _, payload, _ = _check(tmp_path, capsys, input_file=inp, target="../outside/x.py")
    trace = _numeric_trace(payload)
    assert trace["outcome"] == "UNKNOWN"
    assert "matcher_status" not in trace
    assert payload["evaluation_complete"] is False


# ── §8.C.5 CLI ───────────────────────────────────────────────────────────────

WITHIN = "ROUTER_DEADLINE_S = 3\ndef run(x):\n    return classify(x, 2)\n"
ABOVE = "ROUTER_DEADLINE_S = 60\ndef run(x):\n    return classify(x, 2)\n"
UNKNOWN_ONLY = "ROUTER_DEADLINE_S = 3\n"
MIXED = "ROUTER_DEADLINE_S = 60\n"


@pytest.mark.parametrize("source,mode,verdict,complete,exit_code", [
    (WITHIN, "strict", "PASS", True, 0),
    (WITHIN, "warn", "PASS", True, 0),
    (ABOVE, "strict", "FAIL", True, 2),
    (ABOVE, "warn", "FAIL", True, 0),
    (UNKNOWN_ONLY, "strict", "PASS", False, 2),
    (UNKNOWN_ONLY, "warn", "PASS", False, 2),
    (MIXED, "strict", "FAIL", False, 2),
    (MIXED, "warn", "FAIL", False, 2),
])
def test_exit_matrix_and_payload_coherence(tmp_path, capsys, source, mode, verdict,
                                           complete, exit_code):
    code, payload, _ = _audit(tmp_path, capsys, ROUTER, source, mode=mode)
    assert (payload["verdict"], payload["evaluation_complete"], code) == (
        verdict, complete, exit_code
    )
    assessment = assess_verdict(json.dumps(payload), code, mode)
    assert assessment.payload is not None, assessment.problem


@pytest.mark.parametrize("source,result_line", [
    (WITHIN, "Result: PASS"),
    (ABOVE, "Result: FAIL"),
    (UNKNOWN_ONLY, "Result: INCOMPLETE"),
    (MIXED, "Result: FAIL (evaluation incomplete)"),
])
def test_human_diagnostics_are_readable(tmp_path, capsys, source, result_line):
    _, _, captured = _audit(tmp_path, capsys, ROUTER, source, json_out=False)
    out = captured.out
    assert out.rstrip().splitlines()[-1] == result_line
    assert '"v":1' not in out  # never the raw canonical JSON
    if source in (ABOVE, MIXED):
        assert "must not exceed 5 seconds" in out
        assert "runtime value 60 (exactly 60) > max 5 seconds" in out
        assert "no implicit tolerance" in out
    if source in (UNKNOWN_ONLY, MIXED):
        assert "unknown call source (line -): SOURCE_NOT_FOUND" in out


def test_output_is_deterministic(tmp_path, capsys):
    _project(tmp_path, {"ADR-001": [_rule()], "ADR-002": [_rule(CALL_ONLY)]})
    path = _write(tmp_path, "src/module.py", "ROUTER_DEADLINE_S = 60\nclassify(x, 9)\nclassify(x, y)\n")
    first = _check(tmp_path, capsys, source=path)
    second = _check(tmp_path, capsys, source=path)
    assert json.dumps(first[1]) == json.dumps(second[1]) and first[0] == second[0]


def test_no_numeric_payloads_are_byte_identical_to_baseline(tmp_path, monkeypatch):
    """Frozen from the pre-ADR-034 implementation (build_legacy_fixture.py)."""
    sys.path.insert(0, str(FIXTURES))
    try:
        import build_legacy_fixture as fixture
    finally:
        sys.path.remove(str(FIXTURES))
    import shutil

    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "legacy_project", project)
    golden = json.loads((FIXTURES / "no_numeric_golden.json").read_text(encoding="utf-8"))
    assert fixture.run_scenarios(project) == golden
    assert len(golden) == 18


def test_historical_payloads_stay_trusted_and_unchanged():
    golden = json.loads((FIXTURES / "no_numeric_golden.json").read_text(encoding="utf-8"))
    for name, record in golden.items():
        mode = "warn" if name.endswith("_warn") else "strict"
        assessment = assess_verdict(record["stdout"], record["exit"], mode)
        assert assessment.payload == json.loads(record["stdout"]), name
        assert "subject" not in assessment.payload


def test_source_file_and_input_are_mutually_exclusive(tmp_path):
    _project(tmp_path, {"ADR-001": [_rule()]})
    path = _write(tmp_path, "src/module.py", WITHIN)
    with pytest.raises(SystemExit) as exc:
        main(["check", "--memory", str(tmp_path / ".mneme" / "project_memory.json"),
              "--source-file", str(path), "--input", str(path), "--query", "q"])
    assert exc.value.code == 2


def test_source_file_rejects_target_path(tmp_path, capsys):
    _project(tmp_path, {"ADR-001": [_rule()]})
    path = _write(tmp_path, "src/module.py", WITHIN)
    code, payload, captured = _check(tmp_path, capsys, source=path, target=path)
    assert code == 2 and payload is None and "--target-path" in captured.err


@pytest.mark.parametrize("setup", [
    "missing", "directory", "outside_root", "not_python", "invalid_utf8", "symlink",
])
def test_source_file_operational_errors_never_pass(tmp_path, capsys, setup):
    project = tmp_path / "project"
    _project(project, {"ADR-001": [_rule()]})
    if setup == "missing":
        path = project / "src" / "absent.py"
    elif setup == "directory":
        path = project / "src" / "pkg.py"
        path.mkdir(parents=True)
    elif setup == "outside_root":
        path = _write(tmp_path, "elsewhere/module.py", WITHIN)
    elif setup == "not_python":
        path = _write(project, "src/module.txt", WITHIN)
    elif setup == "invalid_utf8":
        path = _write(project, "src/module.py", b"LIMIT = 3\n\xff\xfe\n")
    else:
        real = _write(project, "src/real.py", WITHIN)
        path = project / "src" / "link.py"
        try:
            os.symlink(real, path)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
    code, payload, captured = _check(
        tmp_path, capsys, source=path, memory=project / ".mneme" / "project_memory.json"
    )
    assert code == 2
    assert payload is None and captured.out == ""
    assert captured.err.startswith("ERROR: ")


def test_source_file_works_without_numeric_rules(tmp_path, capsys):
    memory = _project(tmp_path, {})
    path = _write(tmp_path, "src/module.py", WITHIN)
    code, payload, _ = _check(tmp_path, capsys, source=path, memory=memory)
    assert code == 0 and payload["verdict"] == "PASS"
    assert payload["subject"]["input_kind"] == "complete_source_file"


# ── §8.C.7 evidence binding ──────────────────────────────────────────────────


def test_evidence_binds_digest_rule_version_applicability_status_outcome(tmp_path, capsys):
    from mneme.decision_governance import evidence_identity_of
    from mneme.path_selectors import RuleEvaluation, SelectorOutcome

    memory = _project(tmp_path, {"ADR-001": [_rule()]})
    data = b"ROUTER_DEADLINE_S = 60\nclassify(x, y)\n"
    path = _write(tmp_path, "src/module.py", data)
    _, payload, _ = _check(tmp_path, capsys, source=path)
    digest = hashlib.sha256(data).hexdigest()
    subject = payload["subject"]
    assert subject["subject_sha256"] == digest
    assert subject["governed_path"] == "src/module.py"
    assert Path(subject["source_path"]) == path.resolve()
    assert Path(subject["memory_path"]) == memory.resolve()
    assert subject["runtime"] == numeric_rule.runtime_label()
    trace = _numeric_trace(payload)
    version = json.loads(memory.read_text(encoding="utf-8"))["decision_index"][
        "decisions"][0]["active_version_id"]
    assert trace["subject_sha256"] == digest
    assert trace["rule_id"] == rule_id_for("ADR-001", _rule())
    assert trace["decision_version_id"] == version
    assert trace["outcome"] == "APPLIED"
    assert (trace["matcher_status"], trace["primary_reason"]) == ("PARTIAL", "UNRECOGNIZED_FORM")
    assert trace["matcher_outcome"] == "VIOLATION"
    violation, = payload["violations"]
    assert (violation["rule_id"], violation["decision_version_id"]) == (
        trace["rule_id"], trace["decision_version_id"]
    )

    bound = RuleEvaluation(
        decision_id="ADR-001", rule_type=trace["rule_type"],
        rule_value=trace["rule_value"], rule_index=0, path_scoped=True,
        outcome=SelectorOutcome.APPLIED, input_path=trace["input_path"],
        rule_id=trace["rule_id"], decision_version_id=trace["decision_version_id"],
    )
    assert evidence_identity_of(bound).complete
    unbound = RuleEvaluation(
        decision_id="ADR-001", rule_type=trace["rule_type"],
        rule_value=trace["rule_value"], rule_index=0, path_scoped=True,
        outcome=SelectorOutcome.APPLIED, input_path=trace["input_path"],
        rule_id=trace["rule_id"], decision_version_id="",
    )
    assert not evidence_identity_of(unbound).complete


def test_tampered_binding_is_untrusted(tmp_path, capsys):
    _, payload, _ = _audit(tmp_path, capsys, ROUTER, ABOVE)
    tampered = copy.deepcopy(payload)
    tampered["applicability"][0]["subject_sha256"] = "0" * 64
    assert assess_verdict(json.dumps(tampered), 2, "strict").payload is None


# ── §8.C.8 F3 conflict noncoverage ───────────────────────────────────────────


def _decision(rules) -> Decision:
    return Decision(id="ADR-001", decision="Router deadline", rules=list(rules),
                    version_id="dver-test")


def test_evaluate_reports_numeric_noncoverage_without_changing_completeness():
    detector = ConflictDetector()
    decisions = [_decision([_rule()])]
    result = detector.evaluate("ROUTER_DEADLINE_S = 600", decisions)
    assert result.conflicts == [] and result.applicability == []
    assert result.evaluation_complete is True
    item, = result.noncoverage
    assert (item.decision_id, item.decision_version_id, item.rule_id, item.reason) == (
        "ADR-001", "dver-test", rule_id_for("ADR-001", _rule()),
        "NOT_EVALUATED_ON_RESPONSE_TEXT",
    )
    assert detector.evaluate("ROUTER_DEADLINE_S = 600", decisions) == result


def test_detect_refuses_a_numeric_decision_set():
    with pytest.raises(NumericRuleNoncoverageError) as exc:
        ConflictDetector().detect("anything", [_decision([_rule()])])
    assert "does not cover" in str(exc.value)
    assert "not cover" in noncoverage_note(exc.value.noncoverage)


def test_literal_only_conflict_results_are_unchanged():
    literal = Rule(type="FORBID_LITERAL", value="psycopg2")
    result = ConflictDetector().evaluate("use psycopg2", [_decision([literal])])
    assert result.noncoverage == []
    assert len(result.conflicts) == 1
    assert ConflictDetector().detect("use psycopg2", [_decision([literal])]) == result.conflicts


def test_strict_pipeline_does_not_raise_on_noncoverage_alone(tmp_path):
    from mneme.pipeline import Pipeline

    memory = _project(tmp_path, {"ADR-001": [_rule()]})
    result = Pipeline(memory, dry_run=True, enforcement_mode="strict").run(
        "router deadline", _override_response="set the router deadline to 600"
    )
    assert result.conflicts == []
    assert result.evaluation_complete is True
    assert [item.rule_id for item in result.noncoverage] == [rule_id_for("ADR-001", _rule())]


# ── §8.C.9 adjacent consumers ────────────────────────────────────────────────


def test_governability_and_protection_never_count_numeric_rules():
    decision = _decision([_rule()])
    governability = assess_governability(decision)
    assert governability.tier == "guidance"
    assert governability.has_literal_rules is False
    assert governability.numeric_audit_only_rules == 1
    report = assess_protection(decision)
    assert report.protection_tier != "protected"
    assert f"numeric:g1-audit-only-not-protected:{rule_id_for('ADR-001', _rule())}" in (
        report.evidence_sources
    )


def test_literal_protection_report_is_unchanged_by_the_wrapper():
    literal = Rule(type="FORBID_LITERAL", value="psycopg2")
    report = assess_protection(_decision([literal]))
    assert report.protection_tier == "protected" and report.evidence_sources == []


def test_protection_activation_and_preservation_reject_numeric_rules(tmp_path):
    from mneme.cli import _preservation_validator
    from mneme.protection import validate_proposal

    decision = _decision([])
    assert validate_proposal(decision, _rule(), memory_path=str(tmp_path / "m.json")).status == (
        "unsupported"
    )
    with pytest.raises(ValueError, match="FORBID_LITERAL"):
        _preservation_validator(tmp_path / "m.json")(decision, _rule())


def test_mcp_and_eventcatalog_serializers_round_trip_the_canonical_rule():
    from mneme.decision_index import decisions_to_canonical
    from mneme.decision_mcp import rule_to_transport
    from mneme.integrations.eventcatalog.importer import _serialize_rule

    rule = _rule()
    canonical, = decisions_to_canonical([_decision([rule])]).rules
    transport = rule_to_transport(canonical)
    assert transport["rule_type"] == "FORBID_NUMERIC_ABOVE"
    assert transport["rule_payload"] == {"value": rule.value}
    assert transport["rule_id"] == rule_id_for("ADR-001", rule)
    serialized = _serialize_rule(rule)
    assert serialized == {"type": rule.type, "value": rule.value, "include_paths": ["src/**"]}


def test_evidence_identity_accepts_numeric_rule_ids():
    from mneme.decision_governance import EvidenceIdentity

    identity = EvidenceIdentity(
        decision_id="ADR-001",
        decision_version_id="dver-" + "0" * 32,
        rule_id=rule_id_for("ADR-001", _rule()),
    )
    assert identity.rule_owned_by_decision


def test_numeric_rule_does_not_change_retrieval():
    from mneme.decision_retriever import DecisionRetriever

    plain = _decision([])
    with_rule = _decision([_rule()])
    a = DecisionRetriever([plain]).retrieve("router deadline")
    b = DecisionRetriever([with_rule]).retrieve("router deadline")
    assert [s.score for s in a] == [s.score for s in b]


def test_hook_constants_mirror_the_matcher_vocabulary():
    from mneme.integrations.claude_code import hook

    assert hook._NUMERIC_RULE_TYPE == numeric_rule.RULE_TYPE
    assert hook._MATCHER_REASON_PRIORITY == numeric_rule.REASON_PRIORITY
    assert set(hook._MATCHER_OUTCOME_BY_STATUS) == numeric_rule.MATCHER_STATUSES
    assert hook._MATCHER_INCOMPLETE == numeric_rule.INCOMPLETE_STATUSES
    assert hook._SOURCE_KINDS == numeric_rule.SOURCE_KINDS


def test_real_baseline_binary_refuses_numeric_memory(tmp_path):
    """Old-reader refusal against the actual pre-ADR-034 rule model, when the
    merge base is available in this checkout's history."""
    repo = Path(__file__).resolve().parents[1]
    base = subprocess.run(
        ["git", "-C", str(repo), "show", "ec72ba9f:mneme/decision_index_persistence.py"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if base.returncode != 0:
        pytest.skip("baseline commit not available")
    assert '"numeric_upper_bound_rule"' not in base.stdout
    assert "SUPPORTED_SEMANTIC_FEATURES = frozenset({APPLICABILITY_FEATURE})" in base.stdout

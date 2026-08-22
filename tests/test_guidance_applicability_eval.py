"""Regression tests for the locked guidance-applicability diagnosis."""

import hashlib
import json
from pathlib import Path

import pytest

from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.guidance_applicability_eval import EVAL_SCHEMA, evaluate_fixture

FIXTURE = (
    Path(__file__).parent / "fixtures" / "guidance_applicability" / "cases.json"
)


def test_fixture_contract_is_locked_and_uses_canonical_k():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest().upper() == (
        "2408DD615BB54E3BB8E03B8A28CA1BE9CDC0670E5C4BBA6C04541BA902BADEAB"
    )
    assert payload["schema"] == EVAL_SCHEMA
    assert payload["locked_on"] == "2026-08-13"
    assert payload["k"] == DEFAULT_MAX_DECISIONS == 3
    assert payload["memory_sha256"] == (
        "983BAA775AAF38AB36C5D83CA07379C16F72A931BD7568BBA58D13C25B2C45DD"
    )
    assert len(payload["cases"]) == 4


def test_locked_failure_is_preserved_and_role_formatting_is_remediated():
    report = evaluate_fixture(FIXTURE)
    assert report["diagnosis_reproduced"]
    assert report["role_contract_reproduced"]
    assert report["role_formatting_contract_reproduced"]
    assert report["production_behavior_changed"] is True
    assert report["role_classifier_wired_to_production"] is True
    assert report["metrics"] == {
        "case_count": 4,
        "baseline_snapshot_matches": 4,
        "direct_macro_recall_at_k": 1.0,
        "historical_adjacent_undifferentiated_selections": 2,
        "adjacent_undifferentiated_selections": 0,
        "adjacent_authorizing_selections": 0,
        "unexpected_selections": 0,
        "role_snapshot_matches": 4,
        "role_aware_formatting_matches": 4,
        "non_authorizing_wording_matches": 4,
        "direct_role_macro_recall": 1.0,
        "known_adjacent_role_hits": 2,
        "known_adjacent_role_total": 2,
        "unclassified_selected_decisions": 0,
        "selection_changed_cases": 0,
    }

    cases = {case["id"]: case for case in report["cases"]}
    auth = cases["e66-auth-storage-overreach"]
    assert auth["selected_ids"] == ["ADR-AUTH", "ADR-STORAGE"]
    assert auth["assigned_direct_ids"] == ["ADR-AUTH"]
    assert auth["assigned_adjacent_constraint_ids"] == ["ADR-STORAGE"]
    assert [item["role"] for item in auth["role_assignments"]] == [
        "direct", "adjacent_constraint",
    ]
    assert auth["historical_adjacent_undifferentiated_ids"] == [
        "ADR-STORAGE"
    ]
    assert auth["adjacent_undifferentiated_ids"] == []
    assert auth["adjacent_authorizing_ids"] == []
    assert auth["production_decision_ids"] == ["ADR-AUTH", "ADR-STORAGE"]
    assert auth["production_scores"] == [8.0, 2.0]
    assert auth["role_aware_formatting_matches"]
    assert auth["non_authorizing_wording_matches"]
    assert auth["score_evidence"] == [
        {
            "decision_id": "ADR-AUTH",
            "score": 8.0,
            "matches": {
                "decision": 2,
                "scope": 2,
                "constraints": 1,
                "anti_patterns": 0,
                "rules": 0,
                "rationale": 1,
            },
        },
        {
            "decision_id": "ADR-STORAGE",
            "score": 2.0,
            "matches": {
                "decision": 0,
                "scope": 1,
                "constraints": 0,
                "anti_patterns": 0,
                "rules": 0,
                "rationale": 0,
            },
        },
    ]


def test_eval_rejects_memory_drift(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_memory = (FIXTURE.parent / payload["memory"]).resolve()
    memory = tmp_path / "project_memory.json"
    memory.write_bytes(source_memory.read_bytes())
    payload["memory"] = "project_memory.json"
    payload["memory_sha256"] = "0" * 64
    target = tmp_path / "cases.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="memory hash mismatch"):
        evaluate_fixture(target)


def test_eval_rejects_overlapping_direct_and_adjacent_ids(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_memory = FIXTURE.parent / payload["memory"]
    memory = tmp_path / "project_memory.json"
    memory.write_bytes(source_memory.resolve().read_bytes())
    payload["memory"] = "project_memory.json"
    payload["cases"][0]["adjacent_ids"] = ["ADR-AUTH"]
    target = tmp_path / "cases.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="both direct and adjacent"):
        evaluate_fixture(target)

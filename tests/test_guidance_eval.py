"""Regression tests for the locked prompt-time guidance retrieval evaluation."""

import json
from pathlib import Path

import pytest

from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.guidance_eval import EVAL_SCHEMA, evaluate_fixture


FIXTURE = (
    Path(__file__).parent / "fixtures" / "guidance_retrieval" / "cases.json"
)


def test_fixture_contract_is_locked_and_uses_canonical_k():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema"] == EVAL_SCHEMA
    assert payload["locked_on"] == "2026-08-13"
    assert payload["k"] == DEFAULT_MAX_DECISIONS == 3
    assert {case["split"] for case in payload["cases"]} == {
        "development", "holdout",
    }
    assert any(case.get("safety_critical") for case in payload["cases"])
    assert any(case.get("no_relevance") for case in payload["cases"])
    assert any(case.get("low_signal") for case in payload["cases"])


def test_locked_guidance_retrieval_gates_pass():
    report = evaluate_fixture(FIXTURE)
    assert report["passed"], {
        result["id"]: result
        for result in report["cases"]
        if result["recall_at_k"] < 1.0
        or result["false_injection"]
        or result["low_signal_injection"]
    }


def test_guidance_eval_rejects_noncanonical_k(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["k"] = DEFAULT_MAX_DECISIONS + 1
    target = tmp_path / "cases.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="K must remain"):
        evaluate_fixture(target)

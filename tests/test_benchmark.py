"""Tests for BenchmarkRunner — scenario loading and PASS/FAIL/WEAK verdicts."""
import json
import warnings
from pathlib import Path

import pytest

from mneme.benchmark import (
    BenchmarkRunner,
    Layer1Score,
    Scenario,
    ScenarioResult,
    ScenarioVerdict,
    load_scenario,
    score_layer1,
)
from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.decision_retriever import ScoredDecision
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision

FIXTURE_SCENARIO = Path(__file__).parent / "fixtures" / "benchmark_scenario"
EXAMPLE_MEMORY = Path(__file__).parent.parent / "examples" / "project_memory.json"
BENCHMARKS_DIR = Path(__file__).parent.parent / "examples" / "benchmarks"


# ── Layer 1 helpers ────────────────────────────────────────────────────────

def _decision(decision_id: str) -> Decision:
    """Minimal Decision for retrieval-only tests (fields here are unused)."""
    return Decision(id=decision_id, decision="placeholder")


def _scored(*pairs: tuple[str, float]) -> list[ScoredDecision]:
    """Build a sorted-desc list of ScoredDecision from (id, score) pairs."""
    items = [
        ScoredDecision(decision=_decision(did), score=score, matches={})
        for did, score in pairs
    ]
    items.sort(key=lambda s: s.score, reverse=True)
    return items


# ── Scenario loading ───────────────────────────────────────────────────────

def test_load_scenario_reads_all_files():
    s = load_scenario(FIXTURE_SCENARIO)
    assert isinstance(s, Scenario)
    assert "postgres" in s.query.lower()
    assert "sqlalchemy" in s.without_mneme.lower()
    assert "json" in s.with_mneme.lower()
    assert s.metadata["name"] == "test_storage_scenario"


def test_load_scenario_raises_on_missing_file(tmp_path):
    (tmp_path / "query.txt").write_text("test query")
    # without_mneme.txt is missing
    with pytest.raises(FileNotFoundError):
        load_scenario(tmp_path)


# ── ScenarioResult ─────────────────────────────────────────────────────────

def test_scenario_result_has_expected_fields():
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(FIXTURE_SCENARIO))
    assert isinstance(result, ScenarioResult)
    assert result.name == "test_storage_scenario"
    assert result.category == "architecture"
    assert isinstance(result.verdict, ScenarioVerdict)
    assert isinstance(result.baseline_violation_count, int)
    assert isinstance(result.enhanced_violation_count, int)
    assert isinstance(result.explanation, str)
    assert isinstance(result.protected_decision_ids_hit, list)


def test_pass_when_baseline_fails_and_enhanced_passes():
    """Baseline triggers violations; enhanced doesn't → PASS."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(FIXTURE_SCENARIO))
    # The fixture is designed so baseline (postgres/sqlalchemy) triggers
    # violations and enhanced (JSON-only) does not.
    assert result.baseline_violation_count >= 1
    assert result.enhanced_violation_count == 0
    assert result.verdict == ScenarioVerdict.PASS


def test_weak_when_baseline_also_clean(tmp_path):
    """If baseline has no violations either, verdict is WEAK."""
    (tmp_path / "query.txt").write_text("Should we use postgres?")
    (tmp_path / "without_mneme.txt").write_text(
        "Keep using JSON files. No databases needed."  # no violations
    )
    (tmp_path / "with_mneme.txt").write_text(
        "Keep using JSON files. No databases needed."
    )
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "weak_scenario",
        "category": "test",
        "description": "Weak — baseline already passes.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": [],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.WEAK


def test_fail_when_enhanced_still_violates(tmp_path):
    """If enhanced response still triggers violations, verdict is FAIL."""
    (tmp_path / "query.txt").write_text("Should we use postgres?")
    (tmp_path / "without_mneme.txt").write_text(
        "Use Postgres. SQLAlchemy migration is the best approach."
    )
    (tmp_path / "with_mneme.txt").write_text(
        "Still recommend Postgres for storage. Add SQLAlchemy ORM."  # still bad
    )
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "fail_scenario",
        "category": "test",
        "description": "Enhanced still violates — Mneme failed.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": [],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.FAIL


# ── Run suite ─────────────────────────────────────────────────────────────

def test_run_suite_loads_all_benchmark_scenarios():
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    results = runner.run_suite(BENCHMARKS_DIR)
    assert len(results) == 7
    names = {r.name for r in results}
    assert "storage_backend_violation" in names
    assert "retrieval_complexity_violation" in names


def test_run_suite_all_scenarios_pass():
    """All shipped benchmark scenarios should pass."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    results = runner.run_suite(BENCHMARKS_DIR)
    failures = [r for r in results if r.verdict != ScenarioVerdict.PASS]
    assert failures == [], (
        f"Expected all scenarios to PASS. Failing: "
        + ", ".join(f"{r.name}={r.verdict}" for r in failures)
    )


# ── Layer 1: score_layer1() unit tests ────────────────────────────────────

def test_layer1_recall_full_when_all_expected_in_top_k():
    """All expected IDs in top-K → recall@K = 1.0."""
    scored = _scored(("d1", 5.0), ("d2", 4.0), ("d3", 3.0))
    s = score_layer1(scored, expected_ids=["d1", "d2"], acceptable_ids=[], k=5)
    assert isinstance(s, Layer1Score)
    assert s.recall == 1.0
    assert s.retrieved_ids == ["d1", "d2", "d3"]


def test_layer1_recall_partial_when_expected_missed():
    """Expected ID outside top-K → recall < 1.0."""
    # d2 is rank 6 — outside top-5.
    scored = _scored(
        ("d1", 5.0), ("noise1", 4.0), ("noise2", 3.0),
        ("noise3", 2.0), ("noise4", 1.5), ("d2", 1.0),
    )
    s = score_layer1(scored, expected_ids=["d1", "d2"], acceptable_ids=[], k=5)
    assert s.recall == 0.5
    assert "d2" not in s.retrieved_ids


def test_layer1_recall_zero_when_no_expected_retrieved():
    """No expected IDs found at all → recall = 0.0."""
    scored = _scored(("noise1", 5.0), ("noise2", 4.0))
    s = score_layer1(scored, expected_ids=["d1"], acceptable_ids=[], k=5)
    assert s.recall == 0.0


def test_layer1_recall_vacuous_one_when_no_expected():
    """Control scenario (empty expected_ids) → recall vacuous-true 1.0."""
    scored = _scored(("noise", 5.0))
    s = score_layer1(scored, expected_ids=[], acceptable_ids=[], k=5)
    assert s.recall == 1.0


def test_layer1_precision_with_extra_irrelevant_retrieved():
    """Extra non-expected IDs lower precision proportionally."""
    # 1 expected (d1) + 3 noise in top-4 → precision 1/4.
    scored = _scored(
        ("d1", 5.0), ("noise1", 4.0), ("noise2", 3.0), ("noise3", 2.0),
    )
    s = score_layer1(scored, expected_ids=["d1"], acceptable_ids=[], k=5)
    assert s.precision == 0.25


def test_layer1_precision_with_acceptable_ids():
    """acceptable_decision_ids count toward precision and suppress injection."""
    scored = _scored(
        ("d1", 5.0), ("ok1", 4.0), ("ok2", 3.0), ("noise", 2.0),
    )
    s = score_layer1(
        scored,
        expected_ids=["d1"],
        acceptable_ids=["ok1", "ok2"],
        k=5,
    )
    # 3 of 4 retrieved are in (expected ∪ acceptable).
    assert s.precision == 0.75


def test_layer1_irrelevant_injection_flips_with_noise():
    """At least one retrieved ID outside relevant set → irrelevant_injection True."""
    scored = _scored(("d1", 5.0), ("noise", 4.0))
    s = score_layer1(scored, expected_ids=["d1"], acceptable_ids=[], k=5)
    assert s.irrelevant_injection is True


def test_layer1_irrelevant_injection_suppressed_by_acceptable():
    """Adding the noisy ID to acceptable_decision_ids suppresses the flag."""
    scored = _scored(("d1", 5.0), ("noise", 4.0))
    s = score_layer1(
        scored,
        expected_ids=["d1"],
        acceptable_ids=["noise"],
        k=5,
    )
    assert s.irrelevant_injection is False


def test_layer1_irrelevant_injection_false_when_only_expected_retrieved():
    """All retrieved are expected → no irrelevant injection."""
    scored = _scored(("d1", 5.0), ("d2", 4.0))
    s = score_layer1(scored, expected_ids=["d1", "d2"], acceptable_ids=[], k=5)
    assert s.irrelevant_injection is False


def test_layer1_excludes_zero_score_decisions():
    """Zero-score (or negative) decisions never count as retrieved.

    Mirrors enforcer._top_nonzero so Layer 1 retrieval matches what the
    enforcer actually sees.
    """
    scored = _scored(("d1", 5.0), ("zero", 0.0), ("d2", 0.0))
    s = score_layer1(scored, expected_ids=["d1", "d2"], acceptable_ids=[], k=5)
    assert s.retrieved_ids == ["d1"]
    assert s.recall == 0.5
    assert s.precision == 1.0


def test_layer1_top_k_truncation():
    """Only the top K are scored, even when more positive-score decisions exist."""
    scored = _scored(*[(f"d{i}", 10.0 - i) for i in range(8)])
    s = score_layer1(scored, expected_ids=["d6"], acceptable_ids=[], k=3)
    assert s.retrieved_ids == ["d0", "d1", "d2"]
    assert s.recall == 0.0  # d6 outside top-3


def test_layer1_precision_vacuous_one_when_nothing_retrieved():
    """No decisions retrieved → precision vacuously 1.0 (no false injections)."""
    s = score_layer1([], expected_ids=["d1"], acceptable_ids=[], k=5)
    assert s.precision == 1.0
    assert s.recall == 0.0
    assert s.irrelevant_injection is False


# ── Layer 1: integration through BenchmarkRunner ───────────────────────────

def test_runner_records_layer1_on_result():
    """The runner attaches Layer 1 metrics to every ScenarioResult."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(FIXTURE_SCENARIO))
    assert result.layer1_k == DEFAULT_MAX_DECISIONS
    assert result.layer1_expected_ids == ["mneme_storage_json"]
    assert "mneme_storage_json" in result.layer1_retrieved_ids
    assert result.layer1_recall == 1.0
    assert 0.0 <= result.layer1_precision <= 1.0


def test_runner_weak_retrieval_when_layer1_recall_incomplete(tmp_path):
    """If retrieval misses an expected ID, verdict is WEAK_RETRIEVAL."""
    (tmp_path / "query.txt").write_text("Should we use postgres?")
    (tmp_path / "without_mneme.txt").write_text(
        "Use Postgres. SQLAlchemy migration is the best approach."
    )
    (tmp_path / "with_mneme.txt").write_text(
        "Keep using JSON files. No databases."
    )
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "missing_id_scenario",
        "category": "test",
        "description": "Expects an ID that does not exist in memory.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["nonexistent_decision_id"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.WEAK_RETRIEVAL
    assert result.layer1_recall == 0.0
    assert "nonexistent_decision_id" in result.layer1_expected_ids


def test_runner_existing_fixtures_still_pass():
    """Regression guard: layered scoring must not change the shipped verdicts."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    results = runner.run_suite(BENCHMARKS_DIR)
    # All shipped scenarios must PASS.
    assert len(results) == 7
    assert all(r.verdict == ScenarioVerdict.PASS for r in results), (
        "Layer 1 introduction changed an existing verdict: "
        + ", ".join(f"{r.name}={r.verdict}" for r in results)
    )
    # Each scenario that declares expected protected IDs must achieve
    # recall = 1.0 (the PASS verdict already proves the expected ID was
    # retrieved). Scenarios with empty expected_protected_decision_ids
    # are excluded — vacuous-true recall would mask a real regression.
    for r in results:
        if not r.layer1_expected_ids:
            continue
        assert r.layer1_recall == 1.0, (
            f"{r.name} recall@{r.layer1_k}={r.layer1_recall}, expected 1.0"
        )


def test_runner_acceptable_decision_ids_field_is_picked_up(tmp_path):
    """The optional acceptable_decision_ids field flows into Layer 1."""
    (tmp_path / "query.txt").write_text("Pick a storage backend")
    (tmp_path / "without_mneme.txt").write_text(
        "Use Postgres with SQLAlchemy."
    )
    (tmp_path / "with_mneme.txt").write_text(
        "Use JSON file storage."
    )
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "acceptable_ids_scenario",
        "category": "architecture",
        "description": "Declares an acceptable id alongside the expected one.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
        "acceptable_decision_ids": ["mneme_retrieval_deterministic"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.layer1_acceptable_ids == ["mneme_retrieval_deterministic"]


# ── v1.1 Step 2: structured-output protocol coexistence ───────────────────

def _write_minimal_txt_pair(tmp_path):
    """Write a minimal valid query.txt + with/without_mneme.txt + scenario.json.

    Used as scaffolding so each Step 2 integration test only needs to drop
    the .json files (and assertions) it cares about.
    """
    (tmp_path / "query.txt").write_text("Should we use postgres?")
    (tmp_path / "without_mneme.txt").write_text(
        "Use Postgres. SQLAlchemy migration is the best approach."
    )
    (tmp_path / "with_mneme.txt").write_text(
        "Keep using JSON files. No databases."
    )


def test_runner_falls_back_to_txt_when_no_json_present(tmp_path):
    """Missing .json siblings silently fall back to TXT — no MALFORMED."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "txt_only_scenario",
        "category": "architecture",
        "description": "Pure TXT path — no structured siblings.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    # TXT keyword path catches "sqlalchemy" / "migration" via the
    # mneme_storage_json anti_patterns.
    assert result.verdict == ScenarioVerdict.PASS
    assert result.baseline_violation_count >= 1


def test_runner_mixed_txt_baseline_json_enhanced_coexists(tmp_path):
    """One side TXT, the other side structured (refused=true) — both valid."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "with_mneme.json").write_text(json.dumps({
        "refused": True,
        "files_changed": [],
        "dependencies_added": [],
    }))
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "mixed_scenario",
        "category": "architecture",
        "description": "Baseline TXT, enhanced JSON+refused.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
        "assertions": [
            {"type": "forbidden_dependency", "value": "sqlalchemy"},
        ],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    # Baseline (TXT) triggers; enhanced (JSON refused) is short-circuit PASS.
    assert result.verdict == ScenarioVerdict.PASS
    assert result.baseline_violation_count >= 1
    assert result.enhanced_violation_count == 0


def test_runner_returns_malformed_on_invalid_json(tmp_path):
    """An existing-but-broken with_mneme.json => ScenarioVerdict.MALFORMED."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "with_mneme.json").write_text("{not valid json}")
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "malformed_scenario",
        "category": "architecture",
        "description": "Broken JSON in with_mneme.json.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.MALFORMED
    assert "with_mneme.json" in result.explanation


def test_runner_storage_backend_uses_structured_path():
    """The migrated fixture must run through the structured Layer 2 path
    and produce baseline triggers from forbidden_dependency / forbidden_path
    matches (not from keyword enforcement).
    """
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "storage_backend_violation"
    scenario = load_scenario(fixture)
    # Structured fixtures present → load_scenario populates them.
    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions, "scenario.json must declare assertions"

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    # Triggers come from the asserted dep/path values, not enforcer keywords.
    joined = " ".join(result.baseline_triggers).lower()
    assert "sqlalchemy" in joined or "alembic" in joined or "migrations/" in joined


def test_runner_framework_abstraction_uses_structured_path():
    """framework_abstraction_violation runs through structured Layer 2 path."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "framework_abstraction_violation"
    scenario = load_scenario(fixture)
    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions, "scenario.json must declare assertions"

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    joined = " ".join(result.baseline_triggers).lower()
    assert "langchain-anthropic" in joined or "src/chains/" in joined


def test_runner_retrieval_complexity_uses_structured_path():
    """retrieval_complexity_violation runs through structured Layer 2 path."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "retrieval_complexity_violation"
    scenario = load_scenario(fixture)
    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions, "scenario.json must declare assertions"

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    joined = " ".join(result.baseline_triggers).lower()
    assert (
        "sentence-transformers" in joined
        or "chromadb" in joined
        or "embeddings/" in joined
        or "vector_store/" in joined
    )


def test_runner_feature_boundary_uses_structured_path():
    """feature_boundary_violation runs through structured Layer 2 path."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "feature_boundary_violation"
    scenario = load_scenario(fixture)
    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions, "scenario.json must declare assertions"

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    joined = " ".join(result.baseline_triggers).lower()
    assert (
        "autogen" in joined
        or "crewai" in joined
        or "agents/" in joined
        or "coordinator" in joined
    )


def test_runner_infra_scope_creep_uses_structured_path():
    """infra_scope_creep_violation runs through structured Layer 2 path."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "infra_scope_creep_violation"
    scenario = load_scenario(fixture)
    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions, "scenario.json must declare assertions"

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    joined = " ".join(result.baseline_triggers).lower()
    assert (
        "redis" in joined
        or "celery" in joined
        or "agents/" in joined
        or "orchestration/" in joined
    )


def test_pydantic_dependency_creep_uses_structured_path():
    """pydantic_dependency_creep runs through the structured Layer 2 path —
    triggers come from forbidden_dependency on `pydantic`, not from TXT
    keyword fallback."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "pydantic_dependency_creep"
    scenario = load_scenario(fixture)

    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    joined = " ".join(result.baseline_triggers).lower()
    # 'pydantic' is the only structured trigger; the TXT path on this fixture's
    # without_mneme.txt would also produce keyword matches on 'pydantic', so
    # also assert on the structured-only path entry.
    assert "pydantic" in joined
    assert "mneme/schemas.py" in joined


def test_openai_provider_violation_uses_structured_path():
    """openai_provider_violation runs through the structured Layer 2 path —
    triggers come from forbidden_dependency / forbidden_path_pattern, not from
    TXT keyword fallback."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "openai_provider_violation"
    scenario = load_scenario(fixture)

    assert scenario.with_mneme_structured is not None
    assert scenario.with_mneme_structured.refused is True
    assert scenario.without_mneme_structured is not None
    assert scenario.without_mneme_structured.refused is False
    assert scenario.assertions

    result = runner.run_scenario(scenario)
    assert result.verdict == ScenarioVerdict.PASS
    joined = " ".join(result.baseline_triggers).lower()
    # The structured-only file path is the strict signal; bare 'openai' would
    # also be produced by the TXT keyword path.
    assert "mneme/providers/openai" in joined


# ── Group A: parser-trivia MALFORMED coverage ─────────────────────────────


def test_runner_returns_malformed_on_invalid_without_mneme_json(tmp_path):
    """Broken JSON in without_mneme.json => MALFORMED, explanation names file."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "without_mneme.json").write_text("{not valid json}")
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "malformed_baseline",
        "category": "architecture",
        "description": "Broken JSON in without_mneme.json.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.MALFORMED
    assert "without_mneme.json" in result.explanation


def test_runner_malformed_on_type_mismatch_refused_not_bool(tmp_path):
    """refused: 'no' (string, not bool) => MALFORMED."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "with_mneme.json").write_text(
        '{"refused": "no", "files_changed": [], "dependencies_added": []}'
    )
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "type_mismatch_refused",
        "category": "architecture",
        "description": "refused must be bool.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.MALFORMED
    assert "refused" in result.explanation


def test_runner_malformed_on_assertions_not_a_list(tmp_path):
    """scenario.json assertions: a dict (not a list) => MALFORMED."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "assertions_not_list",
        "category": "architecture",
        "description": "assertions must be a list.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
        "assertions": {"type": "forbidden_dependency", "value": "sqlalchemy"},
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.MALFORMED
    assert "assertions" in result.explanation


def test_runner_malformed_on_unknown_assertion_type_via_fixture(tmp_path):
    """An unknown assertion type at scenario level => MALFORMED with index."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "unknown_assertion_type",
        "category": "architecture",
        "description": "forbidden_function is not a known assertion type.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
        "assertions": [
            {"type": "forbidden_function", "value": "create_engine"},
        ],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.MALFORMED
    assert "assertions[0]" in result.explanation


def test_runner_malformed_concatenates_both_sides(tmp_path):
    """Both sides broken => explanation lists both filenames separated by '; '."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "with_mneme.json").write_text("{not json}")
    (tmp_path / "without_mneme.json").write_text("{also not json}")
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "both_sides_malformed",
        "category": "architecture",
        "description": "Both sides have broken JSON.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(tmp_path))
    assert result.verdict == ScenarioVerdict.MALFORMED
    assert "with_mneme.json" in result.explanation
    assert "without_mneme.json" in result.explanation
    assert "; " in result.explanation


# ── Group B: governance-integrity adversarial coverage ────────────────────


def test_layer1_irrelevant_injection_stress_at_default_k():
    """At K=DEFAULT_MAX_DECISIONS, K-1 irrelevant retrievals drop precision to
    1/K, recall stays 1.0, and the irrelevant_injection flag fires.

    Stress shape: one expected ID at top score, K-1 noise IDs in the next
    slots, one further expected ID just below K (proving the K cutoff is
    enforced and outside-K relevant decisions don't rescue precision)."""
    scored = _scored(
        ("d1", 5.0),         # expected, in top-K
        ("noise1", 4.0),
        ("noise2", 3.0),     # K=3 cutoff falls here
        ("d2_offcut", 2.0),  # expected but outside top-K
    )
    s = score_layer1(
        scored,
        expected_ids=["d1", "d2_offcut"],
        acceptable_ids=[],
        k=DEFAULT_MAX_DECISIONS,
    )
    assert s.k == DEFAULT_MAX_DECISIONS == 3
    assert s.retrieved_ids == ["d1", "noise1", "noise2"]
    assert s.recall == 0.5  # 1 of 2 expected made the cut
    assert abs(s.precision - (1 / DEFAULT_MAX_DECISIONS)) < 1e-9
    assert s.irrelevant_injection is True


def test_layer1_handles_empty_id_decision_robustly():
    """Documents one corruption mode (empty Decision.id) of the broader
    "partial retrieval corruption" category: an empty id is treated as a
    distinct hashable key by the seen-set, included in retrieved_ids, and
    counted toward irrelevant_injection if not expected. score_layer1 makes
    no well-formedness assumptions about Decision.id beyond hashability.
    Other corruption modes (None decision, invalid scoring) are not
    covered here."""
    valid = _decision("d1")
    corrupted = _decision("")
    scored = [
        ScoredDecision(decision=valid, score=5.0, matches={}),
        ScoredDecision(decision=corrupted, score=4.0, matches={}),
    ]
    s = score_layer1(
        scored, expected_ids=["d1"], acceptable_ids=[], k=DEFAULT_MAX_DECISIONS,
    )
    assert "d1" in s.retrieved_ids
    assert "" in s.retrieved_ids
    assert s.recall == 1.0
    assert s.irrelevant_injection is True  # empty id is not in expected ∪ acceptable


def test_layer1_dedups_decisions_with_duplicate_ids_first_seen_wins():
    """When the same id appears multiple times with different scores, the
    higher-score occurrence is retained (it appears first in the sorted-desc
    list passed by the runner). Documents the seen-set dedup behavior in
    score_layer1. Tied-score dedup is not exercised here — input order
    would tie-break, which is non-deterministic across retrievers."""
    scored = _scored(
        ("d1", 5.0),  # higher-score d1, retained
        ("d1", 4.0),  # duplicate id, dropped
        ("d2", 3.0),
    )
    s = score_layer1(
        scored, expected_ids=["d1", "d2"], acceptable_ids=[],
        k=DEFAULT_MAX_DECISIONS,
    )
    assert s.retrieved_ids == ["d1", "d2"]
    assert len(s.retrieved_ids) == 2
    assert s.recall == 1.0
    assert s.precision == 1.0


def test_runner_handles_contradictory_decisions_in_retrieval(tmp_path):
    """When memory contains two decisions with overlapping scope and
    conflicting anti_patterns, the runner surfaces BOTH in retrieved_ids
    and lets the scenario's own assertions drive the Layer 2 verdict.

    Governance-integrity property: the runner does NOT silently drop one
    decision to resolve the contradiction — that is an ADR-precedence
    concern, intentionally deferred per the v1.1 methodology. The runner
    is faithful to what was retrieved."""
    memory_data = {
        "meta": {
            "name": "contradictory-memory", "description": "test",
            "version": "0.1.0", "owner": "test", "created": "2026-05-09",
        },
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": "policy_json_only",
                "decision": "Use JSON storage only",
                "rationale": "Local-first, zero-setup install.",
                "scope": ["storage", "backend"],
                "constraints": ["no postgres"],
                "anti_patterns": ["sqlalchemy", "alembic"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
            {
                "id": "policy_postgres_required",
                "decision": "Use Postgres storage",
                "rationale": "Relational integrity and transactions.",
                "scope": ["storage", "backend"],
                "constraints": ["no json file storage"],
                "anti_patterns": ["json file storage", "flat file"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
        ],
    }
    memory_file = tmp_path / "contradictory_memory.json"
    memory_file.write_text(json.dumps(memory_data))

    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    (fixture_dir / "query.txt").write_text(
        "How should we handle storage backend persistence?"
    )
    (fixture_dir / "without_mneme.txt").write_text(
        "Use Postgres with SQLAlchemy."
    )
    (fixture_dir / "with_mneme.txt").write_text(
        "Two contradicting policies retrieved; deferring."
    )
    (fixture_dir / "scenario.json").write_text(json.dumps({
        "name": "contradictory_scenario",
        "category": "architecture",
        "description": "Memory has contradictory storage decisions.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": [
            "policy_json_only", "policy_postgres_required",
        ],
    }))

    store = MemoryStore(memory_file)
    store.load()
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(fixture_dir))

    # BOTH contradictory decisions are retrieved — runner does not pick a winner.
    assert "policy_json_only" in result.layer1_retrieved_ids
    assert "policy_postgres_required" in result.layer1_retrieved_ids
    # Recall is 1.0 because both expected IDs are retrieved.
    assert result.layer1_recall == 1.0
    # Verdict resolves deterministically: without_mneme.txt ("Use Postgres
    # with SQLAlchemy") matches anti_patterns of both retrieved decisions
    # (sqlalchemy and postgres), so baseline_count >= 1. with_mneme.txt
    # ("Two contradicting policies retrieved; deferring") trips no
    # forbidden term, so enhanced_count == 0. Both expected ids retrieved
    # → PASS. The governance-integrity property is that the runner
    # surfaces both contradictory decisions for operator review without
    # silently picking one.
    assert result.verdict == ScenarioVerdict.PASS


def test_runner_dedups_decisions_with_duplicate_ids_via_memory_file(tmp_path):
    """MemoryStore.load() preserves duplicate-id decisions in the
    decisions[] array (no load-time uniqueness check). The runner's
    score_layer1 dedups via its seen-set, so the retrieved_ids list never
    contains duplicates regardless of upstream input quality.

    Governance-integrity property: a buggy or merged memory file with
    duplicate decision IDs does not produce inflated retrieval counts."""
    memory_data = {
        "meta": {
            "name": "duplicate-id-memory", "description": "test",
            "version": "0.1.0", "owner": "test", "created": "2026-05-09",
        },
        "items": [], "examples": [],
        "decisions": [
            {
                "id": "dupe_id", "decision": "First copy",
                "scope": ["storage"], "constraints": [],
                "anti_patterns": ["postgres"],
                "created_at": "", "updated_at": "",
            },
            {
                "id": "dupe_id", "decision": "Second copy with different content",
                "scope": ["storage"], "constraints": [],
                "anti_patterns": ["sqlalchemy"],
                "created_at": "", "updated_at": "",
            },
        ],
    }
    memory_file = tmp_path / "dupe_memory.json"
    memory_file.write_text(json.dumps(memory_data))

    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    (fixture_dir / "query.txt").write_text("How should we handle storage backend?")
    (fixture_dir / "without_mneme.txt").write_text("Use Postgres with SQLAlchemy.")
    (fixture_dir / "with_mneme.txt").write_text("Use JSON storage only.")
    (fixture_dir / "scenario.json").write_text(json.dumps({
        "name": "duplicate_id_scenario",
        "category": "architecture",
        "description": "Memory has two decisions sharing the same id.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["dupe_id"],
    }))

    store = MemoryStore(memory_file)
    store.load()
    # MemoryStore is honest about what it loaded.
    assert len(store.decisions()) == 2
    runner = BenchmarkRunner(store)
    result = runner.run_scenario(load_scenario(fixture_dir))

    # Despite two decisions with id="dupe_id" in memory, retrieved_ids
    # contains "dupe_id" exactly once.
    assert result.layer1_retrieved_ids.count("dupe_id") == 1
    assert result.layer1_recall == 1.0


# ── Task 4: TXT-fallback warning ──────────────────────────────────────────


def test_load_scenario_warns_when_txt_only_no_json_siblings(tmp_path):
    """When a scenario has TXT but no JSON siblings, a UserWarning is
    emitted once per missing side. Behaviour is otherwise identical:
    scenario still loads, no MALFORMED, TXT keyword path still drives
    Layer 2."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "txt_only_warning",
        "category": "architecture",
        "description": "TXT only — should produce a UserWarning per side.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scenario = load_scenario(tmp_path)
    msgs = [str(w.message) for w in caught
            if issubclass(w.category, UserWarning)]
    assert any("with_mneme.json" in m for m in msgs), (
        f"Expected with_mneme.json warning; got: {msgs}"
    )
    assert any("without_mneme.json" in m for m in msgs), (
        f"Expected without_mneme.json warning; got: {msgs}"
    )
    # Behaviour preserved: structured payloads None, malformed_reason empty.
    assert scenario.malformed_reason == ""
    assert scenario.with_mneme_structured is None
    assert scenario.without_mneme_structured is None


def test_load_scenario_no_warning_when_both_json_present(tmp_path):
    """When both JSON siblings exist and parse, no UserWarning is emitted."""
    _write_minimal_txt_pair(tmp_path)
    (tmp_path / "with_mneme.json").write_text(json.dumps({
        "refused": True, "files_changed": [], "dependencies_added": [],
    }))
    (tmp_path / "without_mneme.json").write_text(json.dumps({
        "refused": False,
        "files_changed": ["alembic/env.py"],
        "dependencies_added": ["sqlalchemy"],
    }))
    (tmp_path / "scenario.json").write_text(json.dumps({
        "name": "both_json_no_warning",
        "category": "architecture",
        "description": "Both JSON sides present — no warning.",
        "expected_failure_terms": ["postgres"],
        "expected_protected_decision_ids": ["mneme_storage_json"],
    }))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_scenario(tmp_path)
    user_warnings = [w for w in caught
                     if issubclass(w.category, UserWarning)]
    assert user_warnings == [], (
        f"Expected no UserWarning; got {[str(w.message) for w in user_warnings]}"
    )


def test_feature_boundary_violation_retrieves_anti_002_at_rank_1():
    """Step 3C Stage 1 regression: with anti_pattern.content migrated into
    `constraints` (1.5x weight) instead of `rationale` (0.5x weight), the
    feature_boundary_violation scenario must retrieve anti-002 ("Do not
    add agentic loops in v1") at rank 1 — its content includes "tool-use,
    function calling, multi-turn agent loops" which directly answers the
    "Should we add multi-agent support" query.

    Before the fix anti-002 ranked behind mneme_no_agents_v1 because its
    content lived only in rationale. Locking rank 1 here prevents silent
    re-introduction of the migration asymmetry."""
    store = MemoryStore(EXAMPLE_MEMORY); store.load()
    runner = BenchmarkRunner(store)
    fixture = BENCHMARKS_DIR / "feature_boundary_violation"
    result = runner.run_scenario(load_scenario(fixture))
    assert result.layer1_retrieved_ids[0] == "anti-002", (
        f"Expected anti-002 at rank 1 after Stage 1 migration symmetry fix; "
        f"got retrieved_ids={result.layer1_retrieved_ids}"
    )


def test_run_suite_on_shipped_fixtures_emits_no_warnings():
    """Regression guard: every shipped fixture now has both JSON siblings,
    so a clean suite run must emit no UserWarning. If this fires, someone
    removed a JSON sibling from an examples/benchmarks/ fixture."""
    store = MemoryStore(EXAMPLE_MEMORY); store.load()
    runner = BenchmarkRunner(store)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        runner.run_suite(BENCHMARKS_DIR)
    txt_fallback = [
        w for w in caught
        if issubclass(w.category, UserWarning)
        and ("with_mneme.json" in str(w.message)
             or "without_mneme.json" in str(w.message))
    ]
    assert txt_fallback == [], (
        f"Shipped fixtures should not trigger TXT-fallback warnings. "
        f"Got: {[str(w.message) for w in txt_fallback]}"
    )

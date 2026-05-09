"""Tests for BenchmarkRunner — scenario loading and PASS/FAIL/WEAK verdicts."""
import json
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
    assert len(results) == 5
    names = {r.name for r in results}
    assert "storage_backend_violation" in names
    assert "retrieval_complexity_violation" in names


def test_run_suite_all_scenarios_pass():
    """All 5 shipped benchmark scenarios should pass."""
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


def test_runner_existing_5_fixtures_still_pass():
    """Regression guard: layered scoring must not change the 5 v1.0 verdicts."""
    store = MemoryStore(EXAMPLE_MEMORY)
    store.load()
    runner = BenchmarkRunner(store)
    results = runner.run_suite(BENCHMARKS_DIR)
    # Same shape as before: 5 scenarios, all PASS.
    assert len(results) == 5
    assert all(r.verdict == ScenarioVerdict.PASS for r in results), (
        "Layer 1 introduction changed an existing verdict: "
        + ", ".join(f"{r.name}={r.verdict}" for r in results)
    )
    # All 5 declare expected protected IDs; recall should be 1.0 for each
    # (the v1.0 PASS already proved the expected ID was retrieved).
    for r in results:
        assert r.layer1_expected_ids, f"{r.name} missing layer1_expected_ids"
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
    assert "langchain" in joined or "chains/" in joined


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

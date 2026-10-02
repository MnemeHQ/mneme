"""
tests.open_architecture.test_gds_calibration_experiment — Tests for O1A Stage C GDS Calibration.

Validates:
1. Edge contracts for selection policy:
   - empty scored input -> ()
   - top_score <= 0 -> ()
   - exact 80% boundary inclusion (with 1e-9 epsilon)
   - positive-score requirement (score > 0)
   - existing equal-score order preservation (no secondary keys, no decision.id sorting)
   - DecisionRetriever fallback-score behavior
   - unknown policy fails closed
   - duplicate-ID behavior matches upstream sequence (no internal deduplication)
2. Query transformation contracts:
   - only registered structural prefixes are stripped
   - prefix values remain
   - prose lines remain
   - only the five frozen function words are suppressed
   - B3 transformation is deterministic
3. Acceptance gates:
   - Gate 1: B0 reproduces F1 0.103728 ± 1e-4, FPs 930, FNs 0
   - Gate 2: C-T1A reproduces F1 0.621159 ± 1e-4, FPs 69, FNs 11
   - Gate 3: B3 reproduces F1 0.711095 ± 1e-4, FPs <= 45
   - Gate 4: B3 recall >= 0.84, FNs <= 10
   - Gate 5: B3 exact governing-set matches == 26
   - Gate 6: Artifact determinism (two executions emit byte-identical summary JSON)
   - Gate 7: Output directory exists and non-empty fails closed
   - Gate 8: Profile hash determinism and validation
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.open_architecture.gds_calibration_experiment import (
    EVALUATED_POLICIES,
    EVALUATED_PROFILES,
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_FUNCTION_WORDS,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_PARENT_MAIN_SHA,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_SCENARIO_CORPUS_HASH,
    FROZEN_STRUCTURAL_PREFIXES,
    POLICY_RELATIVE_80,
    POLICY_SCORE_GT_ZERO,
    PROFILE_B0,
    PROFILE_B3,
    PROFILE_C_T1A,
    RELATIVE_THRESHOLD_RATIO,
    SELECTION_EPSILON,
    GDSCalibrationExperimentResult,
    compute_experiment_profile_hash,
    execute_gds_calibration_experiment,
    select_decisions_for_policy,
    suppress_structural_labels,
    transform_query_for_b3,
)
from mneme.open_architecture.harness import (
    APPROVED_BATCH_01_REPOSITORIES,
    HarnessPreflightError,
)
from mneme.schemas import Decision


def _make_dummy_decision(decision_id: str, statement: str = "Test decision") -> Decision:
    return Decision(
        id=decision_id,
        decision=statement,
        rationale="Rationale",
        scope=["general"],
    )


# ── Edge Contract Tests ────────────────────────────────────────────────────────


class TestSelectionPolicyEdgeContracts:
    def test_empty_scored_input_returns_empty_tuple(self):
        assert select_decisions_for_policy([], POLICY_SCORE_GT_ZERO) == ()
        assert select_decisions_for_policy([], POLICY_RELATIVE_80) == ()

    def test_top_score_zero_returns_empty_tuple(self):
        d1 = _make_dummy_decision("ref-1")
        d2 = _make_dummy_decision("ref-2")
        scored = [
            ScoredDecision(decision=d1, score=0.0),
            ScoredDecision(decision=d2, score=0.0),
        ]
        assert select_decisions_for_policy(scored, POLICY_SCORE_GT_ZERO) == ()
        assert select_decisions_for_policy(scored, POLICY_RELATIVE_80) == ()

    def test_top_score_negative_returns_empty_tuple(self):
        d1 = _make_dummy_decision("ref-1")
        scored = [ScoredDecision(decision=d1, score=-1.5)]
        assert select_decisions_for_policy(scored, POLICY_SCORE_GT_ZERO) == ()
        assert select_decisions_for_policy(scored, POLICY_RELATIVE_80) == ()

    def test_exact_80_percent_boundary_inclusion_with_epsilon(self):
        # 10.0 * 0.80 = 8.0. An item scoring exactly 8.0 must be included.
        d1 = _make_dummy_decision("ref-top")
        d2 = _make_dummy_decision("ref-boundary")
        d3 = _make_dummy_decision("ref-below")
        scored = [
            ScoredDecision(decision=d1, score=10.0),
            ScoredDecision(decision=d2, score=8.0),
            ScoredDecision(decision=d3, score=7.999),
        ]
        selected = select_decisions_for_policy(scored, POLICY_RELATIVE_80)
        assert selected == ("ref-top", "ref-boundary")

    def test_epsilon_boundary_protection(self):
        # Test float arithmetic slight imprecision where 8.0 - 1e-9 ensures inclusion
        top = 10.0
        boundary = top * RELATIVE_THRESHOLD_RATIO
        d1 = _make_dummy_decision("ref-1")
        d2 = _make_dummy_decision("ref-2")
        scored = [
            ScoredDecision(decision=d1, score=top),
            ScoredDecision(decision=d2, score=boundary),
        ]
        selected = select_decisions_for_policy(scored, POLICY_RELATIVE_80)
        assert selected == ("ref-1", "ref-2")

    def test_positive_score_requirement(self):
        # In a degenerate case where top_score is positive but some items are <= 0
        d1 = _make_dummy_decision("ref-pos")
        d2 = _make_dummy_decision("ref-zero")
        scored = [
            ScoredDecision(decision=d1, score=1.0),
            ScoredDecision(decision=d2, score=0.0),
        ]
        assert select_decisions_for_policy(scored, POLICY_SCORE_GT_ZERO) == ("ref-pos",)
        assert select_decisions_for_policy(scored, POLICY_RELATIVE_80) == ("ref-pos",)

    def test_equal_score_order_preservation(self):
        # Verify that incoming order is preserved without decision.id sorting
        d_z = _make_dummy_decision("ref-z")
        d_a = _make_dummy_decision("ref-a")
        d_m = _make_dummy_decision("ref-m")
        scored = [
            ScoredDecision(decision=d_z, score=5.0),
            ScoredDecision(decision=d_a, score=5.0),
            ScoredDecision(decision=d_m, score=5.0),
        ]
        # Must retain ["ref-z", "ref-a", "ref-m"], NOT alphabetical ["ref-a", "ref-m", "ref-z"]
        assert select_decisions_for_policy(scored, POLICY_RELATIVE_80) == ("ref-z", "ref-a", "ref-m")
        assert select_decisions_for_policy(scored, POLICY_SCORE_GT_ZERO) == ("ref-z", "ref-a", "ref-m")

    def test_decision_retriever_fallback_scores_behavior(self):
        # Empty token query gives all decisions fallback score 1.0
        d1 = _make_dummy_decision("ref-1")
        d2 = _make_dummy_decision("ref-2")
        retriever = DecisionRetriever([d1, d2])
        scored = retriever.retrieve("   ")  # tokenizes to empty set
        assert all(s.score == 1.0 for s in scored)

        # Under relative_80: top is 1.0, threshold is 0.80. All 1.0 items are selected.
        selected_rel80 = select_decisions_for_policy(scored, POLICY_RELATIVE_80)
        assert selected_rel80 == ("ref-1", "ref-2")

        # Under score_gt_zero: all 1.0 items are selected.
        selected_gt0 = select_decisions_for_policy(scored, POLICY_SCORE_GT_ZERO)
        assert selected_gt0 == ("ref-1", "ref-2")

    def test_unknown_policy_fails_closed(self):
        d1 = _make_dummy_decision("ref-1")
        scored = [ScoredDecision(decision=d1, score=5.0)]
        with pytest.raises(ValueError, match="Unknown selection policy"):
            select_decisions_for_policy(scored, "unknown_policy")

    def test_duplicate_id_preserves_upstream_sequence(self):
        # Selection does not deduplicate; it maps exactly to the incoming sequence
        d1 = _make_dummy_decision("ref-dup")
        d2 = _make_dummy_decision("ref-dup")
        scored = [
            ScoredDecision(decision=d1, score=10.0),
            ScoredDecision(decision=d2, score=10.0),
        ]
        assert select_decisions_for_policy(scored, POLICY_RELATIVE_80) == ("ref-dup", "ref-dup")


# ── Query Transformation Tests ─────────────────────────────────────────────────


class TestQueryTransformation:
    def test_only_registered_prefixes_stripped(self):
        raw_query = (
            "Verify database connection pooling.\n"
            "path: src/storage/db.py\n"
            "component: storage\n"
            "change_type: refactor\n"
            "dependencies: psycopg2, sqlalchemy\n"
            "api: storage_v1\n"
            "technology: postgres\n"
            "unregistered_prefix: keep this prefix\n"
            "General context without prefix"
        )
        suppressed = suppress_structural_labels(raw_query)
        lines = suppressed.splitlines()

        assert lines[0] == "Verify database connection pooling."
        assert lines[1] == "src/storage/db.py"
        assert lines[2] == "storage"
        assert lines[3] == "refactor"
        assert lines[4] == "psycopg2, sqlalchemy"
        assert lines[5] == "storage_v1"
        assert lines[6] == "postgres"
        assert lines[7] == "unregistered_prefix: keep this prefix"
        assert lines[8] == "General context without prefix"

    def test_registered_prefixes_constants(self):
        assert set(FROZEN_STRUCTURAL_PREFIXES) == {
            "path: ",
            "component: ",
            "change_type: ",
            "dependencies: ",
            "api: ",
            "technology: ",
        }

    def test_frozen_function_words_constants(self):
        assert FROZEN_FUNCTION_WORDS == frozenset({
            "from",
            "that",
            "when",
            "with",
            "without",
        })

    def test_b3_function_word_suppression(self):
        raw_query = "Read data from cache when available with fallback that fails without error."
        transformed = transform_query_for_b3(raw_query)

        # Verify function words are stripped as whole words
        assert "from" not in transformed.lower().split()
        assert "that" not in transformed.lower().split()
        assert "when" not in transformed.lower().split()
        assert "with" not in transformed.lower().split()
        assert "without" not in transformed.lower().split()

        # Non-function words must be preserved
        assert "read" in transformed.lower()
        assert "data" in transformed.lower()
        assert "cache" in transformed.lower()
        assert "available" in transformed.lower()
        assert "fallback" in transformed.lower()
        assert "fails" in transformed.lower()
        assert "error" in transformed.lower()

    def test_b3_transformation_determinism(self):
        raw = "path: foo/bar\ncomponent: bar\nQuery with and without data from cache."
        t1 = transform_query_for_b3(raw)
        t2 = transform_query_for_b3(raw)
        assert t1 == t2


# ── Full Experiment Acceptance Gates ───────────────────────────────────────────


@pytest.fixture(scope="module")
def experiment_result() -> GDSCalibrationExperimentResult:
    return execute_gds_calibration_experiment()


class TestGDSCalibrationExperimentGates:
    def test_experiment_metadata(self, experiment_result: GDSCalibrationExperimentResult):
        assert experiment_result.experiment_id == "o1a-c-gds-calibration"
        assert experiment_result.baseline_id == FROZEN_BASELINE_ID
        assert experiment_result.parent_main_sha == FROZEN_PARENT_MAIN_SHA
        assert experiment_result.reference_corpus_hash == FROZEN_REFERENCE_CORPUS_HASH
        assert experiment_result.scenario_corpus_hash == FROZEN_SCENARIO_CORPUS_HASH
        assert experiment_result.manifest_config_hash == FROZEN_MANIFEST_CONFIG_HASH
        assert experiment_result.baseline_config_hash == FROZEN_BASELINE_CONFIG_HASH
        assert len(experiment_result.experiment_profile_hash) == 32
        assert set(experiment_result.profiles.keys()) == {PROFILE_B0, PROFILE_C_T1A, PROFILE_B3}
        assert len(experiment_result.scenario_evaluations) == 150  # 50 scenarios * 3 profiles

    def test_gate_1_b0_reproduction(self, experiment_result: GDSCalibrationExperimentResult):
        b0 = experiment_result.profiles[PROFILE_B0]
        assert abs(b0.macro_precision - 0.054865) < 1e-4
        assert abs(b0.macro_recall - 1.000000) < 1e-4
        assert abs(b0.macro_f1 - 0.103728) < 1e-4
        assert b0.total_false_positives == 930
        assert b0.total_false_negatives == 0
        assert b0.exact_set_matches == 0

    def test_gate_2_c_t1a_reproduction(self, experiment_result: GDSCalibrationExperimentResult):
        ct1a = experiment_result.profiles[PROFILE_C_T1A]
        assert abs(ct1a.macro_precision - 0.556024) < 1e-4
        assert abs(ct1a.macro_recall - 0.820000) < 1e-4
        assert abs(ct1a.macro_f1 - 0.621159) < 1e-4
        assert ct1a.total_false_positives == 69
        assert ct1a.total_false_negatives == 11
        assert ct1a.exact_set_matches == 19

    def test_gate_3_b3_target_reproduction(self, experiment_result: GDSCalibrationExperimentResult):
        b3 = experiment_result.profiles[PROFILE_B3]
        assert abs(b3.macro_precision - 0.671190) < 1e-4
        assert abs(b3.macro_recall - 0.840000) < 1e-4
        assert abs(b3.macro_f1 - 0.711095) < 1e-4
        assert b3.total_false_positives <= 45
        assert b3.total_false_positives == 45

    def test_gate_4_b3_recall_and_false_negatives(self, experiment_result: GDSCalibrationExperimentResult):
        b3 = experiment_result.profiles[PROFILE_B3]
        assert b3.macro_recall >= 0.840000
        assert b3.total_false_negatives <= 10
        assert b3.total_false_negatives == 10

    def test_gate_5_b3_exact_governing_set_matches(self, experiment_result: GDSCalibrationExperimentResult):
        b3 = experiment_result.profiles[PROFILE_B3]
        assert b3.exact_set_matches == 26

    def test_gate_6_artifact_emission_and_determinism(self, tmp_path: Path):
        run1_dir = tmp_path / "run1"
        run2_dir = tmp_path / "run2"

        res1 = execute_gds_calibration_experiment(output_dir=run1_dir)
        res2 = execute_gds_calibration_experiment(output_dir=run2_dir)

        artifact1 = (run1_dir / "gds_calibration_summary.json").read_text(encoding="utf-8")
        artifact2 = (run2_dir / "gds_calibration_summary.json").read_text(encoding="utf-8")

        assert artifact1 == artifact2
        assert res1.experiment_profile_hash == res2.experiment_profile_hash

    def test_gate_7_output_dir_non_empty_fails_closed(self, tmp_path: Path):
        out_dir = tmp_path / "non_empty"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "existing.txt").write_text("existing content", encoding="utf-8")

        with pytest.raises(ValueError, match="exists and is non-empty"):
            execute_gds_calibration_experiment(output_dir=out_dir)

    def test_gate_8_per_repository_scenario_counts(self, experiment_result: GDSCalibrationExperimentResult):
        for profile_name in EVALUATED_PROFILES:
            prof = experiment_result.profiles[profile_name]
            assert len(prof.per_repository) == 5
            for repo_id in APPROVED_BATCH_01_REPOSITORIES:
                assert repo_id in prof.per_repository
                repo_sum = prof.per_repository[repo_id]
                assert repo_sum.total_scenarios == 10

    def test_gate_9_preflight_rejection_fails_closed(self, tmp_path: Path):
        # Create an invalid baseline file (status not frozen) that fails preflight
        repo_root = Path(__file__).resolve().parent.parent.parent
        valid_baseline = repo_root / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml"
        content = valid_baseline.read_text(encoding="utf-8")
        bad_content = content.replace("status: frozen", "status: draft")

        bad_baseline = tmp_path / "bad_baseline.yaml"
        bad_baseline.write_text(bad_content, encoding="utf-8")

        with pytest.raises(HarnessPreflightError, match="Baseline status must be 'frozen'"):
            execute_gds_calibration_experiment(baseline_path=bad_baseline)

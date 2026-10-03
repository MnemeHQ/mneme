"""
tests.open_architecture.test_stage_c_closure — Tests and deterministic evidence guard for Stage C Batch 01 closure.

Validates:
1. Committed Stage C closure artifact exists at benchmarks/open_architecture/batch_01/stage_c/stage_c_closure.json.
2. Committed artifact binds required identities and status:
   - status == "CLOSED / FROZEN"
   - accepted_endpoint == "B3"
   - headline_metric == "governing_decision_set_f1"
   - mneme_execution_sha == "fcc36a60b9ec95014eb8931c3bac6bfee418e781"
   - scenario corpus hash == "2ff8751955fd64a33316aca6692dc803"
   - reference corpus hash == "0455bd66aae52551c35b37a63c2d185f"
   - baseline config hash == "31e18dc1e2bd9ad30bec86dce1a9295a"
   - manifest config hash == "4af7e5794011b43d39682cdfeac9f54e"
   - Stage B mixed semantic hash == "sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a"
   - Stage C experiment profile hash == "5f031434a95ea94c53255901b1ada39e"
3. Exact B3 profile definition:
   - selection_policy == "relative_80" (ratio: 0.80, epsilon: 1e-9)
   - query_treatment == B3 transformed query
   - 6 registered structural prefixes and 5 suppressed function words
4. Exact scorecards and metrics match frozen evidence:
   - End-to-end B3 macro F1 == 0.6506666666666666, precision == 0.6023333333333334, recall == 0.79, exact == 22/50
   - Human-reference B3 macro F1 == 0.7110952380952381, exact == 26/50
   - Per-repository metrics match across all 5 repos
   - Comparison across B0, C-T1A, and B3
5. Endpoint rationale captures headline metric, F1 dominance, recall trade-off, and research limitations.
6. Deterministic evidence guard: fresh reconstruction from committed evidence achieves
   both semantic and byte identity with committed closure artifact.
7. Zero model, network, or external API calls performed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.gds_calibration_experiment import (
    FROZEN_FUNCTION_WORDS,
    FROZEN_STRUCTURAL_PREFIXES,
    POLICY_RELATIVE_80,
    PROFILE_B3,
    RELATIVE_THRESHOLD_RATIO,
    SELECTION_EPSILON,
)
from mneme.open_architecture.stage_c_closure import (
    ACCEPTED_B3_END_TO_END_MACRO_F1,
    ACCEPTED_B3_END_TO_END_PRECISION,
    ACCEPTED_B3_END_TO_END_RECALL,
    ACCEPTED_B3_EXACT_SET_MATCHES,
    ACCEPTED_B3_HUMAN_EXACT_SET_MATCHES,
    ACCEPTED_B3_HUMAN_MACRO_F1,
    ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH,
    ACCEPTED_STAGE_C_ENDPOINT,
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_SCENARIO_CORPUS_HASH,
    FROZEN_STAGE_C_CLOSURE_MNEME_SHA,
    FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH,
    HEADLINE_METRIC,
    build_stage_c_closure,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLOSURE_ARTIFACT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "stage_c"
    / "stage_c_closure.json"
)

EXPECTED_B3_E2E_PER_REPO = {
    "adrkit": {
        "exact_set_matches": 6,
        "macro_f1": 0.7333333333333333,
        "macro_precision": 0.75,
        "macro_recall": 0.75,
        "total_false_positives": 5,
        "total_false_negatives": 4,
    },
    "archlint": {
        "exact_set_matches": 3,
        "macro_f1": 0.6066666666666667,
        "macro_precision": 0.525,
        "macro_recall": 0.8,
        "total_false_positives": 12,
        "total_false_negatives": 2,
    },
    "gsa_agentic_coding_quickstart": {
        "exact_set_matches": 3,
        "macro_f1": 0.5733333333333334,
        "macro_precision": 0.4916666666666667,
        "macro_recall": 0.8,
        "total_false_positives": 11,
        "total_false_negatives": 3,
    },
    "helix": {
        "exact_set_matches": 3,
        "macro_f1": 0.5066666666666666,
        "macro_precision": 0.445,
        "macro_recall": 0.7,
        "total_false_positives": 14,
        "total_false_negatives": 3,
    },
    "modonome": {
        "exact_set_matches": 7,
        "macro_f1": 0.8333333333333334,
        "macro_precision": 0.8,
        "macro_recall": 0.9,
        "total_false_positives": 4,
        "total_false_negatives": 1,
    },
}


class TestStageCClosureArtifact:
    def test_committed_closure_artifact_exists(self):
        assert CLOSURE_ARTIFACT_PATH.is_file(), f"Missing artifact: {CLOSURE_ARTIFACT_PATH}"

    def test_committed_closure_artifact_status_and_declaration(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))

        assert data["artifact_type"] == "stage_c_batch_01_closure"
        assert data["artifact_version"] == "0.1"
        assert data["batch_id"] == "o1a-batch-01"
        assert data["closure_status"] == "closed_frozen"
        assert data["headline_metric"] == HEADLINE_METRIC

        decl = data["closure_declaration"]
        assert decl["status"] == "CLOSED / FROZEN"
        assert decl["accepted_endpoint"] == ACCEPTED_STAGE_C_ENDPOINT
        assert "No later Batch 01 Stage C treatment or calibration profile is accepted" in decl["closure_scope"]
        assert "not declared a globally optimal or production-ready" in decl["production_readiness"]

        endpoint = data["endpoint_identity"]
        assert endpoint["endpoint_name"] == ACCEPTED_STAGE_C_ENDPOINT
        assert endpoint["profile"] == ACCEPTED_STAGE_C_ENDPOINT
        assert endpoint["experiment_id"] == "o1a-stage-c-end-to-end"
        assert endpoint["purpose"] == "governing_decision_set_retrieval"

    def test_committed_closure_artifact_required_bindings(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))

        # Execution commit SHA
        assert data["mneme_execution_sha"] == FROZEN_STAGE_C_CLOSURE_MNEME_SHA

        # Corpora and input hashes
        inputs = data["corpora_and_inputs"]
        assert inputs["scenario_corpus_hash"] == FROZEN_SCENARIO_CORPUS_HASH
        assert inputs["reference_corpus_hash"] == FROZEN_REFERENCE_CORPUS_HASH
        assert inputs["baseline_configuration_hash"] == FROZEN_BASELINE_CONFIG_HASH
        assert inputs["manifest_configuration_hash"] == FROZEN_MANIFEST_CONFIG_HASH
        assert inputs["stage_b_mixed_semantic_hash"] == ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH
        assert inputs["stage_c_experiment_profile_hash"] == FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH

        # Dataset counts
        ds = data["dataset"]
        assert ds["total_scenarios"] == 50
        assert ds["scenarios_per_repository"] == 10
        assert ds["total_reference_decisions"] == 100
        assert ds["decisions_per_repository"] == 20

    def test_committed_closure_artifact_b3_profile_definition(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        b3_def = data["b3_profile_definition"]

        assert b3_def["profile_id"] == PROFILE_B3
        assert b3_def["selection_policy"] == POLICY_RELATIVE_80
        assert b3_def["relative_threshold_ratio"] == RELATIVE_THRESHOLD_RATIO
        assert b3_def["selection_epsilon"] == SELECTION_EPSILON
        assert b3_def["query_transformation_function"] == "transform_query_for_b3"
        assert set(b3_def["registered_structural_prefixes"]) == set(FROZEN_STRUCTURAL_PREFIXES)
        assert set(b3_def["suppressed_function_words"]) == set(FROZEN_FUNCTION_WORDS)

    def test_committed_closure_artifact_scorecard_metrics(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        scorecard = data["accepted_endpoint_scorecard"]

        assert scorecard["profile"] == ACCEPTED_STAGE_C_ENDPOINT

        # End-to-end B3 metrics
        e2e = scorecard["end_to_end_metrics"]
        assert e2e["macro_f1"] == ACCEPTED_B3_END_TO_END_MACRO_F1
        assert e2e["macro_precision"] == ACCEPTED_B3_END_TO_END_PRECISION
        assert e2e["macro_recall"] == ACCEPTED_B3_END_TO_END_RECALL
        assert e2e["exact_set_matches"] == ACCEPTED_B3_EXACT_SET_MATCHES
        assert e2e["total_scenarios"] == 50
        assert e2e["total_false_positives"] == 46
        assert e2e["total_false_negatives"] == 13

        # Human-reference B3 metrics
        human = scorecard["human_reference_metrics"]
        assert human["macro_f1"] == ACCEPTED_B3_HUMAN_MACRO_F1
        assert human["exact_set_matches"] == ACCEPTED_B3_HUMAN_EXACT_SET_MATCHES
        assert human["total_false_positives"] == 45
        assert human["total_false_negatives"] == 10

        # Per-repository breakdown
        repos = scorecard["per_repository"]["end_to_end"]
        assert set(repos.keys()) == set(EXPECTED_B3_E2E_PER_REPO.keys())
        for repo_id, exp in EXPECTED_B3_E2E_PER_REPO.items():
            r = repos[repo_id]
            assert r["exact_set_matches"] == exp["exact_set_matches"]
            assert pytest.approx(r["macro_f1"], rel=1e-9) == exp["macro_f1"]
            assert pytest.approx(r["macro_precision"], rel=1e-9) == exp["macro_precision"]
            assert pytest.approx(r["macro_recall"], rel=1e-9) == exp["macro_recall"]
            assert r["total_false_positives"] == exp["total_false_positives"]
            assert r["total_false_negatives"] == exp["total_false_negatives"]

    def test_committed_closure_artifact_profile_comparisons(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        comps = data["profile_evaluations_comparison"]

        e2e_profiles = comps["end_to_end"]
        human_profiles = comps["human_reference"]

        # All 3 profiles present in both
        for prof in ("B0", "C-T1A", "B3"):
            assert prof in e2e_profiles
            assert prof in human_profiles

        # B3 has highest F1 in both
        assert (
            e2e_profiles["B3"]["macro_f1"]
            > e2e_profiles["C-T1A"]["macro_f1"]
            > e2e_profiles["B0"]["macro_f1"]
        )
        assert (
            human_profiles["B3"]["macro_f1"]
            > human_profiles["C-T1A"]["macro_f1"]
            > human_profiles["B0"]["macro_f1"]
        )

        # B3 has highest exact set matches in both
        assert (
            e2e_profiles["B3"]["exact_set_matches"]
            > e2e_profiles["C-T1A"]["exact_set_matches"]
            > e2e_profiles["B0"]["exact_set_matches"]
        )

    def test_committed_closure_artifact_provenance_sources_exist(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        sources = data["provenance_sources"]

        for source_key, rel_path in sources.items():
            abs_path = REPO_ROOT / rel_path
            assert abs_path.is_file(), f"Provenance source '{source_key}' missing at: {abs_path}"

    def test_committed_closure_artifact_endpoint_rationale(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        rat = data["endpoint_rationale"]

        assert rat["headline_metric"] == HEADLINE_METRIC
        assert "highest macro F1" in rat["selection_summary"]
        assert "0.79 vs C-T1A recall 0.81" in rat["tradeoff_disclosure"]
        assert "not demonstrated to be globally optimal" in rat["research_limitations"].lower()
        assert "not definitive causal proof" in rat["research_limitations"].lower()


class TestStageCClosureEvidenceGuard:
    def test_fresh_reconstruction_matches_committed_artifact(self):
        """Verify fresh deterministic reconstruction has semantic and byte identity with committed artifact."""
        fresh = build_stage_c_closure(REPO_ROOT)
        committed_text = CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8")
        committed_dict = json.loads(committed_text)

        # 1. Semantic identity
        assert fresh == committed_dict

        # 2. Byte identity
        serialized_fresh = json.dumps(fresh, indent=2, sort_keys=True) + "\n"
        assert serialized_fresh == committed_text

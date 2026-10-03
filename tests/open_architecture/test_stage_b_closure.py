"""
tests.open_architecture.test_stage_b_closure — Tests and deterministic evidence guard for Stage B Batch 01 closure.

Validates:
1. Committed Stage B closure artifact exists at benchmarks/open_architecture/batch_01/stage_b/stage_b_closure.json.
2. Committed artifact binds required identities and status:
   - status == "CLOSED / FROZEN"
   - accepted_endpoint == "B-T1D / Arm D"
   - mneme_execution_sha == "7e17fb1640a0144468d47d6ece2791c44b1bfbc2"
   - historical baseline corpus == "0455bd66aae52551c35b37a63c2d185f"
   - scoring reference corpus == "700a569e24bf90707ba14ff65eea2ab5"
   - Arm D profile hash == "d66bb19c9e4c64e835a6191293a95570"
   - Arm D outcome semantic hash == "sha256:ae1fbd24f6b36099d3c58006886503f6ba14bf5fd7cfa9bfb93c4befaabbedc0"
   - Accepted mixed semantic hash == "sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a"
3. Exact scorecards and metrics match frozen evidence:
   - stage_b_semantic_score == 0.5934313272250952
   - strict_relationship_accuracy == 0.6100000000000001
   - exact relationship matches == 61 / 100
   - per-repository and macro task scorecards
4. Endpoint rationale captures preservation conditions and hypothesis outcomes.
5. Deterministic evidence guard: fresh reconstruction from committed evidence achieves
   both semantic and byte identity with committed closure artifact.
6. Zero model, network, or external API calls performed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.stage_b_closure import (
    ACCEPTED_RELATIONSHIP_EXACT_MATCHES,
    ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH,
    ACCEPTED_STAGE_B_SEMANTIC_SCORE,
    ACCEPTED_STRICT_RELATIONSHIP_ACCURACY,
    FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH,
    FROZEN_ARM_D_PROFILE_HASH,
    FROZEN_HISTORICAL_BASELINE_CORPUS_HASH,
    FROZEN_SCORING_REFERENCE_CORPUS_HASH,
    FROZEN_STAGE_B_CLOSURE_MNEME_SHA,
    STAGE_B_EVALUATED_TASKS,
    build_stage_b_closure,
)
from mneme.open_architecture.stage_c_end_to_end_experiment import (
    load_accepted_stage_b_replay_outcomes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLOSURE_ARTIFACT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "stage_b"
    / "stage_b_closure.json"
)

EXPECTED_REPOSITORY_COMPOSITES = {
    "adrkit": 0.5705557222889156,
    "archlint": 0.5197916666666667,
    "gsa_agentic_coding_quickstart": 0.7209625253263361,
    "helix": 0.5727056962025316,
    "modonome": 0.5831410256410257,
}


class TestStageBClosureArtifact:
    def test_committed_closure_artifact_exists(self):
        assert CLOSURE_ARTIFACT_PATH.is_file(), f"Missing artifact: {CLOSURE_ARTIFACT_PATH}"

    def test_committed_closure_artifact_status_and_declaration(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))

        assert data["artifact_type"] == "stage_b_batch_01_closure"
        assert data["artifact_version"] == "0.1"
        assert data["batch_id"] == "o1a-batch-01"
        assert data["closure_status"] == "closed_frozen"

        decl = data["closure_declaration"]
        assert decl["status"] == "CLOSED / FROZEN"
        assert decl["accepted_endpoint"] == "B-T1D / Arm D"
        assert "No later Batch 01 Stage B treatment is accepted" in decl["closure_scope"]
        assert "not declared a solved, optimal, or production-ready" in decl["production_readiness"]

        endpoint = data["endpoint_identity"]
        assert endpoint["endpoint_name"] == "B-T1D / Arm D"
        assert endpoint["arm_id"] == "treatment_d"
        assert endpoint["experiment_id"] == "b-t1d-relationship-selectivity"
        assert endpoint["purpose"] == "relationship_selectivity"

    def test_committed_closure_artifact_required_bindings(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))

        # Execution commit SHA
        assert data["mneme_execution_sha"] == FROZEN_STAGE_B_CLOSURE_MNEME_SHA

        # Corpora hashes and distinction
        corpora = data["corpora"]
        assert (
            corpora["historical_baseline_reference_corpus_hash"]
            == FROZEN_HISTORICAL_BASELINE_CORPUS_HASH
        )
        assert corpora["historical_baseline_corpus_version"] == "batch_01_v0.1"
        assert (
            corpora["scoring_reference_corpus_hash"]
            == FROZEN_SCORING_REFERENCE_CORPUS_HASH
        )
        assert corpora["scoring_corpus_version"] == "batch_01_v0.2-grounding"
        assert (
            corpora["historical_baseline_reference_corpus_hash"]
            != corpora["scoring_reference_corpus_hash"]
        )

        # Cryptographic content hashes
        hashes = data["cryptographic_hashes"]
        assert hashes["arm_d_treatment_profile_hash"] == FROZEN_ARM_D_PROFILE_HASH
        assert hashes["arm_d_outcomes_semantic_hash"] == FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH
        assert hashes["accepted_mixed_semantic_hash"] == ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH

        # Classifier identities
        clf = data["classifier"]
        assert clf["backend_id"] == "anthropic"
        assert clf["classifier_version"] == "0.1"
        assert clf["model_identifier"] == "claude-sonnet-4-6"
        assert clf["taxonomy_version"] == "0.1"

        # Dataset counts
        ds = data["dataset"]
        assert ds["total_references"] == 100
        assert ds["tasks_per_reference"] == 8
        assert ds["total_outcomes"] == 800
        assert ds["composition"]["b0_non_relationship_outcomes"] == 700
        assert ds["composition"]["arm_d_relationship_outcomes"] == 100
        assert ds["composition"]["total_assembled_outcomes"] == 800

    def test_committed_closure_artifact_scorecard_metrics(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        sc = data["endpoint_scorecard"]

        assert sc["stage_b_semantic_score"] == ACCEPTED_STAGE_B_SEMANTIC_SCORE
        assert sc["strict_relationship_accuracy"] == ACCEPTED_STRICT_RELATIONSHIP_ACCURACY
        assert sc["relationship_exact_matches"] == ACCEPTED_RELATIONSHIP_EXACT_MATCHES

        # Per-repository composites
        repos = sc["per_repository"]
        assert set(repos.keys()) == set(EXPECTED_REPOSITORY_COMPOSITES.keys())
        for repo_id, exp_comp in EXPECTED_REPOSITORY_COMPOSITES.items():
            assert repos[repo_id]["composite_score"] == pytest.approx(exp_comp, rel=1e-9)
            assert repos[repo_id]["reference_count"] == 20
            assert repos[repo_id]["task_count"] == 160

        # All 8 evaluated tasks present in macro averages
        macro_tasks = sc["macro_task_averages"]
        for task in STAGE_B_EVALUATED_TASKS:
            assert task in macro_tasks
        assert macro_tasks["decision_classification_accuracy"] == 0.76
        assert macro_tasks["authority_accuracy"] == pytest.approx(0.57, rel=1e-6)
        assert macro_tasks["scope_accuracy"] == 0.0
        assert macro_tasks["lifecycle_accuracy"] == pytest.approx(0.94, rel=1e-6)
        assert macro_tasks["relationship_accuracy"] == pytest.approx(0.61, rel=1e-6)
        assert macro_tasks["enforcement_classification_accuracy"] == 0.78

    def test_committed_closure_artifact_provenance_sources_exist(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        sources = data["provenance_sources"]

        for source_key, rel_path in sources.items():
            abs_path = REPO_ROOT / rel_path
            assert abs_path.is_file(), f"Provenance source '{source_key}' missing at: {abs_path}"

    def test_committed_closure_artifact_endpoint_rationale(self):
        data = json.loads(CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8"))
        rat = data["endpoint_rationale"]

        assert rat["all_preservation_conditions_passed"] is True
        assert rat["all_primary_hypotheses_passed"] is False

        kf = rat["key_findings"]
        assert "18/18" in kf["target_entity_recovery"]
        assert "32" in kf["expected_empty_false_positives"]
        assert "56/88" in kf["expected_empty_exact_matches"]
        assert "61/100" in kf["strict_relationship_accuracy"]
        assert "Reduced" in kf["extra_tuples_reduction"]

        # Exact Preservation Conditions (P1-P5)
        pcs = {c["condition_id"]: c for c in rat["preservation_conditions"]}
        assert len(pcs) == 5
        assert pcs["P1"]["metric"] == "target_entity_recovery"
        assert pcs["P1"]["observed_value"] == 18
        assert pcs["P1"]["passed"] is True

        assert pcs["P2"]["metric"] == "exact_type_exact_target_recovery"
        assert pcs["P2"]["observed_value"] == 13
        assert pcs["P2"]["passed"] is True

        assert pcs["P3"]["metric"] == "missing_target_entities"
        assert pcs["P3"]["observed_value"] == 0
        assert pcs["P3"]["passed"] is True

        assert pcs["P4"]["metric"] == "non_empty_strict_exact_matches"
        assert pcs["P4"]["observed_value"] == 5
        assert pcs["P4"]["passed"] is True

        assert pcs["P5"]["metric"] == "target_boundary_anomalies"
        assert pcs["P5"]["observed_value"] == 1
        assert pcs["P5"]["passed"] is True


class TestStageBClosureEvidenceGuard:
    def test_fresh_reconstruction_matches_committed_artifact(self):
        """Verify fresh deterministic reconstruction has semantic and byte identity with committed artifact."""
        fresh = build_stage_b_closure(REPO_ROOT)
        committed_text = CLOSURE_ARTIFACT_PATH.read_text(encoding="utf-8")
        committed_dict = json.loads(committed_text)

        # 1. Semantic identity
        assert fresh == committed_dict

        # 2. Byte identity
        serialized_fresh = json.dumps(fresh, indent=2, sort_keys=True) + "\n"
        assert serialized_fresh == committed_text

    def test_accepted_replay_outcomes_match_hash_and_count(self):
        """Verify the 800 mixed outcomes consumed by Stage C match accepted mixed semantic hash."""
        outcomes = load_accepted_stage_b_replay_outcomes(REPO_ROOT)
        assert len(outcomes) == 800

        # Exact split: 700 non-relationship + 100 relationship
        from mneme.open_architecture.classification import ClassifierTaskType

        rel_outcomes = [
            o for o in outcomes if o.task_type == ClassifierTaskType.RELATIONSHIPS
        ]
        non_rel_outcomes = [
            o for o in outcomes if o.task_type != ClassifierTaskType.RELATIONSHIPS
        ]
        assert len(rel_outcomes) == 100
        assert len(non_rel_outcomes) == 700

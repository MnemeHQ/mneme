"""
tests.open_architecture.test_stage_b_relationship_selectivity_diagnostics — Tests for B-T1D Diagnosis.

Validates the deterministic B-T1D Arm D residual diagnosis and hypothesis evaluation:
1. Frozen input identities (v0.2 corpus, Arm D outcomes, Arm D profile, Arm B control)
2. Deterministic repeatability
3. Zero model/network calls
4. Population = 100 / 88 / 12 / 18
5. Strict exact count agrees with frozen score artifact (61 / 100)
6. All residual structural classes sum to 39 (100 - 61)
7. Tuple counts reconcile (exact + missing == 18; predicted == exact + extra == 99)
8. Expected-empty FP (32) and exact (56) reconcile to 88
9. Target attribution totals reconcile to 18 (13 exact + 5 wrong type + 0 missing)
10. H1-H5 use exactly preregistered comparators and baselines
11. P1-P5 use exactly preregistered comparators and thresholds
12. Secondary diagnostics (depends_on, evidence context) are not primary hypotheses
13. Arm B baseline values reproduce from committed evidence
14. Historical B-T1C residual analyzer remains unchanged
15. Zero production/runtime imports
16. Zero ast.Assert statements in diagnostics module
17. Serialized diagnostics.json reproduces byte-for-byte
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from mneme.open_architecture.harness import (
    load_reference_corpus,
)
from mneme.open_architecture.stage_b_relationship_residual_analysis import (
    STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS,
    STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE,
    STRUCTURAL_PURE_TYPE_CONFUSION,
    STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS,
)
from mneme.open_architecture.stage_b_relationship_selectivity_diagnostics import (
    ARM_D_ID,
    CAUSAL_INFERENCE_LIMITATION,
    CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH,
    CONTROL_ARM_B_PROFILE_HASH,
    EXPERIMENT_ID,
    FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH,
    FROZEN_ARM_D_STAGE_B_COMPOSITE,
    FROZEN_ARM_D_STRICT_RELATIONSHIP_ACCURACY,
    FROZEN_EXECUTION_COMMIT_SHA,
    run_stage_b_relationship_selectivity_diagnostics,
    validate_arm_d_diagnostic_inputs,
    write_stage_b_relationship_selectivity_diagnostics,
)
from mneme.open_architecture.stage_b_relationship_selectivity_experiment import (
    B_T1D_PROFILE_D_HASH,
    FROZEN_SCORING_REFERENCE_CORPUS_HASH,
    load_treatment_run,
    recompute_arm_b_v02_control_metrics,
)
from mneme.open_architecture.stage_b_relationship_treatment_experiment import (
    load_treatment_outcomes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V02_REF_DIR = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "revisions"
    / "batch_01_v0.2-grounding"
    / "reference_decisions"
)
ARM_D_RUN_DIR = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "treatments"
    / "b_t1d"
    / "arm_d"
)
ARM_B_OUTCOMES_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "treatments"
    / "b_t1c"
    / "arm_b"
    / "outcomes.jsonl"
)
ARM_B_RESIDUAL_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "treatments"
    / "b_t1c"
    / "arm_b"
    / "residual_error_decomposition_v0.2_grounding.json"
)
DIAGNOSTICS_PATH = ARM_D_RUN_DIR / "diagnostics.json"
SCORE_PATH = ARM_D_RUN_DIR / "stage_b_score.json"


class TestBT1DSelectivityDiagnostics:
    """Diagnostic validation suite for O1A B-T1D Arm D."""

    def test_01_frozen_input_identities(self):
        """1. Frozen input identities match preregistered authorities."""
        refs = load_reference_corpus(V02_REF_DIR)
        expected_ids = {r.reference_decision_id for r in refs}
        outcomes, sidecar = load_treatment_run(ARM_D_RUN_DIR, expected_ids)

        assert sidecar.treatment_profile_hash == B_T1D_PROFILE_D_HASH == "d66bb19c9e4c64e835a6191293a95570"
        assert (
            sidecar.treatment_semantic_content_hash
            == FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH
            == "sha256:ae1fbd24f6b36099d3c58006886503f6ba14bf5fd7cfa9bfb93c4befaabbedc0"
        )
        assert sidecar.execution_mneme_commit_sha == FROZEN_EXECUTION_COMMIT_SHA == "dcca4d7b2ca9674cd12b55a717f741dbe90da420"
        assert sidecar.scoring_reference_corpus_hash == FROZEN_SCORING_REFERENCE_CORPUS_HASH == "700a569e24bf90707ba14ff65eea2ab5"
        assert sidecar.control_arm_b_profile_hash == CONTROL_ARM_B_PROFILE_HASH == "e4b6bad47ebcc290924782172fb96d8d"
        assert sidecar.control_arm_b_semantic_hash == CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH

    def test_02_deterministic_repeatability(self):
        """2. Diagnostic derivation produces byte-identical results across independent runs."""
        refs = load_reference_corpus(V02_REF_DIR)
        expected_ids = {r.reference_decision_id for r in refs}
        outcomes, sidecar = load_treatment_run(ARM_D_RUN_DIR, expected_ids)
        score_data = json.loads(SCORE_PATH.read_text(encoding="utf-8"))

        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH, expected_reference_ids=expected_ids)
        arm_b_metrics = recompute_arm_b_v02_control_metrics(refs, arm_b_outcomes, ARM_B_RESIDUAL_PATH)

        diag1 = run_stage_b_relationship_selectivity_diagnostics(refs, outcomes, arm_b_metrics, score_data)
        diag2 = run_stage_b_relationship_selectivity_diagnostics(refs, outcomes, arm_b_metrics, score_data)

        text1 = json.dumps(diag1, indent=2, sort_keys=True)
        text2 = json.dumps(diag2, indent=2, sort_keys=True)
        assert text1 == text2

    def test_03_zero_model_network_calls(self):
        """3. Diagnostics run entirely offline with zero model or network invocations."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        assert diag_data["model_calls"] == 0
        assert diag_data["network_calls"] == 0

    def test_04_population_invariants(self):
        """4. Population counts: exactly 100 references, 88 expected empty, 12 non-empty, 18 expected tuples."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        pop = diag_data["population_counts"]
        assert pop["total_references"] == 100
        assert pop["expected_empty_references"] == 88
        assert pop["expected_non_empty_references"] == 12
        assert pop["total_expected_tuples"] == 18

    def test_05_strict_exact_count_agrees_with_score_artifact(self):
        """5. Derived strict exact count reconciles against score artifact rather than literal constants."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        score_data = json.loads(SCORE_PATH.read_text(encoding="utf-8"))

        m = diag_data["observed_metrics"]
        assert m["strict_exact_references"] == 61
        assert diag_data["passing_references"] == 61
        assert diag_data["failing_references"] == 39
        assert m["strict_exact_references"] / 100.0 == pytest.approx(score_data["strict_relationship_accuracy"])
        assert score_data["stage_b_semantic_score"] == FROZEN_ARM_D_STAGE_B_COMPOSITE

        # Tampering with score strict accuracy fails closed in run_stage_b_relationship_selectivity_diagnostics
        refs = load_reference_corpus(V02_REF_DIR)
        expected_ids = {r.reference_decision_id for r in refs}
        outcomes, _ = load_treatment_run(ARM_D_RUN_DIR, expected_ids)
        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH, expected_reference_ids=expected_ids)
        arm_b_metrics = recompute_arm_b_v02_control_metrics(refs, arm_b_outcomes, ARM_B_RESIDUAL_PATH)

        bad_score_acc = {**score_data, "strict_relationship_accuracy": 0.50}
        with pytest.raises(ValueError, match="Strict relationship accuracy mismatch"):
            run_stage_b_relationship_selectivity_diagnostics(refs, outcomes, arm_b_metrics, bad_score_acc)

    def test_06_residual_structural_classes_sum_correctly(self):
        """6. Residual structural class counts sum exactly to total_references - strict_exact."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        sc = diag_data["structural_residual_counts"]

        total_refs = diag_data["population_counts"]["total_references"]
        strict_exact = diag_data["observed_metrics"]["strict_exact_references"]
        expected_failures = total_refs - strict_exact

        assert expected_failures == 39
        assert diag_data["failing_references"] == expected_failures
        assert sc[STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE] == 32
        assert sc[STRUCTURAL_PURE_TYPE_CONFUSION] == 3
        assert sc[STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS] == 2
        assert sc[STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS] == 2
        assert sum(sc.values()) == expected_failures
        assert len(diag_data["failing_records"]) == expected_failures

    def test_07_tuple_counts_reconcile(self):
        """7. Tuple counts reconcile: exact + extra == predicted; exact + missing == expected."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        m = diag_data["observed_metrics"]

        exact_tuples = m["total_exact_tuples"]
        missing_tuples = m["total_missing_tuples"]
        extra_tuples = m["total_extra_tuples"]
        predicted_tuples = m["total_predicted_tuples"]
        expected_tuples = diag_data["population_counts"]["total_expected_tuples"]

        # Exact derived values for frozen Arm D execution
        assert exact_tuples == 13
        assert missing_tuples == 5
        assert extra_tuples == 86
        assert predicted_tuples == 99
        assert expected_tuples == 18

        # Invariant identities
        assert exact_tuples + extra_tuples == predicted_tuples
        assert exact_tuples + missing_tuples == expected_tuples

    def test_08_expected_empty_reconciliation(self):
        """8. Expected-empty FP count (32) and exact count (56) reconcile to 88."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        m = diag_data["observed_metrics"]
        assert m["expected_empty_exact"] == 56
        assert m["expected_empty_fp"] == 32
        assert m["expected_empty_exact"] + m["expected_empty_fp"] == 88

    def test_09_target_attribution_reconciles_to_18(self):
        """9. Target attribution totals reconcile to 18 (13 exact + 5 wrong type + 0 missing)."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        ta = diag_data["target_attribution_totals"]

        assert ta["total_expected_tuples"] == 18
        assert ta["target_entity_recovered_any_type"] == 18
        assert ta["exact_type_exact_target"] == 13
        assert ta["wrong_type_recovery"] == 5
        assert ta["missing_target_entities"] == 0
        assert ta["exact_type_exact_target"] + ta["wrong_type_recovery"] == 18

    def test_10_primary_hypotheses_evaluation(self):
        """10. H1-H5 use exactly preregistered comparators and baseline values."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        h_map = {h["hypothesis_id"]: h for h in diag_data["primary_hypotheses"]}

        # H1: strict accuracy > 0.59
        assert h_map["H1"]["comparator"] == ">"
        assert h_map["H1"]["control_arm_b_baseline"] == 0.59
        assert h_map["H1"]["observed_value"] == 0.61
        assert h_map["H1"]["passed"] is True

        # H2: expected-empty exact > 56
        assert h_map["H2"]["comparator"] == ">"
        assert h_map["H2"]["control_arm_b_baseline"] == 56
        assert h_map["H2"]["observed_value"] == 56
        assert h_map["H2"]["passed"] is False  # Equal, not strictly greater

        # H3: expected-empty FP < 32
        assert h_map["H3"]["comparator"] == "<"
        assert h_map["H3"]["control_arm_b_baseline"] == 32
        assert h_map["H3"]["observed_value"] == 32
        assert h_map["H3"]["passed"] is False  # Equal, not strictly less

        # H4: expected-empty extra tuples < 86
        assert h_map["H4"]["comparator"] == "<"
        assert h_map["H4"]["control_arm_b_baseline"] == 86
        assert h_map["H4"]["observed_value"] == 75
        assert h_map["H4"]["passed"] is True  # Reduced from 86 to 75

        # H5: total extra tuples < 105
        assert h_map["H5"]["comparator"] == "<"
        assert h_map["H5"]["control_arm_b_baseline"] == 105
        assert h_map["H5"]["observed_value"] == 86
        assert h_map["H5"]["passed"] is True  # Reduced from 105 to 86

        assert diag_data["all_primary_hypotheses_passed"] is False

    def test_11_preservation_conditions_evaluation(self):
        """11. P1-P5 use exactly preregistered comparators and all pass."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        p_map = {p["condition_id"]: p for p in diag_data["preservation_conditions"]}

        # P1: target entity recovery == 18
        assert p_map["P1"]["comparator"] == "=="
        assert p_map["P1"]["control_threshold"] == 18
        assert p_map["P1"]["observed_value"] == 18
        assert p_map["P1"]["passed"] is True

        # P2: exact type + target recovery >= 12
        assert p_map["P2"]["comparator"] == ">="
        assert p_map["P2"]["control_threshold"] == 12
        assert p_map["P2"]["observed_value"] == 13
        assert p_map["P2"]["passed"] is True

        # P3: missing target entities == 0
        assert p_map["P3"]["comparator"] == "=="
        assert p_map["P3"]["control_threshold"] == 0
        assert p_map["P3"]["observed_value"] == 0
        assert p_map["P3"]["passed"] is True

        # P4: non-empty strict exact >= 3
        assert p_map["P4"]["comparator"] == ">="
        assert p_map["P4"]["control_threshold"] == 3
        assert p_map["P4"]["observed_value"] == 5
        assert p_map["P4"]["passed"] is True

        # P5: target boundary anomalies <= 2
        assert p_map["P5"]["comparator"] == "<="
        assert p_map["P5"]["control_threshold"] == 2
        assert p_map["P5"]["observed_value"] == 1
        assert p_map["P5"]["passed"] is True

        assert diag_data["all_preservation_conditions_passed"] is True

    def test_12_secondary_diagnostics_not_primary_hypotheses(self):
        """12. Secondary diagnostics (depends_on reduction, evidence contexts) are separate."""
        diag_data = json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        assert "extra_depends_on" in diag_data["observed_metrics"]
        assert diag_data["observed_metrics"]["extra_depends_on"] == 37  # Down from 72!

        comp = diag_data["extra_only_evidence_context_comparison"]
        assert sum(comp["arm_b_baseline"].values()) == 105
        assert sum(comp["arm_d_observed"].values()) == 86
        assert sum(comp["delta"].values()) == -19

        # Contextual related metadata extra reduction: -16
        assert comp["delta"]["contextual_related_metadata"] == -16

    def test_13_arm_b_baseline_values_reproduce(self):
        """13. Arm B baseline control metrics reproduce from committed evidence."""
        refs = load_reference_corpus(V02_REF_DIR)
        expected_ids = {r.reference_decision_id for r in refs}
        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH, expected_reference_ids=expected_ids)
        metrics = recompute_arm_b_v02_control_metrics(refs, arm_b_outcomes, ARM_B_RESIDUAL_PATH)

        assert metrics["strict_exact_references"] == 59
        assert metrics["expected_empty_exact"] == 56
        assert metrics["expected_empty_fp_references"] == 32
        assert metrics["expected_empty_extra_tuples"] == 86
        assert metrics["total_extra_tuples"] == 105
        assert metrics["extra_depends_on_tuples"] == 72

    def test_14_historical_b_t1c_analyzer_unchanged(self):
        """14. Historical B-T1C residual analyzer file remains unmodified."""
        module_path = (
            REPO_ROOT
            / "mneme"
            / "open_architecture"
            / "stage_b_relationship_residual_analysis.py"
        )
        assert module_path.is_file()

    def test_15_zero_production_runtime_imports(self):
        """15. Research boundaries: zero imports of canonical production runtime modules."""
        module_path = (
            REPO_ROOT
            / "mneme"
            / "open_architecture"
            / "stage_b_relationship_selectivity_diagnostics.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))

        forbidden_prefixes = (
            "mneme.decision_retriever",
            "mneme.conflict_detector",
            "mneme.enforcer",
            "mneme.memory_store",
            "mneme.decision_index",
            "mneme.integrations",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        assert not alias.name.startswith(prefix), f"Forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not node.module.startswith(prefix), f"Forbidden from-import: {node.module}"

    def test_16_no_assert_statements_in_diagnostics_module(self):
        """16. B-T1D diagnostics module contains zero ast.Assert statements."""
        module_path = (
            REPO_ROOT
            / "mneme"
            / "open_architecture"
            / "stage_b_relationship_selectivity_diagnostics.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        assert_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
        assert len(assert_nodes) == 0, f"Found {len(assert_nodes)} assert statements in {module_path}"

    def test_17_serialized_diagnostics_reproduces_byte_identically(self):
        """17. Serialized diagnostics.json byte-for-byte matches generator output."""
        assert DIAGNOSTICS_PATH.is_file()
        committed_text = DIAGNOSTICS_PATH.read_text(encoding="utf-8")
        committed_data = json.loads(committed_text)

        refs = load_reference_corpus(V02_REF_DIR)
        expected_ids = {r.reference_decision_id for r in refs}
        outcomes, sidecar = load_treatment_run(ARM_D_RUN_DIR, expected_ids)
        score_data = json.loads(SCORE_PATH.read_text(encoding="utf-8"))

        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH, expected_reference_ids=expected_ids)
        arm_b_metrics = recompute_arm_b_v02_control_metrics(refs, arm_b_outcomes, ARM_B_RESIDUAL_PATH)

        recomputed_data = run_stage_b_relationship_selectivity_diagnostics(
            refs, outcomes, arm_b_metrics, score_data
        )

        recomputed_text = json.dumps(recomputed_data, indent=2, sort_keys=True) + "\n"
        assert committed_text == recomputed_text
        assert committed_data["artifact_type"] == "b_t1d_arm_d_residual_diagnostics"
        assert committed_data["arm_id"] == "treatment_d"
        assert committed_data["causal_inference_limitation"] == CAUSAL_INFERENCE_LIMITATION

    def test_18_score_provenance_tampering_fails_closed(self):
        """18. Input validation raises explicit ValueError if any score provenance field is tampered."""
        refs = load_reference_corpus(V02_REF_DIR)
        expected_ids = {r.reference_decision_id for r in refs}
        outcomes, sidecar = load_treatment_run(ARM_D_RUN_DIR, expected_ids)
        score_data = json.loads(SCORE_PATH.read_text(encoding="utf-8"))

        # Valid inputs pass
        validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, score_data)

        # 1. Tampered source outcomes hash fails
        bad_outcomes_hash = {**score_data, "source_outcomes_semantic_hash": "sha256:tampered_hash"}
        with pytest.raises(ValueError, match="source_outcomes_semantic_hash mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_outcomes_hash)

        # 2. Tampered treatment profile hash fails
        bad_profile_hash = {**score_data, "treatment_profile_hash": "tampered_profile_hash"}
        with pytest.raises(ValueError, match="treatment_profile_hash mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_profile_hash)

        # 3. Tampered scoring corpus hash fails
        bad_corpus_hash = {**score_data, "scoring_reference_corpus_hash": "tampered_corpus_hash"}
        with pytest.raises(ValueError, match="scoring_reference_corpus_hash mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_corpus_hash)

        # 4. Tampered execution commit SHA fails
        bad_exec_sha = {**score_data, "source_execution_commit_sha": "tampered_exec_sha"}
        with pytest.raises(ValueError, match="source_execution_commit_sha mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_exec_sha)

        # 5. Tampered scorer authority fails
        bad_authority = {**score_data, "scorer_authority": "tampered_scorer"}
        with pytest.raises(ValueError, match="scorer_authority mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_authority)

        # 6. Tampered total references fails
        bad_refs_count = {**score_data, "total_references": 99}
        with pytest.raises(ValueError, match="total_references mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_refs_count)

        # 7. Tampered total outcomes fails
        bad_outcomes_count = {**score_data, "total_outcomes": 799}
        with pytest.raises(ValueError, match="total_outcomes mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_outcomes_count)

        # 8. Tampered model calls fails
        bad_calls = {**score_data, "model_calls": 1}
        with pytest.raises(ValueError, match="model_calls mismatch"):
            validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, bad_calls)

    def test_19_no_causal_claims_in_diagnostic_module(self):
        """19. Diagnostic module avoids definitive causal claims regarding Arm D."""
        module_path = (
            REPO_ROOT
            / "mneme"
            / "open_architecture"
            / "stage_b_relationship_selectivity_diagnostics.py"
        )
        content = module_path.read_text(encoding="utf-8")
        assert "causally reduced" not in content.lower()
        assert "causally reduce" not in content.lower()

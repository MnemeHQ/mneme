"""
tests.open_architecture.test_stage_b_relationship_residual_analysis — Tests for v0.2 Residual Analysis.

Validates the deterministic Batch 01 v0.2-grounding Arm B residual error decomposition:
1. Provenance and hash invariants (execution v0.1 corpus, scoring v0.2 corpus, profile, semantic hash).
2. Historical treatment validator remains strictly preserved (accepts v0.1, rejects v0.2).
3. Population invariants: 100 references, 59 passing, 41 failures (32 expected empty, 9 non-empty).
4. Structural classification mechanical partition (32 + 2 + 3 + 4 = 41).
5. Mixed-cause references diagnostics (helix-010, helix-012, helix-013, helix-019).
6. Target boundary anomalies (null target in helix-019, file path in adrkit-015).
7. Target entity attribution and wrong-type target mappings (18/18 recovered, 12 exact, 6 wrong type).
8. Unresolved evidence handling (empty/missing/unmatched evidence fail-safes to 'unresolved').
9. Zero model/network calls and runtime architecture boundaries.
10. Persisted artifact byte consistency and schema completeness.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.harness import (
    load_reference_corpus,
)
from mneme.open_architecture.stage_b_relationship_residual_analysis import (
    ADJUDICATION_ONTOLOGY_GAP,
    ARM_ID,
    BEHAVIOUR_CONFLICTING_TYPE_EXTRA,
    BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION,
    BEHAVIOUR_EXTRA_RELATIONSHIP,
    BEHAVIOUR_TARGET_BOUNDARY_ANOMALY,
    BEHAVIOUR_WRONG_TYPE_RECOVERY,
    CTX_CONTEXTUAL_RELATED_METADATA,
    CTX_LIFECYCLE_REVISION_HISTORY,
    CTX_NARRATIVE_BODY,
    CTX_UNRESOLVED,
    EXPERIMENT_ID,
    FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH,
    FROZEN_ARM_B_PROFILE_HASH,
    FROZEN_EXECUTION_REFERENCE_CORPUS_HASH,
    FROZEN_SCORING_REFERENCE_CORPUS_HASH,
    ORDERED_EVIDENCE_CONTEXT_TAGS,
    STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS,
    STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE,
    STRUCTURAL_PURE_TYPE_CONFUSION,
    STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS,
    classify_reference_structure,
    detect_evidence_context,
    run_residual_error_analysis,
    write_residual_error_decomposition_v0_2,
)
from mneme.open_architecture.stage_b_relationship_treatment_experiment import (
    compute_treatment_semantic_content_hash,
    load_treatment_outcomes,
    validate_frozen_reference_corpus,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V01_REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"
V02_REF_DIR = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "revisions"
    / "batch_01_v0.2-grounding"
    / "reference_decisions"
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
ARTIFACT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "treatments"
    / "b_t1c"
    / "arm_b"
    / "residual_error_decomposition_v0.2_grounding.json"
)


class TestStageBRelationshipResidualAnalysis:
    """Test suite for O1A Arm B residual error decomposition against v0.2."""

    def test_01_provenance_and_hash_invariants(self):
        """1. Provenance hashes match preregistered authorities."""
        assert FROZEN_EXECUTION_REFERENCE_CORPUS_HASH == "0455bd66aae52551c35b37a63c2d185f"
        assert FROZEN_SCORING_REFERENCE_CORPUS_HASH == "700a569e24bf90707ba14ff65eea2ab5"
        assert FROZEN_ARM_B_PROFILE_HASH == "e4b6bad47ebcc290924782172fb96d8d"
        assert (
            FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH
            == "sha256:778f05574d0e835fca893c216c4e240c15e0f30a11893812089dc691b3376092"
        )

        # Content hash check for directories and files
        v01_hash = compute_reference_corpus_content_hash(V01_REF_DIR)
        assert v01_hash == FROZEN_EXECUTION_REFERENCE_CORPUS_HASH

        v02_hash = compute_reference_corpus_content_hash(V02_REF_DIR)
        assert v02_hash == FROZEN_SCORING_REFERENCE_CORPUS_HASH

        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        assert compute_treatment_semantic_content_hash(outcomes) == FROZEN_ARM_B_OUTCOMES_SEMANTIC_HASH

    def test_02_historical_treatment_validator_preservation(self):
        """2. Frozen B-T1C treatment validator still accepts v0.1 only and strictly rejects v0.2."""
        v01_refs = load_reference_corpus(V01_REF_DIR)
        v02_refs = load_reference_corpus(V02_REF_DIR)

        # Accepts v0.1
        val_hash = validate_frozen_reference_corpus(v01_refs)
        assert val_hash == "0455bd66aae52551c35b37a63c2d185f"

        # Rejects v0.2 fail-closed
        with pytest.raises(ValueError, match="Reference corpus content hash mismatch"):
            validate_frozen_reference_corpus(v02_refs)

    def test_03_population_invariants(self):
        """3. Total 100 references, exactly 59 passing, exactly 41 failures."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)

        analysis = run_residual_error_analysis(v02_refs, outcomes)
        assert analysis["total_references"] == 100
        assert analysis["passing_references"] == 59
        assert analysis["failing_references"] == 41

        # 32 empty false positives and 9 non-empty mismatches
        empty_failures = [
            f for f in analysis["failures"]
            if f["reference_structural_class"] == STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE
        ]
        assert len(empty_failures) == 32

        non_empty_failures = [
            f for f in analysis["failures"]
            if f["reference_structural_class"] != STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE
        ]
        assert len(non_empty_failures) == 9

    def test_04_structural_classification_mechanical_partition(self):
        """4. Mechanical derivation of Layer 1 structural classes partitions all 41 failures."""
        # Unit behavior
        # Empty
        assert classify_reference_structure(set(), {("depends_on", "0001")}) == STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE
        # Pure type confusion
        assert (
            classify_reference_structure({("requires", "0005")}, {("refines", "0005")})
            == STRUCTURAL_PURE_TYPE_CONFUSION
        )
        # Exact expected plus extras
        assert (
            classify_reference_structure(
                {("supersedes", "0005")},
                {("supersedes", "0005"), ("depends_on", "0014")},
            )
            == STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS
        )
        # Type confusion plus extras
        assert (
            classify_reference_structure(
                {("requires", "0014")},
                {("depends_on", "0014"), ("depends_on", "0001")},
            )
            == STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS
        )

        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        analysis = run_residual_error_analysis(v02_refs, outcomes)

        counts = analysis["structural_class_counts"]
        assert counts[STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE] == 32
        assert counts[STRUCTURAL_PURE_TYPE_CONFUSION] == 2
        assert counts[STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS] == 3
        assert counts[STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS] == 4
        assert sum(counts.values()) == 41

    def test_05_mixed_cause_references_diagnostics(self):
        """5. Mixed-cause references show multiple distinct tuple-level context tags."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        analysis = run_residual_error_analysis(v02_refs, outcomes)
        fail_map = {f["reference_id"]: f for f in analysis["failures"]}

        # ref-helix-010: related metadata + narrative body
        f10 = fail_map["ref-helix-010"]
        c10 = f10["summary_counts"]["evidence_context_counts"]
        assert c10.get(CTX_CONTEXTUAL_RELATED_METADATA, 0) == 2
        assert c10.get(CTX_NARRATIVE_BODY, 0) == 1

        # ref-helix-012: 7 related metadata + 4 narrative body
        f12 = fail_map["ref-helix-012"]
        c12 = f12["summary_counts"]["evidence_context_counts"]
        assert c12.get(CTX_CONTEXTUAL_RELATED_METADATA, 0) == 7
        assert c12.get(CTX_NARRATIVE_BODY, 0) == 4

        # ref-helix-013: 6 related metadata + 6 narrative body + 1 ambiguous/unresolved
        f13 = fail_map["ref-helix-013"]
        c13 = f13["summary_counts"]["evidence_context_counts"]
        assert c13.get(CTX_CONTEXTUAL_RELATED_METADATA, 0) == 6
        assert c13.get(CTX_NARRATIVE_BODY, 0) == 6
        assert c13.get(CTX_UNRESOLVED, 0) == 1

        # ref-helix-019: 4 related metadata + 2 ambiguous/unresolved
        f19 = fail_map["ref-helix-019"]
        c19 = f19["summary_counts"]["evidence_context_counts"]
        assert c19.get(CTX_CONTEXTUAL_RELATED_METADATA, 0) == 4
        assert c19.get(CTX_UNRESOLVED, 0) == 2

    def test_06_target_boundary_anomalies(self):
        """6. Target boundary anomalies (null and non-canonical path) are tagged correctly."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        analysis = run_residual_error_analysis(v02_refs, outcomes)
        fail_map = {f["reference_id"]: f for f in analysis["failures"]}

        # ref-helix-019 has exception_to None
        t_null = next(
            t for t in fail_map["ref-helix-019"]["per_tuple_diagnostics"]
            if t["target_reference"] is None
        )
        assert BEHAVIOUR_TARGET_BOUNDARY_ANOMALY in t_null["prediction_behaviour_tags"]

        # ref-adrkit-015 has entity-identity.md
        t_path = next(
            t for t in fail_map["ref-adrkit-015"]["per_tuple_diagnostics"]
            if t["target_reference"] == "entity-identity.md"
        )
        assert BEHAVIOUR_TARGET_BOUNDARY_ANOMALY in t_path["prediction_behaviour_tags"]

        # Exactly 2 target boundary anomalies across entire corpus
        assert analysis["prediction_behaviour_aggregate_counts"][BEHAVIOUR_TARGET_BOUNDARY_ANOMALY] == 2

    def test_07_target_attribution_and_wrong_type_mappings(self):
        """7. Target entity recall is 18/18 with exactly 6 wrong-type recoveries and 1 conflicting extra."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        analysis = run_residual_error_analysis(v02_refs, outcomes)
        fail_map = {f["reference_id"]: f for f in analysis["failures"]}

        attr = analysis["target_attribution_totals"]
        assert attr["total_expected_tuples"] == 18
        assert attr["target_entity_recovered_any_type"] == 18
        assert attr["exact_type_exact_target"] == 12
        assert attr["wrong_type_recovery"] == 6
        assert attr["conflicting_type_extra"] == 1

        # Check prediction behaviour counts
        pb_counts = analysis["prediction_behaviour_aggregate_counts"]
        assert pb_counts[BEHAVIOUR_WRONG_TYPE_RECOVERY] == 6
        assert pb_counts[BEHAVIOUR_CONFLICTING_TYPE_EXTRA] == 1
        assert pb_counts[BEHAVIOUR_EXTRA_RELATIONSHIP] == 105
        assert pb_counts[BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION] == 72
        assert pb_counts[BEHAVIOUR_TARGET_BOUNDARY_ANOMALY] == 2

        # Check conflicting extra in ref-adrkit-016
        c16 = fail_map["ref-adrkit-016"]["conflicting_type_extra_mappings"]
        assert len(c16) == 1
        assert c16[0]["target_reference"] == "0012"
        assert c16[0]["expected_type"] == "requires"
        assert c16[0]["conflicting_predicted_type"] == "refines"

        # Check the 6 wrong type recoveries
        expected_wrong_cases = {
            "ref-gsa-agentic-coding-quickstart-002": ("0005", "requires", "refines"),
            "ref-helix-001": ("0014", "requires", "depends_on"),
            "ref-helix-002": ("0002", "requires", "depends_on"),
            "ref-helix-006": ("0004", "requires", "depends_on"),
            "ref-helix-008": ("0002", "requires", "refines"),
            "ref-adrkit-015": ("0012", "refines", "depends_on"),
        }
        for ref_id, (targ, exp_t, pred_t) in expected_wrong_cases.items():
            mappings = fail_map[ref_id]["wrong_type_target_mappings"]
            assert len(mappings) == 1, f"Expected 1 wrong type mapping in {ref_id}"
            assert mappings[0]["target_reference"] == targ
            assert mappings[0]["expected_type"] == exp_t
            assert mappings[0]["predicted_type"] == pred_t

        # Check confusion matrix
        matrix = analysis["target_type_confusion_matrix"]
        assert matrix["refines"]["depends_on"] == 1  # ref-adrkit-015 (0012)
        assert matrix["refines"]["refines"] == 4
        assert matrix["requires"]["depends_on"] == 3  # helix-001, 002, 006
        assert matrix["requires"]["refines"] == 2  # gsa-002, helix-008
        assert matrix["requires"]["requires"] == 5  # adrkit-016 (5 tuples)
        assert matrix["supersedes"]["supersedes"] == 3  # gsa-013 (2 tuples), adrkit-013 (1 tuple)

    def test_08_unresolved_evidence_handling(self):
        """8. Unresolved and ambiguous evidence fallback fails closed without guessing or first-match-wins."""
        # 1. Single unique match resolves normally
        raw_unique = "Header line\n**Related:** ADR-0005 unique occurrence here\nFooter line"
        ctx1, loc1 = detect_evidence_context("ref-test", "0005", "unique occurrence here", raw_unique)
        assert ctx1 == CTX_CONTEXTUAL_RELATED_METADATA
        assert loc1 == "related_metadata_line_1"

        # 2. Missing or empty evidence fails closed
        ctx_m1, loc_m1 = detect_evidence_context("ref-test", "0005", None, raw_unique)
        assert ctx_m1 == CTX_UNRESOLVED
        assert loc_m1 == "missing_evidence"

        ctx_m2, loc_m2 = detect_evidence_context("ref-test", "0005", "   ", raw_unique)
        assert ctx_m2 == CTX_UNRESOLVED
        assert loc_m2 == "missing_evidence"

        # 3. Completely unreferenced phrase fails closed (zero matches)
        ctx_zero, loc_zero = detect_evidence_context(
            "ref-test", "0005", "Completely unreferenced phrase not found in candidate", raw_unique
        )
        assert ctx_zero == CTX_UNRESOLVED
        assert loc_zero == "unresolved"

        # 4. Duplicated exact line match fails closed (ambiguous_normalized_line_match)
        raw_dup_line = (
            "Line 0: preamble\n"
            "Line 1: Identical evidence quote for testing ambiguity.\n"
            "Line 2: intermediate text\n"
            "Line 3: Identical evidence quote for testing ambiguity.\n"
        )
        ctx_dup1, loc_dup1 = detect_evidence_context(
            "ref-test", "0005", "Identical evidence quote for testing ambiguity.", raw_dup_line
        )
        assert ctx_dup1 == CTX_UNRESOLVED
        assert loc_dup1 == "ambiguous_normalized_line_match"

        # 5. Duplicated clause match fails closed (ambiguous_clause_match)
        raw_dup_clause = (
            "Line 0: preamble\n"
            "Line 1: ADR [0005](0005.md) repeated clause phrase\n"
            "Line 2: intermediate text\n"
            "Line 3: ADR [0005](0005.md) repeated clause phrase\n"
        )
        ctx_dup2, loc_dup2 = detect_evidence_context(
            "ref-test", "0005", "ADR [0005](0005.md) repeated clause phrase ... secondary clause", raw_dup_clause
        )
        assert ctx_dup2 == CTX_UNRESOLVED
        assert loc_dup2 == "ambiguous_clause_match"

        # 6. Duplicated target context fallback match fails closed (ambiguous_target_context_match)
        raw_dup_ctx = (
            "Line 0: preamble\n"
            "Line 1: ADR-0005 is deployed with custom parameter configurations for the service.\n"
            "Line 2: middle text\n"
            "Line 3: ADR-0005 was verified with custom parameter configurations in staging.\n"
        )
        ctx_dup3, loc_dup3 = detect_evidence_context(
            "ref-test", "0005", "ADR-0005 has custom parameter configurations elsewhere", raw_dup_ctx
        )
        assert ctx_dup3 == CTX_UNRESOLVED
        assert loc_dup3 == "ambiguous_target_context_match"

    def test_09_zero_network_and_architecture_boundaries(self):
        """9. Zero network/model calls and canonical runtime modules remain unimported."""
        module_path = (
            REPO_ROOT
            / "mneme"
            / "open_architecture"
            / "stage_b_relationship_residual_analysis.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))

        forbidden_prefixes = (
            "mneme.decision_retriever",
            "mneme.conflict_detector",
            "mneme.enforcer",
            "mneme.memory_store",
            "mneme.decision_index",
            "mneme.integrations",
            "anthropic",
            "httpx",
            "requests",
            "urllib",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        assert not alias.name.startswith(prefix), f"Forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not node.module.startswith(prefix), f"Forbidden from-import: {node.module}"

    def test_10_persisted_artifact_consistency(self):
        """10. Persisted JSON artifact matches generator output byte-identically."""
        assert ARTIFACT_PATH.is_file(), f"Artifact missing: {ARTIFACT_PATH}"
        committed_text = ARTIFACT_PATH.read_text(encoding="utf-8")
        committed_data = json.loads(committed_text)

        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        generated_data = run_residual_error_analysis(v02_refs, outcomes)

        # Validate top-level metadata
        assert committed_data["artifact_type"] == "b_t1c_arm_b_residual_error_decomposition_v0.2_grounding"
        assert committed_data["arm_id"] == "treatment_b"
        assert committed_data["experiment_id"] == "b-t1c-relationship-treatment"
        assert committed_data["model_calls"] == 0
        assert committed_data["total_references"] == 100
        assert committed_data["passing_references"] == 59
        assert committed_data["failing_references"] == 41

        # Re-running generator produces exact match
        re_generated_text = json.dumps(generated_data, indent=2, sort_keys=True) + "\n"
        assert committed_text == re_generated_text

    def test_11_adjudicated_ontology_gap_separation(self):
        """11. Ontology gap is separated from evidence context and properly tagged at reference level."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        analysis = run_residual_error_analysis(v02_refs, outcomes)
        fail_map = {f["reference_id"]: f for f in analysis["failures"]}

        # Ontology gap must NOT be an evidence context category
        assert "adjudicated_ontology_gap" not in analysis["evidence_context_aggregate_counts"]
        assert list(analysis["evidence_context_aggregate_counts"].keys()) == sorted(list(ORDERED_EVIDENCE_CONTEXT_TAGS))
        assert sum(analysis["evidence_context_aggregate_counts"].values()) == 113

        # Reference-level ontology gap counts (tuple count is not reported)
        assert analysis["adjudicated_ontology_gap_references"] == 1
        assert "adjudicated_ontology_gap_count" not in analysis

        # ref-helix-020 is tagged with adjudicated_ontology_gap at reference level
        f20 = fail_map["ref-helix-020"]
        assert f20["adjudicated_ontology_gap"] is True

        # Tuples from ref-helix-020 have mechanically observed context and no tuple-level ontology gap tag
        for t in f20["per_tuple_diagnostics"]:
            assert "adjudicated_ontology_gap" not in t
            assert ADJUDICATION_ONTOLOGY_GAP not in t["causal_tags"]
            assert t["evidence_context_tag"] in [CTX_NARRATIVE_BODY, CTX_CONTEXTUAL_RELATED_METADATA, CTX_LIFECYCLE_REVISION_HISTORY, CTX_UNRESOLVED]

        # Other failing references have adjudicated_ontology_gap == False
        for ref_id, f in fail_map.items():
            if ref_id != "ref-helix-020":
                assert f["adjudicated_ontology_gap"] is False

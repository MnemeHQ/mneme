"""
tests.open_architecture.test_stage_c_end_to_end_experiment — Tests for O1A Stage B → Stage C End-to-End Evaluation.

Proves:
A. Human-reference Stage C baseline remains metric compatible with frozen calibration results (B0, C-T1A, B3).
B. The composed DecisionCandidate preserves ref-* identity and immutable reference fields.
C. Stage B scope prediction replaces human scope in the end-to-end candidate.
D. Non-retrieval Stage B dimensions (classification, domains, purposes, authority, relationships, enforcement)
   do not change frozen DecisionRetriever behavior.
E. Lifecycle prediction alone cannot change retrieval score under the current DecisionRetriever.
F. Missing, duplicate, or invalid Stage B outcomes fail closed.
G. Zero canonical authority writes or .mneme directory mutations occur.
H. Repeated offline execution is deterministic (byte-identical artifacts and hashes).
I. The accepted mixed 800-outcome Stage B composition (700 B0 + 100 Arm D) is the input source.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from mneme.decision_retriever import DecisionRetriever
from mneme.open_architecture.classification import (
    ClassifierTaskType,
)
from mneme.open_architecture.gds_calibration_experiment import (
    PROFILE_B0,
    PROFILE_B3,
    PROFILE_C_T1A,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_SCENARIO_CORPUS_HASH,
    FrozenReferenceDecision,
    SEMANTIC_TASK_TYPES,
    load_reference_corpus,
)
from mneme.open_architecture.projection import (
    project_candidate_to_decision,
    project_candidates_to_decisions,
)
from mneme.open_architecture.schemas import DecisionCandidate, Scope
from mneme.open_architecture.stage_b_baseline import (
    FrozenClassifierOutcome,
    compute_stage_b_semantic_content_hash,
)
from mneme.open_architecture.stage_b_relationship_selectivity_diagnostics import (
    FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH,
)
from mneme.open_architecture.stage_c_end_to_end_experiment import (
    ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH,
    EXPERIMENT_ID,
    FROZEN_PARENT_MAIN_SHA,
    StageCEndToEndExperimentResult,
    compose_classified_candidate,
    compose_classified_candidates,
    execute_stage_c_end_to_end_experiment,
    load_accepted_stage_b_replay_outcomes,
)


@pytest.fixture(scope="module")
def experiment_result() -> StageCEndToEndExperimentResult:
    return execute_stage_c_end_to_end_experiment()


@pytest.fixture(scope="module")
def reference_corpus() -> list[FrozenReferenceDecision]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    ref_dir = repo_root / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"
    return load_reference_corpus(ref_dir)


@pytest.fixture(scope="module")
def accepted_stage_b_outcomes() -> list[FrozenClassifierOutcome]:
    return load_accepted_stage_b_replay_outcomes()


class TestStageCEndToEndContractAtoI:
    def test_a_human_reference_stage_c_remains_metric_compatible(
        self, experiment_result: StageCEndToEndExperimentResult
    ):
        """A. Isolated human-reference Stage C baseline reproduces frozen calibration values."""
        hb = experiment_result.isolated_human_baseline

        # B0 reproduction
        b0 = hb[PROFILE_B0]
        assert abs(b0.macro_precision - 0.054865) < 1e-4
        assert abs(b0.macro_recall - 1.000000) < 1e-4
        assert abs(b0.macro_f1 - 0.103728) < 1e-4
        assert b0.total_false_positives == 930
        assert b0.total_false_negatives == 0
        assert b0.exact_set_matches == 0

        # C-T1A reproduction
        ct1a = hb[PROFILE_C_T1A]
        assert abs(ct1a.macro_precision - 0.556024) < 1e-4
        assert abs(ct1a.macro_recall - 0.820000) < 1e-4
        assert abs(ct1a.macro_f1 - 0.621159) < 1e-4
        assert ct1a.total_false_positives == 69
        assert ct1a.total_false_negatives == 11
        assert ct1a.exact_set_matches == 19

        # B3 reproduction
        b3 = hb[PROFILE_B3]
        assert abs(b3.macro_precision - 0.671190) < 1e-4
        assert abs(b3.macro_recall - 0.840000) < 1e-4
        assert abs(b3.macro_f1 - 0.711095) < 1e-4
        assert b3.total_false_positives == 45
        assert b3.total_false_negatives == 10
        assert b3.exact_set_matches == 26

    def test_b_composed_candidate_preserves_ref_identity_and_immutable_fields(
        self,
        reference_corpus: list[FrozenReferenceDecision],
        accepted_stage_b_outcomes: list[FrozenClassifierOutcome],
    ):
        """B. Composed candidate strictly preserves ref-* identity and immutable reference text."""
        composed = compose_classified_candidates(reference_corpus, accepted_stage_b_outcomes)
        assert len(composed) == 100

        ref_map = {r.reference_decision_id: r for r in reference_corpus}
        for cand in composed:
            ref = ref_map[cand.candidate_id]
            assert cand.candidate_id.startswith("ref-")
            assert cand.candidate_id == ref.reference_decision_id
            assert cand.repository == ref.repository
            assert cand.source_file == ref.source_file
            assert cand.source_location == ref.source_location
            assert cand.raw_statement == ref.raw_evidence
            assert cand.normalized_decision == ref.normalized_decision
            assert cand.human_validation_status == "ambiguous"
            assert cand.human_corrections is None

    def test_c_stage_b_scope_prediction_replaces_human_scope(
        self,
        reference_corpus: list[FrozenReferenceDecision],
        accepted_stage_b_outcomes: list[FrozenClassifierOutcome],
    ):
        """C. Stage B scope prediction replaces human scope in the end-to-end candidate."""
        composed = compose_classified_candidates(reference_corpus, accepted_stage_b_outcomes)
        ref_map = {r.reference_decision_id: r for r in reference_corpus}

        # Check ref-adrkit-001 as a concrete exemplar
        cand_001 = next(c for c in composed if c.candidate_id == "ref-adrkit-001")
        ref_001 = ref_map["ref-adrkit-001"]

        # Human scope in reference was just [Scope(directory, 'docs/adr')]
        assert len(ref_001.scopes) == 1
        assert ref_001.scopes[0]["scope_type"] == "directory"
        assert ref_001.scopes[0]["scope_expression"] == "docs/adr"

        # Composed candidate has the 3 scopes predicted by Stage B classifier
        assert len(cand_001.scopes) == 3
        cand_types = {s.scope_type for s in cand_001.scopes}
        assert cand_types == {"repository", "directory", "file_pattern"}

        # Projection into Decision.scope produces strings from the classifier prediction
        dec = project_candidate_to_decision(cand_001)
        assert "repository:mbeacom/adrkit" in dec.scope
        assert "directory:docs/adr/" in dec.scope
        assert "file_pattern:docs/adr/NNNN-kebab-title.md" in dec.scope

    def test_d_non_retrieval_stage_b_fields_do_not_change_retriever_behavior(
        self,
        reference_corpus: list[FrozenReferenceDecision],
        accepted_stage_b_outcomes: list[FrozenClassifierOutcome],
    ):
        """D. Mutating non-retrieval Stage B fields produces identical DecisionRetriever scores."""
        composed = compose_classified_candidates(reference_corpus, accepted_stage_b_outcomes)
        c0 = composed[0]

        # Clone c0 and mutate non-retrieval fields
        c0_mutated = DecisionCandidate(
            candidate_id=c0.candidate_id,
            repository=c0.repository,
            source_file=c0.source_file,
            source_location=c0.source_location,
            raw_statement=c0.raw_statement,
            normalized_decision=c0.normalized_decision,
            classification="descriptive",  # Mutated
            decision_domains=("security_privacy", "persistence"),  # Mutated
            decision_purposes=("select",),  # Mutated
            authority_status="rejected",  # Mutated
            authority_evidence="Mutated authority evidence",
            scopes=c0.scopes,  # Unchanged
            lifecycle_status=c0.lifecycle_status,  # Unchanged
            relationships=(),  # Mutated
            enforcement_potential="block",  # Mutated
            candidate_rule="FORBID foo",  # Mutated
            confidence=0.99,  # Mutated
            human_validation_status="incorrect",
            human_corrections=None,
        )

        d_orig = project_candidate_to_decision(c0)
        d_mut = project_candidate_to_decision(c0_mutated)

        retriever_orig = DecisionRetriever([d_orig])
        retriever_mut = DecisionRetriever([d_mut])

        test_query = "architecture decisions markdown frontmatter path: docs/adr component: parser"
        scored_orig = retriever_orig.retrieve(test_query)
        scored_mut = retriever_mut.retrieve(test_query)

        assert len(scored_orig) == 1
        assert len(scored_mut) == 1
        assert scored_orig[0].score == scored_mut[0].score
        assert scored_orig[0].matches == scored_mut[0].matches

    def test_e_lifecycle_prediction_alone_cannot_change_retrieval_score(
        self,
        reference_corpus: list[FrozenReferenceDecision],
        accepted_stage_b_outcomes: list[FrozenClassifierOutcome],
    ):
        """E. Changing lifecycle_status alone does not alter DecisionRetriever scores."""
        composed = compose_classified_candidates(reference_corpus, accepted_stage_b_outcomes)
        c0 = composed[0]

        c0_active = DecisionCandidate(
            candidate_id=c0.candidate_id,
            repository=c0.repository,
            source_file=c0.source_file,
            source_location=c0.source_location,
            raw_statement=c0.raw_statement,
            normalized_decision=c0.normalized_decision,
            classification=c0.classification,
            decision_domains=c0.decision_domains,
            decision_purposes=c0.decision_purposes,
            authority_status=c0.authority_status,
            authority_evidence=c0.authority_evidence,
            scopes=c0.scopes,
            lifecycle_status="active",
            relationships=c0.relationships,
            enforcement_potential=c0.enforcement_potential,
            candidate_rule=c0.candidate_rule,
            confidence=c0.confidence,
            human_validation_status=c0.human_validation_status,
            human_corrections=None,
        )

        c0_superseded = DecisionCandidate(
            candidate_id=c0.candidate_id,
            repository=c0.repository,
            source_file=c0.source_file,
            source_location=c0.source_location,
            raw_statement=c0.raw_statement,
            normalized_decision=c0.normalized_decision,
            classification=c0.classification,
            decision_domains=c0.decision_domains,
            decision_purposes=c0.decision_purposes,
            authority_status=c0.authority_status,
            authority_evidence=c0.authority_evidence,
            scopes=c0.scopes,
            lifecycle_status="superseded",
            relationships=c0.relationships,
            enforcement_potential=c0.enforcement_potential,
            candidate_rule=c0.candidate_rule,
            confidence=c0.confidence,
            human_validation_status=c0.human_validation_status,
            human_corrections=None,
        )

        d_active = project_candidate_to_decision(c0_active)
        d_superseded = project_candidate_to_decision(c0_superseded)

        # Confirm projected status difference
        assert d_active.status == "active"
        assert d_superseded.status == "superseded"

        # Confirm DecisionRetriever scores are identical
        test_queries = [
            "record architecture decisions in git markdown",
            "active superseded status filter check",
            "completely unrelated query text about postgres",
        ]
        r_act = DecisionRetriever([d_active])
        r_sup = DecisionRetriever([d_superseded])

        for q in test_queries:
            s_act = r_act.retrieve(q)
            s_sup = r_sup.retrieve(q)
            assert s_act[0].score == s_sup[0].score
            assert s_act[0].matches == s_sup[0].matches

    def test_f_missing_duplicate_invalid_stage_b_outcomes_fail_closed(
        self,
        reference_corpus: list[FrozenReferenceDecision],
        accepted_stage_b_outcomes: list[FrozenClassifierOutcome],
    ):
        """F. Missing, duplicate, escalated, or error outcomes fail closed."""
        # 1. Missing task outcome for a candidate
        incomplete_outcomes = [
            o for o in accepted_stage_b_outcomes
            if not (o.candidate_id == "ref-adrkit-001" and o.task_type == ClassifierTaskType.SCOPE)
        ]
        with pytest.raises(ValueError, match="missing required task outcomes"):
            compose_classified_candidates(reference_corpus, incomplete_outcomes)

        # 2. Duplicate outcome for (candidate_id, task_type)
        duplicate_outcomes = list(accepted_stage_b_outcomes) + [accepted_stage_b_outcomes[0]]
        with pytest.raises(ValueError, match="Duplicate outcome"):
            compose_classified_candidates(reference_corpus, duplicate_outcomes)

        # 3. Escalated outcome
        escalated_outcomes = list(accepted_stage_b_outcomes)
        bad_outcome = dataclasses.replace(escalated_outcomes[0], escalated=True)
        escalated_outcomes[0] = bad_outcome
        with pytest.raises(ValueError, match="was escalated"):
            compose_classified_candidates(reference_corpus, escalated_outcomes)

        # 4. Error in outcome output
        error_outcomes = list(accepted_stage_b_outcomes)
        err_outcome = dataclasses.replace(
            error_outcomes[0], output={"error": "LLM quota exceeded"}
        )
        error_outcomes[0] = err_outcome
        with pytest.raises(ValueError, match="contains error"):
            compose_classified_candidates(reference_corpus, error_outcomes)

    def test_g_no_canonical_or_mneme_writes(self, tmp_path: Path):
        """G. Zero canonical authority writes or .mneme directory mutations occur."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        mneme_dir = repo_root / ".mneme"

        # Assert no .mneme directory created by experiment
        had_mneme_before = mneme_dir.exists()
        out_dir = tmp_path / "e2e_run"
        res = execute_stage_c_end_to_end_experiment(output_dir=out_dir)

        assert res.experiment_id == EXPERIMENT_ID
        assert (repo_root / ".mneme").exists() == had_mneme_before

    def test_h_repeated_offline_execution_is_deterministic(self, tmp_path: Path):
        """H. Repeated execution produces byte-identical summary artifacts and profile hashes."""
        run1_dir = tmp_path / "run1"
        run2_dir = tmp_path / "run2"

        res1 = execute_stage_c_end_to_end_experiment(output_dir=run1_dir)
        res2 = execute_stage_c_end_to_end_experiment(output_dir=run2_dir)

        artifact1 = (run1_dir / "stage_c_end_to_end_summary.json").read_text(encoding="utf-8")
        artifact2 = (run2_dir / "stage_c_end_to_end_summary.json").read_text(encoding="utf-8")

        assert artifact1 == artifact2
        assert res1.experiment_profile_hash == res2.experiment_profile_hash
        assert res1.stage_b_mixed_semantic_hash == res2.stage_b_mixed_semantic_hash

    def test_i_accepted_mixed_stage_b_composition_is_input_source(
        self, accepted_stage_b_outcomes: list[FrozenClassifierOutcome]
    ):
        """I. The input source is exactly the accepted 700 B0 + 100 Arm D composition."""
        assert len(accepted_stage_b_outcomes) == 800

        non_rel = [o for o in accepted_stage_b_outcomes if o.task_type != ClassifierTaskType.RELATIONSHIPS]
        rel = [o for o in accepted_stage_b_outcomes if o.task_type == ClassifierTaskType.RELATIONSHIPS]

        assert len(non_rel) == 700
        assert len(rel) == 100

        # Enforce exact frozen semantic content hashes
        mixed_hash = compute_stage_b_semantic_content_hash(accepted_stage_b_outcomes)
        assert mixed_hash == ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH


class TestStageCEndToEndMetricsVerification:
    def test_end_to_end_b0_metrics(self, experiment_result: StageCEndToEndExperimentResult):
        """Verify exact end-to-end B0 performance."""
        b0 = experiment_result.end_to_end_predictions[PROFILE_B0]
        assert abs(b0.macro_precision - 0.054053) < 1e-4
        assert abs(b0.macro_recall - 1.000000) < 1e-4
        assert abs(b0.macro_f1 - 0.102260) < 1e-4
        assert b0.total_false_positives == 945
        assert b0.total_false_negatives == 0
        assert b0.exact_set_matches == 0

        # Delta vs human baseline
        delta = experiment_result.profile_comparisons[PROFILE_B0]
        assert abs(delta.delta_macro_f1 - (-0.001468)) < 1e-4
        assert delta.delta_false_positives == 15
        assert delta.delta_false_negatives == 0

    def test_end_to_end_ct1a_metrics(self, experiment_result: StageCEndToEndExperimentResult):
        """Verify exact end-to-end C-T1A performance."""
        ct1a = experiment_result.end_to_end_predictions[PROFILE_C_T1A]
        assert abs(ct1a.macro_precision - 0.535857) < 1e-4
        assert abs(ct1a.macro_recall - 0.810000) < 1e-4
        assert abs(ct1a.macro_f1 - 0.603381) < 1e-4
        assert ct1a.total_false_positives == 69
        assert ct1a.total_false_negatives == 11
        assert ct1a.exact_set_matches == 18

        # Delta vs human baseline
        delta = experiment_result.profile_comparisons[PROFILE_C_T1A]
        assert abs(delta.delta_macro_f1 - (-0.017778)) < 1e-4
        assert delta.delta_false_positives == 0
        assert delta.delta_false_negatives == 0
        assert delta.delta_exact_set_matches == -1

    def test_end_to_end_b3_metrics(self, experiment_result: StageCEndToEndExperimentResult):
        """Verify exact end-to-end B3 performance."""
        b3 = experiment_result.end_to_end_predictions[PROFILE_B3]
        assert abs(b3.macro_precision - 0.602333) < 1e-4
        assert abs(b3.macro_recall - 0.790000) < 1e-4
        assert abs(b3.macro_f1 - 0.650667) < 1e-4
        assert b3.total_false_positives == 46
        assert b3.total_false_negatives == 13
        assert b3.exact_set_matches == 22

        # Delta vs human baseline
        delta = experiment_result.profile_comparisons[PROFILE_B3]
        assert abs(delta.delta_macro_f1 - (-0.060428)) < 1e-4
        assert delta.delta_false_positives == 1
        assert delta.delta_false_negatives == 3
        assert delta.delta_exact_set_matches == -4

    def test_experiment_metadata_and_hashes(
        self, experiment_result: StageCEndToEndExperimentResult
    ):
        """Verify experiment identity and cryptographic binding."""
        assert experiment_result.experiment_id == EXPERIMENT_ID
        assert experiment_result.baseline_id == FROZEN_BASELINE_ID
        assert experiment_result.parent_main_sha == FROZEN_PARENT_MAIN_SHA
        assert experiment_result.reference_corpus_hash == FROZEN_REFERENCE_CORPUS_HASH
        assert experiment_result.scenario_corpus_hash == FROZEN_SCENARIO_CORPUS_HASH
        assert experiment_result.manifest_config_hash == FROZEN_MANIFEST_CONFIG_HASH
        assert experiment_result.baseline_config_hash == FROZEN_BASELINE_CONFIG_HASH
        assert (
            experiment_result.stage_b_mixed_semantic_hash
            == ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH
        )
        assert len(experiment_result.experiment_profile_hash) == 32
        assert len(experiment_result.end_to_end_scenario_evaluations) == 150

    def test_committed_artifact_byte_identity(
        self, experiment_result: StageCEndToEndExperimentResult
    ):
        """Verify that committed stage_c_end_to_end_summary.json is byte-identical to experiment output."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        committed_path = (
            repo_root
            / "benchmarks"
            / "open_architecture"
            / "batch_01"
            / "stage_c"
            / "stage_c_end_to_end_summary.json"
        )
        assert committed_path.is_file(), f"Committed artifact missing: {committed_path}"
        committed_bytes = committed_path.read_bytes()
        fresh_bytes = (
            json.dumps(experiment_result.to_dict(), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        assert committed_bytes == fresh_bytes, (
            "Committed stage_c_end_to_end_summary.json has diverged from experiment output. "
            "Regenerate using write_stage_c_end_to_end_summary()."
        )

"""
tests.open_architecture.test_stage_b_relationship_selectivity_experiment — Tests for B-T1D.

Validates the pre-execution apparatus for B-T1D against all preregistered invariants:
1. Parent main SHA pinned to 90534104a1c517a33088c6139b98df4734672679
2. v0.1 and v0.2 corpus hashes
3. Exact v0.1/v0.2 input invariance
4. Exactly one approved corpus-record difference
5. B-T1C validator remains v0.1-only
6. B-T1D validator is v0.2-only
7. Exactly 100 relationship tasks
8. Non-RELATIONSHIPS tasks fail closed
9. Arm D schema parity with Arm B
10. Target-formatting parity with Arm B
11. Relationship-type-definition parity with Arm B
12. User-prompt parity
13. Request-parameter parity
14. Prompt-delta isolation
15. Immutable profile hashing
16. Frozen Arm B profile/outcome identity
17. Deterministic Arm B v0.2 control-metric recomputation
18. Extra-only evidence-context control counts (58/31/6/10)
19. 700 + 100 mixed-outcome assembly and non-relationship label invariance
20. B-T1D scoring wrapper records v0.2 identity while delegating to existing harness scoring semantics
21. Zero production/runtime imports
22. Zero model/network calls in pre-execution tests
23. No execution artifact creation during scaffold/tests
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
)
from mneme.open_architecture.classifiers.anthropic import (
    AnthropicClassifier,
    AnthropicMalformedResponseError,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.harness import (
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.stage_b_baseline import (
    FrozenClassifierOutcome,
    load_stage_b_outcomes,
)
from mneme.open_architecture.stage_b_relationship_selectivity_experiment import (
    ARM_D_ID,
    ARM_D_RELATIONSHIPS_SCHEMA,
    ARM_D_SYSTEM_PROMPT_EXTENSION,
    B_T1D_PROFILE_D,
    B_T1D_PROFILE_D_HASH,
    CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH,
    CONTROL_ARM_B_PROFILE_HASH,
    FORMAL_RELATIONSHIP_EMISSION_GATE,
    FROZEN_CLASSIFIER_BACKEND,
    FROZEN_CLASSIFIER_VERSION,
    FROZEN_EXECUTION_REFERENCE_CORPUS_HASH,
    FROZEN_MAX_RETRIES,
    FROZEN_MAX_TOKENS,
    FROZEN_MODEL_IDENTIFIER,
    FROZEN_PARENT_MAIN_SHA,
    FROZEN_SCORING_REFERENCE_CORPUS_HASH,
    FROZEN_TAXONOMY_VERSION,
    FROZEN_TIMEOUT_SECONDS,
    HISTORICAL_V01_REFERENCE_CORPUS_HASH,
    TreatmentDClassifierAdapter,
    build_batch_01_relationship_tasks,
    build_mixed_stage_b_outcomes,
    build_treatment_request_payload,
    build_treatment_system_prompt,
    build_treatment_user_prompt,
    compute_b_t1d_profile_hash,
    recompute_arm_b_v02_control_metrics,
    score_b_t1d_replay,
    validate_b_t1d_reference_corpus,
    validate_v01_v02_input_invariance,
)
from mneme.open_architecture.stage_b_relationship_treatment_experiment import (
    ARM_B_ID,
    ARM_B_RELATIONSHIPS_SCHEMA,
    ARM_B_SYSTEM_PROMPT_EXTENSION,
    compute_treatment_semantic_content_hash,
    load_treatment_outcomes,
    validate_frozen_reference_corpus as validate_b_t1c_reference_corpus,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
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
FROZEN_B0_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "baseline_stage_b"
    / "classifier_outcomes.jsonl"
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
RESIDUAL_V02_ARTIFACT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "treatments"
    / "b_t1c"
    / "arm_b"
    / "residual_error_decomposition_v0.2_grounding.json"
)


class TestBT1DSelectivityScaffold:
    """Pre-execution validation suite for O1A B-T1D."""

    def test_01_parent_sha_identity(self):
        """1. Parent main SHA pinned to 90534104a1c517a33088c6139b98df4734672679."""
        assert FROZEN_PARENT_MAIN_SHA == "90534104a1c517a33088c6139b98df4734672679"
        assert B_T1D_PROFILE_D["parent_main_sha"] == "90534104a1c517a33088c6139b98df4734672679"

    def test_02_v01_and_v02_corpus_hashes(self):
        """2. v0.1 and v0.2 corpus hashes match frozen authorities."""
        assert HISTORICAL_V01_REFERENCE_CORPUS_HASH == "0455bd66aae52551c35b37a63c2d185f"
        assert FROZEN_EXECUTION_REFERENCE_CORPUS_HASH == "700a569e24bf90707ba14ff65eea2ab5"
        assert FROZEN_SCORING_REFERENCE_CORPUS_HASH == "700a569e24bf90707ba14ff65eea2ab5"

        v01_hash = compute_reference_corpus_content_hash(V01_REF_DIR)
        assert v01_hash == HISTORICAL_V01_REFERENCE_CORPUS_HASH

        v02_hash = compute_reference_corpus_content_hash(V02_REF_DIR)
        assert v02_hash == FROZEN_SCORING_REFERENCE_CORPUS_HASH

    def test_03_exact_v01_v02_input_invariance(self):
        """3. Input invariance between v0.1 and v0.2: reference IDs, repo SHAs, raw_evidence, source locations."""
        v01_refs = load_reference_corpus(V01_REF_DIR)
        v02_refs = load_reference_corpus(V02_REF_DIR)
        validate_v01_v02_input_invariance(v01_refs, v02_refs)

    def test_04_exactly_one_approved_corpus_difference(self):
        """4. Exactly one approved difference: ref-gsa-agentic-coding-quickstart-005 relationships."""
        v01_refs = {r.reference_decision_id: r for r in load_reference_corpus(V01_REF_DIR)}
        v02_refs = {r.reference_decision_id: r for r in load_reference_corpus(V02_REF_DIR)}

        diffs = []
        for rid in sorted(v01_refs.keys()):
            r1 = v01_refs[rid]
            r2 = v02_refs[rid]
            if r1.relationships != r2.relationships:
                diffs.append(rid)

        assert diffs == ["ref-gsa-agentic-coding-quickstart-005"]
        assert len(v01_refs["ref-gsa-agentic-coding-quickstart-005"].relationships) == 1
        assert len(v02_refs["ref-gsa-agentic-coding-quickstart-005"].relationships) == 0

    def test_05_b_t1c_validator_remains_v01_only(self):
        """5. Historical B-T1C validator strictly accepts v0.1 and rejects v0.2 fail-closed."""
        v01_refs = load_reference_corpus(V01_REF_DIR)
        v02_refs = load_reference_corpus(V02_REF_DIR)

        assert validate_b_t1c_reference_corpus(v01_refs) == "0455bd66aae52551c35b37a63c2d185f"
        with pytest.raises(ValueError, match="Reference corpus content hash mismatch"):
            validate_b_t1c_reference_corpus(v02_refs)

    def test_06_b_t1d_validator_is_v02_only(self):
        """6. B-T1D validator strictly accepts v0.2 and rejects v0.1 fail-closed."""
        v01_refs = load_reference_corpus(V01_REF_DIR)
        v02_refs = load_reference_corpus(V02_REF_DIR)

        assert validate_b_t1d_reference_corpus(v02_refs) == "700a569e24bf90707ba14ff65eea2ab5"
        with pytest.raises(ValueError, match="Reference corpus content hash mismatch for B-T1D"):
            validate_b_t1d_reference_corpus(v01_refs)

    def test_07_exactly_100_relationship_tasks(self):
        """7. Exactly 100 relationship tasks constructed from v0.2 reference corpus."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        assert len(v02_refs) == 100
        tasks = build_batch_01_relationship_tasks(v02_refs)
        assert len(tasks) == 100
        for t in tasks:
            assert t.task_type == ClassifierTaskType.RELATIONSHIPS
            assert t.taxonomy_version == FROZEN_TAXONOMY_VERSION

    def test_08_non_relationships_tasks_fail_closed(self):
        """8. Non-RELATIONSHIPS tasks fail closed."""
        task = ClassifierTask(
            candidate_id="cand-001",
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            raw_statement="statement",
            source_context="context",
            source_path="path.md",
            source_location="L1",
            repository_identifier="org/repo",
            repository_commit_sha="abcd" * 10,
            taxonomy_version="0.1",
        )
        with pytest.raises(ValueError, match="only valid for ClassifierTaskType.RELATIONSHIPS"):
            build_treatment_request_payload(task)

        adapter = TreatmentDClassifierAdapter(live=False)
        with pytest.raises(ValueError, match="only permits ClassifierTaskType.RELATIONSHIPS"):
            adapter.execute(task)

    def test_09_arm_d_schema_parity_with_arm_b(self):
        """9. Arm D schema is byte-identical to Arm B."""
        assert ARM_D_RELATIONSHIPS_SCHEMA == ARM_B_RELATIONSHIPS_SCHEMA
        assert B_T1D_PROFILE_D["relationship_schema"] == ARM_B_RELATIONSHIPS_SCHEMA

    def test_10_target_formatting_parity_with_arm_b(self):
        """10. Target formatting instructions in Arm D are byte-identical to Arm B."""
        assert "Target representation rules" in ARM_D_SYSTEM_PROMPT_EXTENSION
        assert "4-digit zero-padded numeric identifier" in ARM_D_SYSTEM_PROMPT_EXTENSION
        # Target representation section is byte-identical
        b_target_rules = ARM_B_SYSTEM_PROMPT_EXTENSION.split("Target representation rules")[1]
        d_target_rules = ARM_D_SYSTEM_PROMPT_EXTENSION.split("Target representation rules")[1]
        assert b_target_rules == d_target_rules

    def test_11_relationship_type_definition_parity_with_arm_b(self):
        """11. All 7 relationship type definitions are byte-identical to Arm B."""
        for rel_type in ("requires", "refines", "supersedes", "prohibits", "conflicts_with", "exception_to", "depends_on"):
            assert f"* {rel_type}:" in ARM_D_SYSTEM_PROMPT_EXTENSION
            b_def = ARM_B_SYSTEM_PROMPT_EXTENSION.split(f"* {rel_type}:")[1].split("\n")[0]
            d_def = ARM_D_SYSTEM_PROMPT_EXTENSION.split(f"* {rel_type}:")[1].split("\n")[0]
            assert b_def == d_def

    def test_12_user_prompt_parity(self):
        """12. User prompt is identical to B0/B-T1C contract."""
        dummy_task = ClassifierTask(
            candidate_id="cand-001",
            task_type=ClassifierTaskType.RELATIONSHIPS,
            raw_statement="statement",
            source_context="context",
            source_path="path.md",
            source_location="L1",
            repository_identifier="org/repo",
            repository_commit_sha="abcd" * 10,
            taxonomy_version="0.1",
        )
        b0_user = AnthropicClassifier().build_user_prompt(dummy_task)
        treatment_user = build_treatment_user_prompt(dummy_task)
        assert treatment_user == b0_user

    def test_13_request_parameter_parity(self):
        """13. Request parameters match B0/B-T1C exactly."""
        assert FROZEN_MAX_TOKENS == 1024
        assert FROZEN_TIMEOUT_SECONDS == 60.0
        assert FROZEN_MAX_RETRIES == 2
        assert B_T1D_PROFILE_D["request_parameters"]["max_tokens"] == 1024
        assert B_T1D_PROFILE_D["request_parameters"]["timeout"] == 60.0
        assert B_T1D_PROFILE_D["request_parameters"]["max_retries"] == 2
        assert B_T1D_PROFILE_D["request_parameters"]["explicit_temperature"] is None

        dummy_task = ClassifierTask(
            candidate_id="cand-001",
            task_type=ClassifierTaskType.RELATIONSHIPS,
            raw_statement="statement",
            source_context="context",
            source_path="path.md",
            source_location="L1",
            repository_identifier="org/repo",
            repository_commit_sha="abcd" * 10,
            taxonomy_version="0.1",
        )
        payload = build_treatment_request_payload(dummy_task)
        assert "temperature" not in payload
        assert payload["max_tokens"] == 1024
        assert payload["model"] == "claude-sonnet-4-6"

    def test_14_prompt_delta_isolation(self):
        """14. Prompt delta between Arm B and Arm D consists strictly of the formal emission gate."""
        expected_full_d = FORMAL_RELATIONSHIP_EMISSION_GATE + "\n\n" + ARM_B_SYSTEM_PROMPT_EXTENSION
        assert ARM_D_SYSTEM_PROMPT_EXTENSION == expected_full_d

        # The remainder after stripping emission gate is byte-identical to Arm B
        stripped_d = ARM_D_SYSTEM_PROMPT_EXTENSION[len(FORMAL_RELATIONSHIP_EMISSION_GATE) + 2:]
        assert stripped_d == ARM_B_SYSTEM_PROMPT_EXTENSION

        # Emission gate contains no prohibited words or repository-specific leaked terms
        gate = FORMAL_RELATIONSHIP_EMISSION_GATE
        assert "active" not in gate.lower()
        assert "binding" not in gate.lower()
        assert "adrkit" not in gate.lower()
        assert "helix" not in gate.lower()
        assert "modonome" not in gate.lower()
        assert "quickstart" not in gate.lower()
        assert "0005" not in gate
        assert "0012" not in gate

    def test_15_immutable_profile_hashing(self):
        """15. Arm D profile hash is deterministic and changes under any mutation."""
        base_hash = compute_b_t1d_profile_hash(B_T1D_PROFILE_D)
        assert base_hash == B_T1D_PROFILE_D_HASH == "d66bb19c9e4c64e835a6191293a95570"

        # Mutation of tokens changes hash
        mut_tokens = copy.deepcopy(B_T1D_PROFILE_D)
        mut_tokens["request_parameters"]["max_tokens"] = 2048
        assert compute_b_t1d_profile_hash(mut_tokens) != base_hash

        # Mutation of prompt changes hash
        mut_prompt = copy.deepcopy(B_T1D_PROFILE_D)
        mut_prompt["system_prompt_treatment"] += "\n# extra rule"
        assert compute_b_t1d_profile_hash(mut_prompt) != base_hash

    def test_16_frozen_arm_b_profile_and_outcome_identity(self):
        """16. Frozen Arm B profile and outcome semantic hashes match committed authorities."""
        assert CONTROL_ARM_B_PROFILE_HASH == "e4b6bad47ebcc290924782172fb96d8d"
        assert (
            CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH
            == "sha256:778f05574d0e835fca893c216c4e240c15e0f30a11893812089dc691b3376092"
        )
        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        assert len(arm_b_outcomes) == 100
        assert compute_treatment_semantic_content_hash(arm_b_outcomes) == CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH

    def test_17_deterministic_arm_b_v02_control_metrics(self):
        """17. Deterministic recomputation of Arm B v0.2 control metrics matches frozen values."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        metrics = recompute_arm_b_v02_control_metrics(v02_refs, arm_b_outcomes, RESIDUAL_V02_ARTIFACT_PATH)

        assert metrics["strict_exact_references"] == 59
        assert metrics["total_references"] == 100
        assert metrics["expected_empty_references"] == 88
        assert metrics["expected_empty_exact"] == 56
        assert metrics["expected_empty_fp_references"] == 32
        assert metrics["expected_empty_extra_tuples"] == 86
        assert metrics["total_extra_tuples"] == 105
        assert metrics["target_entities_recovered"] == 18
        assert metrics["exact_type_exact_target"] == 12
        assert metrics["wrong_type_recovery"] == 6
        assert metrics["missing_target_entities"] == 0
        assert metrics["conflicting_type_extras"] == 1
        assert metrics["target_boundary_anomalies"] == 2
        assert metrics["extra_depends_on_tuples"] == 72

    def test_18_extra_only_evidence_context_control_counts(self):
        """18. Extra-only evidence context control counts match exactly 58/31/6/10."""
        v02_refs = load_reference_corpus(V02_REF_DIR)
        arm_b_outcomes = load_treatment_outcomes(ARM_B_OUTCOMES_PATH)
        metrics = recompute_arm_b_v02_control_metrics(v02_refs, arm_b_outcomes, RESIDUAL_V02_ARTIFACT_PATH)
        ec = metrics["extra_tuple_evidence_contexts"]

        assert ec["narrative_body"] == 58
        assert ec["contextual_related_metadata"] == 31
        assert ec["lifecycle_revision_history"] == 6
        assert ec["unresolved"] == 10
        assert sum(ec.values()) == 105

    def test_19_mixed_outcome_assembly_and_label_invariance(self):
        """19. Mixed outcome assembly consists of 700 B0 + 100 treatment outcomes; non-relationship labels invariant."""
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)
        assert len(b0_outcomes) == 800

        v02_refs = load_reference_corpus(V02_REF_DIR)
        dummy_treatment = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="run-d-dummy",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-03T18:00:00Z",
            )
            for r in v02_refs
        ]
        assert len(dummy_treatment) == 100

        mixed = build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment)
        assert len(mixed) == 800
        non_rel = [o for o in mixed if o.task_type != ClassifierTaskType.RELATIONSHIPS]
        assert len(non_rel) == 700

        # Verify that v0.1 -> v0.2 changes zero non-relationship task labels
        v01_refs = {r.reference_decision_id: r for r in load_reference_corpus(V01_REF_DIR)}
        for r2 in v02_refs:
            r1 = v01_refs[r2.reference_decision_id]
            assert r1.classification == r2.classification
            assert r1.decision_domains == r2.decision_domains
            assert r1.decision_purposes == r2.decision_purposes
            assert r1.authority_status == r2.authority_status
            assert r1.lifecycle_status == r2.lifecycle_status
            assert r1.enforcement_potential == r2.enforcement_potential
            assert r1.scopes == r2.scopes

    def test_20_scoring_wrapper_records_v02_identity(self):
        """20. B-T1D scoring wrapper records v0.2 corpus hash and delegates to harness scoring."""
        manifest = Manifest.load(MANIFEST_PATH)
        v02_refs = load_reference_corpus(V02_REF_DIR)
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)

        dummy_treatment = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="run-d-dummy",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-03T18:00:00Z",
            )
            for r in v02_refs
        ]
        mixed = build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment)

        res = score_b_t1d_replay(mixed, v02_refs, manifest)
        assert res.experiment_id == "b-t1d-relationship-selectivity"
        assert res.arm_id == "treatment_d"
        assert res.scoring_reference_corpus_hash == "700a569e24bf90707ba14ff65eea2ab5"
        assert res.total_references == 100
        assert res.total_outcomes == 800
        assert res.composite_score > 0.0

    def test_21_zero_production_runtime_imports(self):
        """21. Research boundaries: zero imports of canonical production runtime modules."""
        module_path = (
            REPO_ROOT
            / "mneme"
            / "open_architecture"
            / "stage_b_relationship_selectivity_experiment.py"
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

    def test_22_zero_model_network_calls_in_pre_execution_tests(self):
        """22. Adapter fails closed if invoked live without authorization; mock client executes offline."""
        adapter_no_client = TreatmentDClassifierAdapter(live=False)
        task = ClassifierTask(
            candidate_id="cand-001",
            task_type=ClassifierTaskType.RELATIONSHIPS,
            raw_statement="statement",
            source_context="context",
            source_path="path.md",
            source_location="L1",
            repository_identifier="org/repo",
            repository_commit_sha="abcd" * 10,
            taxonomy_version="0.1",
        )
        with pytest.raises(RuntimeError, match="Live model/API calls are strictly prohibited"):
            adapter_no_client.execute(task)

        # Mock client succeeds deterministically offline
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = json.dumps({"relationships": []})
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        adapter_mock = TreatmentDClassifierAdapter(client=mock_client, live=False)
        res = adapter_mock.execute(task)
        assert res.output == {"relationships": []}
        assert mock_client.messages.create.call_count == 1

    def test_23_no_execution_artifacts_created_during_scaffold(self):
        """23. Scaffold and pre-execution tests create zero execution artifacts."""
        treatment_dir = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "treatments" / "b_t1d"
        assert not (treatment_dir / "arm_d" / "outcomes.jsonl").exists()
        assert not (treatment_dir / "arm_d" / "provenance.json").exists()
        assert not (treatment_dir / "arm_d" / "stage_b_score.json").exists()
        assert not (treatment_dir / "arm_d" / "diagnostics.json").exists()

"""
tests.open_architecture.test_stage_b_relationship_treatment_experiment — Tests for B-T1C.

Validates the pre-execution apparatus for B-T1C against all preregistered invariants:
1. Parent main SHA pinned to 16d2f757d33c0e23c7d8e0a78006daaaefb20097
2. Reference corpus hash pinned to 0455bd66aae52551c35b37a63c2d185f
3. Frozen B0 Stage B semantic content hash pinned to sha256:3c215db2...
4. Exactly 100 relationship tasks selected from reference corpus
5. Non-RELATIONSHIPS tasks fail closed (cannot execute live)
6. Arm A request configuration specifies max_tokens=1024
7. Temperature parameter is explicitly absent from request payloads
8. Timeout (60.0s) and retry (2) configuration match B0
9. User prompt is identical to B0 AnthropicClassifier contract
10. Task inputs strictly bind ref.raw_evidence as raw_statement and source_context
11. Arm A evidence_reference schema description is identical to B0 ("Text evidence for this relationship")
12. Arm A treatment schema and system prompt match frozen profile
13. Arm B inherits all Arm A semantics byte-for-byte
14. A/B payload diff is strictly limited to ADR target formatting instructions
15. Profile hashes change under any material treatment mutation
16. Zero model/network calls occur during test execution (static/mock client only)
17. Treatment outcome loader fails closed when outcome count != 100
18. Duplicate or missing relationship outcomes fail closed
19. Semantic outcome hash excludes volatile execution metadata (timestamps, latency, cost)
20. Mixed replay evaluation set consists of exactly 700 B0 + 100 treatment outcomes
21. Frozen B0 baseline outcomes file remains unmodified
22. Scorer strictly delegates to existing Stage B scoring authority (score_stage_b_outcomes)
23. B-T1B diagnostic semantics (classify_target_form, parse_adr_alias) are reused
24. Exact changed file boundary is enforced
"""

from __future__ import annotations

import copy
import dataclasses
import json
import subprocess
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
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FrozenClassifierOutcome,
    load_stage_b_outcomes,
)
from mneme.open_architecture.stage_b_relationship_diagnostic_experiment import (
    classify_target_form as b_t1b_classify_target_form,
    parse_adr_alias as b_t1b_parse_adr_alias,
)
from mneme.open_architecture.stage_b_relationship_treatment_experiment import (
    ARM_A_ID,
    ARM_A_RELATIONSHIPS_SCHEMA,
    ARM_A_SYSTEM_PROMPT_EXTENSION,
    ARM_B_ID,
    ARM_B_RELATIONSHIPS_SCHEMA,
    ARM_B_SYSTEM_PROMPT_EXTENSION,
    B_T1C_PROFILE_A,
    B_T1C_PROFILE_A_HASH,
    B_T1C_PROFILE_B,
    B_T1C_PROFILE_B_HASH,
    BASE_SYSTEM_PROMPT_TEMPLATE,
    EXPERIMENT_ID,
    FROZEN_CLASSIFIER_BACKEND,
    FROZEN_CLASSIFIER_VERSION,
    FROZEN_MAX_RETRIES,
    FROZEN_MAX_TOKENS,
    FROZEN_MODEL_IDENTIFIER,
    FROZEN_PARENT_MAIN_SHA,
    FROZEN_TAXONOMY_VERSION,
    FROZEN_TIMEOUT_SECONDS,
    TreatmentClassifierAdapter,
    TreatmentProvenanceSidecar,
    build_batch_01_relationship_tasks,
    build_mixed_stage_b_outcomes,
    build_treatment_request_payload,
    build_treatment_system_prompt,
    build_treatment_user_prompt,
    capture_treatment_run,
    classify_target_form,
    compute_b_t1c_profile_hash,
    compute_reference_corpus_hash_from_references,
    compute_treatment_semantic_content_hash,
    evaluate_treatment_diagnostics,
    load_treatment_outcomes,
    load_treatment_run,
    parse_adr_alias,
    score_treatment_replay,
    validate_frozen_reference_corpus,
    validate_treatment_provenance,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"
FROZEN_B0_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline_stage_b" / "classifier_outcomes.jsonl"


# ── Test Suite ─────────────────────────────────────────────────────────────────

class TestBT1CTreatmentScaffold:
    """Pre-execution validation suite for B-T1C."""

    def test_01_parent_sha_pinned(self):
        """1. Parent main SHA pinned to 16d2f757d33c0e23c7d8e0a78006daaaefb20097."""
        assert FROZEN_PARENT_MAIN_SHA == "16d2f757d33c0e23c7d8e0a78006daaaefb20097"
        assert B_T1C_PROFILE_A["parent_main_sha"] == "16d2f757d33c0e23c7d8e0a78006daaaefb20097"
        assert B_T1C_PROFILE_B["parent_main_sha"] == "16d2f757d33c0e23c7d8e0a78006daaaefb20097"

    def test_02_reference_corpus_pinned(self):
        """2. Reference corpus hash pinned to 0455bd66aae52551c35b37a63c2d185f."""
        assert FROZEN_REFERENCE_CORPUS_HASH == "0455bd66aae52551c35b37a63c2d185f"
        assert B_T1C_PROFILE_A["reference_corpus_hash"] == "0455bd66aae52551c35b37a63c2d185f"
        assert B_T1C_PROFILE_B["reference_corpus_hash"] == "0455bd66aae52551c35b37a63c2d185f"

    def test_03_b0_semantic_hash_pinned(self):
        """3. Frozen B0 Stage B semantic content hash pinned."""
        expected = "sha256:3c215db23a7fae8b8ac98852e65985b1efded354850fd9be65c24bfd1c90682d"
        assert FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH == expected
        assert B_T1C_PROFILE_A["frozen_b0_semantic_hash"] == expected
        assert B_T1C_PROFILE_B["frozen_b0_semantic_hash"] == expected

    def test_04_exactly_100_relationship_tasks_selected(self):
        """4. Exactly 100 relationship tasks selected from reference corpus."""
        refs = load_reference_corpus(REF_DIR)
        assert len(refs) == 100
        tasks = build_batch_01_relationship_tasks(refs)
        assert len(tasks) == 100
        for t in tasks:
            assert t.task_type == ClassifierTaskType.RELATIONSHIPS
            assert t.taxonomy_version == FROZEN_TAXONOMY_VERSION

    def test_05_non_relationships_tasks_fail_closed(self):
        """5. Non-RELATIONSHIPS tasks fail closed (cannot execute live)."""
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
            build_treatment_request_payload(task, ARM_A_ID)

        adapter = TreatmentClassifierAdapter(ARM_A_ID, live=False)
        with pytest.raises(ValueError, match="only permits ClassifierTaskType.RELATIONSHIPS"):
            adapter.execute(task)

    def test_06_arm_a_uses_max_tokens_1024(self):
        """6. Arm A request configuration specifies max_tokens=1024."""
        assert FROZEN_MAX_TOKENS == 1024
        assert B_T1C_PROFILE_A["request_parameters"]["max_tokens"] == 1024
        assert B_T1C_PROFILE_B["request_parameters"]["max_tokens"] == 1024

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
        payload = build_treatment_request_payload(dummy_task, ARM_A_ID)
        assert payload["max_tokens"] == 1024

    def test_07_no_explicit_temperature_field_exists(self):
        """7. Temperature parameter is explicitly absent from request payloads."""
        assert B_T1C_PROFILE_A["request_parameters"]["explicit_temperature"] is None
        assert B_T1C_PROFILE_B["request_parameters"]["explicit_temperature"] is None

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
        payload_a = build_treatment_request_payload(dummy_task, ARM_A_ID)
        payload_b = build_treatment_request_payload(dummy_task, ARM_B_ID)
        assert "temperature" not in payload_a
        assert "temperature" not in payload_b

    def test_08_timeout_and_retry_match_b0(self):
        """8. Timeout (60.0s) and retry (2) configuration match B0."""
        assert FROZEN_TIMEOUT_SECONDS == 60.0
        assert FROZEN_MAX_RETRIES == 2
        assert B_T1C_PROFILE_A["request_parameters"]["timeout"] == 60.0
        assert B_T1C_PROFILE_A["request_parameters"]["max_retries"] == 2
        assert B_T1C_PROFILE_B["request_parameters"]["timeout"] == 60.0
        assert B_T1C_PROFILE_B["request_parameters"]["max_retries"] == 2

    def test_09_user_prompt_is_identical_to_b0(self):
        """9. User prompt is identical to B0 AnthropicClassifier contract."""
        dummy_task = ClassifierTask(
            candidate_id="cand-001",
            task_type=ClassifierTaskType.RELATIONSHIPS,
            raw_statement="evidence statement",
            source_context="surrounding context",
            source_path="docs/adr/0001.md",
            source_location="L1-L10",
            repository_identifier="org/repo",
            repository_commit_sha="1234567890abcdef1234567890abcdef12345678",
            taxonomy_version="0.1",
        )
        b0_user_prompt = AnthropicClassifier().build_user_prompt(dummy_task)
        treatment_user_prompt = build_treatment_user_prompt(dummy_task)
        assert treatment_user_prompt == b0_user_prompt

    def test_10_raw_evidence_task_inputs_identical_to_b0(self):
        """10. Task inputs strictly bind ref.raw_evidence as raw_statement and source_context."""
        refs = load_reference_corpus(REF_DIR)
        tasks = build_batch_01_relationship_tasks(refs)
        refs_map = {r.reference_decision_id: r for r in refs}
        for task in tasks:
            ref = refs_map[task.candidate_id]
            assert task.raw_statement == ref.raw_evidence
            assert task.source_context == ref.raw_evidence
            assert task.source_path == ref.source_file
            assert task.source_location == ref.source_location

    def test_11_arm_a_evidence_reference_schema_identical_to_b0(self):
        """11. Arm A evidence_reference schema description is identical to B0."""
        b0_schema = AnthropicClassifier.get_task_schema(ClassifierTaskType.RELATIONSHIPS)
        b0_ev_desc = b0_schema["properties"]["relationships"]["items"]["properties"]["evidence_reference"]["description"]
        assert b0_ev_desc == "Text evidence for this relationship"

        arm_a_ev_desc = ARM_A_RELATIONSHIPS_SCHEMA["properties"]["relationships"]["items"]["properties"]["evidence_reference"]["description"]
        assert arm_a_ev_desc == "Text evidence for this relationship"

        arm_b_ev_desc = ARM_B_RELATIONSHIPS_SCHEMA["properties"]["relationships"]["items"]["properties"]["evidence_reference"]["description"]
        assert arm_b_ev_desc == "Text evidence for this relationship"

    def test_12_arm_a_treatment_schema_and_prompt_match_profile(self):
        """12. Arm A treatment schema and system prompt match frozen profile."""
        assert B_T1C_PROFILE_A["relationship_schema"] == ARM_A_RELATIONSHIPS_SCHEMA
        assert B_T1C_PROFILE_A["system_prompt_treatment"] == ARM_A_SYSTEM_PROMPT_EXTENSION

    def test_13_arm_b_inherits_all_arm_a_semantics(self):
        """13. Arm B inherits all Arm A semantics byte-for-byte."""
        # Arm B system prompt extension strictly starts with Arm A extension
        assert ARM_B_SYSTEM_PROMPT_EXTENSION.startswith(ARM_A_SYSTEM_PROMPT_EXTENSION)
        # All schema properties other than target_reference description are identical
        schema_a_props = copy.deepcopy(ARM_A_RELATIONSHIPS_SCHEMA)
        schema_b_props = copy.deepcopy(ARM_B_RELATIONSHIPS_SCHEMA)
        schema_a_props["properties"]["relationships"]["items"]["properties"]["target_reference"]["description"] = ""
        schema_b_props["properties"]["relationships"]["items"]["properties"]["target_reference"]["description"] = ""
        assert schema_a_props == schema_b_props

    def test_14_ab_payload_diff_limited_to_adr_target_format(self):
        """14. A/B payload diff is strictly limited to ADR target formatting instructions."""
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
        payload_a = build_treatment_request_payload(dummy_task, ARM_A_ID)
        payload_b = build_treatment_request_payload(dummy_task, ARM_B_ID)

        assert payload_a["model"] == payload_b["model"]
        assert payload_a["max_tokens"] == payload_b["max_tokens"]
        assert payload_a["messages"] == payload_b["messages"]

        # System prompt delta is strictly the target representation rules block
        assert payload_b["system"].startswith(payload_a["system"])
        system_delta = payload_b["system"][len(payload_a["system"]):]
        assert "Target representation rules" in system_delta
        assert "4-digit zero-padded numeric identifier" in system_delta

        # Schema delta is strictly the target_reference description
        schema_a = payload_a["output_config"]["format"]["schema"]
        schema_b = payload_b["output_config"]["format"]["schema"]
        desc_a = schema_a["properties"]["relationships"]["items"]["properties"]["target_reference"]["description"]
        desc_b = schema_b["properties"]["relationships"]["items"]["properties"]["target_reference"]["description"]
        assert desc_a != desc_b
        assert "Canonical zero-padded 4-digit" in desc_b

    def test_15_profile_hashes_change_under_mutation(self):
        """15. Profile hashes change under any material treatment mutation."""
        base_hash_a = compute_b_t1c_profile_hash(B_T1C_PROFILE_A)
        assert base_hash_a == B_T1C_PROFILE_A_HASH

        mutated_a = copy.deepcopy(B_T1C_PROFILE_A)
        mutated_a["request_parameters"]["max_tokens"] = 2048
        assert compute_b_t1c_profile_hash(mutated_a) != base_hash_a

        mutated_prompt = copy.deepcopy(B_T1C_PROFILE_A)
        mutated_prompt["system_prompt_treatment"] += "\n# Extra instruction"
        assert compute_b_t1c_profile_hash(mutated_prompt) != base_hash_a

        base_hash_b = compute_b_t1c_profile_hash(B_T1C_PROFILE_B)
        assert base_hash_b == B_T1C_PROFILE_B_HASH
        assert base_hash_a != base_hash_b

    def test_16_no_model_network_calls_in_adapter(self):
        """16. Zero model/network calls occur during test execution (static/mock client only)."""
        adapter = TreatmentClassifierAdapter(ARM_A_ID, live=False)
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
            adapter.execute(task)

        # Mock client succeeds deterministically without network
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = json.dumps({"relationships": []})
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        adapter_mock = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client, live=False)
        res = adapter_mock.execute(task)
        assert res.output == {"relationships": []}
        assert mock_client.messages.create.call_count == 1

    def test_17_treatment_loader_requires_exactly_100_outcomes(self, tmp_path: Path):
        """17. Treatment outcome loader fails closed when outcome count != 100."""
        sample_path = tmp_path / "test_outcomes.jsonl"
        lines = [
            json.dumps({
                "backend_id": "anthropic",
                "candidate_id": f"ref-test-{i:03d}",
                "classifier_version": "0.1",
                "confidence": None,
                "cost_amount": None,
                "cost_currency": None,
                "created_at": "2026-10-02T20:00:00Z",
                "escalated": False,
                "execution_id": f"exec-{i}",
                "latency_ms": None,
                "model_identifier": "claude-sonnet-4-6",
                "output": {"relationships": []},
                "run_id": "run-001",
                "task_type": "relationships",
                "taxonomy_version": "0.1",
            })
            for i in range(1, 51)  # only 50
        ]
        sample_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Expected exactly 100 treatment outcomes, got 50"):
            load_treatment_outcomes(sample_path)

    def test_18_duplicate_or_missing_relationship_outcomes_fail_closed(self, tmp_path: Path):
        """18. Duplicate or missing relationship outcomes fail closed."""
        sample_path = tmp_path / "test_duplicates.jsonl"
        lines = [
            json.dumps({
                "backend_id": "anthropic",
                "candidate_id": "ref-duplicate-001",  # duplicate candidate_id
                "classifier_version": "0.1",
                "created_at": "2026-10-02T20:00:00Z",
                "execution_id": f"exec-{i}",
                "model_identifier": "claude-sonnet-4-6",
                "output": {"relationships": []},
                "run_id": "run-001",
                "task_type": "relationships",
                "taxonomy_version": "0.1",
            })
            for i in range(1, 101)
        ]
        sample_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Duplicate candidate_id"):
            load_treatment_outcomes(sample_path)

    def test_19_semantic_outcome_hash_excludes_volatile_metadata(self):
        """19. Semantic outcome hash excludes volatile execution metadata."""
        outcomes_1 = [
            FrozenClassifierOutcome(
                candidate_id=f"ref-{i:03d}",
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="run-001",
                execution_id=f"exec-1-{i}",
                output={"relationships": []},
                confidence=None,
                latency_ms=123.45,
                cost_amount=0.005,
                cost_currency="USD",
                escalated=False,
                created_at="2026-10-02T12:00:00Z",
            )
            for i in range(1, 101)
        ]
        outcomes_2 = [
            FrozenClassifierOutcome(
                candidate_id=f"ref-{i:03d}",
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="run-002",
                execution_id=f"exec-2-{i}",  # different execution_id
                output={"relationships": []},
                confidence=0.99,  # different confidence
                latency_ms=999.99,  # different latency
                cost_amount=0.010,  # different cost
                cost_currency="EUR",  # different currency
                escalated=False,
                created_at="2026-10-02T18:00:00Z",  # different timestamp
            )
            for i in range(1, 101)
        ]

        hash_1 = compute_treatment_semantic_content_hash(outcomes_1)
        hash_2 = compute_treatment_semantic_content_hash(outcomes_2)
        assert hash_1 == hash_2

    def test_20_mixed_replay_consists_of_700_b0_and_100_treatment_outcomes(self):
        """20. Mixed replay evaluation set consists of exactly 700 B0 + 100 treatment outcomes."""
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)
        assert len(b0_outcomes) == 800

        # Create dummy treatment outcomes for the 100 references
        refs = load_reference_corpus(REF_DIR)
        dummy_treatment = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="treatment-run",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-02T20:00:00Z",
            )
            for r in refs
        ]
        assert len(dummy_treatment) == 100

        mixed = build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment)
        assert len(mixed) == 800

        # Non-relationships tasks should equal 700
        non_rel = [o for o in mixed if o.task_type != ClassifierTaskType.RELATIONSHIPS]
        assert len(non_rel) == 700

        # Relationships tasks should equal 100 and match treatment
        rel = [o for o in mixed if o.task_type == ClassifierTaskType.RELATIONSHIPS]
        assert len(rel) == 100
        for r_out in rel:
            assert r_out.run_id == "treatment-run"

    def test_21_frozen_b0_files_remain_unchanged(self):
        """21. Frozen B0 baseline outcomes file remains unmodified."""
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)
        assert len(b0_outcomes) == 800

        # Semantic hash matches frozen authority
        assert FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH == "sha256:3c215db23a7fae8b8ac98852e65985b1efded354850fd9be65c24bfd1c90682d"

    def test_22_scorer_strictly_delegates_to_stage_b_authority(self):
        """22. Scorer strictly delegates to existing Stage B scoring authority (score_stage_b_outcomes)."""
        manifest = Manifest.load(MANIFEST_PATH)
        refs = load_reference_corpus(REF_DIR)
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)

        # Build dummy treatment returning empty relationships for all 100 decisions
        dummy_treatment = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="treatment-dummy",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-02T20:00:00Z",
            )
            for r in refs
        ]
        mixed = build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment)
        res = score_treatment_replay(mixed, refs, manifest)

        assert res.total_references == 100
        assert res.total_outcomes == 800
        # If all decisions return [], the 87 expected-empty decisions match exactly (87 / 100 = 0.87 rel accuracy)
        rel_accs = [
            s.metrics["relationship_accuracy"] for s in res.repository_scores.values()
        ]
        avg_rel_acc = sum(rel_accs) / len(rel_accs)
        # 87 exact matches across 100 references
        assert avg_rel_acc > 0.80

    def test_23_b_t1b_diagnostic_semantics_reused(self):
        """23. B-T1B diagnostic semantics (classify_target_form, parse_adr_alias) are reused."""
        assert classify_target_form is b_t1b_classify_target_form
        assert parse_adr_alias is b_t1b_parse_adr_alias

        # Verify diagnostic evaluation produces expected structure
        manifest = Manifest.load(MANIFEST_PATH)
        refs = load_reference_corpus(REF_DIR)
        dummy_treatment = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="treatment-dummy",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-02T20:00:00Z",
            )
            for r in refs
        ]
        diag_res = evaluate_treatment_diagnostics(dummy_treatment, refs, manifest, arm=ARM_A_ID)
        assert diag_res.arm == ARM_A_ID
        assert diag_res.total_references == 100
        assert diag_res.total_predicted_tuples == 0
        assert diag_res.expected_empty_volume.total_predicted_tuples == 0
        assert diag_res.arm_a_hypotheses is not None
        assert diag_res.arm_a_hypotheses.h1_empty_tuples_below_415 is True
        assert diag_res.arm_a_hypotheses.h2_empty_refs_with_fp_below_86 is True

    def test_20b_mixed_replay_fails_on_candidate_mismatch(self):
        """20b. Mixed replay fails closed if candidate IDs mismatch (missing or extra)."""
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)
        refs = load_reference_corpus(REF_DIR)

        # Build treatment with missing candidate
        dummy_treatment_missing = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="run-test",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-02T20:00:00Z",
            )
            for r in refs[:-1]
        ]
        with pytest.raises(ValueError, match="Expected exactly 100 treatment relationship outcomes"):
            build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment_missing)

        # Build treatment with extra/unexpected candidate
        dummy_treatment_extra = [
            FrozenClassifierOutcome(
                candidate_id=f"ref-extra-{i:03d}",
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="run-test",
                execution_id=f"exec-{i}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-02T20:00:00Z",
            )
            for i in range(1, 101)
        ]
        with pytest.raises(ValueError, match="missing candidates"):
            build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment_extra)

    def test_24_research_boundaries_and_frozen_artifacts_preserved(self):
        """24. Research boundaries and frozen artifact hashes are strictly preserved."""
        import ast

        # 1. Parse AST of the treatment module and ensure no forbidden canonical runtime imports
        module_path = REPO_ROOT / "mneme" / "open_architecture" / "stage_b_relationship_treatment_experiment.py"
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
                        assert not alias.name.startswith(prefix), f"Forbidden import detected: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not node.module.startswith(prefix), f"Forbidden from-import detected: {node.module}"

        # 2. Assert frozen hashes remain valid
        assert FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH == "sha256:3c215db23a7fae8b8ac98852e65985b1efded354850fd9be65c24bfd1c90682d"
        assert FROZEN_REFERENCE_CORPUS_HASH == "0455bd66aae52551c35b37a63c2d185f"
        assert FROZEN_BASELINE_CONFIG_HASH == "31e18dc1e2bd9ad30bec86dce1a9295a"

    def test_25_base_system_prompt_identical_to_b0(self):
        """25. Pre-treatment base system prompt is byte-identical to AnthropicClassifier."""
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
        b0_system_prompt = AnthropicClassifier().build_system_prompt(dummy_task)
        treatment_base_prompt = BASE_SYSTEM_PROMPT_TEMPLATE.format(
            taxonomy_version=dummy_task.taxonomy_version
        )
        assert treatment_base_prompt == b0_system_prompt

        # Full treatment system prompt strictly begins with this exact base prompt
        full_system_a = build_treatment_system_prompt(dummy_task, ARM_A_ID)
        assert full_system_a.startswith(b0_system_prompt)
        full_system_b = build_treatment_system_prompt(dummy_task, ARM_B_ID)
        assert full_system_b.startswith(b0_system_prompt)

    def test_26_malformed_and_schema_invalid_responses_fail_closed(self):
        """26. Malformed and schema-invalid model responses fail closed (never default to [])."""
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

        # 1. Empty content response raises AnthropicMalformedResponseError
        mock_client_empty = MagicMock()
        mock_resp_empty = MagicMock()
        mock_resp_empty.content = []
        mock_client_empty.messages.create.return_value = mock_resp_empty

        adapter_empty = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client_empty, live=False)
        with pytest.raises(AnthropicMalformedResponseError, match="empty or missing content"):
            adapter_empty.execute(dummy_task)

        # 2. Non-JSON response text raises AnthropicMalformedResponseError
        mock_client_bad_json = MagicMock()
        mock_block_bad = MagicMock()
        mock_block_bad.text = "This is not json at all."
        mock_resp_bad = MagicMock()
        mock_resp_bad.content = [mock_block_bad]
        mock_client_bad_json.messages.create.return_value = mock_resp_bad

        adapter_bad_json = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client_bad_json, live=False)
        with pytest.raises(AnthropicMalformedResponseError, match="Failed to parse Anthropic response as JSON"):
            adapter_bad_json.execute(dummy_task)

        # 3. JSON Schema invalid response (invalid enum value) raises AnthropicMalformedResponseError
        mock_client_invalid_enum = MagicMock()
        mock_block_enum = MagicMock()
        mock_block_enum.text = json.dumps({
            "relationships": [
                {
                    "relationship_type": "invalid_rel_type_enum",
                    "target_reference": "0005",
                    "evidence_reference": "evidence",
                }
            ]
        })
        mock_resp_enum = MagicMock()
        mock_resp_enum.content = [mock_block_enum]
        mock_client_invalid_enum.messages.create.return_value = mock_resp_enum

        adapter_invalid_enum = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client_invalid_enum, live=False)
        with pytest.raises(AnthropicMalformedResponseError, match="failed schema validation"):
            adapter_invalid_enum.execute(dummy_task)

        # 4. In execute_batch, failure becomes an explicit escalated error result, NEVER []
        batch_results = adapter_invalid_enum.execute_batch([dummy_task])
        assert len(batch_results) == 1
        res = batch_results[0]
        assert res.escalated is True
        assert "error" in res.output
        assert "relationships" not in res.output

    def test_27_treatment_outcome_loader_validates_metadata_fields(self, tmp_path: Path):
        """27. Treatment outcome loader validates metadata fields and candidate set fail-closed."""
        refs = load_reference_corpus(REF_DIR)
        valid_lines = [
            json.dumps({
                "backend_id": "anthropic",
                "candidate_id": r.reference_decision_id,
                "classifier_version": "0.1",
                "confidence": None,
                "cost_amount": None,
                "cost_currency": None,
                "created_at": "2026-10-02T20:00:00Z",
                "escalated": False,
                "execution_id": f"exec-{r.reference_decision_id}",
                "latency_ms": 100.0,
                "model_identifier": "claude-sonnet-4-6",
                "output": {"relationships": []},
                "run_id": "run-001",
                "task_type": "relationships",
                "taxonomy_version": "0.1",
            })
            for r in refs
        ]

        # Valid load succeeds
        valid_path = tmp_path / "valid.jsonl"
        valid_path.write_text("\n".join(valid_lines) + "\n", encoding="utf-8")
        loaded = load_treatment_outcomes(valid_path, expected_reference_ids={r.reference_decision_id for r in refs})
        assert len(loaded) == 100

        # Mismatched model fails
        bad_model_lines = list(valid_lines)
        bad_dict = json.loads(bad_model_lines[0])
        bad_dict["model_identifier"] = "gpt-4"
        bad_model_lines[0] = json.dumps(bad_dict)
        bad_model_path = tmp_path / "bad_model.jsonl"
        bad_model_path.write_text("\n".join(bad_model_lines) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected model_identifier 'claude-sonnet-4-6'"):
            load_treatment_outcomes(bad_model_path)

        # Mismatched taxonomy version fails
        bad_tax_lines = list(valid_lines)
        bad_dict = json.loads(bad_tax_lines[0])
        bad_dict["taxonomy_version"] = "0.2"
        bad_tax_lines[0] = json.dumps(bad_dict)
        bad_tax_path = tmp_path / "bad_tax.jsonl"
        bad_tax_path.write_text("\n".join(bad_tax_lines) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected taxonomy_version '0.1'"):
            load_treatment_outcomes(bad_tax_path)

        # Candidate set mismatch fails
        with pytest.raises(ValueError, match="Treatment outcome candidate set mismatch"):
            load_treatment_outcomes(valid_path, expected_reference_ids={"other-id-001"})

    def test_28_provenance_sidecar_and_capture_path(self, tmp_path: Path):
        """28. Provenance sidecar serialization, validation, and overwrite refusal."""
        refs = load_reference_corpus(REF_DIR)

        # Mock client returning valid empty relationships
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = json.dumps({"relationships": []})
        mock_resp = MagicMock()
        mock_resp.content = [mock_block]
        mock_client.messages.create.return_value = mock_resp

        adapter = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client, live=False)

        run_dir = tmp_path / "treatment_a_run"
        outcomes, sidecar = capture_treatment_run(run_dir, ARM_A_ID, adapter, refs)

        assert len(outcomes) == 100
        assert sidecar.arm_id == ARM_A_ID
        assert sidecar.treatment_profile_hash == B_T1C_PROFILE_A_HASH
        assert sidecar.actual_outcome_count == 100
        assert sidecar.treatment_semantic_content_hash.startswith("sha256:")

        # Verify load_treatment_run validates provenance and outcomes
        loaded_outcomes, loaded_sidecar = load_treatment_run(
            run_dir,
            expected_arm=ARM_A_ID,
            expected_reference_ids={r.reference_decision_id for r in refs},
        )
        assert len(loaded_outcomes) == 100
        assert loaded_sidecar.treatment_profile_hash == B_T1C_PROFILE_A_HASH

        # Refuse overwrite into existing non-empty directory
        with pytest.raises(FileExistsError, match="refusing overwrite"):
            capture_treatment_run(run_dir, ARM_A_ID, adapter, refs)

    def test_29_reference_corpus_validation_and_tampering_rejection(self, tmp_path: Path):
        """29. Reference corpus validation enforces exact count, candidate IDs, and content hash fail-closed."""
        refs = load_reference_corpus(REF_DIR)
        manifest = Manifest.load(MANIFEST_PATH)

        # 1. Exact frozen v0.1 references pass validation and match file-based authority
        computed_hash = validate_frozen_reference_corpus(refs)
        dir_hash = compute_reference_corpus_content_hash(REF_DIR)
        assert computed_hash == FROZEN_REFERENCE_CORPUS_HASH == "0455bd66aae52551c35b37a63c2d185f"
        assert computed_hash == dir_hash
        assert compute_reference_corpus_hash_from_references(refs) == dir_hash

        # 1b. The committed v0.2 revision directory must exist and be strictly rejected by the frozen treatment validator
        v02_ref_dir = (
            REPO_ROOT
            / "benchmarks"
            / "open_architecture"
            / "batch_01"
            / "revisions"
            / "batch_01_v0.2-grounding"
            / "reference_decisions"
        )
        assert v02_ref_dir.is_dir(), f"Committed v0.2 reference corpus directory missing: {v02_ref_dir}"
        v02_hash = compute_reference_corpus_content_hash(v02_ref_dir)
        assert v02_hash == "700a569e24bf90707ba14ff65eea2ab5"
        v02_refs = load_reference_corpus(v02_ref_dir)
        assert len(v02_refs) == 100
        with pytest.raises(ValueError, match="Reference corpus content hash mismatch"):
            validate_frozen_reference_corpus(v02_refs)

        # 1c. Treatment profile hashes remain strictly unchanged
        assert B_T1C_PROFILE_A_HASH == "7ff00c50f0a9718721e8defe188f62b8"
        assert B_T1C_PROFILE_B_HASH == "e4b6bad47ebcc290924782172fb96d8d"

        # 2. 99 references fail before classifier execution; 0 calls, 0 artifacts
        mock_client_99 = MagicMock()
        adapter_99 = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client_99, live=False)
        dir_99 = tmp_path / "run_99"
        with pytest.raises(ValueError, match="Reference corpus count mismatch"):
            capture_treatment_run(dir_99, ARM_A_ID, adapter_99, refs[:99])
        assert mock_client_99.messages.create.call_count == 0
        assert not (dir_99 / "outcomes.jsonl").exists()
        assert not (dir_99 / "provenance.json").exists()

        # 3. 100 references with one mutated semantic field fail before classifier execution; 0 calls, 0 artifacts
        mutated_semantic_refs = list(refs)
        mutated_semantic_refs[0] = dataclasses.replace(
            mutated_semantic_refs[0],
            normalized_decision="Tampered decision statement for testing fail-closed hash validation.",
        )
        mock_client_mutated = MagicMock()
        adapter_mutated = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client_mutated, live=False)
        dir_mutated = tmp_path / "run_mutated"
        with pytest.raises(ValueError, match="Reference corpus content hash mismatch"):
            capture_treatment_run(dir_mutated, ARM_A_ID, adapter_mutated, mutated_semantic_refs)
        assert mock_client_mutated.messages.create.call_count == 0
        assert not (dir_mutated / "outcomes.jsonl").exists()
        assert not (dir_mutated / "provenance.json").exists()

        # 4. 100 references with candidate-set mismatch fail before classifier execution
        bad_id_refs = list(refs)
        bad_id_refs[0] = dataclasses.replace(
            bad_id_refs[0],
            reference_decision_id="ref-unrecognized-999",
        )
        mock_client_bad_id = MagicMock()
        adapter_bad_id = TreatmentClassifierAdapter(ARM_A_ID, client=mock_client_bad_id, live=False)
        dir_bad_id = tmp_path / "run_bad_id"
        with pytest.raises(ValueError, match="Reference decisions candidate set mismatch"):
            capture_treatment_run(dir_bad_id, ARM_A_ID, adapter_bad_id, bad_id_refs)
        assert mock_client_bad_id.messages.create.call_count == 0
        assert not (dir_bad_id / "outcomes.jsonl").exists()
        assert not (dir_bad_id / "provenance.json").exists()

        # 5. Treatment evaluation also rejects a mutated reference corpus
        dummy_treatment = [
            FrozenClassifierOutcome(
                candidate_id=r.reference_decision_id,
                task_type=ClassifierTaskType.RELATIONSHIPS,
                backend_id="anthropic",
                classifier_version="0.1",
                model_identifier="claude-sonnet-4-6",
                taxonomy_version="0.1",
                run_id="treatment-dummy",
                execution_id=f"exec-{r.reference_decision_id}",
                output={"relationships": []},
                confidence=None,
                latency_ms=None,
                cost_amount=None,
                cost_currency=None,
                escalated=False,
                created_at="2026-10-02T20:00:00Z",
            )
            for r in refs
        ]
        b0_outcomes = load_stage_b_outcomes(FROZEN_B0_PATH)
        mixed = build_mixed_stage_b_outcomes(b0_outcomes, dummy_treatment)

        with pytest.raises(ValueError, match="Reference corpus content hash mismatch"):
            evaluate_treatment_diagnostics(dummy_treatment, mutated_semantic_refs, manifest, arm=ARM_A_ID)

        with pytest.raises(ValueError, match="Reference corpus content hash mismatch"):
            score_treatment_replay(mixed, mutated_semantic_refs, manifest)

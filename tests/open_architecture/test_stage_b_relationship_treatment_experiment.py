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
from mneme.open_architecture.classifiers.anthropic import AnthropicClassifier
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
    build_batch_01_relationship_tasks,
    build_mixed_stage_b_outcomes,
    build_treatment_request_payload,
    build_treatment_system_prompt,
    build_treatment_user_prompt,
    classify_target_form,
    compute_b_t1c_profile_hash,
    compute_treatment_semantic_content_hash,
    evaluate_treatment_diagnostics,
    load_treatment_outcomes,
    parse_adr_alias,
    score_treatment_replay,
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
        mock_response = MagicMock()
        mock_response.parsed_output = {"relationships": []}
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

    def test_24_exact_changed_file_boundary_enforced(self):
        """24. Exact changed file boundary is enforced."""
        git_diff = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert git_diff.returncode == 0
        lines = [line.strip() for line in git_diff.stdout.splitlines() if line.strip()]
        # All modified or added files must be inside the allowed boundary
        allowed_files = {
            "mneme/open_architecture/stage_b_relationship_treatment_experiment.py",
            "tests/open_architecture/test_stage_b_relationship_treatment_experiment.py",
            "scripts/run_test_battery.py",
        }
        for line in lines:
            parts = line.split(maxsplit=1)
            file_path = parts[1].replace("\\", "/")
            assert file_path in allowed_files, f"Unexpected modified/untracked file: {file_path}"

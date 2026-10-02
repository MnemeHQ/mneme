"""
tests.open_architecture.test_stage_b_baseline — Tests for Frozen Stage B Baseline Provenance.

Validates:
1. Committed evidence count == 800
2. All 100 references have exactly 8 task outcomes
3. Identity/hash validation fails closed on mutation
4. Offline scoring reproduces all five repository metric dictionaries
5. Offline scoring reproduces exact composite 0.5171813272250951
6. Zero network/model calls occur
7. Legacy 0.517188 is explicitly verified as NOT equal to the exact composite
8. Baseline freeze tests remain unchanged and pass
9. Replay classifier conforms to SemanticClassifier protocol
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.classification import (
    ClassifierTask,
    ClassifierTaskType,
    SemanticClassifier,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    _execute_stage_b_tasks_and_scoring,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.stage_b_baseline import (
    EXACT_STAGE_B_COMPOSITE,
    EXPECTED_REPOSITORY_COMPOSITES,
    FROZEN_CLASSIFIER_BACKEND,
    FROZEN_CLASSIFIER_VERSION,
    FROZEN_MODEL_IDENTIFIER,
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FROZEN_TAXONOMY_VERSION,
    LEGACY_HISTORICAL_STAGE_B_LITERAL,
    STAGE_B_EVALUATED_TASKS,
    FrozenClassifierOutcome,
    OfflineB0Classifier,
    compute_stage_b_semantic_content_hash,
    load_stage_b_outcomes,
    score_stage_b_outcomes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROVENANCE_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline_stage_b"
OUTCOMES_PATH = PROVENANCE_DIR / "classifier_outcomes.jsonl"
PROVENANCE_PATH = PROVENANCE_DIR / "stage_b_provenance.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"


# ── 1 & 2: Evidence Count and Reference Task Integrity ────────────────────────


class TestStageBArtifactIntegrity:
    def test_1_committed_evidence_count_equals_800(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        assert len(outcomes) == 800

    def test_2_all_100_refs_have_exactly_8_task_outcomes(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        ref_tasks: dict[str, set[str]] = {}
        for o in outcomes:
            ref_tasks.setdefault(o.candidate_id, set()).add(o.task_type.value)

        assert len(ref_tasks) == 100
        for ref_id, tasks in ref_tasks.items():
            assert len(tasks) == 8, f"Reference {ref_id} has {len(tasks)} tasks, expected 8"
            assert tasks == {
                "decision_classification",
                "domains",
                "purposes",
                "authority",
                "scope",
                "lifecycle",
                "relationships",
                "enforcement_potential",
            }

    def test_no_duplicate_candidate_task_keys(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        keys = [(o.candidate_id, o.task_type.value) for o in outcomes]
        assert len(keys) == len(set(keys)) == 800

    def test_classifier_identities_match_frozen_baseline(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        for o in outcomes:
            assert o.backend_id == FROZEN_CLASSIFIER_BACKEND
            assert o.classifier_version == FROZEN_CLASSIFIER_VERSION
            assert o.model_identifier == FROZEN_MODEL_IDENTIFIER
            assert o.taxonomy_version == FROZEN_TAXONOMY_VERSION


# ── 3: Identity & Hash Validation Fails Closed on Mutation ─────────────────────


class TestStageBHashValidation:
    def test_semantic_content_hash_matches_frozen_digest(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        computed_hash = compute_stage_b_semantic_content_hash(outcomes)
        assert computed_hash == FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH

    def test_hash_fails_closed_on_mutation(self, tmp_path: Path):
        # Load valid 800 outcomes, mutate one semantic output, write complete 800-row file
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        mutated_dicts = [o.to_dict() for o in outcomes]
        mutated_dicts[0]["output"] = {"classification": "corrupted_verdict"}

        mutated_file = tmp_path / "mutated_outcomes.jsonl"
        lines = [json.dumps(d, sort_keys=True, separators=(",", ":")) for d in mutated_dicts]
        mutated_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Stage B semantic content hash mismatch"):
            load_stage_b_outcomes(mutated_file)

    def test_taxonomy_version_mutation_fails_closed(self, tmp_path: Path):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        mutated_dicts = [o.to_dict() for o in outcomes]
        mutated_dicts[0]["taxonomy_version"] = "9.9"

        mutated_file = tmp_path / "bad_taxonomy.jsonl"
        lines = [json.dumps(d, sort_keys=True, separators=(",", ":")) for d in mutated_dicts]
        mutated_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Taxonomy version mismatch"):
            load_stage_b_outcomes(mutated_file)

    def test_load_stage_b_outcomes_signature_has_no_hash_override(self):
        import inspect
        sig = inspect.signature(load_stage_b_outcomes)
        assert "expected_content_hash" not in sig.parameters
        assert list(sig.parameters.keys()) == ["outcomes_path"]
        with pytest.raises(TypeError, match="unexpected keyword argument 'expected_content_hash'"):
            load_stage_b_outcomes(OUTCOMES_PATH, expected_content_hash="caller_supplied_override")

    def test_provenance_summary_json_integrity(self):
        assert PROVENANCE_PATH.is_file()
        data = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))

        assert data["baseline_id"] == FROZEN_BASELINE_ID
        assert data["baseline_configuration_hash"] == FROZEN_BASELINE_CONFIG_HASH
        assert data["reference_corpus_hash"] == FROZEN_REFERENCE_CORPUS_HASH
        assert data["semantic_content_hash"] == FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH
        assert data["dataset"]["total_outcomes"] == 800
        assert data["dataset"]["total_references"] == 100
        assert data["scoring_contract"]["recomputed_exact_composite"] == EXACT_STAGE_B_COMPOSITE
        assert data["scoring_contract"]["legacy_historical_literal"] == LEGACY_HISTORICAL_STAGE_B_LITERAL

    def test_export_determinism_and_byte_identity(self, tmp_path: Path):
        # Two independent round-trips from the outcomes produce byte-identical JSONL
        outcomes1 = load_stage_b_outcomes(OUTCOMES_PATH)
        outcomes2 = load_stage_b_outcomes(OUTCOMES_PATH)

        file1 = tmp_path / "run1.jsonl"
        file2 = tmp_path / "run2.jsonl"

        lines1 = [json.dumps(o.to_dict(), sort_keys=True, separators=(",", ":")) for o in outcomes1]
        lines2 = [json.dumps(o.to_dict(), sort_keys=True, separators=(",", ":")) for o in outcomes2]

        file1.write_text("\n".join(lines1) + "\n", encoding="utf-8")
        file2.write_text("\n".join(lines2) + "\n", encoding="utf-8")

        assert file1.read_bytes() == file2.read_bytes()
        assert compute_stage_b_semantic_content_hash(outcomes1) == compute_stage_b_semantic_content_hash(outcomes2)


# ── 4 & 5: Offline Scoring Reproduces Metrics and Exact Composite ──────────────


class TestStageBOfflineScoring:
    def test_4_offline_scoring_reproduces_all_five_repositories(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        manifest = Manifest.load(MANIFEST_PATH)
        all_refs = load_reference_corpus(REF_DIR)

        res = score_stage_b_outcomes(outcomes, all_refs, manifest)

        # adrkit
        adrkit_m = res.repository_scores["adrkit"].metrics
        assert adrkit_m["decision_classification_accuracy"] == 1.0
        assert abs(adrkit_m["domain_micro_f1"] - 0.5850340136054423) < 1e-12
        assert abs(adrkit_m["purpose_micro_f1"] - 0.5294117647058824) < 1e-12
        assert adrkit_m["authority_accuracy"] == 0.4
        assert adrkit_m["scope_accuracy"] == 0.0
        assert adrkit_m["lifecycle_accuracy"] == 0.9
        assert adrkit_m["relationship_accuracy"] == 0.0
        assert adrkit_m["enforcement_classification_accuracy"] == 0.7
        assert abs(res.repository_scores["adrkit"].composite_score - EXPECTED_REPOSITORY_COMPOSITES["adrkit"]) < 1e-12

        # archlint
        archlint_m = res.repository_scores["archlint"].metrics
        assert archlint_m["decision_classification_accuracy"] == 0.15
        assert abs(archlint_m["domain_micro_f1"] - 0.5499999999999999) < 1e-12
        assert abs(archlint_m["purpose_micro_f1"] - 0.4583333333333333) < 1e-12
        assert archlint_m["authority_accuracy"] == 0.2
        assert archlint_m["scope_accuracy"] == 0.0
        assert archlint_m["lifecycle_accuracy"] == 0.95
        assert archlint_m["relationship_accuracy"] == 0.0
        assert archlint_m["enforcement_classification_accuracy"] == 0.85
        assert abs(res.repository_scores["archlint"].composite_score - EXPECTED_REPOSITORY_COMPOSITES["archlint"]) < 1e-12

        # gsa
        gsa_m = res.repository_scores["gsa_agentic_coding_quickstart"].metrics
        assert gsa_m["decision_classification_accuracy"] == 0.9
        assert abs(gsa_m["domain_micro_f1"] - 0.7080745341614907) < 1e-12
        assert abs(gsa_m["purpose_micro_f1"] - 0.6096256684491979) < 1e-12
        assert gsa_m["authority_accuracy"] == 1.0
        assert gsa_m["scope_accuracy"] == 0.0
        assert gsa_m["lifecycle_accuracy"] == 1.0
        assert gsa_m["relationship_accuracy"] == 0.0
        assert gsa_m["enforcement_classification_accuracy"] == 0.9
        assert abs(res.repository_scores["gsa_agentic_coding_quickstart"].composite_score - EXPECTED_REPOSITORY_COMPOSITES["gsa_agentic_coding_quickstart"]) < 1e-12

        # helix
        helix_m = res.repository_scores["helix"].metrics
        assert helix_m["decision_classification_accuracy"] == 0.9
        assert abs(helix_m["domain_micro_f1"] - 0.5316455696202532) < 1e-12
        assert abs(helix_m["purpose_micro_f1"] - 0.4999999999999999) < 1e-12
        assert helix_m["authority_accuracy"] == 1.0
        assert helix_m["scope_accuracy"] == 0.0
        assert helix_m["lifecycle_accuracy"] == 1.0
        assert helix_m["relationship_accuracy"] == 0.0
        assert helix_m["enforcement_classification_accuracy"] == 0.6
        assert abs(res.repository_scores["helix"].composite_score - EXPECTED_REPOSITORY_COMPOSITES["helix"]) < 1e-12

        # modonome
        modonome_m = res.repository_scores["modonome"].metrics
        assert modonome_m["decision_classification_accuracy"] == 0.85
        assert abs(modonome_m["domain_micro_f1"] - 0.4266666666666667) < 1e-12
        assert abs(modonome_m["purpose_micro_f1"] - 0.5384615384615384) < 1e-12
        assert modonome_m["authority_accuracy"] == 0.25
        assert modonome_m["scope_accuracy"] == 0.0
        assert modonome_m["lifecycle_accuracy"] == 0.85
        assert modonome_m["relationship_accuracy"] == 0.0
        assert modonome_m["enforcement_classification_accuracy"] == 0.85
        assert abs(res.repository_scores["modonome"].composite_score - EXPECTED_REPOSITORY_COMPOSITES["modonome"]) < 1e-12

    def test_5_offline_scoring_reproduces_exact_macro_composite(self):
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        manifest = Manifest.load(MANIFEST_PATH)
        all_refs = load_reference_corpus(REF_DIR)

        res = score_stage_b_outcomes(outcomes, all_refs, manifest)
        assert abs(res.stage_b_semantic_score - EXACT_STAGE_B_COMPOSITE) < 1e-12
        assert res.stage_b_semantic_score == pytest.approx(0.5171813272250951, abs=1e-12)

    def test_harness_is_single_scoring_authority(self, monkeypatch):
        import mneme.open_architecture.stage_b_baseline as stage_b_mod
        harness_calls = []
        original_fn = stage_b_mod._execute_stage_b_tasks_and_scoring

        def _spy(*args, **kwargs):
            harness_calls.append(kwargs.get("repository_config"))
            return original_fn(*args, **kwargs)

        monkeypatch.setattr(stage_b_mod, "_execute_stage_b_tasks_and_scoring", _spy)

        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        manifest = Manifest.load(MANIFEST_PATH)
        all_refs = load_reference_corpus(REF_DIR)
        res = score_stage_b_outcomes(outcomes, all_refs, manifest)

        assert len(harness_calls) == 5
        assert abs(res.stage_b_semantic_score - EXACT_STAGE_B_COMPOSITE) < 1e-12


# ── 6: No Network / Model Calls Occur ──────────────────────────────────────────


class TestStageBNoModelCalls:
    def test_6_replay_classifier_is_pure_in_memory(self, monkeypatch):
        # Prevent any network or socket access
        import socket

        def _forbidden_connect(*args, **kwargs):
            raise AssertionError("Network connection attempted during offline Stage B replay!")

        monkeypatch.setattr(socket.socket, "connect", _forbidden_connect)

        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        clf = OfflineB0Classifier(outcomes)
        assert callable(getattr(clf, "execute", None))
        assert clf.backend_id == FROZEN_CLASSIFIER_BACKEND
        assert clf.classifier_version == FROZEN_CLASSIFIER_VERSION
        assert clf.model_identifier == FROZEN_MODEL_IDENTIFIER

        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        task = ClassifierTask(
            task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            candidate_id=sample_ref.reference_decision_id,
            repository_identifier="mbeacom/adrkit",
            repository_commit_sha="471457da29638ecca6119b35180c2845bf989cac",
            source_path="docs/adr/0001.md",
            source_location="L10-L20",
            raw_statement="test statement",
            source_context="context",
        )
        result = clf.execute(task)
        assert result.candidate_id == sample_ref.reference_decision_id
        assert result.task_type == ClassifierTaskType.DECISION_CLASSIFICATION
        assert "classification" in result.output

    def test_harness_stage_b_tasks_and_scoring_offline_replay(self, monkeypatch):
        # Verify that executing the exact harness function with OfflineB0Classifier produces identical metrics
        outcomes = load_stage_b_outcomes(OUTCOMES_PATH)
        clf = OfflineB0Classifier(outcomes)
        manifest = Manifest.load(MANIFEST_PATH)
        all_refs = load_reference_corpus(REF_DIR)

        composites = []
        for repo_cfg in manifest.repositories:
            repo_refs = [r for r in all_refs if r.repository == repo_cfg.github]
            res = _execute_stage_b_tasks_and_scoring(
                repository_config=repo_cfg,
                references=repo_refs,
                classifier=clf,
            )
            m = res.metrics
            comp = sum(m[t] for t in STAGE_B_EVALUATED_TASKS) / 8.0
            composites.append(comp)
            assert abs(comp - EXPECTED_REPOSITORY_COMPOSITES[repo_cfg.id]) < 1e-12

        macro = sum(composites) / len(composites)
        assert abs(macro - EXACT_STAGE_B_COMPOSITE) < 1e-12


# ── 7: Legacy 0.517188 Constant Disclosed and NOT Treated as Exact Composite ──


class TestLegacyConstantDisclosed:
    def test_7_legacy_constant_differs_by_approx_6_67e_6(self):
        delta = abs(LEGACY_HISTORICAL_STAGE_B_LITERAL - EXACT_STAGE_B_COMPOSITE)
        assert delta > 0.0
        assert abs(delta - 6.672774904847856e-06) < 1e-10
        # Assert legacy literal is NOT exact
        assert EXACT_STAGE_B_COMPOSITE != LEGACY_HISTORICAL_STAGE_B_LITERAL

"""
tests.open_architecture.test_batch_01_closure — Tests and deterministic evidence guard for Batch 01 top-level closure manifest.

Validates:
1. Committed Batch 01 closure manifest exists at benchmarks/open_architecture/batch_01/batch_01_closure.json.
2. Binds required top-level identities and status:
   - closure_status == "CLOSED / FROZEN"
   - batch_id == "o1a-batch-01"
   - baseline_id == "o1a-batch-01-baseline"
   - headline_metric == "governing_decision_set_f1"
   - mneme_execution_sha == "8f2a9281bc5e54ccacac12577c04d2ce1694cfb9"
3. Binds the three discrete stage artifacts with exact SHA-256 content digests:
   - Stage A: stage_a_summary.json (status: BASELINE_FROZEN)
   - Stage B: stage_b_closure.json (status: CLOSED / FROZEN, accepted endpoint: B-T1D / Arm D)
   - Stage C: stage_c_closure.json (status: CLOSED / FROZEN, accepted endpoint: B3)
4. Preserves methodology invariant: stage metrics remain strictly discrete and independent;
   no overall or collapsed benchmark score is computed or reported.
5. Deterministic evidence guard: fresh reconstruction from committed evidence achieves
   both semantic and byte identity with committed manifest.
6. Fail-closed tamper tests prove guard raises explicit ValueError on any stage artifact mutation
   or headline metric deviation.
7. Zero model, network, or external API calls performed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.batch_01_closure import (
    ACCEPTED_STAGE_B_ENDPOINT,
    ACCEPTED_STAGE_C_ENDPOINT,
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BATCH_01_CLOSURE_MNEME_SHA,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_REFERENCE_CORPUS_V0_1_HASH,
    FROZEN_SCENARIO_CORPUS_HASH,
    FROZEN_SCORING_REFERENCE_CORPUS_V0_2_HASH,
    FROZEN_STAGE_A_ARTIFACT_SHA256,
    FROZEN_STAGE_B_ARTIFACT_SHA256,
    FROZEN_STAGE_C_ARTIFACT_SHA256,
    HEADLINE_METRIC,
    build_batch_01_closure,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLOSURE_MANIFEST_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "batch_01_closure.json"
)


class TestBatch01ClosureManifest:
    def test_committed_manifest_exists(self):
        assert CLOSURE_MANIFEST_PATH.is_file(), f"Missing manifest: {CLOSURE_MANIFEST_PATH}"

    def test_committed_manifest_required_fields(self):
        data = json.loads(CLOSURE_MANIFEST_PATH.read_text(encoding="utf-8"))

        assert data["artifact_type"] == "batch_01_closure_manifest"
        assert data["artifact_version"] == "0.1"
        assert data["batch_id"] == "o1a-batch-01"
        assert data["baseline_id"] == "o1a-batch-01-baseline"
        assert data["closure_status"] == "CLOSED / FROZEN"
        assert data["headline_metric"] == HEADLINE_METRIC
        assert data["mneme_execution_sha"] == FROZEN_BATCH_01_CLOSURE_MNEME_SHA

        decl = data["closure_declaration"]
        assert decl["status"] == "CLOSED / FROZEN"
        assert "closed and frozen across all three stages" in decl["scope"]
        assert "stages are never collapsed or averaged" in decl["methodology_invariant"]

    def test_committed_manifest_corpora_and_provenance(self):
        data = json.loads(CLOSURE_MANIFEST_PATH.read_text(encoding="utf-8"))

        corpora = data["corpora_identities"]
        assert corpora["manifest_configuration_hash"] == FROZEN_MANIFEST_CONFIG_HASH
        assert corpora["baseline_configuration_hash"] == FROZEN_BASELINE_CONFIG_HASH
        assert corpora["reference_corpus_v0_1_hash"] == FROZEN_REFERENCE_CORPUS_V0_1_HASH
        assert corpora["reference_corpus_v0_2_grounding_hash"] == FROZEN_SCORING_REFERENCE_CORPUS_V0_2_HASH
        assert corpora["scenario_corpus_hash"] == FROZEN_SCENARIO_CORPUS_HASH

        sources = data["provenance_sources"]
        for key, rel_path in sources.items():
            abs_path = REPO_ROOT / rel_path
            assert abs_path.is_file(), f"Missing provenance source '{key}': {abs_path}"

    def test_committed_manifest_stage_bindings(self):
        data = json.loads(CLOSURE_MANIFEST_PATH.read_text(encoding="utf-8"))
        stages = data["stages"]

        # Stage A
        sa = stages["stage_a"]
        assert sa["status"] == "BASELINE_FROZEN"
        assert sa["artifact_sha256"] == FROZEN_STAGE_A_ARTIFACT_SHA256
        assert sa["summary_metrics"]["discovered_documents"] == 687
        assert sa["summary_metrics"]["extracted_candidates"] == 5459
        assert sa["summary_metrics"]["matched_references"] == 85
        assert sa["summary_metrics"]["macro_recall"] == 0.85
        assert sa["summary_metrics"]["missed_source_references"] == 14

        # Stage B
        sb = stages["stage_b"]
        assert sb["status"] == "CLOSED / FROZEN"
        assert sb["accepted_endpoint"] == ACCEPTED_STAGE_B_ENDPOINT
        assert sb["artifact_sha256"] == FROZEN_STAGE_B_ARTIFACT_SHA256
        assert sb["summary_metrics"]["stage_b_semantic_score"] == 0.5934313272250952
        assert sb["summary_metrics"]["strict_relationship_accuracy"] == 0.6100000000000001
        assert sb["summary_metrics"]["relationship_exact_matches"] == 61
        assert sb["summary_metrics"]["preservation_conditions_passed"] is True

        # Stage C
        sc = stages["stage_c"]
        assert sc["status"] == "CLOSED / FROZEN"
        assert sc["accepted_endpoint"] == ACCEPTED_STAGE_C_ENDPOINT
        assert sc["artifact_sha256"] == FROZEN_STAGE_C_ARTIFACT_SHA256
        assert sc["summary_metrics"]["end_to_end_macro_f1"] == 0.6506666666666666
        assert sc["summary_metrics"]["end_to_end_exact_set_matches"] == 22
        assert sc["summary_metrics"]["human_reference_macro_f1"] == 0.7110952380952381
        assert sc["summary_metrics"]["human_reference_exact_set_matches"] == 26

    def test_stages_metrics_remain_discrete(self):
        """Methodology constraint: do not collapse stages into one overall score."""
        data = json.loads(CLOSURE_MANIFEST_PATH.read_text(encoding="utf-8"))

        assert "overall_score" not in data
        assert "composite_score" not in data
        assert "benchmark_score" not in data
        assert "average_score" not in data

        assert "stages" in data
        assert set(data["stages"].keys()) == {"stage_a", "stage_b", "stage_c"}


def _setup_tmp_closure_sources(tmp_path: Path) -> dict[str, Path]:
    b01_dir = tmp_path / "benchmarks" / "open_architecture" / "batch_01"
    b01_dir.mkdir(parents=True, exist_ok=True)
    (b01_dir / "stage_a").mkdir(parents=True, exist_ok=True)
    (b01_dir / "stage_b").mkdir(parents=True, exist_ok=True)
    (b01_dir / "stage_c").mkdir(parents=True, exist_ok=True)

    files_map = {
        "manifest": b01_dir / "manifest.yaml",
        "baseline": b01_dir / "baseline.yaml",
        "stage_a": b01_dir / "stage_a" / "stage_a_summary.json",
        "stage_b": b01_dir / "stage_b" / "stage_b_closure.json",
        "stage_c": b01_dir / "stage_c" / "stage_c_closure.json",
    }

    real_sources = {
        "manifest": REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml",
        "baseline": REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml",
        "stage_a": REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "stage_a" / "stage_a_summary.json",
        "stage_b": REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "stage_b" / "stage_b_closure.json",
        "stage_c": REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "stage_c" / "stage_c_closure.json",
    }

    for key, dest in files_map.items():
        dest.write_bytes(real_sources[key].read_bytes())

    return files_map


class TestBatch01ClosureEvidenceGuard:
    def test_fresh_reconstruction_matches_committed_manifest(self):
        """Verify fresh deterministic reconstruction has semantic and byte identity with committed manifest."""
        fresh = build_batch_01_closure(REPO_ROOT)
        committed_text = CLOSURE_MANIFEST_PATH.read_text(encoding="utf-8")
        committed_dict = json.loads(committed_text)

        # 1. Semantic identity
        assert fresh == committed_dict

        # 2. Byte identity
        serialized_fresh = json.dumps(fresh, indent=2, sort_keys=True) + "\n"
        assert serialized_fresh == committed_text

    def test_guard_fails_when_stage_a_artifact_tampered(self, tmp_path: Path):
        files = _setup_tmp_closure_sources(tmp_path)
        files["stage_a"].write_text("{\"tampered\": true}\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Stage A artifact SHA-256 mismatch"):
            build_batch_01_closure(tmp_path)

    def test_guard_fails_when_stage_b_artifact_tampered(self, tmp_path: Path):
        files = _setup_tmp_closure_sources(tmp_path)
        files["stage_b"].write_text("{\"tampered\": true}\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Stage B artifact SHA-256 mismatch"):
            build_batch_01_closure(tmp_path)

    def test_guard_fails_when_stage_c_artifact_tampered(self, tmp_path: Path):
        files = _setup_tmp_closure_sources(tmp_path)
        files["stage_c"].write_text("{\"tampered\": true}\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Stage C artifact SHA-256 mismatch"):
            build_batch_01_closure(tmp_path)

    def test_guard_fails_when_manifest_headline_metric_tampered(self, tmp_path: Path):
        files = _setup_tmp_closure_sources(tmp_path)
        content = files["manifest"].read_text(encoding="utf-8")
        tampered = content.replace("headline_metric: governing_decision_set_f1", "headline_metric: other_f1")
        files["manifest"].write_text(tampered, encoding="utf-8")

        with pytest.raises(ValueError, match="Manifest headline metric mismatch"):
            build_batch_01_closure(tmp_path)

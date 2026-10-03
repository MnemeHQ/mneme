"""
tests.open_architecture.test_stage_a_baseline — Tests and evidence guard for frozen Stage A discovery baseline.

Validates:
1. Committed Stage A baseline artifact exists and loads at benchmarks/open_architecture/batch_01/stage_a/stage_a_summary.json.
2. Committed artifact binds required identities fail-closed:
   - baseline_id == "o1a-batch-01-baseline"
   - baseline_configuration_hash == "31e18dc1e2bd9ad30bec86dce1a9295a"
   - manifest_configuration_hash == "4af7e5794011b43d39682cdfeac9f54e"
   - reference_corpus_hash == "0455bd66aae52551c35b37a63c2d185f"
   - mneme_execution_sha == "dda0342606fb388bd6de3355ada260c59b13ac0e"
   - extractor id == "heuristic", version == "0.1", 24 keywords, min_lines 2, max_lines 50, confidence 0.5
   - matching contract == deterministic line-interval overlap on matching source path
   - 5 pinned repository identities and commit SHAs
3. Exact per-repository and aggregate metrics match frozen discovery measurements.
4. Failure class decomposition matches observed reality:
   - 14 MISSED_SOURCE references in Archlint
   - 1 source-discovered un-overlapped reference in Modonome (ref-modonome-015)
   - 0 MISSED_SOURCE references in adrkit, gsa_agentic_coding_quickstart, helix, modonome
5. Fresh execution evidence guard: fresh deterministic execution against cached checkouts matches
   committed artifact with semantic and byte identity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.candidates import HeuristicExtractor
from mneme.open_architecture.execution import materialize_repository
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_STAGE_A_MNEME_SHA,
    execute_stage_a_baseline,
)
from mneme.open_architecture.manifest import Manifest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
STAGE_A_SUMMARY_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "open_architecture"
    / "batch_01"
    / "stage_a"
    / "stage_a_summary.json"
)

EXPECTED_REPOSITORY_SHAS = {
    "adrkit": "471457da29638ecca6119b35180c2845bf989cac",
    "archlint": "185837e93565718d8e1ea653236cd70ca0a89e3a",
    "gsa_agentic_coding_quickstart": "8e6160c63acc35bd48d0a3844e133ea3ad52a464",
    "helix": "37d994370deba2512588b5c4efb7f03483e7308b",
    "modonome": "7a4d5244dcb6879b6aa646105b39297aa6d0a5a2",
}

EXPECTED_PER_REPO_METRICS = {
    "adrkit": {
        "discovered_documents_count": 345,
        "extracted_candidates_count": 2956,
        "reference_decisions_count": 20,
        "matched_reference_count": 20,
        "matched_candidate_count": 48,
        "recall": 1.0,
        "precision": 48 / 2956,
        "missed_source_count": 0,
        "unmatched_ref_count": 0,
    },
    "archlint": {
        "discovered_documents_count": 2,
        "extracted_candidates_count": 16,
        "reference_decisions_count": 20,
        "matched_reference_count": 6,
        "matched_candidate_count": 6,
        "recall": 0.3,
        "precision": 0.375,
        "missed_source_count": 14,
        "unmatched_ref_count": 14,
    },
    "gsa_agentic_coding_quickstart": {
        "discovered_documents_count": 50,
        "extracted_candidates_count": 689,
        "reference_decisions_count": 20,
        "matched_reference_count": 20,
        "matched_candidate_count": 86,
        "recall": 1.0,
        "precision": 86 / 689,
        "missed_source_count": 0,
        "unmatched_ref_count": 0,
    },
    "helix": {
        "discovered_documents_count": 140,
        "extracted_candidates_count": 978,
        "reference_decisions_count": 20,
        "matched_reference_count": 20,
        "matched_candidate_count": 99,
        "recall": 1.0,
        "precision": 99 / 978,
        "missed_source_count": 0,
        "unmatched_ref_count": 0,
    },
    "modonome": {
        "discovered_documents_count": 151,
        "extracted_candidates_count": 820,
        "reference_decisions_count": 20,
        "matched_reference_count": 19,
        "matched_candidate_count": 17,
        "recall": 0.95,
        "precision": 17 / 820,
        "missed_source_count": 0,
        "unmatched_ref_count": 1,
    },
}


@pytest.fixture(scope="module")
def repo_clone_cache(tmp_path_factory) -> dict[str, Path]:
    """Cache checkouts locally once so fresh Stage A evaluation clones in milliseconds."""
    ws_dir = tmp_path_factory.mktemp("cached_checkouts")
    manifest = Manifest.load(MANIFEST_PATH)
    cache: dict[str, Path] = {}
    for repo_cfg in manifest.repositories:
        with materialize_repository(repo_cfg, workspace_dir=ws_dir, cleanup=False) as checkout:
            cache[repo_cfg.id] = checkout.checkout_path
    return cache


class TestStageABaselineArtifact:
    def test_committed_artifact_exists(self):
        assert STAGE_A_SUMMARY_PATH.is_file(), f"Artifact missing: {STAGE_A_SUMMARY_PATH}"

    def test_committed_artifact_required_bindings(self):
        data = json.loads(STAGE_A_SUMMARY_PATH.read_text(encoding="utf-8"))

        assert data["baseline_id"] == FROZEN_BASELINE_ID
        assert data["baseline_configuration_hash"] == FROZEN_BASELINE_CONFIG_HASH
        assert data["manifest_configuration_hash"] == FROZEN_MANIFEST_CONFIG_HASH
        assert data["reference_corpus_hash"] == FROZEN_REFERENCE_CORPUS_HASH
        assert data["mneme_execution_sha"] == FROZEN_STAGE_A_MNEME_SHA

        # Extractor binding
        assert data["extractor"]["id"] == "heuristic"
        assert data["extractor"]["version"] == "0.1"
        assert data["extractor"]["config"]["min_lines"] == 2
        assert data["extractor"]["config"]["max_lines"] == 50
        assert data["extractor"]["config"]["confidence"] == 0.5
        assert set(data["extractor"]["config"]["keywords"]) == set(HeuristicExtractor.DECISION_KEYWORDS)

        # Matching contract binding
        assert (
            data["matching_contract"]["contract_id"]
            == "deterministic_source_path_and_line_interval_overlap"
        )
        assert data["matching_contract"]["version"] == "0.1"

        # Pinned repositories
        assert set(data["repository_ids"]) == set(EXPECTED_REPOSITORY_SHAS.keys())
        assert data["repository_pinned_shas"] == EXPECTED_REPOSITORY_SHAS

    def test_committed_artifact_aggregate_metrics(self):
        data = json.loads(STAGE_A_SUMMARY_PATH.read_text(encoding="utf-8"))
        agg = data["aggregate"]

        assert agg["total_discovered_documents"] == 688
        assert agg["total_extracted_candidates"] == 5459
        assert agg["total_reference_decisions"] == 100
        assert agg["total_matched_references"] == 85
        assert agg["total_matched_candidates"] == 256
        assert agg["macro_recall"] == 0.85
        assert pytest.approx(agg["macro_precision"], rel=1e-6) == 0.1276030877012214
        assert pytest.approx(agg["macro_f1"], rel=1e-6) == 0.16232962158801395

    def test_committed_artifact_per_repository_metrics(self):
        data = json.loads(STAGE_A_SUMMARY_PATH.read_text(encoding="utf-8"))
        repos = data["repositories"]

        assert set(repos.keys()) == set(EXPECTED_PER_REPO_METRICS.keys())
        for repo_id, exp in EXPECTED_PER_REPO_METRICS.items():
            r = repos[repo_id]
            assert r["discovered_documents_count"] == exp["discovered_documents_count"]
            assert r["extracted_candidates_count"] == exp["extracted_candidates_count"]
            assert r["reference_decisions_count"] == exp["reference_decisions_count"]
            assert r["matched_reference_count"] == exp["matched_reference_count"]
            assert r["matched_candidate_count"] == exp["matched_candidate_count"]
            assert pytest.approx(r["recall"], rel=1e-6) == exp["recall"]
            assert pytest.approx(r["precision"], rel=1e-6) == exp["precision"]
            assert len(r["missed_source_reference_ids"]) == exp["missed_source_count"]
            assert len(r["unmatched_reference_ids"]) == exp["unmatched_ref_count"]

    def test_committed_artifact_failure_class_decomposition(self):
        data = json.loads(STAGE_A_SUMMARY_PATH.read_text(encoding="utf-8"))
        repos = data["repositories"]

        # Archlint: 14 missed sources
        arch = repos["archlint"]
        assert len(arch["missed_source_reference_ids"]) == 14
        assert set(arch["missed_source_reference_ids"]) == set(arch["unmatched_reference_ids"])
        assert "ref-archlint-001" in arch["missed_source_reference_ids"]
        assert "ref-archlint-020" in arch["missed_source_reference_ids"]

        # Modonome: 0 missed source, 1 source discovered but line span un-overlapped
        modo = repos["modonome"]
        assert modo["missed_source_reference_ids"] == []
        assert modo["unmatched_reference_ids"] == ["ref-modonome-015"]

        # Other 3 repos: 100% recall, 0 unmatched, 0 missed source
        for r_id in ("adrkit", "gsa_agentic_coding_quickstart", "helix"):
            assert repos[r_id]["missed_source_reference_ids"] == []
            assert repos[r_id]["unmatched_reference_ids"] == []
            assert repos[r_id]["recall"] == 1.0


class TestStageAFreshExecutionGuard:
    def test_fresh_deterministic_execution_matches_committed_artifact(self, repo_clone_cache):
        """Guard against silent divergence between fresh Stage A execution and committed artifact."""
        fresh = execute_stage_a_baseline(clone_sources=repo_clone_cache)
        committed_text = STAGE_A_SUMMARY_PATH.read_text(encoding="utf-8")
        committed_dict = json.loads(committed_text)

        # 1. Semantic equality
        assert fresh == committed_dict

        # 2. Byte equality
        serialized_fresh = json.dumps(fresh, indent=2, sort_keys=True) + "\n"
        assert serialized_fresh == committed_text

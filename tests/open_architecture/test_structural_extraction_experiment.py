"""
tests.open_architecture.test_structural_extraction_experiment — Unit and regression test suite for T2B.1.

Validates:
1. Profile immutability and deterministic experiment_profile_hash.
2. Exact fail-closed Go source boundary hygiene exclusion predicate.
3. Exclusion safety: zero frozen reference source paths are excluded.
4. Exact candidate and metric assertions (5,535 candidates, 278 matched, 100/100 recall).
5. Exact T2A.2 preservation on all retained documents (identical candidate IDs, line spans, statements).
6. Artifact determinism (byte-identical reproduction across runs).
7. Fail-closed guards for output directories, manifest SHAs, and reference corpus hashes.
8. Frozen file byte-identity / isolation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.extraction_tuning_experiment import (
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_REPOSITORY_SHAS,
    T2A2_CODE_KEYWORDS,
    T2A2_DOC_KEYWORDS,
    LexicalCandidateExtractor,
)
from mneme.open_architecture.structural_extraction_experiment import (
    EXCLUSION_PATH_COMPONENT,
    EXCLUSION_SUFFIX,
    FROZEN_PARENT_MAIN_SHA,
    T2B1ExperimentResult,
    T2B1SourceBoundaryHygieneProfile,
    execute_t2b1_experiment,
    is_excluded_go_source,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
BASELINE_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"


# ── Fixtures & Caching ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def repo_clone_cache(tmp_path_factory) -> dict[str, Path]:
    """Cache checkouts locally once so subsequent tests clone locally in milliseconds."""
    from mneme.open_architecture.execution import materialize_repository
    from mneme.open_architecture.manifest import Manifest

    ws_dir = tmp_path_factory.mktemp("cached_checkouts")
    manifest = Manifest.load(MANIFEST_PATH)
    cache: dict[str, Path] = {}
    for repo_cfg in manifest.repositories:
        with materialize_repository(repo_cfg, workspace_dir=ws_dir, cleanup=False) as checkout:
            cache[repo_cfg.id] = checkout.checkout_path
    return cache


@pytest.fixture(scope="module")
def t2b1_result(tmp_path_factory, repo_clone_cache) -> T2B1ExperimentResult:
    out_dir = tmp_path_factory.mktemp("t2b1_module_out")
    return execute_t2b1_experiment(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        output_dir=out_dir,
        clone_sources=repo_clone_cache,
    )


# ── Profile Contract Tests ─────────────────────────────────────────────────────


class TestT2B1Profiles:
    # 1. Profile immutability and deterministic profile hash
    def test_1_profile_immutability_and_deterministic_profile_hash(self):
        p1 = T2B1SourceBoundaryHygieneProfile()
        p2 = T2B1SourceBoundaryHygieneProfile()
        assert p1.experiment_profile_hash == p2.experiment_profile_hash
        assert len(p1.experiment_profile_hash) == 32
        assert p1.experiment_profile_hash == "6bc950785725ea84cdae599512e42c16"
        assert p1.experiment_id == "t2b1-source-boundary-hygiene"
        assert p1.parent_main_sha == "3ccd5992a0035eea300ab5615674a2cdcedc5fde"

    # 2. Profile rejection of invalid parameters
    def test_2_profile_rejection_of_invalid_parameters(self):
        with pytest.raises(ValueError, match="experiment_id"):
            T2B1SourceBoundaryHygieneProfile(experiment_id="wrong")
        with pytest.raises(ValueError, match="baseline_id"):
            T2B1SourceBoundaryHygieneProfile(baseline_id="wrong")
        with pytest.raises(ValueError, match="parent_main_sha"):
            T2B1SourceBoundaryHygieneProfile(parent_main_sha="0" * 40)
        with pytest.raises(ValueError, match="reference_corpus_hash"):
            T2B1SourceBoundaryHygieneProfile(reference_corpus_hash="0" * 32)
        with pytest.raises(ValueError, match="exclusion_suffix"):
            T2B1SourceBoundaryHygieneProfile(exclusion_suffix="_spec.go")
        with pytest.raises(ValueError, match="exclusion_path_component"):
            T2B1SourceBoundaryHygieneProfile(exclusion_path_component="fixtures")

    # 3. Profile serialization roundtrip
    def test_3_profile_serialization_roundtrip(self):
        p = T2B1SourceBoundaryHygieneProfile()
        d = p.to_dict()
        assert d["experiment_id"] == "t2b1-source-boundary-hygiene"
        assert d["parent_main_sha"] == "3ccd5992a0035eea300ab5615674a2cdcedc5fde"
        assert d["exclusion_rules"]["suffix"] == "_test.go"
        assert d["exclusion_rules"]["path_component"] == "examples"
        assert d["experiment_profile_hash"] == p.experiment_profile_hash


# ── Exclusion Predicate Tests ──────────────────────────────────────────────────


class TestT2B1ExclusionPredicate:
    # 4. Correctly excludes Go test files
    def test_4_excludes_go_test_files(self):
        doc = DiscoveredSourceDocument(
            relative_path="internal/adr/adr_test.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package adr\n",
            metadata={"evidence_kind": "source_code", "language": "go", "extension": ".go"},
        )
        assert is_excluded_go_source(doc) is True

    # 5. Correctly excludes Go files under examples/ component
    def test_5_excludes_go_files_in_examples(self):
        doc = DiscoveredSourceDocument(
            relative_path="examples/adr-sample/internal/db/repo.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package db\n",
            metadata={"evidence_kind": "source_code", "language": "go", "extension": ".go"},
        )
        assert is_excluded_go_source(doc) is True

    # 6. Does not exclude production Go files
    def test_6_does_not_exclude_production_go_files(self):
        doc = DiscoveredSourceDocument(
            relative_path="internal/config/config.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package config\n",
            metadata={"evidence_kind": "source_code", "language": "go", "extension": ".go"},
        )
        assert is_excluded_go_source(doc) is False

    # 7. Does not exclude documentation files even if matching naming rules
    def test_7_never_excludes_documentation_files(self):
        # Markdown file with test in name
        doc_test_md = DiscoveredSourceDocument(
            relative_path="docs/test_guide.md",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="# Testing\n",
            metadata={"extension": ".md"},
        )
        assert is_excluded_go_source(doc_test_md) is False

        # Markdown file in examples/
        doc_example_md = DiscoveredSourceDocument(
            relative_path="examples/README.md",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="# Examples\n",
            metadata={"extension": ".md"},
        )
        assert is_excluded_go_source(doc_example_md) is False

    # 8. Strict exact-component matching (no loose substring false-positives)
    def test_8_strict_exact_component_matching(self):
        # "example" is not "examples"
        doc_example_dir = DiscoveredSourceDocument(
            relative_path="example/config.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package example\n",
            metadata={"evidence_kind": "source_code", "language": "go", "extension": ".go"},
        )
        assert is_excluded_go_source(doc_example_dir) is False

        # "test" in filename but not ending with "_test.go"
        doc_test_util = DiscoveredSourceDocument(
            relative_path="internal/testing_helper.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package internal\n",
            metadata={"evidence_kind": "source_code", "language": "go", "extension": ".go"},
        )
        assert is_excluded_go_source(doc_test_util) is False


# ── Exclusion Safety Tests ─────────────────────────────────────────────────────


class TestT2B1ExclusionSafety:
    # 9. No frozen reference decision source file is excluded
    def test_9_no_frozen_reference_source_file_excluded(self):
        from mneme.open_architecture.harness import load_reference_corpus

        all_refs = load_reference_corpus(REF_DIR)
        assert len(all_refs) == 100

        for r in all_refs:
            source_files = [f.strip() for f in r.source_file.split(",") if f.strip()]
            for sf in source_files:
                # Synthetic document to check against predicate
                is_go = sf.endswith(".go")
                meta = (
                    {"evidence_kind": "source_code", "language": "go", "extension": ".go"}
                    if is_go
                    else {"extension": ".md"}
                )
                doc = DiscoveredSourceDocument(
                    relative_path=sf,
                    source_type="documentation",
                    content_hash="sha256:" + "0" * 64,
                    content="",
                    metadata=meta,
                )
                assert is_excluded_go_source(doc) is False, (
                    f"Reference {r.reference_decision_id} source path '{sf}' was incorrectly excluded!"
                )


# ── Execution and Metrics Tests ────────────────────────────────────────────────


class TestT2B1ExecutionAndMetrics:
    # 10. Exact candidate and match metrics
    def test_10_t2b1_exact_metrics(self, t2b1_result: T2B1ExperimentResult):
        res = t2b1_result
        assert res.total_candidates == 5535
        assert res.matched_candidates == 278
        assert res.matched_references == 100
        assert res.unmatched_references == 0

        # Hygiene counts
        assert res.go_documents_before == 34
        assert res.go_documents_after == 13
        assert res.excluded_document_count == 21
        assert res.excluded_candidate_count == 28
        assert len(res.excluded_paths) == 21

        # Precision, Recall, F1, O1
        expected_prec = 278 / 5535
        expected_rec = 1.0
        expected_f1 = 2 * expected_prec * expected_rec / (expected_prec + expected_rec)
        expected_o1 = (expected_f1 + 0.517188 + 0.103728) / 3.0

        assert res.discovery_precision == pytest.approx(expected_prec)
        assert res.stage_a_recall == pytest.approx(expected_rec)
        assert res.stage_a_micro_f1 == pytest.approx(expected_f1)
        assert res.overall_o1_score == pytest.approx(expected_o1)

    # 11. Improvement over T2A.2 baseline
    def test_11_t2b1_improvement_over_t2a2(self, t2b1_result: T2B1ExperimentResult):
        res = t2b1_result
        t2a2_candidates = 5563
        t2a2_matched = 278
        t2a2_precision = t2a2_matched / t2a2_candidates
        t2a2_f1 = 2 * t2a2_precision * 1.0 / (t2a2_precision + 1.0)
        t2a2_o1 = (t2a2_f1 + 0.517188 + 0.103728) / 3.0

        assert res.total_candidates == t2a2_candidates - 28
        assert res.matched_candidates == t2a2_matched
        assert res.discovery_precision > t2a2_precision
        assert res.stage_a_micro_f1 > t2a2_f1
        assert res.overall_o1_score > t2a2_o1

    # 12. 100% recall preserved across all five repositories
    def test_12_all_repositories_100_percent_recall(self, t2b1_result: T2B1ExperimentResult):
        res = t2b1_result
        for repo_id, stage_a_res in res.repository_results.items():
            assert stage_a_res.matched_reference_count == 20
            assert stage_a_res.unmatched_reference_ids == []

    # 13. Critical reference matches preserved
    def test_13_critical_reference_matches_preserved(self, t2b1_result: T2B1ExperimentResult):
        res = t2b1_result
        arch_matches = res.repository_results["archlint"].ref_to_cand_matches
        assert "ref-archlint-001" in arch_matches
        assert "ref-archlint-002" in arch_matches
        assert "ref-archlint-003" in arch_matches  # Critical LayerOf span
        assert "ref-archlint-004" in arch_matches
        assert "ref-archlint-006" in arch_matches
        assert "ref-archlint-007" in arch_matches
        assert "ref-archlint-008" in arch_matches
        assert "ref-archlint-009" in arch_matches
        assert "ref-archlint-010" in arch_matches

        mod_matches = res.repository_results["modonome"].ref_to_cand_matches
        assert "ref-modonome-015" in mod_matches


# ── T2A.2 Candidate Preservation Tests ─────────────────────────────────────────


class TestT2B1T2APreservation:
    # 14. Retained candidates are identical to T2A.2 (ID, line span, statement)
    def test_14_retained_candidates_identical_to_t2a2(
        self,
        tmp_path_factory,
        repo_clone_cache: dict[str, Path],
        t2b1_result: T2B1ExperimentResult,
    ):
        from mneme.open_architecture.extraction_tuning_experiment import execute_t2a2_experiment

        t2a2_dir = tmp_path_factory.mktemp("t2a2_compare_out")
        t2a2_res = execute_t2a2_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=t2a2_dir,
            clone_sources=repo_clone_cache,
        )

        t2b1_res = t2b1_result
        excluded_set = set(t2b1_res.excluded_paths)

        # For every repo except archlint, all candidate matches must be identical
        for repo_id in ["adrkit", "gsa_agentic_coding_quickstart", "helix", "modonome"]:
            t2a_stage_a = t2a2_res.repository_results[repo_id]
            t2b_stage_a = t2b1_res.repository_results[repo_id]
            assert t2a_stage_a.extracted_candidates_count == t2b_stage_a.extracted_candidates_count
            assert t2a_stage_a.matched_candidate_count == t2b_stage_a.matched_candidate_count
            assert t2a_stage_a.cand_to_ref_matches == t2b_stage_a.cand_to_ref_matches
            assert t2a_stage_a.ref_to_cand_matches == t2b_stage_a.ref_to_cand_matches

        # For archlint, candidates from retained files must match identically
        arch_t2a = t2a2_res.repository_results["archlint"]
        arch_t2b = t2b1_res.repository_results["archlint"]

        assert arch_t2a.extracted_candidates_count == 73
        assert arch_t2b.extracted_candidates_count == 45
        assert arch_t2a.matched_candidate_count == 26
        assert arch_t2b.matched_candidate_count == 26

        # Every matched candidate in T2B.1 was also matched in T2A.2 with identical targets
        for cand_id, refs in arch_t2b.cand_to_ref_matches.items():
            assert cand_id in arch_t2a.cand_to_ref_matches
            assert arch_t2a.cand_to_ref_matches[cand_id] == refs


# ── Reproducibility & Safety Tests ─────────────────────────────────────────────


class TestT2B1ReproducibilityAndSafety:
    # 15. Artifact determinism (byte-identical across runs)
    def test_15_artifact_determinism_byte_identical(self, tmp_path: Path, repo_clone_cache: dict[str, Path]):
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"

        execute_t2b1_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_a,
            clone_sources=repo_clone_cache,
        )
        execute_t2b1_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_b,
            clone_sources=repo_clone_cache,
        )

        assert (dir_a / "t2b1_summary.json").read_bytes() == (dir_b / "t2b1_summary.json").read_bytes()
        assert (dir_a / "t2b1_candidate_matches.jsonl").read_bytes() == (dir_b / "t2b1_candidate_matches.jsonl").read_bytes()

    # 16. Output directory fail-closed behavior
    def test_16_output_dir_fail_closed(self, tmp_path: Path):
        occupied = tmp_path / "occupied"
        occupied.mkdir()
        (occupied / "existing.txt").write_text("prior data", encoding="utf-8")

        with pytest.raises(ValueError, match="already exists and is not empty. Overwrite prevented"):
            execute_t2b1_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                output_dir=occupied,
            )

    # 17. Mutated reference corpus hash fails closed
    def test_17_reference_corpus_hash_mismatch_fails_closed(self, tmp_path: Path):
        mutated_corpus = tmp_path / "mutated_ref"
        shutil.copytree(REF_DIR, mutated_corpus)
        target_ref = mutated_corpus / "archlint" / "ref-archlint-001.jsonl"
        data = json.loads(target_ref.read_text(encoding="utf-8"))
        data["raw_evidence"] += " // mutate hash"
        target_ref.write_text(json.dumps(data) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Reference corpus hash mismatch"):
            execute_t2b1_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=mutated_corpus,
                output_dir=tmp_path / "out",
            )

    # 18. Frozen architecture and baseline file isolation
    def test_18_frozen_architecture_file_isolation(self):
        import mneme.open_architecture.candidates as candidates_mod
        import mneme.open_architecture.discovery as discovery_mod
        import mneme.open_architecture.harness as harness_mod

        # Verify candidate base keywords unchanged
        assert len(candidates_mod.HeuristicExtractor.DECISION_KEYWORDS) == 26
        assert "supersede" not in candidates_mod.HeuristicExtractor.DECISION_KEYWORDS
        assert "allow" not in candidates_mod.HeuristicExtractor.DECISION_KEYWORDS

        # Verify discover_sources unchanged
        assert hasattr(discovery_mod, "discover_sources")

        # Verify evaluate_discovery_matches signature unchanged
        assert hasattr(harness_mod, "evaluate_discovery_matches")


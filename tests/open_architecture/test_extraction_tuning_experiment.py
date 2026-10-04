"""
tests.open_architecture.test_extraction_tuning_experiment — Verification for T2A extraction tuning.

Covers all 20 required gates:
1. Profile immutability and deterministic profile hash
2. Fail-closed profile overrides
3. Exact source-code metadata predicate
4. Exact frozen five-repository source stream
5. Exact pinned SHA validation
6. Exact reference-corpus hash validation
7. 3-root / 8-term candidate-ID equivalence
8. T2A.1 exact candidate/match metrics
9. T2A.2 exact candidate/match metrics
10. All four extraction misses recovered
11. Zero regression across all 96 T1 matched references
12. T2A.2 precision and F1 > corrected T1
13. T2A.2 precision and F1 > T2A.1
14. Artifact determinism (byte-identical across runs)
15. Output directory fail-closed behavior
16. Zero model calls
17. Zero canonical writes
18. Frozen semantic module hashes remain unchanged
19. Corrected T1 accounting remains 272 matched candidates
20. Test-policy registration verified
"""

from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mneme.open_architecture.candidates import HeuristicExtractor
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.extraction_tuning_experiment import (
    FROZEN_BASELINE_ID,
    FROZEN_PARENT_MAIN_SHA,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_REPOSITORY_SHAS,
    LIFECYCLE_ROOT_KEYWORDS,
    PERMISSION_ROOT_KEYWORDS,
    T2A1_GLOBAL_KEYWORDS,
    T2A2_CODE_KEYWORDS,
    T2A2_DOC_KEYWORDS,
    T2A1GlobalLexicalProfile,
    T2A2ScopedLexicalProfile,
    T2AExperimentResult,
    execute_t2a1_experiment,
    execute_t2a2_experiment,
    is_source_code_document,
)
from mneme.open_architecture.source_coverage_experiment import (
    B0_OTHER_REPOS_MATCHED_CANDIDATES,
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
def t2a1_result(tmp_path_factory, repo_clone_cache) -> T2AExperimentResult:
    out_dir = tmp_path_factory.mktemp("t2a1_module_out")
    return execute_t2a1_experiment(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        output_dir=out_dir,
        clone_sources=repo_clone_cache,
    )


@pytest.fixture(scope="module")
def t2a2_result(tmp_path_factory, repo_clone_cache) -> T2AExperimentResult:
    out_dir = tmp_path_factory.mktemp("t2a2_module_out")
    return execute_t2a2_experiment(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        output_dir=out_dir,
        clone_sources=repo_clone_cache,
    )


# ── Profile Contract Tests ─────────────────────────────────────────────────────


class TestT2AProfiles:
    # 1. Profile immutability and deterministic profile hash
    def test_1_profile_immutability_and_deterministic_profile_hash(self):
        p1 = T2A1GlobalLexicalProfile()
        p2 = T2A1GlobalLexicalProfile()
        assert p1.experiment_profile_hash == p2.experiment_profile_hash
        assert len(p1.experiment_profile_hash) == 32
        assert p1.experiment_id == "t2a1-global-lexical"
        assert p1.parent_main_sha == "f098955711d9260b4c238769359d4a29a5bab922"

        p3 = T2A2ScopedLexicalProfile()
        p4 = T2A2ScopedLexicalProfile()
        assert p3.experiment_profile_hash == p4.experiment_profile_hash
        assert len(p3.experiment_profile_hash) == 32
        assert p3.experiment_id == "t2a2-scoped-lexical"
        assert p3.parent_main_sha == "f098955711d9260b4c238769359d4a29a5bab922"

        assert p1.experiment_profile_hash != p3.experiment_profile_hash

        with pytest.raises(FrozenInstanceError):
            p1.experiment_id = "other"  # type: ignore[misc]

    # 2. Fail-closed profile overrides
    def test_2_fail_closed_profile_overrides(self):
        with pytest.raises(ValueError, match="experiment_id must be 't2a1-global-lexical'"):
            T2A1GlobalLexicalProfile(experiment_id="custom")

        with pytest.raises(ValueError, match="baseline_id must be"):
            T2A1GlobalLexicalProfile(baseline_id="custom")

        with pytest.raises(ValueError, match="parent_main_sha must be"):
            T2A1GlobalLexicalProfile(parent_main_sha="custom")

        with pytest.raises(ValueError, match="reference_corpus_hash must be"):
            T2A1GlobalLexicalProfile(reference_corpus_hash="0" * 32)

        with pytest.raises(ValueError, match="keywords must be exactly"):
            T2A1GlobalLexicalProfile(keywords=("custom",))

        with pytest.raises(ValueError, match="experiment_id must be 't2a2-scoped-lexical'"):
            T2A2ScopedLexicalProfile(experiment_id="custom")

        with pytest.raises(ValueError, match="doc_keywords must be exactly"):
            T2A2ScopedLexicalProfile(doc_keywords=("custom",))

        with pytest.raises(ValueError, match="code_keywords must be exactly"):
            T2A2ScopedLexicalProfile(code_keywords=("custom",))


# ── Predicate & Stream Contract Tests ──────────────────────────────────────────


class TestT2APredicatesAndStreams:
    # 3. Exact source-code metadata predicate
    def test_3_exact_source_code_metadata_predicate(self):
        # Valid Go document satisfies all 3 markers
        doc_go = DiscoveredSourceDocument(
            relative_path="internal/config/config.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package config\n",
            metadata={
                "evidence_kind": "source_code",
                "language": "go",
                "extension": ".go",
            },
        )
        assert is_source_code_document(doc_go) is True

        # Missing evidence_kind
        doc_no_kind = DiscoveredSourceDocument(
            relative_path="internal/config/config.go",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="package config\n",
            metadata={"language": "go", "extension": ".go"},
        )
        assert is_source_code_document(doc_no_kind) is False

        # Wrong language
        doc_wrong_lang = DiscoveredSourceDocument(
            relative_path="main.py",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="print(1)\n",
            metadata={
                "evidence_kind": "source_code",
                "language": "python",
                "extension": ".py",
            },
        )
        assert is_source_code_document(doc_wrong_lang) is False

        # Regular Markdown document
        doc_md = DiscoveredSourceDocument(
            relative_path="README.md",
            source_type="documentation",
            content_hash="sha256:" + "0" * 64,
            content="# Title\n",
            metadata={"extension": ".md"},
        )
        assert is_source_code_document(doc_md) is False

    # 4. Exact frozen five-repository source stream
    def test_4_exact_frozen_five_repository_source_stream(self):
        expected_repos = {
            "adrkit",
            "gsa_agentic_coding_quickstart",
            "helix",
            "archlint",
            "modonome",
        }
        assert set(FROZEN_REPOSITORY_SHAS.keys()) == expected_repos

    # 5. Exact pinned SHA validation
    def test_5_exact_pinned_sha_validation(self, tmp_path: Path):
        # Mutated manifest with incorrect SHA fails closed
        manifest_data = json.loads(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "batch_id": "o1a-batch-01",
                    "status": "frozen",
                    "repositories": [
                        {
                            "id": "archlint",
                            "github": "muhammetsafak/archlint",
                            "commit_sha": "0" * 40,
                            "primary_test": "test",
                            "validation_status": "reviewed",
                        }
                    ],
                    "targets": {
                        "decisions_total": 20,
                        "scenarios_total": 10,
                        "decisions_per_repository": 20,
                        "scenarios_per_repository": 10,
                    },
                    "sampling": {
                        "clear_explicit": 5,
                        "scoped": 5,
                        "lifecycle_or_supersession": 3,
                        "ambiguous_or_conflicting": 3,
                        "enforcement_potential": 2,
                        "unusual_or_difficult": 2,
                    },
                }
            )
        )
        bad_manifest = tmp_path / "bad_manifest.yaml"
        import yaml

        bad_manifest.write_text(yaml.safe_dump(manifest_data), encoding="utf-8")

        with pytest.raises(ValueError):
            execute_t2a1_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=bad_manifest,
                reference_corpus_dir=REF_DIR,
                output_dir=tmp_path / "out",
            )

    # 6. Exact reference-corpus hash validation
    def test_6_exact_reference_corpus_hash_validation(self, tmp_path: Path):
        mutated_corpus = tmp_path / "mutated_ref"
        shutil.copytree(REF_DIR, mutated_corpus)
        target_ref = mutated_corpus / "archlint" / "ref-archlint-001.jsonl"
        data = json.loads(target_ref.read_text(encoding="utf-8"))
        data["raw_evidence"] += " // mutate hash"
        target_ref.write_text(json.dumps(data) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Reference corpus hash mismatch"):
            execute_t2a1_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=mutated_corpus,
                output_dir=tmp_path / "out",
            )


# ── Vocabulary Equivalence Tests ───────────────────────────────────────────────


class TestVocabularyEquivalence:
    # 7. 3-root / 8-term candidate-ID equivalence
    def test_7_three_root_versus_eight_term_candidate_id_equivalence(self, repo_clone_cache: dict[str, Path]):
        from mneme.open_architecture.candidates import HeuristicExtractor
        from mneme.open_architecture.discovery import discover_sources
        from mneme.open_architecture.execution import materialize_repository
        from mneme.open_architecture.manifest import Manifest
        from mneme.open_architecture.source_coverage_experiment import (
            discover_go_sources,
        )

        manifest = Manifest.load(MANIFEST_PATH)
        base_kws = HeuristicExtractor.DECISION_KEYWORDS
        kws_8 = base_kws | {
            "supersede",
            "superseded",
            "supersedes",
            "deprecate",
            "deprecated",
            "allow",
            "allows",
            "allowed",
        }
        kws_3 = base_kws | {"supersede", "deprecate", "allow"}

        for repo_cfg in manifest.repositories:
            with materialize_repository(repo_cfg, clone_source=repo_clone_cache[repo_cfg.id]) as checkout:
                docs = list(discover_sources(checkout).documents)
                if repo_cfg.id == "archlint":
                    docs.extend(discover_go_sources(checkout).documents)
                docs.sort(key=lambda d: d.relative_path)

                ext_8 = HeuristicExtractor()
                ext_8.DECISION_KEYWORDS = kws_8
                cands_8 = []
                for d in docs:
                    cands_8.extend(ext_8.extract(d, checkout.resolved_commit_sha))
                ids_8 = {c.candidate_id for c in cands_8}

                ext_3 = HeuristicExtractor()
                ext_3.DECISION_KEYWORDS = kws_3
                cands_3 = []
                for d in docs:
                    cands_3.extend(ext_3.extract(d, checkout.resolved_commit_sha))
                ids_3 = {c.candidate_id for c in cands_3}

                # Prove set difference in both directions is strictly empty
                assert ids_3 - ids_8 == set(), f"3-root minus 8-term non-empty in {repo_cfg.id}"
                assert ids_8 - ids_3 == set(), f"8-term minus 3-root non-empty in {repo_cfg.id}"


# ── Execution and Metrics Tests ────────────────────────────────────────────────


class TestT2AExecutionAndMetrics:
    # 8. T2A.1 exact candidate/match metrics
    def test_8_t2a1_exact_metrics(self, t2a1_result: T2AExperimentResult):
        res = t2a1_result
        assert isinstance(res, T2AExperimentResult)
        assert res.total_candidates == 5671
        assert res.matched_candidates == 279
        assert res.matched_references == 100
        assert res.unmatched_references == 0

        expected_prec = 279 / 5671
        expected_rec = 1.0
        expected_f1 = 2 * expected_prec * expected_rec / (expected_prec + expected_rec)
        assert res.discovery_precision == pytest.approx(expected_prec)
        assert res.stage_a_recall == pytest.approx(1.0)
        assert res.stage_a_micro_f1 == pytest.approx(expected_f1)

    # 9. T2A.2 exact candidate/match metrics
    def test_9_t2a2_exact_metrics(self, t2a2_result: T2AExperimentResult):
        res = t2a2_result
        assert isinstance(res, T2AExperimentResult)
        assert res.total_candidates == 5563
        assert res.matched_candidates == 278
        assert res.matched_references == 100
        assert res.unmatched_references == 0

        expected_prec = 278 / 5563
        expected_rec = 1.0
        expected_f1 = 2 * expected_prec * expected_rec / (expected_prec + expected_rec)
        assert res.discovery_precision == pytest.approx(expected_prec)
        assert res.stage_a_recall == pytest.approx(1.0)
        assert res.stage_a_micro_f1 == pytest.approx(expected_f1)

    # 10. All four extraction misses recovered
    def test_10_all_four_extraction_misses_recovered(self, t2a2_result: T2AExperimentResult):
        res = t2a2_result
        arch_matched_ids = set(res.repository_results["archlint"].ref_to_cand_matches.keys())
        assert "ref-archlint-008" in arch_matched_ids
        assert "ref-archlint-009" in arch_matched_ids
        assert "ref-archlint-010" in arch_matched_ids

        mod_matched_ids = set(res.repository_results["modonome"].ref_to_cand_matches.keys())
        assert "ref-modonome-015" in mod_matched_ids

    # 11. Zero regression across all 96 T1 matched references
    def test_11_zero_regression_across_all_96_t1_matched_references(self, t2a2_result: T2AExperimentResult):
        res = t2a2_result
        for repo_id, stage_a_res in res.repository_results.items():
            assert stage_a_res.matched_reference_count == 20
            assert stage_a_res.unmatched_reference_ids == []

    # 12. T2A.2 precision and F1 > corrected T1
    def test_12_t2a2_precision_and_f1_higher_than_t1(self, t2a2_result: T2AExperimentResult):
        res = t2a2_result
        t1_precision = 272 / 5507
        t1_f1 = 2 * t1_precision * 0.96 / (t1_precision + 0.96)

        assert res.discovery_precision > t1_precision
        assert res.stage_a_micro_f1 > t1_f1

    # 13. T2A.2 precision and F1 > T2A.1
    def test_13_t2a2_precision_and_f1_higher_than_t2a1(
        self,
        t2a1_result: T2AExperimentResult,
        t2a2_result: T2AExperimentResult,
    ):
        res_1 = t2a1_result
        res_2 = t2a2_result

        assert res_2.discovery_precision > res_1.discovery_precision
        assert res_2.stage_a_micro_f1 > res_1.stage_a_micro_f1
        assert res_2.total_candidates < res_1.total_candidates


# ── Reproducibility & Safety Tests ─────────────────────────────────────────────


class TestT2AReproducibilityAndSafety:
    # 14. Artifact determinism (byte-identical across runs)
    def test_14_artifact_determinism_byte_identical(self, tmp_path: Path, repo_clone_cache: dict[str, Path]):
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"

        execute_t2a2_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_a,
            clone_sources=repo_clone_cache,
        )
        execute_t2a2_experiment(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_b,
            clone_sources=repo_clone_cache,
        )

        assert (dir_a / "t2a2_summary.json").read_bytes() == (dir_b / "t2a2_summary.json").read_bytes()
        assert (dir_a / "t2a2_candidate_matches.jsonl").read_bytes() == (dir_b / "t2a2_candidate_matches.jsonl").read_bytes()

    # 15. Output directory fail-closed behavior
    def test_15_output_dir_fail_closed(self, tmp_path: Path):
        occupied = tmp_path / "occupied"
        occupied.mkdir()
        (occupied / "existing.txt").write_text("prior data", encoding="utf-8")

        with pytest.raises(ValueError, match="already exists and is not empty. Overwrite prevented"):
            execute_t2a1_experiment(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                output_dir=occupied,
            )

    # 16. Zero model calls
    def test_16_zero_model_calls(self):
        import mneme.open_architecture.extraction_tuning_experiment as mod
        text = inspect.getsource(mod)
        assert "SemanticClassifier" not in text
        assert "Anthropic" not in text
        assert "chat.completions" not in text
        assert "ClassifierTask" not in text

    # 17. Zero canonical writes
    def test_17_zero_canonical_writes(self):
        import mneme.open_architecture.extraction_tuning_experiment as mod
        vars_dict = vars(mod)
        forbidden = [
            "DecisionAuthorityService",
            "MemoryStore",
            "DecisionProposal",
            "DecisionIndex",
            "adrs_to_decisions",
            "resolve_precedence",
        ]
        for name in forbidden:
            assert name not in vars_dict, f"Forbidden canonical component '{name}' imported in experiment module"

    # 18. Frozen semantic module hashes remain bound to the pinned engine
    def test_18_frozen_semantic_module_hashes_remain_unchanged(self):
        from tests.open_architecture.test_baseline import (
            FROZEN_SEMANTIC_MODULE_HASHES,
            frozen_semantic_module_hash,
        )
        for rel_path, expected_hash in FROZEN_SEMANTIC_MODULE_HASHES.items():
            actual_hash = frozen_semantic_module_hash(rel_path)
            assert actual_hash == expected_hash, f"Hash mismatch in {rel_path}"

    # 19. Corrected T1 accounting remains 272 matched candidates
    def test_19_corrected_t1_accounting_remains_272_matched_candidates(self):
        assert B0_OTHER_REPOS_MATCHED_CANDIDATES == 250, (
            "B0_OTHER_REPOS_MATCHED_CANDIDATES must be exactly 250 (256 - 6)"
        )
        t1_total_matched = B0_OTHER_REPOS_MATCHED_CANDIDATES + 22
        assert t1_total_matched == 272, "T1 total matched candidates must be exactly 272"

    # 20. Test-policy registration verified
    def test_20_test_policy_registration_verified(self):
        from tests.test_test_policy import unclassified_canonical_test_paths
        unclassified = unclassified_canonical_test_paths()
        assert not unclassified, f"Unclassified test paths exist: {unclassified}"

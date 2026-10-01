"""
tests.open_architecture.test_source_coverage_experiment — Verification for T1 Stage A coverage.

Covers all 17 required gates:
1. Deterministic profile hash
2. Profile hash is derived, not caller-controlled
3. .go-only enumeration
4. Deterministic ordering
5. .git exclusion
6. File symlink skipping
7. Directory symlink/junction skipping
8. Oversized diagnostic
9. Undecodable UTF-8 diagnostic
10. Valid SHA-256 content hash
11. Valid DiscoveredSourceDocument adaptation using source_type='documentation'
12. Frozen DOCUMENTATION_EXTENSIONS unchanged
13. Frozen evaluate_stage_a_discovery signature unchanged
14. Output directory overwrite protection
15. Zero model/classifier calls
16. Zero canonical writes
17. Archlint pinned-corpus result:
    - 34 Go documents
    - 48 additional extracted candidates
    - all 14 previously MISSED_SOURCE Archlint references become source-covered
    - exactly 11 of those become Stage-A matched
    - ref-archlint-008 remains unmatched
    - ref-archlint-009 remains unmatched
    - ref-archlint-010 remains unmatched
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mneme.open_architecture.candidates import HeuristicExtractor
from mneme.open_architecture.discovery import (
    DOCUMENTATION_EXTENSIONS,
    DiscoveredSourceDocument,
    DiscoveryResult,
)
from mneme.open_architecture.harness import evaluate_stage_a_discovery
from mneme.open_architecture.source_coverage_experiment import (
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    PINNED_ARCHLINT_GITHUB,
    PINNED_ARCHLINT_REPO_ID,
    PINNED_ARCHLINT_SHA,
    SourceCoverageExperimentProfile,
    SourceCoverageExperimentResult,
    calculate_source_coverage,
    discover_go_sources,
    execute_source_coverage_experiment,
)

REF_DIR = Path(__file__).parent.parent.parent / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"


# ── Profile Contract Tests ─────────────────────────────────────────────────────


class TestSourceCoverageProfile:
    # 1. Deterministic profile hash
    def test_1_deterministic_profile_hash(self):
        p1 = SourceCoverageExperimentProfile()
        p2 = SourceCoverageExperimentProfile()
        assert p1.experiment_profile_hash == p2.experiment_profile_hash
        assert len(p1.experiment_profile_hash) == 32
        assert p1.experiment_id == "t1-source-coverage-go"
        assert p1.baseline_id == FROZEN_BASELINE_ID
        assert p1.target_repository == PINNED_ARCHLINT_REPO_ID
        assert p1.target_extension == ".go"
        assert p1.reference_corpus_hash == FROZEN_REFERENCE_CORPUS_HASH

    # 2. Profile hash is derived, not caller-controlled
    def test_2_profile_hash_is_derived_not_caller_controlled(self):
        # Attempting to supply experiment_profile_hash as a constructor kwarg must fail
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            SourceCoverageExperimentProfile(experiment_profile_hash="custom_hash_123")  # type: ignore[call-arg]

        # Profile is frozen
        p = SourceCoverageExperimentProfile()
        with pytest.raises(FrozenInstanceError):
            p.experiment_id = "other"  # type: ignore[misc]

    # 2b. Profile fields are strictly bounded (fail closed on caller overrides)
    def test_2b_profile_fields_strictly_bounded(self):
        with pytest.raises(ValueError, match="experiment_id must be strictly 't1-source-coverage-go'"):
            SourceCoverageExperimentProfile(experiment_id="other")

        with pytest.raises(ValueError, match="baseline_id must be strictly 'o1a-batch-01-baseline'"):
            SourceCoverageExperimentProfile(baseline_id="other")

        with pytest.raises(ValueError, match="target_repository must be strictly 'archlint'"):
            SourceCoverageExperimentProfile(target_repository="other")

        with pytest.raises(ValueError, match="target_extension must be strictly '.go'"):
            SourceCoverageExperimentProfile(target_extension=".py")

        with pytest.raises(ValueError, match="reference_corpus_hash must be strictly"):
            SourceCoverageExperimentProfile(reference_corpus_hash="0" * 32)


# ── Go Discovery Adapter Tests ─────────────────────────────────────────────────


class TestGoDiscoveryAdapter:
    # 3. .go-only enumeration
    def test_3_go_only_enumeration(self, tmp_path: Path):
        (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Doc\n", encoding="utf-8")
        (tmp_path / "script.py").write_text("print(1)\n", encoding="utf-8")
        (tmp_path / "data.json").write_text("{}\n", encoding="utf-8")
        (tmp_path / "style.css").write_text("body {}\n", encoding="utf-8")

        result = discover_go_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["main.go"]
        # Non-.go files must not produce noisy diagnostics
        assert len(result.diagnostics) == 0

    # 4. Deterministic ordering
    def test_4_deterministic_ordering(self, tmp_path: Path):
        (tmp_path / "z.go").write_text("package z\n", encoding="utf-8")
        (tmp_path / "a.go").write_text("package a\n", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.go").write_text("package b\n", encoding="utf-8")
        (tmp_path / "sub" / "a.go").write_text("package sa\n", encoding="utf-8")

        result = discover_go_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["a.go", "sub/a.go", "sub/b.go", "z.go"]

    # 5. .git exclusion
    def test_5_git_exclusion(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hook.go").write_text("package hook\n", encoding="utf-8")
        (tmp_path / "real.go").write_text("package real\n", encoding="utf-8")

        result = discover_go_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["real.go"]
        assert not any(".git" in g.path for g in result.diagnostics)

    # 6. File symlink skipping
    def test_6_file_symlink_skipping(self, tmp_path: Path):
        target = tmp_path / "target.go"
        target.write_text("package target\n", encoding="utf-8")
        link = tmp_path / "link.go"

        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported in this environment")

        result = discover_go_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert "target.go" in paths
        assert "link.go" not in paths
        diag = next((g for g in result.diagnostics if g.path == "link.go"), None)
        assert diag is not None
        assert diag.kind == "symlink_skipped"

    # 7. Directory symlink / junction skipping
    def test_7_directory_symlink_or_junction_skipping(self, tmp_path: Path):
        target_dir = tmp_path / "target_pkg"
        target_dir.mkdir()
        (target_dir / "target.go").write_text("package pkg\n", encoding="utf-8")
        link_dir = tmp_path / "link_pkg"

        created = False
        try:
            link_dir.symlink_to(target_dir, target_is_directory=True)
            created = True
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(target_dir), str(link_dir))
                created = True
            except Exception:
                pass

        if not created:
            pytest.skip("Neither symlinks nor directory junctions could be created in this environment")

        result = discover_go_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert "target_pkg/target.go" in paths
        assert not any("link_pkg" in p for p in paths)
        diag = next((g for g in result.diagnostics if "link_pkg" in g.path), None)
        assert diag is not None
        assert diag.kind == "symlink_skipped"

    # 8. Oversized diagnostic
    def test_8_oversized_diagnostic(self, tmp_path: Path):
        (tmp_path / "huge.go").write_text("package main\n" + "var x = 1\n" * 200, encoding="utf-8")
        (tmp_path / "small.go").write_text("package main\n", encoding="utf-8")

        result = discover_go_sources(tmp_path, max_file_size_bytes=100)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["small.go"]

        diag = next((g for g in result.diagnostics if g.path == "huge.go"), None)
        assert diag is not None
        assert diag.kind == "file_oversized"

    # 9. Undecodable UTF-8 diagnostic
    def test_9_undecodable_utf8_diagnostic(self, tmp_path: Path):
        (tmp_path / "binary.go").write_bytes(b"package main\n\xff\xfe\x00")
        (tmp_path / "valid.go").write_text("package main\n", encoding="utf-8")

        result = discover_go_sources(tmp_path)
        paths = [d.relative_path for d in result.documents]
        assert paths == ["valid.go"]

        diag = next((g for g in result.diagnostics if g.path == "binary.go"), None)
        assert diag is not None
        assert diag.kind == "undecodable_encoding"

    # 10. Valid SHA-256 content hash
    def test_10_valid_sha256_content_hash(self, tmp_path: Path):
        raw = b"package config\n\ntype Config struct{}\n"
        expected_hash = "sha256:" + hashlib.sha256(raw).hexdigest().lower()
        (tmp_path / "config.go").write_bytes(raw)

        result = discover_go_sources(tmp_path)
        assert len(result.documents) == 1
        assert result.documents[0].content_hash == expected_hash

    # 11. Valid DiscoveredSourceDocument adaptation using source_type='documentation'
    def test_11_valid_discovered_source_document_adaptation(self, tmp_path: Path):
        (tmp_path / "adr.go").write_text("package adr\n", encoding="utf-8")
        result = discover_go_sources(tmp_path)
        assert len(result.documents) == 1
        doc = result.documents[0]

        assert doc.source_type == "documentation"
        assert doc.relative_path == "adr.go"
        assert doc.metadata["extension"] == ".go"
        assert doc.metadata["evidence_kind"] == "source_code"
        assert doc.metadata["language"] == "go"
        assert doc.metadata["is_mneme_adr"] is False


# ── Frozen Preservation & Immutability Tests ───────────────────────────────────


class TestFrozenImmutabilityPreserved:
    # 12. Frozen DOCUMENTATION_EXTENSIONS unchanged
    def test_12_frozen_documentation_extensions_unchanged(self):
        assert DOCUMENTATION_EXTENSIONS == frozenset({".md", ".mdx", ".rst"}), (
            "DOCUMENTATION_EXTENSIONS in discovery.py must not be modified"
        )

    # 13. Frozen evaluate_stage_a_discovery signature unchanged
    def test_13_frozen_evaluate_stage_a_discovery_signature_unchanged(self):
        sig = inspect.signature(evaluate_stage_a_discovery)
        params = list(sig.parameters.keys())
        assert params == ["repository_config", "references", "clone_source", "workspace_dir"]
        assert "extractor" not in params
        assert "supported_extensions" not in params
        assert "checkout_dir" not in params


# ── Artifact & Overwrite Protection Tests ──────────────────────────────────────


class TestExecutionSafetyAndArtifacts:
    # 14. Output directory overwrite protection
    def test_14_output_directory_overwrite_protection(self, tmp_path: Path):
        occupied_dir = tmp_path / "occupied"
        occupied_dir.mkdir()
        (occupied_dir / "prior.txt").write_text("existing", encoding="utf-8")

        with pytest.raises(ValueError, match="already exists and is not empty. Overwrite prevented"):
            execute_source_coverage_experiment(
                reference_corpus_dir=REF_DIR,
                output_dir=occupied_dir,
            )

    # 14b. Mutated reference corpus rejected fail-closed
    def test_14b_mutated_reference_corpus_rejected_fail_closed(self, tmp_path: Path):
        import shutil

        # Copy frozen reference corpus into a temporary directory
        mutated_corpus = tmp_path / "mutated_corpus"
        shutil.copytree(REF_DIR, mutated_corpus)

        # Mutate one file while keeping the 20 reference count
        target_ref = mutated_corpus / "archlint" / "ref-archlint-001.jsonl"
        text = target_ref.read_text(encoding="utf-8")
        data = json.loads(text)
        data["raw_evidence"] += " // mutation to alter content hash"
        target_ref.write_text(json.dumps(data) + "\n", encoding="utf-8")

        out_dir = tmp_path / "out"
        with pytest.raises(ValueError, match="Reference corpus hash mismatch"):
            execute_source_coverage_experiment(
                reference_corpus_dir=mutated_corpus,
                output_dir=out_dir,
            )

    # 15. Zero model / classifier calls
    def test_15_zero_model_calls(self):
        import mneme.open_architecture.source_coverage_experiment as exp_module
        module_text = inspect.getsource(exp_module)
        assert "SemanticClassifier" not in module_text
        assert "Anthropic" not in module_text
        assert "chat.completions" not in module_text
        assert "ClassifierTask" not in module_text

    # 16. Zero canonical writes
    def test_16_zero_canonical_writes(self):
        import mneme.open_architecture.source_coverage_experiment as exp_module
        module_vars = vars(exp_module)
        forbidden = [
            "DecisionAuthorityService",
            "MemoryStore",
            "DecisionProposal",
            "DecisionIndex",
            "adrs_to_decisions",
            "resolve_precedence",
        ]
        for name in forbidden:
            assert name not in module_vars, f"Forbidden canonical component '{name}' imported in experiment module"
        module_text = inspect.getsource(exp_module)
        assert "MemoryStore(" not in module_text
        assert "DecisionProposal(" not in module_text
        assert "DecisionIndex(" not in module_text


# ── Archlint Pinned-Corpus Ground Truth Execution ──────────────────────────────


class TestArchlintPinnedCorpusExecution:
    # 17. Archlint pinned-corpus result
    def test_17_archlint_pinned_corpus_result(self, tmp_path: Path):
        out_dir = tmp_path / "t1_archlint_artifacts"
        profile = SourceCoverageExperimentProfile()

        result = execute_source_coverage_experiment(
            experiment_profile=profile,
            reference_corpus_dir=REF_DIR,
            output_dir=out_dir,
        )

        assert isinstance(result, SourceCoverageExperimentResult)

        # 17a. 34 Go documents discovered in Archlint
        assert result.go_documents_count == 34, f"Expected 34 Go documents, got {result.go_documents_count}"

        # 17b. 48 additional extracted candidates from Go files
        assert result.go_candidates_count == 48, f"Expected 48 Go candidates, got {result.go_candidates_count}"

        # 17c. All 14 previously MISSED_SOURCE Archlint references become source-covered
        sc = result.archlint_source_coverage
        assert sc["total_references"] == 20
        assert sc["source_covered_count"] == 20
        assert sc["source_coverage_rate"] == 1.0
        assert sc["missed_source_count"] == 0
        assert sc["missed_source_reference_ids"] == []

        # 17d. Exactly 11 of those become Stage-A matched (total 17 matched: 6 doc + 11 code)
        stage_a = result.archlint_stage_a
        assert stage_a.reference_decisions_count == 20
        assert stage_a.matched_reference_count == 17

        # 17e. Exactly ref-archlint-008, 009, 010 remain unmatched
        expected_unmatched = ["ref-archlint-008", "ref-archlint-009", "ref-archlint-010"]
        assert stage_a.unmatched_reference_ids == expected_unmatched

        # 17f. Artifacts written deterministically
        assert (out_dir / "t1_summary.json").is_file()
        assert (out_dir / "candidate_matches.jsonl").is_file()

        summary = json.loads((out_dir / "t1_summary.json").read_text(encoding="utf-8"))
        assert "executed_at" not in summary, "t1_summary.json must not contain non-deterministic wall-clock timestamps"
        assert summary["experiment_id"] == "t1-source-coverage-go"
        assert summary["archlint"]["go_documents_count"] == 34
        assert summary["archlint"]["go_extracted_candidates"] == 48
        assert summary["archlint"]["source_covered_count"] == 20
        assert summary["archlint"]["stage_a_matched_references"] == 17
        assert summary["archlint"]["unmatched_reference_ids"] == expected_unmatched
        assert summary["aggregate"]["matched_references"] == 96
        assert summary["aggregate"]["total_candidates"] == 5507
        assert summary["aggregate"]["matched_candidates"] == 272
        expected_precision = 272 / 5507
        expected_recall = 96 / 100
        expected_f1 = (
            2 * expected_precision * expected_recall / (expected_precision + expected_recall)
        )
        expected_overall_o1 = (expected_f1 + 0.517188 + 0.103728) / 3.0
        assert summary["aggregate"]["discovery_precision"] == pytest.approx(expected_precision)
        assert summary["aggregate"]["stage_a_recall"] == pytest.approx(expected_recall)
        assert summary["aggregate"]["stage_a_micro_f1"] == pytest.approx(expected_f1)
        assert summary["aggregate"]["t1_overall_o1_score"] == pytest.approx(expected_overall_o1)

        # Verify candidate_matches.jsonl
        lines = [l for l in (out_dir / "candidate_matches.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == stage_a.extracted_candidates_count
        first_cand = json.loads(lines[0])
        assert "candidate_id" in first_cand
        assert "source_path" in first_cand
        assert "matched" in first_cand

    # 18. Deterministic artifact bytes identical across runs
    def test_18_deterministic_artifact_bytes_identical(self, tmp_path: Path):
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"
        profile = SourceCoverageExperimentProfile()

        execute_source_coverage_experiment(
            experiment_profile=profile,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_a,
        )

        execute_source_coverage_experiment(
            experiment_profile=profile,
            reference_corpus_dir=REF_DIR,
            output_dir=dir_b,
        )

        # Byte-for-byte identical verification
        summary_a = (dir_a / "t1_summary.json").read_bytes()
        summary_b = (dir_b / "t1_summary.json").read_bytes()
        assert summary_a == summary_b, "t1_summary.json must be byte-for-byte identical across runs"

        matches_a = (dir_a / "candidate_matches.jsonl").read_bytes()
        matches_b = (dir_b / "candidate_matches.jsonl").read_bytes()
        assert matches_a == matches_b, "candidate_matches.jsonl must be byte-for-byte identical across runs"

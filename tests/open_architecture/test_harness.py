"""
tests.open_architecture.test_harness — Comprehensive tests for the O1A Batch 01 staged benchmark harness.

Covers all 10 Stage A/B/C and preflight requirements:
1. frozen manifest hash direct binding
2. Stage B cannot execute without valid preflight
3. invalid preflight causes classifier execution count == 0
4. classification failure on expected prescriptive ref increments FN / reduces recall
5. all successful Stage B semantic dimensions persist normalized ResearchStore rows
6. failed dimension persists raw escalated execution but no normalized semantic row
7. Stage A public path cannot use an unverified checkout_dir or substitute extractor
8. pure Stage A matching helper still covers 1->N, N->1, discontinuous, multi-file, MISSED_SOURCE
9. human reference DecisionCandidate confidence is None
10. persisted reference discovery_confidence is None
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from mneme.open_architecture.baseline import (
    FROZEN_SEMANTIC_MNEME_SHA,
    BaselineConfig,
)
from mneme.open_architecture.candidates import (
    ExtractedCandidate,
    HeuristicExtractor,
    LineSpan,
)
from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    StaticClassifier,
)
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.export import import_scenarios_jsonl
from mneme.open_architecture.gds_evaluation import compute_suite_gds_metrics
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_SCENARIO_CORPUS_HASH,
    BatchPreflightResult,
    BatchProvenanceEnvelope,
    FrozenReferenceDecision,
    HarnessPreflightError,
    SEMANTIC_TASK_TYPES,
    build_stage_b_tasks,
    evaluate_discovery_matches,
    evaluate_stage_a_discovery,
    execute_stage_b_classification,
    execute_stage_c_gds,
    load_reference_corpus,
    parse_reference_intervals,
    preflight_batch_01,
)
from mneme.open_architecture.manifest import Manifest, RepositoryConfig
from mneme.open_architecture.orchestrator import _compute_scenario_content_hash
from mneme.open_architecture.run_metadata import RunMetadata
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    ChangeContext,
    DecisionCandidate,
    Scope,
)
from mneme.open_architecture.store import (
    AnalysisRunRecord,
    ClassifierVersionRecord,
    RepositoryRecord,
    ResearchStore,
    TaxonomyVersionRecord,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"
SCENARIOS_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "scenarios" / "scenarios.jsonl"


# ── Helpers & Fixtures ─────────────────────────────────────────────────────────


class MockTrackingClassifier(StaticClassifier):
    """Classifier configured with frozen Anthropic identity that tracks execution count."""

    def __init__(
        self,
        backend_id: str = "anthropic",
        classifier_version: str = "0.1",
        model_identifier: str | None = "claude-sonnet-4-6",
        **kwargs,
    ):
        super().__init__(
            backend_id=backend_id,
            classifier_version=classifier_version,
            model_identifier=model_identifier,
            **kwargs,
        )
        self.call_count = 0

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        self.call_count += 1
        return super().execute(task)


class MockFailingClassifier(StaticClassifier):
    """Classifier configured with frozen Anthropic identity that raises on a task type."""

    def __init__(
        self,
        failing_task_type: ClassifierTaskType,
        error_message: str = "Simulated API error",
        backend_id: str = "anthropic",
        classifier_version: str = "0.1",
        model_identifier: str | None = "claude-sonnet-4-6",
        **kwargs,
    ):
        super().__init__(
            backend_id=backend_id,
            classifier_version=classifier_version,
            model_identifier=model_identifier,
            **kwargs,
        )
        self.failing_task_type = failing_task_type
        self.error_message = error_message
        self.call_count = 0

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        self.call_count += 1
        if task.task_type == self.failing_task_type:
            raise RuntimeError(self.error_message)
        return super().execute(task)


def _make_dummy_extracted_candidate(
    candidate_id: str,
    source_path: str,
    start_line: int,
    end_line: int,
) -> ExtractedCandidate:
    return ExtractedCandidate(
        candidate_id=candidate_id,
        repository_identifier="mbeacom/adrkit",
        repository_commit_sha="471457da29638ecca6119b35180c2845bf989cac",
        source_path=source_path,
        source_content_hash="sha256:" + "0" * 64,
        source_location=LineSpan(start_line, end_line),
        raw_statement="Dummy statement text",
        discovery_confidence=0.85,
    )


@pytest.fixture
def valid_preflight() -> BatchPreflightResult:
    return preflight_batch_01(
        baseline_path=BASELINE_PATH,
        manifest_path=MANIFEST_PATH,
        reference_corpus_dir=REF_DIR,
        scenarios_path=SCENARIOS_PATH,
    )


# ── Test Suite ─────────────────────────────────────────────────────────────────


class TestO1AHarness:
    """Tests all requirements of O1A Batch 01 staged benchmark harness."""

    # 1. preflight rejects baseline mismatch before classifier execution
    def test_1_preflight_rejects_baseline_mismatch(self, tmp_path: Path):
        bad_baseline_file = tmp_path / "bad_baseline.yaml"
        yaml_data = BASELINE_PATH.read_text(encoding="utf-8")
        bad_baseline_file.write_text(yaml_data.replace("status: frozen", "status: planned"), encoding="utf-8")

        with pytest.raises(HarnessPreflightError, match="status must be 'frozen'"):
            preflight_batch_01(
                baseline_path=bad_baseline_file,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
            )

    # 2. preflight rejects reference corpus hash mismatch
    def test_2_preflight_rejects_reference_corpus_hash_mismatch(self, tmp_path: Path):
        empty_ref_dir = tmp_path / "empty_ref_dir"
        empty_ref_dir.mkdir()
        sub = empty_ref_dir / "adrkit"
        sub.mkdir()
        (sub / "ref-adrkit-001.jsonl").write_text('{"reference_decision_id": "ref-adrkit-001"}\n', encoding="utf-8")

        with pytest.raises(HarnessPreflightError, match="Reference corpus content hash mismatch"):
            preflight_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=empty_ref_dir,
                scenarios_path=SCENARIOS_PATH,
            )

    # 3. preflight rejects global scenario corpus hash mismatch
    def test_3_preflight_rejects_global_scenario_corpus_hash_mismatch(self, tmp_path: Path):
        bad_scenarios_file = tmp_path / "bad_scenarios.jsonl"
        lines = SCENARIOS_PATH.read_text(encoding="utf-8").splitlines()
        first_scn = json.loads(lines[0])
        first_scn["description"] = "Mutated description for testing hash mismatch"
        lines[0] = json.dumps(first_scn)
        bad_scenarios_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(HarnessPreflightError, match="Scenario corpus content hash mismatch"):
            preflight_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=bad_scenarios_file,
            )

    # 4. preflight rejects classifier identity mismatch
    def test_4_preflight_rejects_classifier_identity_mismatch(self):
        mismatched_classifier = StaticClassifier(
            backend_id="wrong-backend",
            classifier_version="0.1",
            model_identifier="wrong-model",
        )
        with pytest.raises(HarnessPreflightError, match="Classifier backend_id mismatch"):
            preflight_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                classifier=mismatched_classifier,
            )

    # 4b. preflight rejects extractor keyword set mismatch
    def test_4b_preflight_rejects_extractor_keyword_mismatch(self):
        assert FROZEN_BASELINE_CONFIG_HASH == "31e18dc1e2bd9ad30bec86dce1a9295a"

        class MismatchedKeywordsExtractor(HeuristicExtractor):
            DECISION_KEYWORDS = frozenset({"adopt", "standardize"})

        mismatched_extractor = MismatchedKeywordsExtractor()
        with pytest.raises(HarnessPreflightError, match="Extractor keywords mismatch"):
            preflight_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                extractor=mismatched_extractor,
            )

    # 4c. frozen manifest hash direct binding (rejects matching pair that differs from frozen identity)
    def test_4c_preflight_rejects_manifest_hash_differing_from_frozen_identity(self, tmp_path: Path):
        bad_manifest_file = tmp_path / "bad_manifest.yaml"
        manifest_text = MANIFEST_PATH.read_text(encoding="utf-8").replace("batch_id: \"o1a-batch-01\"", "batch_id: \"other-batch\"")
        bad_manifest_file.write_text(manifest_text, encoding="utf-8")
        bad_manifest = Manifest.load(bad_manifest_file)
        new_manifest_hash = bad_manifest.configuration_hash()

        # Update baseline to match bad_manifest so baseline/manifest agree with each other
        bad_baseline_file = tmp_path / "bad_baseline.yaml"
        baseline_text = BASELINE_PATH.read_text(encoding="utf-8")
        baseline_text = baseline_text.replace("batch_id: \"o1a-batch-01\"", "batch_id: \"other-batch\"")
        baseline_text = baseline_text.replace(f'configuration_hash: "{FROZEN_MANIFEST_CONFIG_HASH}"', f'configuration_hash: "{new_manifest_hash}"')
        bad_baseline_file.write_text(baseline_text, encoding="utf-8")

        with pytest.raises(HarnessPreflightError, match="Manifest configuration hash does not match frozen identity"):
            preflight_batch_01(
                baseline_path=bad_baseline_file,
                manifest_path=bad_manifest_file,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
            )

    # 4d. preflight always checks runtime HeuristicExtractor even without extractor argument
    def test_4d_preflight_always_checks_runtime_heuristic_extractor(self):
        res = preflight_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
        )
        assert res.status == "preflight_ok"
        assert res.classifier_backend_id == "anthropic"
        assert res.classifier_version == "0.1"
        assert res.classifier_model_identifier == "claude-sonnet-4-6"

    # 5. Stage A 1 -> N overlap (one candidate matching multiple references)
    def test_5_stage_a_one_candidate_matching_multiple_references(self):
        ref1 = FrozenReferenceDecision.from_dict({
            "reference_decision_id": "ref-test-001",
            "repository": "test/repo",
            "repository_commit_sha": "0" * 40,
            "source_file": "docs/adr/0001.md",
            "source_location": "L10-L20",
            "raw_evidence": "Evidence 1",
            "normalized_decision": "Decision 1",
            "classification": "prescriptive",
            "decision_domains": ["persistence"],
            "decision_purposes": ["standardize"],
            "authority_status": "explicitly_accepted",
            "scopes": [],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
        })
        ref2 = FrozenReferenceDecision.from_dict({
            "reference_decision_id": "ref-test-002",
            "repository": "test/repo",
            "repository_commit_sha": "0" * 40,
            "source_file": "docs/adr/0001.md",
            "source_location": "L25-L35",
            "raw_evidence": "Evidence 2",
            "normalized_decision": "Decision 2",
            "classification": "prescriptive",
            "decision_domains": ["persistence"],
            "decision_purposes": ["standardize"],
            "authority_status": "explicitly_accepted",
            "scopes": [],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
        })

        cand = _make_dummy_extracted_candidate(
            "cand-00000000000000000000000000000001",
            "docs/adr/0001.md",
            start_line=5,
            end_line=40,
        )

        res = evaluate_discovery_matches(
            candidates=[cand],
            discovered_paths={"docs/adr/0001.md"},
            references=[ref1, ref2],
            repo_id="test",
            discovered_documents_count=1,
        )

        # 1 candidate counts once for precision (1/1 = 1.0)
        # both references match independently for recall (2/2 = 1.0)
        assert res.matched_candidate_count == 1
        assert res.matched_reference_count == 2
        assert res.precision == 1.0
        assert res.recall == 1.0

    # 6. Stage A N -> 1 overlap (multiple candidates matching one reference)
    def test_6_stage_a_multiple_candidates_matching_one_reference(self):
        ref = FrozenReferenceDecision.from_dict({
            "reference_decision_id": "ref-test-001",
            "repository": "test/repo",
            "repository_commit_sha": "0" * 40,
            "source_file": "docs/adr/0001.md",
            "source_location": "L25-L48",
            "raw_evidence": "Evidence",
            "normalized_decision": "Decision",
            "classification": "prescriptive",
            "decision_domains": ["persistence"],
            "decision_purposes": ["standardize"],
            "authority_status": "explicitly_accepted",
            "scopes": [],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
        })

        cand1 = _make_dummy_extracted_candidate("cand-00000000000000000000000000000001", "docs/adr/0001.md", 25, 30)
        cand2 = _make_dummy_extracted_candidate("cand-00000000000000000000000000000002", "docs/adr/0001.md", 35, 45)

        res = evaluate_discovery_matches(
            candidates=[cand1, cand2],
            discovered_paths={"docs/adr/0001.md"},
            references=[ref],
            repo_id="test",
            discovered_documents_count=1,
        )

        # Both candidates participate normally in precision (2/2 = 1.0)
        # The reference counts once for recall (1/1 = 1.0)
        assert res.matched_candidate_count == 2
        assert res.matched_reference_count == 1
        assert res.precision == 1.0
        assert res.recall == 1.0

    # 7. Stage A discontinuous intervals
    def test_7_stage_a_discontinuous_intervals(self):
        loc = "L16-L29, L53-L67"
        intervals = parse_reference_intervals("internal/config/config.go", loc)
        assert len(intervals) == 2
        assert intervals[0] == ("internal/config/config.go", 16, 29)
        assert intervals[1] == ("internal/config/config.go", 53, 67)

        cand = _make_dummy_extracted_candidate("cand-00000000000000000000000000000001", "internal/config/config.go", 60, 70)
        ref = FrozenReferenceDecision.from_dict({
            "reference_decision_id": "ref-test-001",
            "repository": "test/repo",
            "repository_commit_sha": "0" * 40,
            "source_file": "internal/config/config.go",
            "source_location": loc,
            "raw_evidence": "Evidence",
            "normalized_decision": "Decision",
            "classification": "prescriptive",
            "decision_domains": ["persistence"],
            "decision_purposes": ["standardize"],
            "authority_status": "explicitly_accepted",
            "scopes": [],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
        })

        res = evaluate_discovery_matches(
            candidates=[cand],
            discovered_paths={"internal/config/config.go"},
            references=[ref],
            repo_id="test",
            discovered_documents_count=1,
        )
        assert res.matched_reference_count == 1
        assert res.recall == 1.0

    # 8. Stage A multi-file reference
    def test_8_stage_a_multi_file_reference(self):
        source_file = "internal/lang/golang.go, internal/lang/typescript.go, internal/lang/python.go"
        source_loc = "golang.go:L17-L44; typescript.go:L20-L47; python.go:L19-L80"
        intervals = parse_reference_intervals(source_file, source_loc)
        assert len(intervals) == 3
        assert intervals[0] == ("internal/lang/golang.go", 17, 44)
        assert intervals[1] == ("internal/lang/typescript.go", 20, 47)
        assert intervals[2] == ("internal/lang/python.go", 19, 80)

    # 9. Stage A MISSED_SOURCE remains in denominator
    def test_9_stage_a_missed_source_remains_in_denominator(self):
        ref = FrozenReferenceDecision.from_dict({
            "reference_decision_id": "ref-archlint-001",
            "repository": "muhammetsafak/archlint",
            "repository_commit_sha": "185837e93565718d8e1ea653236cd70ca0a89e3a",
            "source_file": "internal/config/config.go",  # Not in discovered markdown docs
            "source_location": "L16-L29",
            "raw_evidence": "Go source evidence",
            "normalized_decision": "Decision",
            "classification": "prescriptive",
            "decision_domains": ["architecture_structure"],
            "decision_purposes": ["standardize"],
            "authority_status": "explicitly_accepted",
            "scopes": [],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
        })

        res = evaluate_discovery_matches(
            candidates=[],
            discovered_paths={"README.md"},
            references=[ref],
            repo_id="archlint",
            discovered_documents_count=1,
        )

        assert res.reference_decisions_count == 1
        assert res.matched_reference_count == 0
        assert res.recall == 0.0
        assert "ref-archlint-001" in res.missed_source_reference_ids

    # 9b. Stage A public path cannot use an unverified checkout_dir or substitute extractor
    def test_9b_stage_a_public_path_has_no_extractor_or_checkout_dir_params(self):
        sig = inspect.signature(evaluate_stage_a_discovery)
        assert "checkout_dir" not in sig.parameters, (
            "evaluate_stage_a_discovery must not expose checkout_dir; "
            "it must always delegate to materialize_repository"
        )
        assert "extractor" not in sig.parameters, (
            "evaluate_stage_a_discovery must not expose extractor parameter; "
            "it must always use frozen runtime HeuristicExtractor"
        )

    # 10. Stage B produces exactly 160 tasks/repo and 800/batch
    def test_10_stage_b_task_counts(self):
        all_refs = load_reference_corpus(REF_DIR)
        assert len(all_refs) == 100

        batch_tasks = build_stage_b_tasks(all_refs)
        assert len(batch_tasks) == 800  # 100 * 8

        adrkit_refs = [r for r in all_refs if r.repository == "mbeacom/adrkit"]
        assert len(adrkit_refs) == 20
        adrkit_tasks = build_stage_b_tasks(adrkit_refs)
        assert len(adrkit_tasks) == 160  # 20 * 8

    # 11. Stage B preserves ref-* task/result identity
    def test_11_stage_b_preserves_ref_identity(self):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        assert sample_ref.reference_decision_id == "ref-adrkit-001"

        tasks = build_stage_b_tasks([sample_ref])
        for t in tasks:
            assert t.candidate_id == "ref-adrkit-001"
            assert t.task_type in SEMANTIC_TASK_TYPES

    # 11b. Stage B cannot execute without valid preflight
    def test_11b_stage_b_requires_valid_preflight(self):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        clf = MockTrackingClassifier()

        with pytest.raises(HarnessPreflightError, match="requires a valid BatchPreflightResult"):
            execute_stage_b_classification(
                repository_config=config,
                references=[sample_ref],
                classifier=clf,
                preflight=None,  # type: ignore
            )

    # 11c. Invalid preflight causes classifier execution count == 0
    def test_11c_invalid_preflight_causes_zero_classifier_executions(self):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        clf = MockTrackingClassifier()

        invalid_preflight = BatchPreflightResult(
            status="failed",
            baseline_id="o1a-batch-01-baseline",
            baseline_configuration_hash=FROZEN_BASELINE_CONFIG_HASH,
            manifest_configuration_hash=FROZEN_MANIFEST_CONFIG_HASH,
            reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
            scenario_corpus_hash=FROZEN_SCENARIO_CORPUS_HASH,
            semantic_mneme_sha=FROZEN_SEMANTIC_MNEME_SHA,
            repositories_verified=("adrkit",),
            classifier_backend_id="anthropic",
            classifier_version="0.1",
            classifier_model_identifier="claude-sonnet-4-6",
        )

        with pytest.raises(HarnessPreflightError, match="preflight status must be 'preflight_ok'"):
            execute_stage_b_classification(
                repository_config=config,
                references=[sample_ref],
                classifier=clf,
                preflight=invalid_preflight,
            )

        assert clf.call_count == 0, "Classifier must not be called when preflight is invalid"

    # 11d. Stage B rejects classifier backend mismatch before any execution
    def test_11d_stage_b_rejects_classifier_backend_mismatch(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        clf = MockTrackingClassifier(backend_id="wrong_backend")

        with pytest.raises(HarnessPreflightError, match="Stage B classifier backend mismatch"):
            execute_stage_b_classification(
                repository_config=config,
                references=[sample_ref],
                classifier=clf,
                preflight=valid_preflight,
            )
        assert clf.call_count == 0, "Execution count must be 0 on backend mismatch"

    # 11e. Stage B rejects classifier version mismatch before any execution
    def test_11e_stage_b_rejects_classifier_version_mismatch(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        clf = MockTrackingClassifier(classifier_version="9.9")

        with pytest.raises(HarnessPreflightError, match="Stage B classifier version mismatch"):
            execute_stage_b_classification(
                repository_config=config,
                references=[sample_ref],
                classifier=clf,
                preflight=valid_preflight,
            )
        assert clf.call_count == 0, "Execution count must be 0 on version mismatch"

    # 11f. Stage B rejects classifier model mismatch before any execution
    def test_11f_stage_b_rejects_classifier_model_mismatch(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        clf = MockTrackingClassifier(model_identifier="wrong-model")

        with pytest.raises(HarnessPreflightError, match="Stage B classifier model mismatch"):
            execute_stage_b_classification(
                repository_config=config,
                references=[sample_ref],
                classifier=clf,
                preflight=valid_preflight,
            )
        assert clf.call_count == 0, "Execution count must be 0 on model mismatch"

    # 11g. Default StaticClassifier cannot execute Stage B even with valid preflight
    def test_11g_default_static_classifier_cannot_execute_stage_b(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        clf = StaticClassifier()  # default backend="static", model="static/test"

        with pytest.raises(HarnessPreflightError, match="Stage B classifier backend mismatch"):
            execute_stage_b_classification(
                repository_config=config,
                references=[sample_ref],
                classifier=clf,
                preflight=valid_preflight,
            )

    # 12. Stage B exact scalar metrics (classification, authority, lifecycle, enforcement)
    def test_12_stage_b_exact_scalar_metrics(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        clf = StaticClassifier(
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status, "evidence": "good"},
                ClassifierTaskType.SCOPE: {"scopes": list(sample_ref.scopes)},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": list(sample_ref.relationships)},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            },
        )
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
        )

        m = res.metrics
        assert m["decision_classification_accuracy"] == 1.0
        assert m["prescriptive_intent_precision"] == 1.0
        assert m["prescriptive_intent_recall"] == 1.0
        assert m["prescriptive_intent_f1"] == 1.0
        assert m["authority_accuracy"] == 1.0
        assert m["lifecycle_accuracy"] == 1.0
        assert m["enforcement_classification_accuracy"] == 1.0

    # 12b. Classification failure on expected prescriptive ref increments FN / reduces recall
    def test_12b_prescriptive_intent_failure_reduces_recall(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        assert sample_ref.classification == "prescriptive"

        # Classifier fails on DECISION_CLASSIFICATION
        clf = MockFailingClassifier(
            failing_task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            error_message="Classification provider failure",
            outputs={
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": list(sample_ref.scopes)},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": list(sample_ref.relationships)},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            },
        )
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
        )

        m = res.metrics
        assert m["prescriptive_intent_recall"] == 0.0, "Expected prescriptive reference must count as FN upon failure"
        assert m["decision_classification_accuracy"] == 0.0

    # 13. Stage B domain/purpose multi-label metrics
    def test_13_stage_b_domain_purpose_metrics(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        clf = StaticClassifier(
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": ["developer_workflow", "persistence"]},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": list(sample_ref.scopes)},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": list(sample_ref.relationships)},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            },
        )
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
        )

        m = res.metrics
        assert m["domain_macro_precision"] == 0.5
        assert m["domain_macro_recall"] == 0.5
        assert m["domain_macro_f1"] == 0.5

    # 14. Stage B scope order-insensitive equality
    def test_14_stage_b_scope_order_insensitive_equality(self, valid_preflight: BatchPreflightResult):
        ref = FrozenReferenceDecision.from_dict({
            "reference_decision_id": "ref-test-001",
            "repository": "test/repo",
            "repository_commit_sha": "0" * 40,
            "source_file": "docs/adr/0001.md",
            "source_location": "L10-L20",
            "raw_evidence": "Evidence",
            "normalized_decision": "Decision",
            "classification": "prescriptive",
            "decision_domains": ["persistence"],
            "decision_purposes": ["standardize"],
            "authority_status": "explicitly_accepted",
            "scopes": [
                {"scope_type": "directory", "scope_expression": "docs/adr"},
                {"scope_type": "package", "scope_expression": "@adrkit/core"},
            ],
            "lifecycle_status": "active",
            "relationships": [],
            "enforcement_potential": "deterministic_rule",
        })

        clf = StaticClassifier(
            backend_id="anthropic",
            classifier_version="0.1",
            model_identifier="claude-sonnet-4-6",
            outputs={
                ClassifierTaskType.SCOPE: {
                    "scopes": [
                        {"scope_type": "package", "scope_expression": "@adrkit/core"},
                        {"scope_type": "directory", "scope_expression": "docs/adr"},
                    ]
                }
            },
        )
        config = RepositoryConfig("test", "test/repo", "0" * 40, "test", "reviewed")
        res = execute_stage_b_classification(
            repository_config=config,
            references=[ref],
            classifier=clf,
            preflight=valid_preflight,
        )
        assert res.metrics["scope_accuracy"] == 1.0

    # 15. Stage B classifier failure scores zero without aborting batch
    def test_15_stage_b_classifier_failure_scores_zero_without_aborting(self, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        clf = MockFailingClassifier(
            failing_task_type=ClassifierTaskType.AUTHORITY,
            error_message="Rate limit 429",
        )
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
        )

        assert res.reference_count == 1
        assert res.metrics["authority_accuracy"] == 0.0
        assert "ref-adrkit-001" in res.incomplete_references
        assert "Rate limit 429" in res.incomplete_references["ref-adrkit-001"]["authority"]

    # 16. Stage C projects human ref-* identities and confidence is None
    def test_16_stage_c_projects_human_ref_identities_and_confidence_none(self):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        cand = sample_ref.to_decision_candidate()
        assert cand.candidate_id == "ref-adrkit-001"
        assert cand.normalized_decision == sample_ref.normalized_decision
        assert cand.human_validation_status == "correct"
        assert cand.confidence is None, "Human reference DecisionCandidate must not have invented confidence"

    # 17. Stage C executes exactly 10 scenarios per repository
    def test_17_stage_c_executes_10_scenarios_per_repo(self):
        adrkit_refs = load_reference_corpus(REF_DIR, repo_id="adrkit")
        all_scenarios = import_scenarios_jsonl(SCENARIOS_PATH)
        adrkit_scenarios = [s for s in all_scenarios if s.repository == "mbeacom/adrkit"]
        assert len(adrkit_scenarios) == 10

        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        res = execute_stage_c_gds(
            repository_config=config,
            references=adrkit_refs,
            scenarios=adrkit_scenarios,
        )
        assert res.scenario_count == 10
        assert len(res.scenario_results) == 10
        assert res.suite_metrics["macro_recall"] == 1.0

    # 18. Stage C batch aggregate contains all 50 scenarios
    def test_18_stage_c_batch_aggregate_contains_all_50_scenarios(self):
        all_refs = load_reference_corpus(REF_DIR)
        all_scenarios = import_scenarios_jsonl(SCENARIOS_PATH)
        assert len(all_scenarios) == 50

        manifest = Manifest.load(MANIFEST_PATH)
        all_results = []
        for repo in manifest.repositories:
            repo_refs = [r for r in all_refs if r.repository == repo.github]
            repo_scenarios = [s for s in all_scenarios if s.repository == repo.github]
            res = execute_stage_c_gds(
                repository_config=repo,
                references=repo_refs,
                scenarios=repo_scenarios,
            )
            all_results.extend(res.scenario_results)

        assert len(all_results) == 50
        suite = compute_suite_gds_metrics(all_results)
        assert suite["macro_recall"] == 1.0
        assert suite["macro_f1"] > 0.0

    # 19. ambiguous scenario remains in primary aggregate and is also diagnosable
    def test_19_ambiguous_scenario_remains_in_primary_aggregate_and_diagnosable(self):
        archlint_refs = load_reference_corpus(REF_DIR, repo_id="archlint")
        all_scenarios = import_scenarios_jsonl(SCENARIOS_PATH)
        archlint_scenarios = [s for s in all_scenarios if s.repository == "muhammetsafak/archlint"]
        assert len(archlint_scenarios) == 10

        ambiguous = next(s for s in archlint_scenarios if s.validation_state == "ambiguous")
        assert ambiguous.scenario_id == "scn-archlint-009"

        config = RepositoryConfig("archlint", "muhammetsafak/archlint", "185837e93565718d8e1ea653236cd70ca0a89e3a", "test", "reviewed")
        res = execute_stage_c_gds(
            repository_config=config,
            references=archlint_refs,
            scenarios=archlint_scenarios,
        )

        assert res.scenario_count == 10
        diag = res.diagnostic_by_validation_state
        assert "reviewed" in diag
        assert "ambiguous" in diag
        assert diag["ambiguous"]["macro_recall"] == 1.0

    # 20. global scenario corpus hash differs from per-run subset hash
    def test_20_global_scenario_corpus_hash_differs_from_per_run_subset_hash(self):
        all_scenarios = import_scenarios_jsonl(SCENARIOS_PATH)
        global_hash = _compute_scenario_content_hash(all_scenarios)
        assert global_hash == FROZEN_SCENARIO_CORPUS_HASH

        adrkit_scenarios = [s for s in all_scenarios if s.repository == "mbeacom/adrkit"]
        subset_hash = _compute_scenario_content_hash(adrkit_scenarios)
        assert subset_hash != global_hash

        env = BatchProvenanceEnvelope(
            scenario_corpus_hash=global_hash,
            runs={
                "adrkit": RunMetadata(
                    run_id="run-test",
                    batch_id="o1a-batch-01",
                    repo_id="adrkit",
                    repo_commit_sha="471457da29638ecca6119b35180c2845bf989cac",
                    mneme_version="0.9.2",
                    mneme_commit_sha="b885c3532f37f2f84ff765ba3b94cddd339edfa1",
                    benchmark_schema_version="0.1",
                    taxonomy_version="0.1",
                    classifier_version="0.1",
                    configuration_hash="test",
                    started_at="2026-09-30T00:00:00Z",
                    completed_at=None,
                    status="completed",
                    scenario_content_hash=subset_hash,
                )
            },
        )
        d = env.to_dict()
        assert d["scenario_corpus_hash"] == global_hash
        assert d["runs"]["adrkit"]["scenario_content_hash"] == subset_hash

    # 21. ResearchStore semantic persistence, failed dimension isolation, and discovery_confidence is None
    def test_21_research_store_semantic_persistence(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        db_path = tmp_path / "test_research.db"
        store = ResearchStore(db_path)
        store.initialize_schema()

        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")

        run_id = "run-sample-b-001"
        store.upsert_repository(RepositoryRecord(config.id, "url", config.github, "main"))
        store.upsert_taxonomy_version(TaxonomyVersionRecord("0.1", "2026-09-30", "test"))
        store.upsert_classifier_version(ClassifierVersionRecord("0.1", "2026-09-30", "test"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id=run_id,
            repo_id=config.id,
            repo_commit_sha=config.commit_sha,
            mneme_version="0.9.2",
            mneme_commit_sha="0"*40,
            taxonomy_version="0.1",
            classifier_version="0.1",
            benchmark_schema_version="0.1",
            configuration_hash="conf",
            started_at="2026-09-30T00:00:00Z",
            completed_at=None,
            status="completed",
        ))

        # Classifier succeeds on 7 dimensions, fails on AUTHORITY
        clf = MockFailingClassifier(
            failing_task_type=ClassifierTaskType.AUTHORITY,
            error_message="Authority API timeout",
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.SCOPE: {"scopes": list(sample_ref.scopes)},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": list(sample_ref.relationships)},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            },
        )

        execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
            research_store=store,
            run_id=run_id,
        )

        conn = store.connect()

        # 1. Decision candidate row has discovery_confidence == None
        cand_row = conn.execute(
            "SELECT candidate_id, discovery_confidence FROM decision_candidates WHERE candidate_id = ?",
            (sample_ref.reference_decision_id,),
        ).fetchone()
        assert cand_row is not None
        assert cand_row[0] == sample_ref.reference_decision_id
        assert cand_row[1] is None, "Persisted reference discovery_confidence must be None"

        # 2. Successful dimensions persist normalized child rows
        cls_rows = conn.execute("SELECT classification FROM candidate_classifications WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(cls_rows) == 1
        assert cls_rows[0][0] == sample_ref.classification

        dom_rows = conn.execute("SELECT domain FROM candidate_domains WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(dom_rows) == len(sample_ref.decision_domains)

        pur_rows = conn.execute("SELECT purpose FROM candidate_purposes WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(pur_rows) == len(sample_ref.decision_purposes)

        scope_rows = conn.execute("SELECT scope_type FROM candidate_scopes WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(scope_rows) == len(sample_ref.scopes)

        lc_rows = conn.execute("SELECT lifecycle_status FROM candidate_lifecycle WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(lc_rows) == 1
        assert lc_rows[0][0] == sample_ref.lifecycle_status

        enf_rows = conn.execute("SELECT enforcement_potential FROM enforcement_assessments WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(enf_rows) == 1
        assert enf_rows[0][0] == sample_ref.enforcement_potential

        # 3. Failed dimension (AUTHORITY): raw escalated execution exists, but NO candidate_authority row exists
        exec_rows = conn.execute(
            "SELECT task_type, escalated FROM classifier_executions WHERE candidate_id = ? AND task_type = 'authority'",
            (sample_ref.reference_decision_id,),
        ).fetchall()
        assert len(exec_rows) == 1
        assert exec_rows[0][1] == 1, "Failed task must persist escalated=1 execution record"

        auth_rows = conn.execute("SELECT authority_status FROM candidate_authority WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(auth_rows) == 0, "Failed semantic dimension must NOT create a normalized child row"

        # All 8 tasks persisted in classifier_executions
        all_execs = conn.execute("SELECT execution_id FROM classifier_executions WHERE candidate_id = ?", (sample_ref.reference_decision_id,)).fetchall()
        assert len(all_execs) == 8

    # 22. zero writes to .mneme/ or canonical authority services
    def test_22_zero_writes_to_canonical_mneme(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "rs.db")
        store.initialize_schema()
        conn = store.connect()
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "decisions" not in tables
        assert "decision_index" not in tables
        assert "memory_store" not in tables

    # 23. existing frozen semantic-module boundary remains green
    def test_23_frozen_semantic_module_boundary_remains_green(self):
        import hashlib
        from tests.open_architecture.test_baseline import FROZEN_SEMANTIC_MODULE_HASHES

        mismatches: list[str] = []
        for rel_path, expected_hash in FROZEN_SEMANTIC_MODULE_HASHES.items():
            mod_path = REPO_ROOT / rel_path
            assert mod_path.is_file(), f"Frozen module missing: {rel_path}"
            raw_bytes = mod_path.read_bytes().replace(b"\r\n", b"\n")
            actual_hash = hashlib.sha256(raw_bytes).hexdigest()
            if actual_hash != expected_hash:
                mismatches.append(f"{rel_path}: expected {expected_hash}, got {actual_hash}")

        assert not mismatches, (
            f"Frozen core modules modified:\n" + "\n".join(mismatches)
        )

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

import hashlib
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
    BatchExecutionProfile,
    Batch01RunResult,
    FrozenReferenceDecision,
    HarnessPreflightError,
    HarnessRunError,
    SEMANTIC_TASK_TYPES,
    build_stage_b_tasks,
    evaluate_discovery_matches,
    evaluate_stage_a_discovery,
    execute_stage_b_classification,
    execute_stage_c_gds,
    load_reference_corpus,
    parse_reference_intervals,
    preflight_batch_01,
    run_batch_01,
    run_frozen_batch_01,
    ClassifierExperimentProfile,
    ClassifierExperimentResult,
    execute_classifier_experiment,
    StageADiscoveryResult,
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
    ApplicabilityScenarioRecord,
    ClassifierVersionRecord,
    RepositoryRecord,
    ResearchStore,
    ScenarioExpectedDecisionRecord,
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
        from tests.open_architecture.test_baseline import (
            FROZEN_SEMANTIC_MODULE_HASHES,
            frozen_semantic_module_hash,
        )

        mismatches: list[str] = []
        for rel_path, expected_hash in FROZEN_SEMANTIC_MODULE_HASHES.items():
            actual_hash = frozen_semantic_module_hash(rel_path)
            if actual_hash != expected_hash:
                mismatches.append(f"{rel_path}: expected {expected_hash}, got {actual_hash}")

        assert not mismatches, (
            f"Frozen core modules differ from pinned Batch 01 commit:\n"
            + "\n".join(mismatches)
        )

    # 24. preflight failure performs zero materializations, zero classifier calls, zero execution
    def test_24_runner_preflight_failure_stops_before_execution(self, tmp_path: Path, monkeypatch):
        bad_baseline = tmp_path / "bad_baseline.yaml"
        bad_baseline.write_text(BASELINE_PATH.read_text(encoding="utf-8").replace("status: frozen", "status: planned"), encoding="utf-8")

        stage_a_called = False
        def fake_stage_a(*args, **kwargs):
            nonlocal stage_a_called
            stage_a_called = True
        monkeypatch.setattr("mneme.open_architecture.harness.evaluate_stage_a_discovery", fake_stage_a)

        store = ResearchStore(tmp_path / "store.db")
        tracking_clf = MockTrackingClassifier()
        with pytest.raises(HarnessPreflightError):
            run_frozen_batch_01(
                baseline_path=bad_baseline,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "B", "C"),
                classifier=tracking_clf,
                research_store=store,
                output_dir=tmp_path / "out",
            )
        assert not stage_a_called
        assert tracking_clf.call_count == 0

    # 25. A + C mode: covers 5 repos, 100 refs in Stage A, 50 scenarios in Stage C, zero model calls
    def test_25_runner_a_plus_c_mode(self, tmp_path: Path, monkeypatch):
        stage_a_repos = []
        def fake_stage_a(repository_config, references, **kwargs):
            stage_a_repos.append(repository_config.id)
            return StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=5,
                extracted_candidates_count=len(references),
                reference_decisions_count=len(references),
                matched_reference_count=len(references),
                matched_candidate_count=len(references),
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            )
        monkeypatch.setattr("mneme.open_architecture.harness.evaluate_stage_a_discovery", fake_stage_a)

        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "out"
        res = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            classifier=None,
            research_store=store,
            output_dir=out_dir,
        )
        assert len(stage_a_repos) == 5
        assert len(res.stage_a_results) == 5
        assert sum(r.reference_decisions_count for r in res.stage_a_results.values()) == 100
        assert len(res.stage_c_results) == 5
        assert sum(r.scenario_count for r in res.stage_c_results.values()) == 50
        assert len(res.stage_b_results) == 0
        assert len(res.envelope.runs) == 5
        for meta in res.envelope.runs.values():
            assert meta.configuration_hash is not None
        assert res.envelope.execution_profile.execution_stages == ("A", "C")
        assert res.envelope.execution_profile.execution_scope == "staged_validation"
        assert res.envelope.to_dict()["execution_stages"] == ["A", "C"]
        assert res.envelope.to_dict()["execution_scope"] == "staged_validation"

    # 26. complete A + B + C mode: 100 refs, exactly 800 tasks, 50 scenarios
    def test_26_runner_complete_a_b_c_mode(self, tmp_path: Path, monkeypatch):
        def fake_stage_a(repository_config, references, **kwargs):
            return StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=5,
                extracted_candidates_count=20,
                reference_decisions_count=len(references),
                matched_reference_count=len(references),
                matched_candidate_count=20,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            )
        monkeypatch.setattr("mneme.open_architecture.harness.evaluate_stage_a_discovery", fake_stage_a)

        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "out"
        tracking_clf = MockTrackingClassifier()
        res = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "B", "C"),
            classifier=tracking_clf,
            research_store=store,
            output_dir=out_dir,
        )
        assert len(res.stage_a_results) == 5
        assert len(res.stage_b_results) == 5
        assert len(res.stage_c_results) == 5
        assert sum(r.reference_count for r in res.stage_b_results.values()) == 100
        assert sum(r.task_count for r in res.stage_b_results.values()) == 800
        assert tracking_clf.call_count == 800
        assert sum(r.scenario_count for r in res.stage_c_results.values()) == 50
        for meta in res.envelope.runs.values():
            assert meta.configuration_hash is not None
        assert res.envelope.execution_profile.execution_stages == ("A", "B", "C")
        assert res.envelope.execution_profile.execution_scope == "full_baseline"
        assert res.envelope.to_dict()["execution_stages"] == ["A", "B", "C"]
        assert res.envelope.to_dict()["execution_scope"] == "full_baseline"

    # 27. Stage C uses frozen human references independently of Stage B output
    def test_27_stage_c_independent_of_stage_b(self, tmp_path: Path, monkeypatch):
        def fake_stage_a(repository_config, references, **kwargs):
            return StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            )
        monkeypatch.setattr("mneme.open_architecture.harness.evaluate_stage_a_discovery", fake_stage_a)

        store_ac = ResearchStore(tmp_path / "store_ac.db")
        out_ac = tmp_path / "out_ac"
        res_ac = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store_ac,
            output_dir=out_ac,
        )
        failing_clf = MockFailingClassifier(
            failing_task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
            error_message="Total classification failure",
        )
        store_abc = ResearchStore(tmp_path / "store_abc.db")
        out_abc = tmp_path / "out_abc"
        res_abc = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "B", "C"),
            classifier=failing_clf,
            research_store=store_abc,
            output_dir=out_abc,
        )
        for repo_id in res_ac.stage_c_results:
            ac_metrics = res_ac.stage_c_results[repo_id].suite_metrics
            abc_metrics = res_abc.stage_c_results[repo_id].suite_metrics
            assert ac_metrics == abc_metrics

    # 28. BatchProvenanceEnvelope preserves all 5 repo runs and frozen hashes
    def test_28_batch_provenance_envelope_preserves_identities(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )
        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "out"
        res = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store,
            output_dir=out_dir,
        )
        env = res.envelope
        assert len(env.runs) == 5
        assert set(env.runs.keys()) == {"adrkit", "gsa_agentic_coding_quickstart", "helix", "archlint", "modonome"}
        assert env.baseline_configuration_hash == FROZEN_BASELINE_CONFIG_HASH
        assert env.manifest_configuration_hash == FROZEN_MANIFEST_CONFIG_HASH
        assert env.reference_corpus_hash == FROZEN_REFERENCE_CORPUS_HASH
        assert env.scenario_corpus_hash == FROZEN_SCENARIO_CORPUS_HASH
        assert env.semantic_mneme_sha == FROZEN_SEMANTIC_MNEME_SHA

    # 29. deterministic output ordering and serialization
    def test_29_deterministic_artifact_emission(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )
        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "artifacts"
        res = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store,
            output_dir=out_dir,
        )
        assert (out_dir / "provenance_envelope.json").is_file()
        assert (out_dir / "preflight.json").is_file()
        assert (out_dir / "stage_a_summary.json").is_file()
        assert (out_dir / "stage_c_summary.json").is_file()
        assert (out_dir / "summary.json").is_file()
        assert not (out_dir / "stage_b_summary.json").exists()

        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "completed"
        assert summary["execution_scope"] == "staged_validation"
        assert summary["execution_stages"] == ["A", "C"]
        assert summary["repositories"] == ["adrkit", "archlint", "gsa_agentic_coding_quickstart", "helix", "modonome"]

    # 30. repeated executions into same ResearchStore are append-preserving
    def test_30_repeated_executions_into_same_store_appends_distinct_runs(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )
        store = ResearchStore(tmp_path / "research.db")
        out1 = tmp_path / "out1"
        out2 = tmp_path / "out2"
        res1 = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store,
            output_dir=out1,
        )
        res2 = run_frozen_batch_01(
            baseline_path=BASELINE_path if False else BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store,
            output_dir=out2,
        )
        run_ids1 = {m.run_id for m in res1.envelope.runs.values()}
        run_ids2 = {m.run_id for m in res2.envelope.runs.values()}
        assert run_ids1.isdisjoint(run_ids2)
        all_runs = store.list_analysis_runs()
        assert len(all_runs) == 10

    # 31. failed execution records failed run status where run already created
    def test_31_failed_execution_records_failed_status(self, tmp_path: Path, monkeypatch):
        def failing_stage_c(*args, **kwargs):
            raise RuntimeError("Simulated stage C crash")
        monkeypatch.setattr("mneme.open_architecture.harness.execute_stage_c_gds", failing_stage_c)

        store = ResearchStore(tmp_path / "research_failed.db")
        out_dir = tmp_path / "out"
        with pytest.raises(RuntimeError, match="Simulated stage C crash"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("C",),
                research_store=store,
                output_dir=out_dir,
            )

        runs = store.list_analysis_runs()
        assert len(runs) >= 1
        assert runs[0].status == "failed"

    # 32. invalid stage combinations fail closed
    def test_32_invalid_stages_fail_closed(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "store.db")
        out = tmp_path / "out"
        with pytest.raises(ValueError, match="Stage selection must not be empty"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=(),
                research_store=store,
                output_dir=out,
            )

        with pytest.raises(ValueError, match="Invalid stage"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "X"),
                research_store=store,
                output_dir=out,
            )

        with pytest.raises(ValueError, match="Stage B requires an explicit SemanticClassifier"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "B", "C"),
                classifier=None,
                research_store=store,
                output_dir=out,
            )

    # 33. research-only store isolation - no canonical Mneme state written
    def test_33_runner_no_canonical_mneme_writes(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )
        store_path = tmp_path / "research_isolated.db"
        store = ResearchStore(store_path)
        out_dir = tmp_path / "artifacts"

        tracking_clf = MockTrackingClassifier()
        run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "B", "C"),
            classifier=tracking_clf,
            research_store=store,
            output_dir=out_dir,
        )

        conn = store.connect()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "decisions" not in tables
        assert "decision_index" not in tables
        assert "memory_store" not in tables
        assert "project_memory" not in tables

    # 34. RunMetadata matches exact frozen semantic module hash
    def test_34_run_metadata_matches_frozen_semantic_hash(self):
        mod_path = REPO_ROOT / "mneme" / "open_architecture" / "run_metadata.py"
        raw_bytes = mod_path.read_bytes().replace(b"\r\n", b"\n")
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        assert actual_hash == "67edd59dfb7bb53c73121ad954efcddd4d112ef790cb3495fce59a8588b47a19"

    # 35. A+C and A+B+C have identical RunMetadata config identity but distinct BatchExecutionProfile hashes
    def test_35_ac_and_abc_identical_run_metadata_config_hash_different_profile_hash(self):
        meta1 = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="471457da29638ecca6119b35180c2845bf989cac",
        )
        meta2 = RunMetadata.create(
            batch_id="o1a-batch-01",
            repo_id="adrkit",
            repo_commit_sha="471457da29638ecca6119b35180c2845bf989cac",
        )
        assert meta1.configuration_hash == meta2.configuration_hash

        prof_ac = BatchExecutionProfile.create(stages=("A", "C"))
        prof_abc = BatchExecutionProfile.create(stages=("A", "B", "C"))
        assert prof_ac.execution_profile_hash != prof_abc.execution_profile_hash
        assert prof_ac.execution_scope == "staged_validation"
        assert prof_abc.execution_scope == "full_baseline"

    # 36. equivalent normalized stage sets produce equivalent execution_profile_hash
    def test_36_batch_execution_profile_order_insensitive_hash(self):
        prof_ac1 = BatchExecutionProfile.create(stages=("A", "C"))
        prof_ac2 = BatchExecutionProfile.create(stages=("C", "A"))
        assert prof_ac1.execution_profile_hash == prof_ac2.execution_profile_hash
        assert prof_ac1.execution_stages == ("A", "C")

    # 37. BatchProvenanceEnvelope explicitly records execution profile fields
    def test_37_envelope_records_execution_profile_fields(self):
        prof = BatchExecutionProfile.create(stages=("A", "C"))
        env = BatchProvenanceEnvelope(execution_profile=prof)
        d = env.to_dict()
        assert d["execution_stages"] == ["A", "C"]
        assert d["execution_scope"] == "staged_validation"
        assert d["execution_profile_hash"] == prof.execution_profile_hash
        assert d["execution_profile"] == prof.to_dict()

    # 38. A+C followed by A+B+C in same ResearchStore succeeds without collision and reuses scenarios safely
    def test_38_ac_followed_by_abc_in_same_store_succeeds_without_collision(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )
        store = ResearchStore(tmp_path / "shared_store.db")
        out_ac = tmp_path / "out_ac"
        out_abc = tmp_path / "out_abc"

        res_ac = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store,
            output_dir=out_ac,
        )
        summary_ac = json.loads((out_ac / "summary.json").read_text(encoding="utf-8"))
        assert summary_ac["execution_scope"] == "staged_validation"
        assert summary_ac["execution_stages"] == ["A", "C"]

        tracking_clf = MockTrackingClassifier()
        res_abc = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "B", "C"),
            classifier=tracking_clf,
            research_store=store,
            output_dir=out_abc,
        )
        summary_abc = json.loads((out_abc / "summary.json").read_text(encoding="utf-8"))
        assert summary_abc["execution_scope"] == "full_baseline"
        assert summary_abc["execution_stages"] == ["A", "B", "C"]

        all_runs = store.list_analysis_runs()
        assert len(all_runs) == 10
        conn = store.connect()
        scenarios_count = conn.execute("SELECT count(*) FROM applicability_scenarios").fetchone()[0]
        assert scenarios_count == 50

    # 39. missing research_store fails before materialization or execution
    def test_39_runner_missing_store_fails_before_execution(self, tmp_path: Path):
        with pytest.raises(ValueError, match="research_store must be explicitly provided"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "C"),
                research_store=None,
                output_dir=tmp_path / "out",
            )

    # 40. missing output_dir fails before materialization or execution
    def test_40_runner_missing_output_dir_fails_before_execution(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "store.db")
        with pytest.raises(ValueError, match="output_dir must be explicitly provided"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "C"),
                research_store=store,
                output_dir=None,
            )

    # 41. existing non-empty output_dir fails closed without modifying contents
    def test_41_runner_non_empty_output_dir_fails_closed(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "existing_artifacts"
        out_dir.mkdir()
        canary = out_dir / "canary.txt"
        canary.write_text("prior content", encoding="utf-8")

        with pytest.raises(HarnessRunError, match="already exists and is not empty"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "C"),
                research_store=store,
                output_dir=out_dir,
            )
        assert canary.read_text(encoding="utf-8") == "prior content"

    # 42. existing empty output directory succeeds
    def test_42_runner_empty_output_dir_succeeds(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )
        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "empty_dir"
        out_dir.mkdir()
        res = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            research_store=store,
            output_dir=out_dir,
        )
        assert (out_dir / "summary.json").is_file()

    # 43. persisted scenario mismatch in ResearchStore fails closed
    def test_43_stage_c_persisted_scenario_mismatch_fails_closed(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "mismatch.db")
        store.initialize_schema()
        store.upsert_repository(
            RepositoryRecord(
                repo_id="adrkit",
                repository_url="https://github.com/mbeacom/adrkit",
                repository_identifier="mbeacom/adrkit",
                default_branch="main",
            )
        )
        store.insert_applicability_scenario(
            ApplicabilityScenarioRecord(
                scenario_id="scn-adrkit-001",
                repo_id="adrkit",
                description="Mutated description that contradicts frozen scenario",
                path="some/path",
                component="comp",
                change_type="add",
                dependencies_json="[]",
                api_context=None,
                technology_context=None,
                other_context=None,
                validation_state="reviewed",
            )
        )
        ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        all_scenarios = import_scenarios_jsonl(SCENARIOS_PATH)
        adrkit_scenarios = [s for s in all_scenarios if s.repository == "mbeacom/adrkit"]

        with pytest.raises(HarnessRunError, match="does not match the frozen scenario"):
            execute_stage_c_gds(
                repository_config=config,
                references=[ref],
                scenarios=adrkit_scenarios,
                research_store=store,
                run_id="run-test",
            )

    # 44. persisted expected decisions mismatch in ResearchStore fails closed
    def test_44_stage_c_persisted_expected_decisions_mismatch_fails_closed(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "mismatch_exp.db")
        store.initialize_schema()
        store.upsert_repository(
            RepositoryRecord(
                repo_id="adrkit",
                repository_url="https://github.com/mbeacom/adrkit",
                repository_identifier="mbeacom/adrkit",
                default_branch="main",
            )
        )
        all_scenarios = import_scenarios_jsonl(SCENARIOS_PATH)
        target_scn = next(s for s in all_scenarios if s.scenario_id == "scn-adrkit-001")
        store.insert_applicability_scenario(
            ApplicabilityScenarioRecord(
                scenario_id=target_scn.scenario_id,
                repo_id="adrkit",
                description=target_scn.description,
                path=target_scn.change_context.path,
                component=target_scn.change_context.component,
                change_type=target_scn.change_context.change_type,
                dependencies_json=json.dumps(list(target_scn.change_context.dependencies)),
                api_context=target_scn.change_context.api,
                technology_context=target_scn.change_context.technology,
                other_context=target_scn.change_context.other_context,
                validation_state=target_scn.validation_state,
            )
        )
        store.insert_scenario_expected_decision(
            ScenarioExpectedDecisionRecord(
                scenario_id=target_scn.scenario_id,
                candidate_id="ref-wrong-candidate",
            )
        )
        ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")

        with pytest.raises(HarnessRunError, match="differ from the frozen expected set"):
            execute_stage_c_gds(
                repository_config=config,
                references=[ref],
                scenarios=[target_scn],
                research_store=store,
                run_id="run-test",
            )

    # 45. Stage B execution with Anthropic SDK below 1.0.0 fails before task execution
    def test_45_stage_b_sdk_below_1_0_fails_before_task_execution(self, tmp_path: Path, monkeypatch):
        import anthropic
        monkeypatch.setattr(anthropic, "__version__", "0.52.0")

        store = ResearchStore(tmp_path / "blocked.db")
        out_dir = tmp_path / "out"
        tracking_clf = MockTrackingClassifier()

        with pytest.raises(HarnessPreflightError, match="Stage B requires anthropic>=1.0.0.*found 0.52.0"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "B", "C"),
                classifier=tracking_clf,
                research_store=store,
                output_dir=out_dir,
            )

        assert tracking_clf.call_count == 0
        conn = store.connect()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "classifier_executions" not in tables
        assert not (out_dir / "summary.json").exists()

    # 46. A+C mode executes successfully even with Anthropic SDK below 1.0.0
    def test_46_ac_mode_succeeds_even_with_sdk_below_1_0(self, tmp_path: Path, monkeypatch):
        import anthropic
        monkeypatch.setattr(anthropic, "__version__", "0.52.0")

        monkeypatch.setattr(
            "mneme.open_architecture.harness.evaluate_stage_a_discovery",
            lambda repository_config, references, **kwargs: StageADiscoveryResult(
                repo_id=repository_config.id,
                discovered_documents_count=1,
                extracted_candidates_count=1,
                reference_decisions_count=len(references),
                matched_reference_count=1,
                matched_candidate_count=1,
                recall=1.0,
                precision=1.0,
                f1=1.0,
                cand_to_ref_matches={},
                ref_to_cand_matches={},
                unmatched_reference_ids=[],
                unmatched_candidate_ids=[],
                missed_source_reference_ids=[],
                diagnostic_ior_ioc={},
            ),
        )

        store = ResearchStore(tmp_path / "ac_old_sdk.db")
        out_dir = tmp_path / "out"
        res = run_frozen_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            stages=("A", "C"),
            classifier=None,
            research_store=store,
            output_dir=out_dir,
        )
        assert res.execution_profile.execution_scope == "staged_validation"
        assert res.execution_profile.execution_stages == ("A", "C")
        assert (out_dir / "summary.json").is_file()

    # 47. valid Anthropic SDK >= 1.0.0 passes the environment prerequisite
    def test_47_valid_sdk_passes_prerequisite(self, monkeypatch):
        import anthropic
        monkeypatch.setattr(anthropic, "__version__", "1.0.0")

        tracking_clf = MockTrackingClassifier()
        preflight = preflight_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            classifier=tracking_clf,
        )
        assert preflight.status == "preflight_ok"

    # 48. frozen B0 runner rejects Sonnet 5.5 and accepts only Sonnet 4.6
    def test_48_frozen_b0_runner_rejects_sonnet_5_5_and_accepts_sonnet_4_6(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "store.db")
        out = tmp_path / "out"
        sonnet_55_clf = MockTrackingClassifier(model_identifier="claude-sonnet-5-5")

        with pytest.raises(HarnessPreflightError, match="Classifier model mismatch: expected 'claude-sonnet-4-6', got 'claude-sonnet-5-5'"):
            run_frozen_batch_01(
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                scenarios_path=SCENARIOS_PATH,
                stages=("A", "B", "C"),
                classifier=sonnet_55_clf,
                research_store=store,
                output_dir=out,
            )

        sonnet_46_clf = MockTrackingClassifier(model_identifier="claude-sonnet-4-6")
        preflight = preflight_batch_01(
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            scenarios_path=SCENARIOS_PATH,
            classifier=sonnet_46_clf,
        )
        assert preflight.status == "preflight_ok"

    # 49. M1 experimental path accepts explicit Sonnet 5.5
    def test_49_m1_experimental_path_accepts_sonnet_5_5(self, tmp_path: Path):
        profile = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-5-5",
        )
        clf = MockTrackingClassifier(model_identifier="claude-sonnet-5-5")
        store = ResearchStore(tmp_path / "m1_store.db")
        out_dir = tmp_path / "m1_artifacts"

        res = execute_classifier_experiment(
            experiment_profile=profile,
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            classifier=clf,
            research_store=store,
            output_dir=out_dir,
        )
        assert res.experiment_id == "o1a-batch-01-m1-sonnet-5-5"
        assert res.profile.comparator_model_identifier == "claude-sonnet-5-5"
        assert len(res.results_by_repo) == 5
        assert clf.call_count == 800
        assert (out_dir / "experiment_profile.json").is_file()
        assert (out_dir / "stage_b_summary.json").is_file()
        assert (out_dir / "summary.json").is_file()

    # 50. experiment profile hash changes with model and is deterministic
    def test_50_experiment_profile_hash_changes_with_model_and_is_deterministic(self):
        prof_55_a = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-5-5",
        )
        prof_55_b = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-5-5",
        )
        prof_46 = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-4-6",
        )
        assert prof_55_a.experiment_profile_hash == prof_55_b.experiment_profile_hash
        assert prof_55_a.experiment_profile_hash != prof_46.experiment_profile_hash

    # 51. M1 cannot modify reference corpus or semantic task set
    def test_51_m1_cannot_modify_reference_corpus_or_semantic_task_set(self, tmp_path: Path):
        bad_ref_dir = tmp_path / "bad_ref"
        bad_ref_dir.mkdir()
        profile = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-5-5",
        )
        clf = MockTrackingClassifier(model_identifier="claude-sonnet-5-5")
        store = ResearchStore(tmp_path / "store.db")
        out = tmp_path / "out"

        with pytest.raises(HarnessPreflightError, match="Reference corpus hash mismatch"):
            execute_classifier_experiment(
                experiment_profile=profile,
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=bad_ref_dir,
                classifier=clf,
                research_store=store,
                output_dir=out,
            )

        assert len(profile.semantic_tasks) == 8
        assert set(profile.semantic_tasks) == {t.value for t in SEMANTIC_TASK_TYPES}
        assert profile.max_tokens == 1024

    # 52. M1 uses existing task builder and task schemas
    def test_52_m1_uses_existing_task_builder_and_schemas(self):
        refs = load_reference_corpus(REF_DIR, repo_id="adrkit")
        tasks = build_stage_b_tasks(refs)
        assert len(tasks) == 160
        from mneme.open_architecture.classifiers.anthropic import AnthropicClassifier
        clf = AnthropicClassifier(model_identifier="claude-sonnet-5-5")
        for t in tasks[:8]:
            schema = clf.get_task_schema(t.task_type)
            assert "type" in schema
            assert schema["type"] == "object"

    # 53. M1 output directory overwrite protection
    def test_53_m1_output_dir_overwrite_protection(self, tmp_path: Path):
        profile = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-5-5",
        )
        clf = MockTrackingClassifier(model_identifier="claude-sonnet-5-5")
        store = ResearchStore(tmp_path / "store.db")
        out_dir = tmp_path / "occupied"
        out_dir.mkdir()
        (out_dir / "existing.txt").write_text("prior data", encoding="utf-8")

        with pytest.raises(HarnessRunError, match="already exists and is not empty"):
            execute_classifier_experiment(
                experiment_profile=profile,
                baseline_path=BASELINE_PATH,
                manifest_path=MANIFEST_PATH,
                reference_corpus_dir=REF_DIR,
                classifier=clf,
                research_store=store,
                output_dir=out_dir,
            )

    # 54. duplicate relationship output does not crash persistence
    def test_54_duplicate_relationship_output_does_not_crash_persistence(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        store = ResearchStore(tmp_path / "store.db")
        store.initialize_schema()
        run_id = "run-rel-dedup-test"
        store.upsert_repository(RepositoryRecord(config.id, config.github, config.id, "main"))
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

        dup_relationships = [
            {"relationship_type": "requires", "target_reference": "ADR-0001", "confidence": 0.95},
            {"relationship_type": "requires", "target_reference": "ADR-0001", "confidence": 0.85},
        ]
        clf = MockTrackingClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": list(sample_ref.scopes)},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": dup_relationships},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            }
        )

        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
            research_store=store,
            run_id=run_id,
        )

        conn = store.connect()
        # 1. Raw classifier execution preserves both entries
        exec_row = conn.execute(
            "SELECT output_json FROM classifier_executions WHERE candidate_id = ? AND task_type = 'relationships'",
            (sample_ref.reference_decision_id,),
        ).fetchone()
        assert exec_row is not None
        raw_output = json.loads(exec_row[0])
        assert len(raw_output["relationships"]) == 2
        assert raw_output["relationships"] == dup_relationships

        # 2. Normalized candidate_relationships contains exactly one semantic record
        rel_rows = conn.execute(
            "SELECT relationship_id, relationship_type, target_reference, confidence FROM candidate_relationships WHERE source_candidate_id = ?",
            (sample_ref.reference_decision_id,),
        ).fetchall()
        assert len(rel_rows) == 1
        assert rel_rows[0][1] == "requires"
        assert rel_rows[0][2] == "ADR-0001"
        assert rel_rows[0][3] == 0.95

        # 3. Stage B relationship score unchanged from existing set semantics
        expected_set = {(r["relationship_type"], r.get("target_reference")) for r in sample_ref.relationships}
        expected_acc = 1.0 if {("requires", "ADR-0001")} == expected_set else 0.0
        assert res.metrics["relationship_accuracy"] == expected_acc

    # 55. duplicate scope output does not crash persistence
    def test_55_duplicate_scope_output_does_not_crash_persistence(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        store = ResearchStore(tmp_path / "store.db")
        store.initialize_schema()
        run_id = "run-scope-dedup-test"
        store.upsert_repository(RepositoryRecord(config.id, config.github, config.id, "main"))
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

        dup_scopes = [
            {"scope_type": "directory", "scope_expression": "packages/index"},
            {"scope_type": "directory", "scope_expression": "packages/index"},
        ]
        clf = MockTrackingClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": dup_scopes},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": list(sample_ref.relationships)},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            }
        )

        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
            research_store=store,
            run_id=run_id,
        )

        conn = store.connect()
        # 1. Raw classifier execution preserves both entries
        exec_row = conn.execute(
            "SELECT output_json FROM classifier_executions WHERE candidate_id = ? AND task_type = 'scope'",
            (sample_ref.reference_decision_id,),
        ).fetchone()
        assert exec_row is not None
        raw_output = json.loads(exec_row[0])
        assert len(raw_output["scopes"]) == 2
        assert raw_output["scopes"] == dup_scopes

        # 2. Normalized candidate_scopes contains exactly one semantic record
        sc_rows = conn.execute(
            "SELECT scope_id, scope_type, scope_expression FROM candidate_scopes WHERE candidate_id = ?",
            (sample_ref.reference_decision_id,),
        ).fetchall()
        assert len(sc_rows) == 1
        assert sc_rows[0][1] == "directory"
        assert sc_rows[0][2] == "packages/index"

        # 3. Stage B scope score unchanged
        expected_set = {(s["scope_type"], s.get("scope_expression")) for s in sample_ref.scopes}
        expected_acc = 1.0 if {("directory", "packages/index")} == expected_set else 0.0
        assert res.metrics["scope_accuracy"] == expected_acc

    # 56. distinct relationships remain separately persisted
    def test_56_distinct_relationships_remain_separately_persisted(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        store = ResearchStore(tmp_path / "store.db")
        store.initialize_schema()
        run_id = "run-distinct-rel-test"
        store.upsert_repository(RepositoryRecord(config.id, config.github, config.id, "main"))
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

        distinct_rels = [
            {"relationship_type": "requires", "target_reference": "ADR-0001"},
            {"relationship_type": "refines", "target_reference": "ADR-0002"},
        ]
        clf = MockTrackingClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": list(sample_ref.scopes)},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": distinct_rels},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            }
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
        rel_rows = conn.execute(
            "SELECT relationship_type, target_reference FROM candidate_relationships WHERE source_candidate_id = ? ORDER BY relationship_type",
            (sample_ref.reference_decision_id,),
        ).fetchall()
        assert len(rel_rows) == 2
        assert rel_rows[0][0] == "refines"
        assert rel_rows[0][1] == "ADR-0002"
        assert rel_rows[1][0] == "requires"
        assert rel_rows[1][1] == "ADR-0001"

    # 57. distinct scopes remain separately persisted
    def test_57_distinct_scopes_remain_separately_persisted(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        store = ResearchStore(tmp_path / "store.db")
        store.initialize_schema()
        run_id = "run-distinct-scope-test"
        store.upsert_repository(RepositoryRecord(config.id, config.github, config.id, "main"))
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

        distinct_scopes = [
            {"scope_type": "directory", "scope_expression": "packages/index"},
            {"scope_type": "package", "scope_expression": "@prisma/client"},
        ]
        clf = MockTrackingClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": distinct_scopes},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": list(sample_ref.relationships)},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            }
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
        sc_rows = conn.execute(
            "SELECT scope_type, scope_expression FROM candidate_scopes WHERE candidate_id = ? ORDER BY scope_type",
            (sample_ref.reference_decision_id,),
        ).fetchall()
        assert len(sc_rows) == 2
        assert sc_rows[0][0] == "directory"
        assert sc_rows[0][1] == "packages/index"
        assert sc_rows[1][0] == "package"
        assert sc_rows[1][1] == "@prisma/client"

    # 58. deterministic persisted IDs remain stable
    def test_58_deterministic_persisted_ids_remain_stable(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        store = ResearchStore(tmp_path / "store.db")
        store.initialize_schema()
        run_id = "run-deterministic-id-test"
        store.upsert_repository(RepositoryRecord(config.id, config.github, config.id, "main"))
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

        rel_type = "requires"
        rel_target = "ADR-0001"
        sc_type = "directory"
        sc_expr = "packages/index"

        clf = MockTrackingClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {"scopes": [{"scope_type": sc_type, "scope_expression": sc_expr}]},
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {"relationships": [{"relationship_type": rel_type, "target_reference": rel_target}]},
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            }
        )

        execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
            research_store=store,
            run_id=run_id,
        )

        ref_id = sample_ref.reference_decision_id
        expected_rel_id = f"rel-{hashlib.sha256(f'{run_id}:{ref_id}:{rel_type}:{rel_target}'.encode()).hexdigest()[:32]}"
        expected_sc_id = f"sc-{hashlib.sha256(f'{run_id}:{ref_id}:{sc_type}:{sc_expr}'.encode()).hexdigest()[:32]}"

        conn = store.connect()
        rel_id = conn.execute("SELECT relationship_id FROM candidate_relationships WHERE source_candidate_id = ?", (ref_id,)).fetchone()[0]
        sc_id = conn.execute("SELECT scope_id FROM candidate_scopes WHERE candidate_id = ?", (ref_id,)).fetchone()[0]

        assert rel_id == expected_rel_id
        assert sc_id == expected_sc_id

    # 59. B0 Stage B path uses the same fixed helper and remains semantically unchanged
    def test_59_b0_stage_b_path_handles_duplicates(self, tmp_path: Path, valid_preflight: BatchPreflightResult):
        sample_ref = load_reference_corpus(REF_DIR, repo_id="adrkit")[0]
        config = RepositoryConfig("adrkit", "mbeacom/adrkit", "471457da29638ecca6119b35180c2845bf989cac", "test", "reviewed")
        store = ResearchStore(tmp_path / "store.db")
        store.initialize_schema()
        run_id = "run-b0-helper-test"
        store.upsert_repository(RepositoryRecord(config.id, config.github, config.id, "main"))
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

        clf = MockTrackingClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": sample_ref.classification},
                ClassifierTaskType.DOMAINS: {"domains": list(sample_ref.decision_domains)},
                ClassifierTaskType.PURPOSES: {"purposes": list(sample_ref.decision_purposes)},
                ClassifierTaskType.AUTHORITY: {"authority": sample_ref.authority_status},
                ClassifierTaskType.SCOPE: {
                    "scopes": [
                        {"scope_type": "directory", "scope_expression": "packages/index"},
                        {"scope_type": "directory", "scope_expression": "packages/index"},
                    ]
                },
                ClassifierTaskType.LIFECYCLE: {"lifecycle": sample_ref.lifecycle_status},
                ClassifierTaskType.RELATIONSHIPS: {
                    "relationships": [
                        {"relationship_type": "requires", "target_reference": "ADR-0001"},
                        {"relationship_type": "requires", "target_reference": "ADR-0001"},
                    ]
                },
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": sample_ref.enforcement_potential},
            }
        )

        res = execute_stage_b_classification(
            repository_config=config,
            references=[sample_ref],
            classifier=clf,
            preflight=valid_preflight,
            research_store=store,
            run_id=run_id,
        )
        assert res.reference_count == 1

    # 60. M1 experiment path uses the same fixed helper and handles duplicates
    def test_60_m1_experiment_path_handles_duplicates(self, tmp_path: Path):
        profile = ClassifierExperimentProfile.create(
            experiment_id="o1a-batch-01-m1-sonnet-5-5",
            comparator_model_identifier="claude-sonnet-5-5",
        )
        clf = MockTrackingClassifier(
            model_identifier="claude-sonnet-5-5",
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": "prescriptive"},
                ClassifierTaskType.DOMAINS: {"domains": ["architecture_structure"]},
                ClassifierTaskType.PURPOSES: {"purposes": ["constrain"]},
                ClassifierTaskType.AUTHORITY: {"authority": "explicitly_accepted"},
                ClassifierTaskType.SCOPE: {
                    "scopes": [
                        {"scope_type": "directory", "scope_expression": "packages/index"},
                        {"scope_type": "directory", "scope_expression": "packages/index"},
                    ]
                },
                ClassifierTaskType.LIFECYCLE: {"lifecycle": "active"},
                ClassifierTaskType.RELATIONSHIPS: {
                    "relationships": [
                        {"relationship_type": "requires", "target_reference": "ADR-0001"},
                        {"relationship_type": "requires", "target_reference": "ADR-0001"},
                    ]
                },
                ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": "deterministic_rule"},
            }
        )
        store = ResearchStore(tmp_path / "m1_store.db")
        out_dir = tmp_path / "m1_artifacts"

        res = execute_classifier_experiment(
            experiment_profile=profile,
            baseline_path=BASELINE_PATH,
            manifest_path=MANIFEST_PATH,
            reference_corpus_dir=REF_DIR,
            classifier=clf,
            research_store=store,
            output_dir=out_dir,
        )
        assert len(res.results_by_repo) == 5
        assert clf.call_count == 800
        conn = store.connect()
        scope_count = conn.execute("SELECT COUNT(*) FROM candidate_scopes").fetchone()[0]
        rel_count = conn.execute("SELECT COUNT(*) FROM candidate_relationships").fetchone()[0]
        assert scope_count == 100
        assert rel_count == 100

    # 61. classification.py frozen hash unchanged
    def test_61_classification_frozen_hash_unchanged(self):
        from tests.open_architecture.test_baseline import FROZEN_SEMANTIC_MODULE_HASHES
        class_file = REPO_ROOT / "mneme" / "open_architecture" / "classification.py"
        raw_bytes = class_file.read_bytes().replace(b"\r\n", b"\n")
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        assert actual_hash == FROZEN_SEMANTIC_MODULE_HASHES["mneme/open_architecture/classification.py"]

    # 62. ResearchStore schema unchanged
    def test_62_research_store_schema_unchanged(self, tmp_path: Path):
        store = ResearchStore(tmp_path / "test_store.db")
        store.initialize_schema()
        conn = store.connect()
        scope_cols = {col[1]: col[2] for col in conn.execute("PRAGMA table_info(candidate_scopes)").fetchall()}
        assert set(scope_cols.keys()) == {
            "scope_id", "candidate_id", "run_id", "scope_type", "scope_expression", "confidence", "evidence_reference"
        }
        rel_cols = {col[1]: col[2] for col in conn.execute("PRAGMA table_info(candidate_relationships)").fetchall()}
        assert set(rel_cols.keys()) == {
            "relationship_id", "run_id", "source_candidate_id", "relationship_type", "target_candidate_id",
            "target_reference", "confidence", "evidence_reference"
        }

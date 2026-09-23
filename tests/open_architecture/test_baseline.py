"""
tests.open_architecture.test_baseline — Tests for O1A3.1 frozen baseline configuration contract.

Verifies all 17 requirements of O1A3.1 freeze specification:
1. All five repository SHAs are non-null 40-character lowercase hex.
2. All five repositories remain exactly the approved Batch 01 set.
3. Target counts remain 100 decisions / 50 scenarios.
4. Sampling contract remains unchanged.
5. Semantic Mneme SHA is fixed to the O1A2 base SHA.
6. Extractor identity/configuration is explicit.
7. Classifier identity/configuration is explicit when freeze is complete.
8. Exactly eight semantic tasks are frozen.
9. Retrieval policy is explicit (score_gt_zero).
10. Scenario renderer identity and field order are explicit.
11. Baseline configuration hash is deterministic.
12. Changing a repo SHA changes baseline identity.
13. Changing classifier model/version changes baseline identity.
14. Changing extractor config changes baseline identity.
15. Changing scenario corpus identity changes baseline identity.
16. status: frozen is rejected unless all required freeze prerequisites exist.
17. No semantic runtime module is modified.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from mneme.open_architecture.baseline import (
    APPROVED_BATCH_01_REPOSITORIES,
    EXPECTED_RENDERER_FIELD_ORDER,
    EXPECTED_SEMANTIC_TASKS,
    FROZEN_SEMANTIC_MNEME_SHA,
    BaselineClassifier,
    BaselineConfig,
    BaselineCorpusStatus,
    BaselineExtractor,
    BaselineFreezeError,
    BaselineRepository,
    BaselineRetrievalPolicy,
    BaselineScenarioRenderer,
    validate_baseline_freeze,
)
from mneme.open_architecture.manifest import Manifest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
BASELINE_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml"


@pytest.fixture
def manifest() -> Manifest:
    assert MANIFEST_PATH.is_file(), f"manifest.yaml not found at {MANIFEST_PATH}"
    return Manifest.load(MANIFEST_PATH)


@pytest.fixture
def baseline() -> BaselineConfig:
    assert BASELINE_PATH.is_file(), f"baseline.yaml not found at {BASELINE_PATH}"
    return BaselineConfig.load(BASELINE_PATH)


class TestBatch01BaselineFreeze:
    """Covers all 17 O1A3.1 freeze requirements."""

    # 1. all five repository SHAs are non-null 40-character lowercase hex
    def test_1_repository_shas_non_null_40_char_lowercase_hex(self, manifest: Manifest, baseline: BaselineConfig):
        assert len(manifest.repositories) == 5
        assert len(baseline.repositories) == 5

        hex_40_pattern = re.compile(r"^[0-9a-f]{40}$")

        for repo in manifest.repositories:
            assert repo.commit_sha is not None, f"manifest repo '{repo.id}' has null commit_sha"
            assert hex_40_pattern.match(repo.commit_sha), (
                f"manifest repo '{repo.id}' SHA '{repo.commit_sha}' is not a 40-char lowercase hex"
            )

        for repo in baseline.repositories:
            assert hex_40_pattern.match(repo.commit_sha), (
                f"baseline repo '{repo.id}' SHA '{repo.commit_sha}' is not a 40-char lowercase hex"
            )

    # 2. all five repositories remain exactly the approved Batch 01 set
    def test_2_approved_batch_01_repositories(self, manifest: Manifest, baseline: BaselineConfig):
        expected_ids = {"adrkit", "gsa_agentic_coding_quickstart", "helix", "archlint", "modonome"}
        expected_github = {
            "mbeacom/adrkit",
            "GSA-TTS/agentic-coding-quickstart",
            "AZX-PBC-OSS/helix",
            "muhammetsafak/archlint",
            "enumind/modonome",
        }

        manifest_ids = {r.id for r in manifest.repositories}
        manifest_github = {r.github for r in manifest.repositories}
        baseline_ids = {r.id for r in baseline.repositories}
        baseline_github = {r.github for r in baseline.repositories}

        assert manifest_ids == expected_ids
        assert manifest_github == expected_github
        assert baseline_ids == expected_ids
        assert baseline_github == expected_github

    # 3. target counts remain 100 decisions / 50 scenarios
    def test_3_target_counts_100_decisions_50_scenarios(self, manifest: Manifest):
        assert manifest.targets.decisions_total == 100
        assert manifest.targets.scenarios_total == 50
        assert manifest.targets.decisions_per_repository == 20
        assert manifest.targets.scenarios_per_repository == 10
        manifest.validate_target_consistency()

    # 4. sampling contract remains unchanged
    def test_4_sampling_contract_unchanged(self, manifest: Manifest):
        s = manifest.sampling
        assert s.clear_explicit == 5
        assert s.scoped == 5
        assert s.lifecycle_or_supersession == 3
        assert s.ambiguous_or_conflicting == 3
        assert s.enforcement_potential == 2
        assert s.unusual_or_difficult == 2
        assert s.total() == 20

    # 5. semantic Mneme SHA is fixed
    def test_5_semantic_mneme_sha_fixed(self, baseline: BaselineConfig):
        assert baseline.semantic_mneme_sha == "3673c36855fb1e30d46942ce826c50be4888df5e"
        assert baseline.semantic_mneme_sha == FROZEN_SEMANTIC_MNEME_SHA

    # 6. extractor identity/configuration is explicit
    def test_6_extractor_identity_and_config_explicit(self, baseline: BaselineConfig):
        ext = baseline.extractor
        assert ext.id == "heuristic"
        assert ext.version == "0.1"
        assert ext.config["min_lines"] == 2
        assert ext.config["max_lines"] == 50
        assert ext.config["confidence"] == 0.5
        assert isinstance(ext.config["keywords"], list)
        assert len(ext.config["keywords"]) > 10
        assert "adopt" in ext.config["keywords"]
        assert "require" in ext.config["keywords"]

    # 7. classifier identity/configuration is explicit when freeze is complete
    def test_7_classifier_identity_and_config_explicit(self, baseline: BaselineConfig):
        clf = baseline.classifier
        assert clf.backend_id == "anthropic"
        assert clf.classifier_version == "0.1"
        assert clf.model_identifier == "claude-sonnet-4-6"
        assert clf.config["temperature"] == 0.0
        assert clf.config["max_tokens"] == 1024
        assert clf.config["output_config"]["format"]["type"] == "json_schema"

    # 8. exactly eight semantic tasks are frozen
    def test_8_exactly_eight_semantic_tasks_frozen(self, baseline: BaselineConfig):
        assert len(baseline.semantic_tasks) == 8
        assert tuple(baseline.semantic_tasks) == EXPECTED_SEMANTIC_TASKS

    # 9. retrieval policy is explicit
    def test_9_retrieval_policy_explicit(self, baseline: BaselineConfig):
        ret = baseline.retrieval_policy
        assert ret.policy_id == "score_gt_zero"
        assert ret.version == "0.1"
        assert "projection" in ret.projection.lower()
        assert "decisionretriever" in ret.retriever.lower()
        assert "score > 0" in ret.selection

    # 10. scenario renderer identity is explicit
    def test_10_scenario_renderer_identity_explicit(self, baseline: BaselineConfig):
        rnd = baseline.scenario_renderer
        assert rnd.renderer_id == "eight_field_v1"
        assert rnd.version == "0.1"
        assert tuple(rnd.field_order) == EXPECTED_RENDERER_FIELD_ORDER

    # 11. baseline configuration hash is deterministic
    def test_11_baseline_configuration_hash_deterministic(self, baseline: BaselineConfig):
        hash1 = baseline.configuration_hash()
        hash2 = baseline.configuration_hash()
        assert hash1 == hash2
        assert len(hash1) == 32
        # Load from disk again and verify
        reloaded = BaselineConfig.load(BASELINE_PATH)
        assert reloaded.configuration_hash() == hash1

    # 12. changing a repo SHA changes baseline identity
    def test_12_changing_repo_sha_changes_baseline_identity(self, baseline: BaselineConfig):
        original_hash = baseline.configuration_hash()

        # Mutate one repository SHA
        mutated_repos = list(baseline.repositories)
        mutated_repos[0] = BaselineRepository(
            id=mutated_repos[0].id,
            github=mutated_repos[0].github,
            commit_sha="0" * 40,
            default_branch=mutated_repos[0].default_branch,
            primary_test=mutated_repos[0].primary_test,
        )

        mutated_config = BaselineConfig(
            schema_version=baseline.schema_version,
            baseline_id=baseline.baseline_id,
            status=baseline.status,
            semantic_mneme_sha=baseline.semantic_mneme_sha,
            mneme_version=baseline.mneme_version,
            benchmark_schema_version=baseline.benchmark_schema_version,
            taxonomy_version=baseline.taxonomy_version,
            manifest_ref=baseline.manifest_ref,
            repositories=tuple(mutated_repos),
            extractor=baseline.extractor,
            classifier=baseline.classifier,
            semantic_tasks=baseline.semantic_tasks,
            retrieval_policy=baseline.retrieval_policy,
            scenario_renderer=baseline.scenario_renderer,
            scenario_corpus=baseline.scenario_corpus,
            reference_corpus=baseline.reference_corpus,
        )

        assert mutated_config.configuration_hash() != original_hash

    # 13. changing classifier model/version changes baseline identity
    def test_13_changing_classifier_model_or_version_changes_baseline_identity(self, baseline: BaselineConfig):
        original_hash = baseline.configuration_hash()

        # Mutate classifier model
        mutated_classifier = BaselineClassifier(
            backend_id=baseline.classifier.backend_id,
            classifier_version=baseline.classifier.classifier_version,
            model_identifier="claude-3-7-sonnet-20250219",
            config=baseline.classifier.config,
        )

        mutated_config = BaselineConfig(
            schema_version=baseline.schema_version,
            baseline_id=baseline.baseline_id,
            status=baseline.status,
            semantic_mneme_sha=baseline.semantic_mneme_sha,
            mneme_version=baseline.mneme_version,
            benchmark_schema_version=baseline.benchmark_schema_version,
            taxonomy_version=baseline.taxonomy_version,
            manifest_ref=baseline.manifest_ref,
            repositories=baseline.repositories,
            extractor=baseline.extractor,
            classifier=mutated_classifier,
            semantic_tasks=baseline.semantic_tasks,
            retrieval_policy=baseline.retrieval_policy,
            scenario_renderer=baseline.scenario_renderer,
            scenario_corpus=baseline.scenario_corpus,
            reference_corpus=baseline.reference_corpus,
        )

        assert mutated_config.configuration_hash() != original_hash

        # Mutate classifier version
        mutated_classifier_ver = BaselineClassifier(
            backend_id=baseline.classifier.backend_id,
            classifier_version="0.2",
            model_identifier=baseline.classifier.model_identifier,
            config=baseline.classifier.config,
        )

        mutated_config_ver = BaselineConfig(
            schema_version=baseline.schema_version,
            baseline_id=baseline.baseline_id,
            status=baseline.status,
            semantic_mneme_sha=baseline.semantic_mneme_sha,
            mneme_version=baseline.mneme_version,
            benchmark_schema_version=baseline.benchmark_schema_version,
            taxonomy_version=baseline.taxonomy_version,
            manifest_ref=baseline.manifest_ref,
            repositories=baseline.repositories,
            extractor=baseline.extractor,
            classifier=mutated_classifier_ver,
            semantic_tasks=baseline.semantic_tasks,
            retrieval_policy=baseline.retrieval_policy,
            scenario_renderer=baseline.scenario_renderer,
            scenario_corpus=baseline.scenario_corpus,
            reference_corpus=baseline.reference_corpus,
        )

        assert mutated_config_ver.configuration_hash() != original_hash

    # 14. changing extractor config changes baseline identity
    def test_14_changing_extractor_config_changes_baseline_identity(self, baseline: BaselineConfig):
        original_hash = baseline.configuration_hash()

        mutated_extractor = BaselineExtractor(
            id=baseline.extractor.id,
            version=baseline.extractor.version,
            config={**baseline.extractor.config, "min_lines": 3},
        )

        mutated_config = BaselineConfig(
            schema_version=baseline.schema_version,
            baseline_id=baseline.baseline_id,
            status=baseline.status,
            semantic_mneme_sha=baseline.semantic_mneme_sha,
            mneme_version=baseline.mneme_version,
            benchmark_schema_version=baseline.benchmark_schema_version,
            taxonomy_version=baseline.taxonomy_version,
            manifest_ref=baseline.manifest_ref,
            repositories=baseline.repositories,
            extractor=mutated_extractor,
            classifier=baseline.classifier,
            semantic_tasks=baseline.semantic_tasks,
            retrieval_policy=baseline.retrieval_policy,
            scenario_renderer=baseline.scenario_renderer,
            scenario_corpus=baseline.scenario_corpus,
            reference_corpus=baseline.reference_corpus,
        )

        assert mutated_config.configuration_hash() != original_hash

    # 15. changing scenario corpus identity changes baseline identity
    def test_15_changing_scenario_corpus_identity_changes_baseline_identity(self, baseline: BaselineConfig):
        original_hash = baseline.configuration_hash()

        mutated_corpus = BaselineCorpusStatus(
            status="complete",
            total_required=50,
            per_repository_required=10,
            content_hash="abc123def456" * 2,
            location=baseline.scenario_corpus.location,
        )

        mutated_config = BaselineConfig(
            schema_version=baseline.schema_version,
            baseline_id=baseline.baseline_id,
            status=baseline.status,
            semantic_mneme_sha=baseline.semantic_mneme_sha,
            mneme_version=baseline.mneme_version,
            benchmark_schema_version=baseline.benchmark_schema_version,
            taxonomy_version=baseline.taxonomy_version,
            manifest_ref=baseline.manifest_ref,
            repositories=baseline.repositories,
            extractor=baseline.extractor,
            classifier=baseline.classifier,
            semantic_tasks=baseline.semantic_tasks,
            retrieval_policy=baseline.retrieval_policy,
            scenario_renderer=baseline.scenario_renderer,
            scenario_corpus=mutated_corpus,
            reference_corpus=baseline.reference_corpus,
        )

        assert mutated_config.configuration_hash() != original_hash

    # 16. status: frozen is rejected unless all required freeze prerequisites exist
    def test_16_status_frozen_rejected_unless_prerequisites_exist(self, baseline: BaselineConfig, manifest: Manifest):
        # Current state: corpora are missing, so freeze must be rejected
        blockers = baseline.check_freeze_prerequisites()
        assert len(blockers) >= 2
        assert any("scenario" in b.lower() for b in blockers)
        assert any("reference" in b.lower() for b in blockers)

        with pytest.raises(BaselineFreezeError, match="Baseline cannot be marked 'frozen'"):
            baseline.validate_freeze()

        # If a manifest with status='frozen' is passed, it must also be rejected
        manifest_dict = manifest.to_dict()
        manifest_dict["status"] = "frozen"
        frozen_manifest = Manifest.from_dict(manifest_dict)

        with pytest.raises(BaselineFreezeError, match="cannot be marked 'frozen'"):
            validate_baseline_freeze(baseline, manifest=frozen_manifest)

        # Baseline with all prerequisites satisfied CAN validate successfully
        complete_scenarios = BaselineCorpusStatus(
            status="complete",
            total_required=50,
            per_repository_required=10,
            content_hash="sha256:11112222333344445555666677778888",
            location="scenarios/",
        )
        complete_reference = BaselineCorpusStatus(
            status="complete",
            total_required=100,
            per_repository_required=20,
            content_hash="sha256:88887777666655554444333322221111",
            location="reference_decisions/",
        )
        fully_satisfied_baseline = BaselineConfig(
            schema_version=baseline.schema_version,
            baseline_id=baseline.baseline_id,
            status="frozen",
            semantic_mneme_sha=baseline.semantic_mneme_sha,
            mneme_version=baseline.mneme_version,
            benchmark_schema_version=baseline.benchmark_schema_version,
            taxonomy_version=baseline.taxonomy_version,
            manifest_ref=baseline.manifest_ref,
            repositories=baseline.repositories,
            extractor=baseline.extractor,
            classifier=baseline.classifier,
            semantic_tasks=baseline.semantic_tasks,
            retrieval_policy=baseline.retrieval_policy,
            scenario_renderer=baseline.scenario_renderer,
            scenario_corpus=complete_scenarios,
            reference_corpus=complete_reference,
        )

        assert fully_satisfied_baseline.check_freeze_prerequisites() == []
        fully_satisfied_baseline.validate_freeze()  # Should not raise

    # 17. no semantic runtime module is modified
    def test_17_no_semantic_runtime_module_modified(self):
        base_sha = "3673c36855fb1e30d46942ce826c50be4888df5e"
        res = subprocess.run(
            ["git", "diff", "--name-only", base_sha],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        diff_files = [f.strip().replace("\\", "/") for f in res.stdout.splitlines() if f.strip()]

        semantic_runtime_modules = {
            "mneme/decision_retriever.py",
            "mneme/enforcer.py",
            "mneme/conflict_detector.py",
            "mneme/memory_store.py",
            "mneme/decision_index.py",
            "mneme/schemas.py",
            "mneme/open_architecture/candidates.py",
            "mneme/open_architecture/classification.py",
            "mneme/open_architecture/orchestrator.py",
            "mneme/open_architecture/projection.py",
            "mneme/open_architecture/gds_evaluation.py",
            "mneme/open_architecture/discovery.py",
            "mneme/open_architecture/execution.py",
            "mneme/open_architecture/store.py",
            "mneme/open_architecture/run_metadata.py",
            "mneme/open_architecture/export.py",
            "mneme/open_architecture/reporting.py",
        }

        # None of the semantic runtime modules should be modified
        assert semantic_runtime_modules.isdisjoint(diff_files), (
            f"Semantic runtime modules modified: {set(diff_files) & semantic_runtime_modules}"
        )

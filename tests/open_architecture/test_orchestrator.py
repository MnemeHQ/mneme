"""
tests.open_architecture.test_orchestrator — Tests for O1A research run orchestrator.

Covers:
- Full offline local-repository pipeline using StaticClassifier + HeuristicExtractor
- Explicit extractor/classifier injection (fail-closed on None)
- Incomplete candidate handling (observable, not dropped or fabricated)
- ResearchStore persistence (analysis_runs, source_documents, decision_candidates,
  semantic dimensions, classifier_executions, scenarios, results)
- Historical run append-preservation (no silent overwrite of completed run)
- Multi-run candidate coexistence without PK collision
- Run-specific classifier execution separation
- Distinct execution configuration hashes for different backends/extractors/scenarios
- Expected reference labels preserved even when machine discovery misses them
- Exactly eight classifier tasks executed per candidate (PURPOSES occurs once)
- PreflightResult contract (does not claim completed analysis or produce metrics)
- Architectural boundary enforcement
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from mneme.open_architecture.candidates import HeuristicExtractor
from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTaskType,
    StaticClassifier,
)
from mneme.open_architecture.manifest import (
    Manifest,
    RepositoryConfig,
    SamplingConfig,
    TargetsConfig,
)
from mneme.open_architecture.orchestrator import (
    IncompleteCandidateRecord,
    OpenArchitectureRunResult,
    PreflightResult,
    preflight_open_architecture_analysis,
    run_open_architecture_analysis,
)
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    ChangeContext,
)
from mneme.open_architecture.store import ResearchStore


# ── Fixtures & Helpers ─────────────────────────────────────────────────────────


def _create_test_repo(path: Path, owner_repo: str = "mbeacom/adrkit") -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{owner_repo}.git"],
        cwd=str(path),
        check=True,
    )

    # Create ADR and doc files
    adr_dir = path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001.md").write_text(
        "---\n"
        "id: ADR-001\n"
        "title: Standardize on SQLite for Research\n"
        "status: accepted\n"
        "priority: foundational\n"
        "date: 2026-01-01\n"
        "scope: storage\n"
        "---\n"
        "# Storage Decision\n"
        "We decide to standardize on SQLite for all research storage.\n"
        "PostgreSQL is prohibited for local benchmarks.\n",
        encoding="utf-8",
        newline="\n",
    )
    (path / "README.md").write_text(
        "# Benchmark Research\nDocumentation and guides.\n",
        encoding="utf-8",
        newline="\n",
    )

    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "add", "."], cwd=str(path), check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "-m", "init"], cwd=str(path), check=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(path), capture_output=True, text=True, check=True)
    return res.stdout.strip().lower()


def _make_manifest(repo_id: str, github: str, commit_sha: str) -> Manifest:
    return Manifest(
        schema_version="0.1",
        batch_id="batch-01-test",
        status="frozen",
        targets=TargetsConfig(
            decisions_total=20,
            scenarios_total=10,
            decisions_per_repository=20,
            scenarios_per_repository=10,
        ),
        repositories=(
            RepositoryConfig(
                id=repo_id,
                github=github,
                commit_sha=commit_sha,
                primary_test="test",
                validation_status="reviewed",
            ),
        ),
        sampling=SamplingConfig(
            clear_explicit=5,
            scoped=5,
            lifecycle_or_supersession=3,
            ambiguous_or_conflicting=3,
            enforcement_potential=2,
            unusual_or_difficult=2,
        ),
        headline_metric="governing_decision_set_f1",
    )


def _make_classifier(valid: bool = True, backend_id: str = "static-test", version: str = "0.1.0", model: str = "test-model") -> StaticClassifier:
    if valid:
        outputs = {
            ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": "prescriptive"},
            ClassifierTaskType.DOMAINS: {"domains": ["persistence"]},
            ClassifierTaskType.PURPOSES: {"purposes": ["standardize", "prohibit"]},
            ClassifierTaskType.AUTHORITY: {"authority": "explicitly_accepted", "evidence": "ADR-001 accepted"},
            ClassifierTaskType.SCOPE: {"scopes": [{"scope_type": "repository", "scope_expression": "storage"}]},
            ClassifierTaskType.LIFECYCLE: {"lifecycle": "active"},
            ClassifierTaskType.RELATIONSHIPS: {"relationships": []},
            ClassifierTaskType.ENFORCEMENT_POTENTIAL: {"enforcement_potential": "deterministic_rule", "candidate_rule": "no postgres"},
        }
    else:
        # Invalid classification to test incomplete candidate handling
        outputs = {
            ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": "invalid_classification_value"},
            ClassifierTaskType.DOMAINS: {"domains": ["invalid_domain"]},
        }
    return StaticClassifier(
        backend_id=backend_id,
        classifier_version=version,
        model_identifier=model,
        outputs=outputs,
        default_confidence=0.95,
    )


# ── Test Suite ─────────────────────────────────────────────────────────────────


class TestOrchestratorPipeline:
    def test_full_offline_pipeline_success(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)

        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        extractor = HeuristicExtractor(confidence=0.85)
        classifier = _make_classifier(valid=True)

        scenario = ApplicabilityScenario(
            scenario_id="scn-001",
            repository="mbeacom/adrkit",
            description="Implement SQLite storage adapter",
            change_context=ChangeContext(
                path="storage/sqlite.py",
                component="storage",
                change_type="add",
                dependencies=("sqlite3",),
                api=None,
                technology="Python",
                other_context=None,
            ),
            expected_governing_decision_ids=("cand-dummy",),
            mneme_governing_decision_ids=(),
            human_notes=None,
            validation_state="unreviewed",
        )

        db_path = tmp_path / "research.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()

        result = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=extractor,
            classifier=classifier,
            scenarios=[scenario],
            research_store=store,
            clone_source=source_repo,
        )

        assert isinstance(result, OpenArchitectureRunResult)
        assert result.is_completed
        assert result.run_metadata.status == "completed"
        assert len(result.discovered_documents) >= 2
        assert len(result.extracted_candidates) >= 1
        assert len(result.composed_candidates) >= 1
        assert len(result.incomplete_candidates) == 0
        assert len(result.classifier_results) >= 8
        assert len(result.gds_results) == 1
        assert "macro_f1" in result.suite_metrics

        # Verify ResearchStore persisted records
        run_record = store.get_analysis_run(result.run_metadata.run_id)
        assert run_record is not None
        assert run_record.status == "completed"

        candidates_in_db = store.list_decision_candidates(result.run_metadata.run_id)
        assert len(candidates_in_db) == len(result.extracted_candidates)

        classifications = store.list_candidate_classifications(candidates_in_db[0].candidate_id)
        assert len(classifications) == 1
        assert classifications[0].classification == "prescriptive"

        scenario_res = store.list_scenario_results("scn-001")
        assert len(scenario_res) == 1
        assert scenario_res[0].run_id == result.run_metadata.run_id

    # 1. Same pinned source analyzed in two different runs in same SQLite store without PK collision
    # 2. Stable candidate ID remains identical across those runs
    # 3. Run-specific classifier executions remain separate
    def test_multi_run_candidate_coexistence_and_separation(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        store = ResearchStore(tmp_path / "coexistence.sqlite")
        store.initialize_schema()

        extractor = HeuristicExtractor()
        classifier_a = _make_classifier(valid=True, backend_id="backend-a", version="1.0", model="model-a")
        classifier_b = _make_classifier(valid=True, backend_id="backend-b", version="2.0", model="model-b")

        # Run A
        res_a = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=extractor,
            classifier=classifier_a,
            research_store=store,
            clone_source=source_repo,
        )

        # Run B with different classifier on the same pinned repository and store
        res_b = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=extractor,
            classifier=classifier_b,
            research_store=store,
            clone_source=source_repo,
        )

        assert res_a.run_metadata.run_id != res_b.run_metadata.run_id

        # 2. Stable candidate ID remains identical across runs
        cand_ids_a = [c.candidate_id for c in res_a.extracted_candidates]
        cand_ids_b = [c.candidate_id for c in res_b.extracted_candidates]
        assert cand_ids_a == cand_ids_b

        # 1. Both candidate observations coexist in the same store
        cands_run_a = store.list_decision_candidates(res_a.run_metadata.run_id)
        cands_run_b = store.list_decision_candidates(res_b.run_metadata.run_id)
        assert len(cands_run_a) == len(cands_run_b) == len(cand_ids_a)

        # 3. Classifier executions remain separately attributable to each run
        first_cand_id = cand_ids_a[0]
        execs = store.list_classifier_executions(first_cand_id)
        # Exactly 8 executions for run A + 8 executions for run B = 16
        assert len(execs) == 16
        backends = {e.classifier_backend for e in execs}
        assert backends == {"backend-a", "backend-b"}

    # 4. Identical execution configuration cannot silently overwrite a completed run
    def test_identical_configuration_cannot_overwrite_completed_run(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        store = ResearchStore(tmp_path / "store.sqlite")
        store.initialize_schema()

        run1 = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            research_store=store,
            clone_source=source_repo,
        )
        assert run1.is_completed

        with pytest.raises(ValueError, match="Completed analysis run already exists"):
            run_open_architecture_analysis(
                repository_config=repo_config,
                manifest=manifest,
                extractor=HeuristicExtractor(),
                classifier=_make_classifier(),
                research_store=store,
                clone_source=source_repo,
            )

    # 5. Different classifier backend/model/version produces a distinct execution configuration identity
    def test_different_classifier_produces_distinct_configuration_hash(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = "a" * 40
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]
        extractor = HeuristicExtractor()

        c1 = _make_classifier(backend_id="backend-1", version="0.1", model="model-1")
        c2 = _make_classifier(backend_id="backend-2", version="0.1", model="model-1")
        c3 = _make_classifier(backend_id="backend-1", version="0.2", model="model-1")
        c4 = _make_classifier(backend_id="backend-1", version="0.1", model="model-2")

        p1 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=extractor, classifier=c1)
        p2 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=extractor, classifier=c2)
        p3 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=extractor, classifier=c3)
        p4 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=extractor, classifier=c4)

        hashes = {p1.execution_config_hash, p2.execution_config_hash, p3.execution_config_hash, p4.execution_config_hash}
        assert len(hashes) == 4, "Each classifier variant must have a unique execution_config_hash"

    # 6. Different extractor configuration produces a distinct execution configuration identity
    def test_different_extractor_produces_distinct_configuration_hash(self, tmp_path: Path):
        commit_sha = "a" * 40
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]
        classifier = _make_classifier()

        e1 = HeuristicExtractor(extractor_id="heuristic", extractor_version="0.1")
        e2 = HeuristicExtractor(extractor_id="heuristic", extractor_version="0.2")
        e3 = HeuristicExtractor(extractor_id="ast-parser", extractor_version="0.1")

        p1 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=e1, classifier=classifier)
        p2 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=e2, classifier=classifier)
        p3 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=e3, classifier=classifier)

        hashes = {p1.execution_config_hash, p2.execution_config_hash, p3.execution_config_hash}
        assert len(hashes) == 3

    # 7. Different scenario corpus/content produces a distinct execution configuration identity
    def test_different_scenarios_produce_distinct_configuration_hash(self, tmp_path: Path):
        commit_sha = "a" * 40
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]
        extractor = HeuristicExtractor()
        classifier = _make_classifier()

        sc1 = [ApplicabilityScenario(
            scenario_id="s1", repository="mbeacom/adrkit", description="Desc 1",
            change_context=ChangeContext(None, None, None, (), None, None, None),
            expected_governing_decision_ids=("c1",), mneme_governing_decision_ids=(),
            human_notes=None, validation_state="unreviewed",
        )]
        sc2 = [ApplicabilityScenario(
            scenario_id="s1", repository="mbeacom/adrkit", description="Desc 2 (modified)",
            change_context=ChangeContext(None, None, None, (), None, None, None),
            expected_governing_decision_ids=("c1",), mneme_governing_decision_ids=(),
            human_notes=None, validation_state="unreviewed",
        )]

        p1 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=extractor, classifier=classifier, scenarios=sc1)
        p2 = preflight_open_architecture_analysis(repository_config=repo_config, manifest=manifest, extractor=extractor, classifier=classifier, scenarios=sc2)

        assert p1.execution_config_hash != p2.execution_config_hash

    # 8. An expected governing candidate absent from machine extraction remains persisted as reference truth and counts as a miss
    def test_expected_candidate_absent_from_extraction_persisted_as_miss(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        store = ResearchStore(tmp_path / "store.sqlite")
        store.initialize_schema()

        # Human benchmark reference label specifies an expected decision 'cand-absent-999' that machine will NOT find
        scenario = ApplicabilityScenario(
            scenario_id="scn-reference-001",
            repository="mbeacom/adrkit",
            description="Database migration scenario",
            change_context=ChangeContext("db.py", "db", "mod", (), None, "Python", None),
            expected_governing_decision_ids=("cand-absent-999",),
            mneme_governing_decision_ids=(),
            human_notes=None,
            validation_state="unreviewed",
        )

        res = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            scenarios=[scenario],
            research_store=store,
            clone_source=source_repo,
        )

        # 1. Expected decision IS persisted in ResearchStore scenario_expected_decisions table
        expected_in_db = store.list_scenario_expected_decisions("scn-reference-001")
        assert "cand-absent-999" in expected_in_db

        # 2. It was missed by machine retrieval
        gds_res = res.gds_results[0]
        assert "cand-absent-999" not in gds_res.predicted_governing_decision_ids
        assert gds_res.recall == 0.0
        assert gds_res.f1 == 0.0

    # 9. Exactly eight classifier task executions occur per candidate and PURPOSES occurs once
    def test_exactly_eight_tasks_per_candidate_purposes_once(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        res = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            clone_source=source_repo,
        )

        for cand in res.extracted_candidates:
            cand_tasks = [r.task_type for r in res.classifier_results if r.candidate_id == cand.candidate_id]
            assert len(cand_tasks) == 8
            assert cand_tasks.count(ClassifierTaskType.PURPOSES) == 1
            expected_tasks = {
                ClassifierTaskType.DECISION_CLASSIFICATION,
                ClassifierTaskType.DOMAINS,
                ClassifierTaskType.PURPOSES,
                ClassifierTaskType.AUTHORITY,
                ClassifierTaskType.SCOPE,
                ClassifierTaskType.LIFECYCLE,
                ClassifierTaskType.RELATIONSHIPS,
                ClassifierTaskType.ENFORCEMENT_POTENTIAL,
            }
            assert set(cand_tasks) == expected_tasks

    # 10. Dry-run/preflight does not return or persist a completed semantic analysis
    def test_dry_run_preflight_does_not_claim_completed(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = "a" * 40
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        store = ResearchStore(tmp_path / "store.sqlite")
        store.initialize_schema()

        preflight = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            research_store=store,
            dry_run=True,
        )

        assert isinstance(preflight, PreflightResult)
        assert preflight.status == "preflight_ok"
        assert preflight.status != "completed"
        # No runs created or completed in ResearchStore
        assert store.list_analysis_runs() == []

    # 16. Incomplete candidate outcomes remain observable and reproducible
    def test_incomplete_candidate_outcomes_remain_observable(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        # Classifier outputs invalid domain
        classifier = StaticClassifier(
            outputs={
                ClassifierTaskType.DECISION_CLASSIFICATION: {"classification": "prescriptive"},
                ClassifierTaskType.DOMAINS: {"domains": ["non_existent_domain_xyz"]},
            }
        )

        res = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=classifier,
            clone_source=source_repo,
        )

        assert len(res.incomplete_candidates) >= 1
        inc = res.incomplete_candidates[0]
        assert "domains" in inc.missing_or_failed_dimensions
        assert "non_existent_domain_xyz" in inc.errors["domains"]

    # 17. No canonical authority state is written
    def test_no_canonical_authority_state_written(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        workspace = tmp_path / "ws"
        workspace.mkdir()

        run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            workspace_dir=workspace,
            clone_source=source_repo,
        )

        assert not (workspace / ".mneme").exists()
        assert not (source_repo / ".mneme").exists()

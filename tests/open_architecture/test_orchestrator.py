"""
tests.open_architecture.test_orchestrator — Tests for O1A research run orchestrator.

Covers:
- Full offline local-repository pipeline using StaticClassifier + HeuristicExtractor
- Explicit extractor/classifier injection (fail-closed on None)
- Incomplete candidate handling (observable, not dropped or fabricated)
- ResearchStore persistence (analysis_runs, source_documents, decision_candidates,
  semantic dimensions, classifier_executions, scenarios, results)
- Historical run append-preservation (no silent overwrite of completed run)
- Failed run status recording
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


def _make_classifier(valid: bool = True) -> StaticClassifier:
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
        backend_id="static-test",
        classifier_version="0.1.0",
        model_identifier="test-model",
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
        assert len(result.discovered_documents) >= 2  # README.md + ADR-001.md
        assert len(result.extracted_candidates) >= 1
        assert len(result.composed_candidates) >= 1
        assert len(result.incomplete_candidates) == 0
        assert len(result.classifier_results) >= 8  # 8 dimensions per candidate
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

    def test_explicit_extractor_and_classifier_required(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        with pytest.raises(ValueError, match="extractor must be explicitly provided"):
            run_open_architecture_analysis(
                repository_config=repo_config,
                manifest=manifest,
                extractor=None,  # type: ignore
                classifier=_make_classifier(),
            )

        with pytest.raises(ValueError, match="classifier must be explicitly provided"):
            run_open_architecture_analysis(
                repository_config=repo_config,
                manifest=manifest,
                extractor=HeuristicExtractor(),
                classifier=None,  # type: ignore
            )

    def test_incomplete_candidate_handling(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        extractor = HeuristicExtractor()
        # Invalid classifier produces unclassifiable candidates
        classifier = _make_classifier(valid=False)

        result = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=extractor,
            classifier=classifier,
            clone_source=source_repo,
        )

        assert result.is_completed
        assert len(result.extracted_candidates) >= 1
        # None should be composed with guessed labels
        assert len(result.composed_candidates) == 0
        # All extracted candidates should be observable as incomplete
        assert len(result.incomplete_candidates) == len(result.extracted_candidates)
        first_inc = result.incomplete_candidates[0]
        assert "classification" in first_inc.missing_or_failed_dimensions
        assert "domains" in first_inc.missing_or_failed_dimensions

    def test_historical_completed_run_not_overwritten(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        store = ResearchStore(tmp_path / "store.sqlite")
        store.initialize_schema()

        # Run 1
        res1 = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            research_store=store,
            clone_source=source_repo,
        )
        assert res1.is_completed

        # Attempting identical run on same store must fail rather than overwrite
        with pytest.raises(ValueError, match="Completed analysis run already exists"):
            run_open_architecture_analysis(
                repository_config=repo_config,
                manifest=manifest,
                extractor=HeuristicExtractor(),
                classifier=_make_classifier(),
                research_store=store,
                clone_source=source_repo,
            )

    def test_failed_run_marked_failed(self, tmp_path: Path, monkeypatch):
        source_repo = tmp_path / "src_repo"
        commit_sha = _create_test_repo(source_repo)
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        store = ResearchStore(tmp_path / "store.sqlite")
        store.initialize_schema()

        from mneme.open_architecture import orchestrator

        def _exploding_discover(*args, **kwargs):
            raise RuntimeError("Simulated discovery explosion")

        monkeypatch.setattr(orchestrator, "discover_sources", _exploding_discover)

        with pytest.raises(RuntimeError, match="Simulated discovery explosion"):
            run_open_architecture_analysis(
                repository_config=repo_config,
                manifest=manifest,
                extractor=HeuristicExtractor(),
                classifier=_make_classifier(),
                research_store=store,
                clone_source=source_repo,
            )

        # Analysis run must exist and be marked 'failed'
        runs = store.list_analysis_runs("adrkit")
        assert len(runs) == 1
        assert runs[0].status == "failed"

    def test_dry_run_mode(self, tmp_path: Path):
        source_repo = tmp_path / "src_repo"
        commit_sha = "a" * 40
        manifest = _make_manifest("adrkit", "mbeacom/adrkit", commit_sha)
        repo_config = manifest.repositories[0]

        result = run_open_architecture_analysis(
            repository_config=repo_config,
            manifest=manifest,
            extractor=HeuristicExtractor(),
            classifier=_make_classifier(),
            dry_run=True,
        )

        assert result.is_completed
        assert len(result.discovered_documents) == 0
        assert len(result.extracted_candidates) == 0
        assert not (tmp_path / ".mneme").exists()
